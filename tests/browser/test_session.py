"""BrowserSession against the live sandbox: the gate holds, steps are valid, nothing leaks."""

import json
from datetime import UTC, datetime

import pytest

from evilweb.server import serve
from tripwire.browser.safety_gate import GateConfig, SafetyBlocked
from tripwire.browser.session import BrowserSession, SessionConfig
from tripwire.schemas.trace import ActionKind, Budgets, Mode, RunStatus, SiteType, Target, Trace

LIMITS = Budgets(steps=60, wall_seconds=300, page_loads=30, llm_spend_usd_micros=0)


@pytest.fixture
def sandbox_session(browser, tmp_path):
    def make(**kw) -> BrowserSession:
        gate = GateConfig(
            mode=Mode.SANDBOX, allowed_hosts=("127.0.0.1",), limits=LIMITS, min_action_interval_s=0
        )
        return BrowserSession(SessionConfig(gate=gate, run_dir=tmp_path, **kw), browser=browser)

    return make


# --- adversarial: the gate ----------------------------------------------------------


def test_off_allowlist_navigation_is_blocked_logged_and_never_sent(sandbox_session, tmp_path):
    with serve("consent_asymmetry-clean-skin1") as url, sandbox_session() as s:
        s.goto(url + "/")
        with pytest.raises(SafetyBlocked):
            s.goto("https://example.com/")
        assert s.gate.events[-1].kind == "navigation_blocked"
        assert s.page.url.startswith(url)  # still on the sandbox
        assert all("example.com" not in r.url for st in s.steps for r in st.requests)


def test_link_to_another_domain_is_aborted_by_request_routing(sandbox_session, tmp_path):
    with serve("consent_asymmetry-clean-skin1") as url, sandbox_session() as s:
        s.goto(url + "/")
        s.click(Target(role="button", accessible_name="Reject all"), kind=ActionKind.REJECT_CONSENT)
        # A page could contain such a link; the walker's click goes through routing.
        s.page.evaluate(
            "() => { const a = document.createElement('a'); a.href = 'https://evil.example/';"
            " a.textContent = 'Win a prize'; document.querySelector('main').append(a); }"
        )
        with pytest.raises(SafetyBlocked, match="allowlist"):
            s.click(Target(role="link", accessible_name="Win a prize"))
        assert s.page.url.startswith(url)  # back on the sandbox page, not an error page
        assert any(
            e.kind == "navigation_blocked" and "evil.example" in e.target for e in s.gate.events
        )


def test_sandbox_page_cannot_reach_the_internet(sandbox_session, tmp_path):
    with serve("consent_asymmetry-clean-skin1") as url, sandbox_session() as s:
        s.goto(url + "/")
        result = s.page.evaluate(
            "() => fetch('https://cdn.example/x.js').then(() => 'sent', () => 'blocked')"
        )
        assert result == "blocked"
        assert s.gate.events[-1].kind == "request_blocked"


def test_real_mode_refuses_to_click_pay(browser, tmp_path):
    # The gate does not care that this host is local: in real mode, pay is never clicked.
    gate = GateConfig(mode=Mode.REAL, allowed_hosts=("127.0.0.1",), limits=LIMITS)
    with (
        serve("sneaking-blatant-skin1") as url,
        BrowserSession(SessionConfig(gate=gate, run_dir=tmp_path), browser=browser) as s,
    ):
        s.goto(url + "/checkout/summary")
        before = s.page.url
        with pytest.raises(SafetyBlocked, match="irreversible"):
            s.click(Target(role="link", accessible_name="Proceed to payment"))
        assert s.page.url == before
        assert s.gate.events[-1].kind == "action_blocked"


# --- valid steps, redaction --------------------------------------------------------


def test_a_short_journey_produces_a_valid_trace(sandbox_session, tmp_path):
    with serve("consent_asymmetry-blatant-skin1") as url, sandbox_session() as s:
        start = datetime.now(UTC)
        s.goto(url + "/")
        s.click(Target(role="button", accessible_name="Manage options"))
        s.click(Target(role="button", accessible_name="Legitimate interest"))
        s.click(
            Target(role="button", accessible_name="No thanks, I prefer a worse experience"),
            kind=ActionKind.REJECT_CONSENT,
        )
        steps, used = s.steps, s.budget.used()
    trace = Trace(
        run_id="test",
        site_url=url + "/",
        site_type=SiteType.NEWS,
        mission="first_visit",
        mode=Mode.SANDBOX,
        scenario_id="consent_asymmetry-blatant-skin1",
        started_at=start,
        ended_at=datetime.now(UTC),
        status=RunStatus.COMPLETED,
        budget_limits=LIMITS,
        budgets_used=used,
        steps=steps,
    )
    assert [s.page_load for s in trace.steps] == [True, False, False, False]
    assert trace.budgets_used.page_loads == 1
    assert not trace.steps[-1].overlays  # banner gone after rejecting
    for rel in ("screens/000.png", "a11y/000.yaml", "dom/000.html"):
        assert (tmp_path / rel).exists()


def test_nothing_secret_is_saved(sandbox_session, tmp_path):
    with serve("sneaking-blatant-skin2") as url, sandbox_session() as s:
        s.goto(url + "/signup")
        s.type_into(Target(role="textbox", accessible_name="Work email"), "walker@example.test")
        s.click(Target(role="button", accessible_name="Next"))
        steps = s.steps
    saved = [json.dumps([st.model_dump(mode="json") for st in steps])]
    saved += [p.read_text(encoding="utf-8") for p in tmp_path.rglob("*.html")]
    saved.append((tmp_path / "network.har").read_text(encoding="utf-8"))
    for text in saved:
        assert "sandbox-csrf-token" not in text
    har = (tmp_path / "network.har").read_text(encoding="utf-8")
    assert "walker@example.test" not in har and "walker%40example.test" not in har


def test_typing_into_a_password_field_is_refused(sandbox_session, tmp_path):
    with serve("consent_asymmetry-clean-skin1") as url, sandbox_session() as s:
        s.goto(url + "/")
        s.page.evaluate(
            "() => { const i = document.createElement('input'); i.type = 'password';"
            " i.setAttribute('aria-label', 'Password'); document.querySelector('main').append(i); }"
        )
        with pytest.raises(SafetyBlocked, match="secret"):
            s.type_into(Target(role="textbox", accessible_name="Password"), "hunter2")
