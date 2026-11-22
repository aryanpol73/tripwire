"""The safety gate: rules enforced in code, outside any LLM, that nothing on a page can change.

The walker asks the gate before every navigation, request and action. A "no" raises
SafetyBlocked and is logged as an event that ends up in the trace as a safety_block note.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

from tripwire.schemas.trace import Budgets, Mode

LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}
REAL_SITE_MIN_INTERVAL_S = 2.0
USER_AGENT_TOKEN = "TripwireAudit"

# Controls that complete something irreversible: never clicked on a real site (rules 1, 10).
_IRREVERSIBLE = re.compile(
    r"\b(pay|payment|purchase|buy\s+now|place\s+(my\s+)?order|complete\s+(my\s+)?order"
    r"|submit\s+order|checkout\s+and\s+pay|proceed\s+to\s+pay|donate"
    r"|subscribe|sign\s+me\s+up|start\s+(my\s+)?trial|begin\s+trial|activate|confirm"
    r"|create\s+(my\s+)?account|register|sign\s+up|join\s+now"
    r"|delete|remove\s+(my\s+)?account|close\s+(my\s+)?account|deactivate"
    r"|yes,?\s+i('|\s+a)?m\s+sure|yes,?\s+cancel|send|post\s+comment|publish)\b",
    re.IGNORECASE,
)
# Entering a leave flow changes nothing yet, but needs the owner's approval per run (rule 10).
_LEAVE_FLOW = re.compile(
    r"\b(cancel|unsubscribe|opt\s+out|end\s+(my\s+)?subscription|leave\s+newsletter)\b",
    re.IGNORECASE,
)
_ACCEPT = re.compile(r"\b(accept|agree|allow|ok|got\s+it|i\s+consent)\b", re.IGNORECASE)
_SECRET_FIELD = re.compile(
    r"password|cc-|card|cvc|cvv|one-time-code|otp|upi|iban|account-number", re.IGNORECASE
)
_PAYMENT_URL = re.compile(
    r"pay(ment)?s?\b|/checkout/(confirm|complete|place)|/orders?/(place|create|confirm)"
    r"|razorpay|stripe|paypal|paytm|billdesk|ccavenue|braintree|adyen",
    re.IGNORECASE,
)


class SafetyBlocked(Exception):
    def __init__(self, event: GateEvent):
        super().__init__(f"{event.kind}: {event.reason} ({event.target})")
        self.event = event


class BudgetExceeded(Exception):
    def __init__(self, names: list[str]):
        super().__init__(f"budget exceeded: {', '.join(names)}")
        self.names = names


@dataclass(frozen=True)
class GateEvent:
    kind: str  # navigation_blocked, request_blocked, action_blocked
    target: str
    reason: str
    at: datetime


@dataclass(frozen=True)
class GateConfig:
    mode: Mode
    allowed_hosts: tuple[str, ...]
    limits: Budgets
    min_action_interval_s: float = REAL_SITE_MIN_INTERVAL_S
    approved_account_flows: bool = False  # rule 10: the owner approved this run
    # Red-team runs: apply the real-site action rules on the local sandbox too.
    enforce_real_action_rules: bool = False

    def __post_init__(self) -> None:
        if not self.allowed_hosts:
            raise ValueError("the allowlist cannot be empty")
        if self.mode == Mode.SANDBOX and not set(self.allowed_hosts) <= LOCAL_HOSTS:
            raise ValueError("sandbox runs may only use local hosts (127.0.0.1, localhost)")
        if self.mode == Mode.REAL and self.min_action_interval_s < REAL_SITE_MIN_INTERVAL_S:
            raise ValueError("real sites need at least 2 seconds between actions (rule 5)")


class RobotsPolicy:
    def __init__(self, text: str) -> None:
        self._parser = RobotFileParser()
        self._parser.parse(text.splitlines())

    def allows(self, url: str) -> bool:
        return self._parser.can_fetch(USER_AGENT_TOKEN, url)


def host_allowed(host: str, allowed: tuple[str, ...]) -> bool:
    host = host.lower().rstrip(".")
    return any(host == a or host.endswith("." + a) for a in allowed)


@dataclass
class SafetyGate:
    config: GateConfig
    events: list[GateEvent] = field(default_factory=list)
    robots: dict[str, RobotsPolicy] = field(default_factory=dict)  # host -> policy

    def _block(self, kind: str, target: str, reason: str) -> SafetyBlocked:
        event = GateEvent(kind, target, reason, datetime.now(UTC))
        self.events.append(event)
        return SafetyBlocked(event)

    @property
    def real(self) -> bool:
        return self.config.mode == Mode.REAL

    # --- navigation and requests ----------------------------------------------------

    def check_navigation(self, url: str) -> None:
        parts = urlsplit(url)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            raise self._block("navigation_blocked", url, "only http(s) pages may be opened")
        if not host_allowed(parts.hostname, self.config.allowed_hosts):
            raise self._block("navigation_blocked", url, "host is not on this run's allowlist")
        policy = self.robots.get(parts.hostname)
        if self.real and policy and not policy.allows(url):
            raise self._block("navigation_blocked", url, "disallowed by robots.txt")

    def allows_request(self, url: str, method: str, *, is_navigation: bool) -> bool:
        """Route-handler decision for every request the page makes."""
        if is_navigation:
            try:
                self.check_navigation(url)
            except SafetyBlocked:
                return False
            return True
        parts = urlsplit(url)
        if parts.scheme in ("data", "blob", "about"):
            return True
        on_list = bool(parts.hostname) and host_allowed(parts.hostname, self.config.allowed_hosts)
        if not self.real and not on_list:
            # The sandbox is offline by design: nothing may leave the machine.
            self._block("request_blocked", url, "sandbox runs make no off-host requests")
            return False
        if self.real and method.upper() != "GET" and _PAYMENT_URL.search(url):
            self._block("request_blocked", url, "non-GET request to a payment-like endpoint")
            return False
        return True

    # --- actions --------------------------------------------------------------------

    def check_click(self, *, text: str, role: str, in_consent_overlay: bool = False) -> None:
        if not (self.real or self.config.enforce_real_action_rules):
            return  # sandbox: everything is fake, irreversible actions are allowed (rule 1)
        label = " ".join(text.split())
        if in_consent_overlay and _ACCEPT.search(label):
            raise self._block("action_blocked", label, "never accept consent on a real site")
        if _IRREVERSIBLE.search(label):
            raise self._block("action_blocked", label, "irreversible action on a real site")
        if _LEAVE_FLOW.search(label) and not self.config.approved_account_flows:
            raise self._block("action_blocked", label, "account flows need approval per run")

    def check_type(self, *, field_hint: str) -> None:
        # Secrets are never typed by the agent, in any mode: those steps go to the human.
        if _SECRET_FIELD.search(field_hint):
            raise self._block("action_blocked", field_hint, "secret fields are typed by a human")


class BudgetTracker:
    def __init__(self, limits: Budgets, clock: Callable[[], float] = time.monotonic) -> None:
        self.limits = limits
        self._clock = clock
        self._start = clock()
        self.steps = 0
        self.page_loads = 0
        self.spend_micros = 0

    def add_step(self) -> None:
        self.steps += 1

    def add_page_load(self) -> None:
        self.page_loads += 1

    def add_spend(self, micros: int) -> None:
        self.spend_micros += micros

    def used(self) -> Budgets:
        return Budgets(
            steps=self.steps,
            wall_seconds=round(self._clock() - self._start, 3),
            page_loads=self.page_loads,
            llm_spend_usd_micros=self.spend_micros,
        )

    def check(self) -> None:
        """Called before each action: stop when another action would go past a limit."""
        used, limits = self.used(), self.limits
        over = [
            name
            for name in ("steps", "wall_seconds", "page_loads")
            if getattr(used, name) >= getattr(limits, name)
        ]
        if used.llm_spend_usd_micros > limits.llm_spend_usd_micros:
            over.append("llm_spend_usd_micros")
        if over:
            raise BudgetExceeded(over)


class Pacer:
    """Waits so that actions are at least min_interval seconds apart (rule 5)."""

    def __init__(
        self,
        min_interval: float,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.min_interval = min_interval
        self._clock = clock
        self._sleep = sleep
        self._last: float | None = None

    def wait(self) -> None:
        now = self._clock()
        if self._last is not None:
            remaining = self.min_interval - (now - self._last)
            if remaining > 0:
                self._sleep(remaining)
        self._last = self._clock()
