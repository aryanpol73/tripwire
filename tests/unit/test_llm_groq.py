"""The Groq decision source, offline: a fake client stands in for the API."""

from types import SimpleNamespace

import pytest

from tripwire.llm import tools
from tripwire.llm.client import GroqSource, LlmConfigError, Request, model_source, price_for
from tripwire.llm.prompt import SYSTEM

groq = pytest.importorskip("groq")


def fake_response(name=None, arguments="{}", prompt=3000, completion=200):
    calls = (
        [SimpleNamespace(function=SimpleNamespace(name=name, arguments=arguments))]
        if name
        else None
    )
    message = SimpleNamespace(tool_calls=calls, content=None if name else "thinking aloud")
    return SimpleNamespace(
        model="openai/gpt-oss-120b",
        choices=[SimpleNamespace(message=message, finish_reason="tool_calls" if name else "stop")],
        usage=SimpleNamespace(prompt_tokens=prompt, completion_tokens=completion),
    )


@pytest.fixture
def source(monkeypatch):
    monkeypatch.setenv("TRIPWIRE_MODEL", "openai/gpt-oss-120b")
    monkeypatch.setenv("GROQ_API_KEY", "test-key-not-real")
    src = GroqSource()
    sent = {}

    def create(**kwargs):
        sent.update(kwargs)
        return src._next

    src._client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    src._sent = sent
    return src


REQ = Request(SYSTEM, "prompt", tools.TOOLS)


def test_tool_call_is_parsed_and_priced(source):
    source._next = fake_response("click", '{"element_id": "e2", "purpose": "browse"}')
    d = source.decide(REQ)
    assert (d.tool, d.input) == ("click", {"element_id": "e2", "purpose": "browse"})
    assert d.cost_micros == round(3000 * 0.15 + 200 * 0.60)  # 570 micro-USD
    sent = source._sent
    assert sent["tool_choice"] == "auto" and sent["messages"][0]["role"] == "system"
    assert {t["function"]["name"] for t in sent["tools"]} == tools.TOOL_NAMES


def test_unparseable_arguments_become_an_empty_proposal_that_checks_refuse(source):
    source._next = fake_response("click", "{not json")
    assert source.decide(REQ).input == {}


def test_no_tool_call_stops_cleanly(source):
    source._next = fake_response(None)
    d = source.decide(REQ)
    assert d.tool == "none" and d.stop_reason == "stop"


def test_malformed_call_rejected_by_groq_is_a_refusal_charged_at_worst_case(source):
    def create(**_kw):
        request = SimpleNamespace(method="POST", url="https://api.groq.com", headers={})
        response = SimpleNamespace(status_code=400, headers={}, request=request)
        raise groq.BadRequestError("tool_use_failed: invalid call", response=response, body=None)

    source._client.chat.completions.create = create
    d = source.decide(REQ)
    assert d.tool == "malformed_tool_call"
    assert d.cost_micros == source.worst_case_micros(REQ) > 0
    with pytest.raises(tools.Refused):
        tools.check(d.tool, d.input, None, frozenset())


def test_worst_case_bounds_a_full_length_reply(source):
    assert source.worst_case_micros(REQ) >= 4096 * 0.60


def test_provider_choice():
    assert price_for("openai/gpt-oss-120b", env={}).input_per_mtok == 0.15
    with pytest.raises(LlmConfigError, match="TRIPWIRE_PROVIDER"):
        model_source(env={"ANTHROPIC_API_KEY": "a", "GROQ_API_KEY": "g"})
    with pytest.raises(LlmConfigError, match="unknown TRIPWIRE_PROVIDER"):
        model_source(env={"TRIPWIRE_PROVIDER": "other"})


def test_unpriced_groq_model_is_refused(monkeypatch):
    monkeypatch.setenv("TRIPWIRE_MODEL", "llama-3.3-70b-versatile")
    monkeypatch.delenv("TRIPWIRE_PRICE_IN", raising=False)
    with pytest.raises(LlmConfigError, match="no price known"):
        GroqSource()
