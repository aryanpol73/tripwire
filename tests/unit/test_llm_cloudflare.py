"""The Cloudflare Workers AI decision source, offline: a fake client stands in for the API."""

from types import SimpleNamespace

import pytest

from tripwire.llm import tools
from tripwire.llm.client import (
    CloudflareSource,
    LlmConfigError,
    QuotaExhausted,
    Request,
    model_sources,
)
from tripwire.llm.prompt import SYSTEM

openai = pytest.importorskip("openai")
REQ = Request(SYSTEM, "prompt", tools.TOOLS)


def response(name="click", arguments='{"element_id": "e2", "purpose": "browse"}'):
    call = SimpleNamespace(function=SimpleNamespace(name=name, arguments=arguments))
    msg = SimpleNamespace(tool_calls=[call], content=None)
    return SimpleNamespace(
        model="@cf/openai/gpt-oss-120b",
        choices=[SimpleNamespace(message=msg, finish_reason="tool_calls")],
        usage=SimpleNamespace(prompt_tokens=2000, completion_tokens=100),
    )


@pytest.fixture
def source(monkeypatch):
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "acct")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "test-token-not-real")
    monkeypatch.setenv("CLOUDFLARE_MODEL", "@cf/openai/gpt-oss-120b")
    src = CloudflareSource()
    sent = {}

    def create(**kw):
        sent.update(kw)
        if isinstance(src._next, Exception):
            raise src._next
        return src._next

    src._client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    src._sent = sent
    return src


def status_error(cls, status, message):
    """A real SDK error, built on the HTTP types the installed openai SDK uses."""
    try:
        import httpx2 as http
    except ImportError:
        import httpx as http
    request = http.Request("POST", "https://api.cloudflare.com/client/v4/accounts/a/ai/v1")
    return cls(message, response=http.Response(status, request=request), body=None)


def test_tool_call_is_parsed_priced_and_max_tokens_set(source):
    source._next = response()
    d = source.decide(REQ)
    assert (d.tool, d.input["element_id"]) == ("click", "e2")
    assert d.cost_micros == round(2000 * 0.35 + 100 * 0.75)
    assert source._sent["max_tokens"] == 4096  # Cloudflare's own default is only 256
    assert source._client is not None and source.host == "cloudflare"


def test_rate_limit_and_daily_neuron_quota_become_quota_exhausted(source):
    source._next = status_error(openai.RateLimitError, 429, "too many requests")
    with pytest.raises(QuotaExhausted):
        source.decide(REQ)
    source._next = status_error(openai.APIStatusError, 400, "daily free neuron allocation used")
    with pytest.raises(QuotaExhausted):
        source.decide(REQ)


def test_missing_settings_are_refused(monkeypatch):
    monkeypatch.delenv("CLOUDFLARE_MODEL", raising=False)
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "a")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "t")
    with pytest.raises(LlmConfigError, match="CLOUDFLARE_MODEL"):
        CloudflareSource()


def test_hosts_list_is_read_from_tripwire_hosts():
    with pytest.raises(LlmConfigError, match="unknown hosts"):
        model_sources(env={"TRIPWIRE_HOSTS": "groq,elsewhere"})
