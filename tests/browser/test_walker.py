"""Phase 3 exit check: every scenario's mission runs within budget, the walker's click counts
match ground truth exactly, and repeated runs give identical detector inputs."""

import subprocess
import sys
from pathlib import Path

import pytest

from evilweb import scenarios
from evilweb.ground_truth import build
from evilweb.server import serve
from tripwire.cli import main
from tripwire.eval.fingerprint import fingerprint
from tripwire.mission import load_mission
from tripwire.schemas.io import read_trace
from tripwire.schemas.trace import PriceRole, RunStatus, Trace
from tripwire.walker.scripted_walker import RunRequest, ScriptedWalker


def walk(browser, tmp_path: Path, scenario_id: str) -> Trace:
    sc = scenarios.get(scenario_id)
    with serve(scenario_id) as url:
        return ScriptedWalker(
            RunRequest(
                start_url=url + "/",
                mission=load_mission(sc.mission),
                run_dir=tmp_path / scenario_id,
                run_id=scenario_id,
                site_type=sc.site_type,
                scenario_id=scenario_id,
                browser=browser,
            )
        ).run()


def metrics(truth, rule):
    found = [e.metrics for e in truth.expectations if e.rule == rule]
    return found[0] if found else None


def path(trace: Trace, name: str):
    return next(p for p in trace.paths if p.name == name)


@pytest.mark.parametrize("scenario_id", [s.id for s in scenarios.grid()])
def test_mission_runs_within_budget_and_counts_match_ground_truth(browser, tmp_path, scenario_id):
    trace = walk(browser, tmp_path, scenario_id)
    truth = build(scenario_id)

    assert trace.status == RunStatus.COMPLETED, [n.message for n in trace.notes]
    assert not trace.budgets_used.exceeds(trace.budget_limits)

    consent = metrics(truth, "consent.click_asymmetry")
    if consent:
        assert path(trace, "accept_consent").clicks == consent["accept_clicks"]
        assert path(trace, "reject_consent").clicks == consent["reject_clicks"]
        assert path(trace, "reject_consent").completed

    leave = metrics(truth, "obstruction.roach_motel")
    if leave:
        assert path(trace, "sign_up").clicks == leave["sign_up_clicks"]
        exit_path = next(p for p in trace.paths if p.goal in ("cancel", "unsubscribe"))
        assert exit_path.clicks == leave["leave_clicks"]
        assert exit_path.exit_channel == leave["exit_channel"]

    drift = metrics(truth, "sneaking.price_drift")
    if drift:
        totals = [line for line in trace.commerce.price_ledger if line.role == PriceRole.TOTAL]
        last = max(totals, key=lambda line: line.first_step)
        if truth.site_type == "shop":
            assert last.amount.minor == drift["final_total_minor"]
        late_fees = [
            line.amount.minor
            for line in trace.commerce.price_ledger
            if line.role == PriceRole.FEE and line.mandatory and line.first_step == last.first_step
        ]
        assert sum(late_fees) == drift["drift_from_mandatory_minor"]

    if truth.mission == "reach_payment":
        assert path(trace, "reach_payment").completed


@pytest.mark.parametrize(
    "scenario_id",
    ["consent_asymmetry-blatant-skin3", "sneaking-subtle-skin2", "obstruction-blatant-skin4"],
)
def test_three_runs_give_identical_detector_inputs(browser, tmp_path, scenario_id):
    prints = {fingerprint(walk(browser, tmp_path / str(i), scenario_id)) for i in range(3)}
    assert len(prints) == 1


def test_cli_audit_and_replay(tmp_path, capsys):
    # A separate process, as a user runs it (and with its own Chromium).
    out = tmp_path / "run"
    cmd = [
        sys.executable,
        "-m",
        "tripwire.cli",
        "audit",
        "--scenario",
        "consent_asymmetry-subtle-skin1",
        "--out",
        str(out),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=180)
    assert result.returncode == 0, result.stderr
    trace = read_trace(out / "trace.json")
    assert trace.scenario_id == "consent_asymmetry-subtle-skin1"
    assert main(["replay", str(out)]) == 0
    assert "reject_consent   2 clicks" in capsys.readouterr().out


def test_cli_refuses_real_sites(capsys):
    assert main(["audit", "https://example.com", "--mission", "first_visit"]) == 2
    assert "Phase 7" in capsys.readouterr().err
