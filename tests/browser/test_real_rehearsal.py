"""Phase 7 rehearsal: the real-site rules, applied to the local sandbox. No real site."""

from evilweb import scenarios
from evilweb.server import serve
from tripwire.mission import load_mission
from tripwire.schemas.trace import ActionKind, Mode, NoteKind, PathGoal
from tripwire.walker.base import RunRequest
from tripwire.walker.scripted_walker import ScriptedWalker


def rehearse(browser, tmp_path, scenario_id, mission=None):
    sc = scenarios.get(scenario_id)
    with serve(scenario_id) as url:
        return ScriptedWalker(
            RunRequest(
                start_url=url + "/",
                mission=load_mission(mission or sc.mission),
                run_dir=tmp_path / scenario_id,
                run_id=scenario_id,
                browser=browser,
                mode=Mode.REAL,
                log=lambda _m: None,
            )
        ).run()


def test_real_rules_pace_actions_and_never_accept(browser, tmp_path):
    trace = rehearse(browser, tmp_path, "consent_asymmetry-blatant-skin1")
    assert trace.mode == Mode.REAL
    assert any("Rehearsal" in n.message for n in trace.notes)
    gaps = [
        (b.timestamp - a.timestamp).total_seconds()
        for a, b in zip(trace.steps, trace.steps[1:], strict=False)
    ]
    # ETHICS 5: actions start at least 2 s apart. Timestamps are taken after each page
    # settles, not when the action starts, so each gap jitters around 2 s by the change in
    # settle time; over the whole run that jitter is at most about half a second.
    span = (trace.steps[-1].timestamp - trace.steps[0].timestamp).total_seconds()
    assert gaps and span >= 2.0 * len(gaps) - 0.5 and min(gaps) >= 1.5
    accept = next(p for p in trace.paths if p.goal == PathGoal.ACCEPT_CONSENT)
    assert accept.executed is False
    clicked = [s.action.target.accessible_name or "" for s in trace.steps if s.action.target]
    assert not any(name.lower().startswith("accept") for name in clicked)
    assert trace.budgets_used.page_loads <= 30


def test_real_rules_stop_a_sign_up_at_the_gate(browser, tmp_path):
    trace = rehearse(browser, tmp_path, "obstruction-blatant-skin1")
    # Opening the form ("Start free trial") is allowed; creating the account is not.
    blocks = [n.message for n in trace.notes if n.kind == NoteKind.SAFETY_BLOCK]
    assert any("Start my trial" in m for m in blocks)
    names = [(s.action.target.accessible_name or "") for s in trace.steps
             if s.action.kind == ActionKind.CLICK and s.action.target]  # fmt: skip
    assert "Start my trial" not in names
