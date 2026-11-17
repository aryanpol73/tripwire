"""Safety gate, budgets, pacing and robots.txt: the rules that live in code, not in a prompt."""

import pytest

from tripwire.browser.safety_gate import (
    BudgetExceeded,
    BudgetTracker,
    GateConfig,
    Pacer,
    RobotsPolicy,
    SafetyBlocked,
    SafetyGate,
)
from tripwire.schemas.trace import Budgets, Mode

LIMITS = Budgets(steps=3, wall_seconds=10, page_loads=2, llm_spend_usd_micros=1000)


def sandbox_gate(**kw) -> SafetyGate:
    kw.setdefault("allowed_hosts", ("127.0.0.1",))
    return SafetyGate(GateConfig(mode=Mode.SANDBOX, limits=LIMITS, **kw))


def real_gate(**kw) -> SafetyGate:
    kw.setdefault("allowed_hosts", ("shop.example",))
    return SafetyGate(GateConfig(mode=Mode.REAL, limits=LIMITS, **kw))


# --- Configuration ----------------------------------------------------------------


def test_sandbox_mode_only_allows_local_hosts():
    with pytest.raises(ValueError, match="local"):
        GateConfig(mode=Mode.SANDBOX, allowed_hosts=("example.com",), limits=LIMITS)


def test_real_mode_enforces_the_two_second_floor():
    with pytest.raises(ValueError, match="2"):
        GateConfig(mode=Mode.REAL, allowed_hosts=("a.example",), limits=LIMITS,
                   min_action_interval_s=0.5)  # fmt: skip


def test_allowlist_cannot_be_empty():
    with pytest.raises(ValueError):
        GateConfig(mode=Mode.REAL, allowed_hosts=(), limits=LIMITS)


# --- Navigation -------------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "https://evil.example/",
        "https://shop.example.evil.example/",  # look-alike suffix
        "https://evilshop.example/",
        "file:///etc/passwd",
        "javascript:alert(1)",
    ],
)
def test_off_allowlist_navigation_is_blocked_and_logged(url):
    gate = real_gate()
    with pytest.raises(SafetyBlocked):
        gate.check_navigation(url)
    assert gate.events[-1].kind == "navigation_blocked"
    assert gate.events[-1].target == url


@pytest.mark.parametrize("url", ["https://shop.example/", "https://www.shop.example/cart"])
def test_allowlisted_host_and_subdomains_pass(url):
    real_gate().check_navigation(url)


def test_sandbox_blocks_every_off_host_request_not_just_navigation():
    gate = sandbox_gate()
    assert gate.allows_request("http://127.0.0.1:8100/x.css", "GET", is_navigation=False)
    assert not gate.allows_request("https://cdn.example/x.js", "GET", is_navigation=False)


def test_real_mode_lets_third_party_subresources_load_but_not_navigate():
    gate = real_gate()
    assert gate.allows_request("https://cmp.example/banner.js", "GET", is_navigation=False)
    assert not gate.allows_request("https://cmp.example/", "GET", is_navigation=True)


@pytest.mark.parametrize(
    "url", ["https://shop.example/payment/submit", "https://api.razorpay.com/v1/orders"]
)
def test_real_mode_blocks_non_get_requests_to_payment_endpoints(url):
    gate = real_gate(allowed_hosts=("shop.example", "razorpay.com"))
    assert not gate.allows_request(url, "POST", is_navigation=False)
    assert gate.events[-1].kind == "request_blocked"


def test_robots_disallow_blocks_navigation_in_real_mode():
    gate = real_gate()
    gate.robots["shop.example"] = RobotsPolicy("User-agent: *\nDisallow: /private\n")
    gate.check_navigation("https://shop.example/public")
    with pytest.raises(SafetyBlocked, match="robots"):
        gate.check_navigation("https://shop.example/private/page")


# --- Actions ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    ["Pay now", "Place order", "Buy now", "Proceed to pay", "Start my trial", "Create account",
     "Delete account", "Confirm", "Yes, I am sure", "Send message", "Subscribe"],
)  # fmt: skip
def test_real_mode_denies_irreversible_controls(text):
    gate = real_gate()
    with pytest.raises(SafetyBlocked):
        gate.check_click(text=text, role="button")
    assert gate.events[-1].kind == "action_blocked"


def test_real_mode_never_clicks_accept_on_a_consent_banner():
    gate = real_gate()
    with pytest.raises(SafetyBlocked, match="consent"):
        gate.check_click(text="Accept all", role="button", in_consent_overlay=True)
    gate.check_click(text="Reject all", role="button", in_consent_overlay=True)


def test_leave_flows_need_explicit_approval_on_real_sites():
    with pytest.raises(SafetyBlocked, match="approval"):
        real_gate().check_click(text="Cancel subscription", role="link")
    real_gate(approved_account_flows=True).check_click(text="Cancel subscription", role="link")


@pytest.mark.parametrize("text", ["Add to cart", "Reject all", "Next page", "Pricing"])
def test_ordinary_controls_are_allowed_on_real_sites(text):
    real_gate().check_click(text=text, role="button")


def test_sandbox_allows_irreversible_actions_because_everything_is_fake():
    sandbox_gate().check_click(text="Pay now", role="button")
    sandbox_gate().check_click(text="Accept all", role="button", in_consent_overlay=True)


@pytest.mark.parametrize("field", ["password", "cc-number", "one-time-code", "card"])
def test_typing_secrets_is_denied_in_every_mode(field):
    for gate in (sandbox_gate(), real_gate()):
        with pytest.raises(SafetyBlocked, match="secret"):
            gate.check_type(field_hint=field)


# --- Budgets and pacing -----------------------------------------------------------


class FakeClock:
    def __init__(self):
        self.now = 0.0
        self.slept = []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.slept.append(seconds)
        self.now += seconds


def test_budget_tracker_counts_and_aborts():
    clock = FakeClock()
    budget = BudgetTracker(LIMITS, clock=clock)
    budget.add_step()
    budget.add_page_load()
    budget.check()
    budget.add_page_load()
    budget.add_page_load()
    with pytest.raises(BudgetExceeded, match="page_loads"):
        budget.check()
    assert budget.used().page_loads == 3


def test_wall_clock_budget():
    clock = FakeClock()
    budget = BudgetTracker(LIMITS, clock=clock)
    clock.now = 11
    with pytest.raises(BudgetExceeded, match="wall_seconds"):
        budget.check()


def test_spend_budget_in_micro_dollars():
    budget = BudgetTracker(LIMITS, clock=FakeClock())
    budget.add_spend(1001)
    with pytest.raises(BudgetExceeded, match="llm_spend"):
        budget.check()


def test_pacer_waits_out_the_minimum_interval():
    clock = FakeClock()
    pacer = Pacer(2.0, clock=clock, sleep=clock.sleep)
    pacer.wait()  # first action: no wait
    clock.now += 0.5
    pacer.wait()
    assert clock.slept == [pytest.approx(1.5)]
