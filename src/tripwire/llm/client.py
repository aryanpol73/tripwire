"""Where decisions come from: the model, a recording of it, or a test policy.

Every source returns the same `Decision`. `RecordingSource` writes each decision to
`llm_decisions.jsonl` in the run folder; `ReplaySource` plays such a file back without any
network call, so an LLM run can be repeated exactly (and CI can replay it with no API key).
Cost is computed from token usage and a price table, in integer micro-dollars, and the
walker adds it to the run's spend budget before the next call.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import tomllib
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Protocol

PRICES_FILE = Path(__file__).with_name("prices.toml")
MAX_TOKENS = 4096  # one tool call plus thinking; also bounds the worst-case cost of a call
CHARS_PER_TOKEN = 3  # deliberately low, so the input estimate errs high
# Models that accept the server-side refusal fallback.
FALLBACK_MODELS = {
    "claude-fable-5-2",
    "claude-fable-5-1",
    "claude-opus-5-5",
    "claude-opus-5",
    "claude-sonnet-5-5",
}


class LlmConfigError(Exception):
    pass


class ReplayExhausted(Exception):
    pass


@dataclass(frozen=True)
class Request:
    system: str
    prompt: str
    tools: list[dict[str, Any]]

    @property
    def sha(self) -> str:
        return hashlib.sha256((self.system + "\n\n" + self.prompt).encode("utf-8")).hexdigest()


@dataclass
class Decision:
    tool: str  # a tool name, or "none" when the model answered without a tool call
    input: dict[str, Any] = field(default_factory=dict)
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    cost_micros: int = 0
    stop_reason: str = ""
    text: str = ""


class DecisionSource(Protocol):
    def decide(self, request: Request) -> Decision: ...


# --- prices -------------------------------------------------------------------------


@dataclass(frozen=True)
class Price:
    input_per_mtok: float  # US$ per million tokens == micro-dollars per token
    output_per_mtok: float

    def cost_micros(self, d: Decision) -> int:
        tokens_in = d.input_tokens + 1.25 * d.cache_write_tokens + 0.1 * d.cache_read_tokens
        return math.ceil(tokens_in * self.input_per_mtok + d.output_tokens * self.output_per_mtok)


def price_for(model: str, env: dict[str, str] | None = None) -> Price:
    env = dict(os.environ) if env is None else env
    if env.get("TRIPWIRE_PRICE_IN") and env.get("TRIPWIRE_PRICE_OUT"):
        return Price(float(env["TRIPWIRE_PRICE_IN"]), float(env["TRIPWIRE_PRICE_OUT"]))
    table = tomllib.loads(PRICES_FILE.read_text(encoding="utf-8"))["models"]
    if model not in table:
        raise LlmConfigError(
            f"no price known for {model!r}, so the spend cap cannot be enforced. Add it to "
            f"{PRICES_FILE.name} or set TRIPWIRE_PRICE_IN and TRIPWIRE_PRICE_OUT (US$/1M tokens)."
        )
    row = table[model]
    return Price(float(row["input"]), float(row["output"]))


# --- the real model -----------------------------------------------------------------


class AnthropicSource:
    """Calls the Messages API once per step. Each call is self-contained (system prompt,
    mission, a short action history and the current observation), so the context stays
    small and every call can be recorded and replayed on its own."""

    def __init__(self, model: str | None = None, effort: str | None = None) -> None:
        model = model or os.environ.get("TRIPWIRE_MODEL", "")
        if not model:
            raise LlmConfigError("set TRIPWIRE_MODEL in .env (the model id to use)")
        try:
            import anthropic
        except ImportError as err:
            raise LlmConfigError("install the LLM extra: uv sync --extra llm") from err
        self.model = model
        self.effort = effort or os.environ.get("TRIPWIRE_EFFORT") or None
        self.price = price_for(model)
        self._anthropic = anthropic
        self._client = anthropic.Anthropic()

    def worst_case_micros(self, request: Request) -> int:
        """An upper bound on what the next call can cost: the whole prompt written to the
        cache plus a full max_tokens of output. The walker stops before a call that could
        take spend past the cap."""
        tokens_in = (len(request.system) + len(request.prompt) + 4000) / CHARS_PER_TOKEN
        return math.ceil(
            tokens_in * 1.25 * self.price.input_per_mtok + MAX_TOKENS * self.price.output_per_mtok
        )

    def decide(self, request: Request) -> Decision:
        kwargs: dict[str, Any] = dict(
            model=self.model,
            max_tokens=MAX_TOKENS,
            # The system prompt and tools never change within a run: cache them.
            system=[
                {"type": "text", "text": request.system, "cache_control": {"type": "ephemeral"}}
            ],
            tools=request.tools,
            tool_choice={"type": "auto"},
            messages=[{"role": "user", "content": request.prompt}],
        )
        if self.effort:
            kwargs["output_config"] = {"effort": self.effort}
        if self.model in FALLBACK_MODELS:
            # On a safety decline the API re-runs the call on a fallback model it picks.
            response = self._client.beta.messages.create(
                betas=["server-side-fallback-2026-07-01"], fallbacks="default", **kwargs
            )
        else:
            response = self._client.messages.create(**kwargs)
        usage = response.usage
        decision = Decision(
            tool="none",
            model=response.model,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cache_read_tokens=usage.cache_read_input_tokens or 0,
            cache_write_tokens=usage.cache_creation_input_tokens or 0,
            stop_reason=response.stop_reason or "",
        )
        for block in response.content:
            if block.type == "tool_use" and decision.tool == "none":
                decision.tool, decision.input = block.name, dict(block.input)
            elif block.type == "text":
                decision.text += block.text
        try:  # a fallback model may have answered: bill at its price when known
            price = price_for(response.model) if response.model != self.model else self.price
        except LlmConfigError:
            price = self.price
        decision.cost_micros = price.cost_micros(decision)
        return decision


# --- record and replay ----------------------------------------------------------------


def worst_case(source: DecisionSource, request: Request) -> int:
    estimate = getattr(source, "worst_case_micros", None)
    return estimate(request) if estimate else 0


class RecordingSource:
    def __init__(self, inner: DecisionSource, path: Path) -> None:
        self.inner, self.path, self.seq = inner, path, 0
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")

    def start(self, nonce: str) -> None:
        """The first line holds the run's nonce, so a replay rebuilds identical prompts."""
        self.path.write_text(json.dumps({"nonce": nonce}) + chr(10), encoding="utf-8")

    def worst_case_micros(self, request: Request) -> int:
        return worst_case(self.inner, request)

    def decide(self, request: Request) -> Decision:
        decision = self.inner.decide(request)
        row = {"seq": self.seq, "request_sha": request.sha, **asdict(decision)}
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        self.seq += 1
        return decision


class ReplaySource:
    """Plays back a recording in order. A changed prompt is counted as a divergence (the
    walker notes it); the recorded decision is still used, and the validator still checks
    it against the page as it is now."""

    def __init__(self, path: Path) -> None:
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
        self.nonce = rows.pop(0)["nonce"] if rows and "nonce" in rows[0] else None
        self.rows, self.i, self.divergences = rows, 0, 0

    def worst_case_micros(self, request: Request) -> int:
        return int(self.rows[self.i]["cost_micros"]) if self.i < len(self.rows) else 0

    def decide(self, request: Request) -> Decision:
        if self.i >= len(self.rows):
            raise ReplayExhausted(f"the recording has only {len(self.rows)} decisions")
        row = dict(self.rows[self.i])
        self.i += 1
        if row.pop("request_sha") != request.sha:
            self.divergences += 1
        row.pop("seq", None)
        return Decision(**row)


class PolicySource:
    """A deterministic stand-in for tests: a function from prompt to (tool, input)."""

    def __init__(self, policy: Callable[[Request], tuple[str, dict[str, Any]]], cost: int = 0):
        self.policy, self.cost = policy, cost

    def decide(self, request: Request) -> Decision:
        tool, args = self.policy(request)
        return Decision(tool=tool, input=args, model="policy", cost_micros=self.cost)
