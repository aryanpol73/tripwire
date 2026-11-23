"""Phase 7 preparation, offline: the pre-flight, the labels file, refusals and scoring."""

import shutil
from datetime import date, timedelta
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from tripwire.mission import load_mission
from tripwire.pilot.labels import EXAMPLE, Labels
from tripwire.pilot.preflight import CHECKS, PreflightError, load_preflight, template
from tripwire.pilot.score import score
from tripwire.schemas.trace import Mode
from tripwire.walker.base import RealSitesDisabled, RunRequest
from tripwire.walker.scripted_walker import ScriptedWalker

FIXTURES = Path(__file__).parents[1] / "fixtures" / "traces"


def write_preflight(tmp_path, **override):
    data = {"owner": "Owner", "signed_on": str(date.today()), "checks": dict.fromkeys(CHECKS, True)}
    data["checks"].update(override.pop("checks", {}))
    data.update(override)
    path = tmp_path / "preflight.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


# --- pre-flight --------------------------------------------------------------------------


def test_template_lists_every_check_as_false():
    text = template()
    assert all(f"  {key}: false" in text for key in CHECKS)


def test_missing_preflight_is_refused(tmp_path):
    with pytest.raises(PreflightError, match="no pre-flight file"):
        load_preflight(tmp_path / "nope.yaml")


def test_incomplete_preflight_names_the_open_items(tmp_path):
    path = write_preflight(tmp_path, checks={"phase6_gate_passed": False})
    with pytest.raises(PreflightError, match="phase6_gate_passed"):
        load_preflight(path)


def test_future_dated_preflight_is_refused(tmp_path):
    path = write_preflight(tmp_path, signed_on=str(date.today() + timedelta(days=3)))
    with pytest.raises(PreflightError, match="future"):
        load_preflight(path)


def test_complete_preflight_loads(tmp_path):
    assert load_preflight(write_preflight(tmp_path)).owner == "Owner"


# --- refusals before any browser starts ---------------------------------------------------


def request(tmp_path, url="https://example.org/", mission="first_visit", **kw):
    return RunRequest(start_url=url, mission=load_mission(mission), run_dir=tmp_path / "r",
                      run_id="t", **kw)  # fmt: skip


def test_real_host_without_real_mode_is_refused(tmp_path):
    with pytest.raises(RealSitesDisabled, match="pilot run"):
        ScriptedWalker(request(tmp_path)).run()


def test_real_mode_without_a_complete_preflight_is_refused(tmp_path):
    path = write_preflight(tmp_path, checks={"flows_labelled_before_running": False})
    with pytest.raises(RealSitesDisabled, match="flows_labelled_before_running"):
        ScriptedWalker(request(tmp_path, mode=Mode.REAL, preflight=path)).run()


def test_account_flows_on_a_real_site_need_approval(tmp_path):
    path = write_preflight(tmp_path)
    req = request(tmp_path, mission="sign_up_and_leave", mode=Mode.REAL, preflight=path)
    with pytest.raises(RealSitesDisabled, match="ETHICS 10"):
        ScriptedWalker(req).run()


# --- labels ------------------------------------------------------------------------------


def test_example_labels_are_valid():
    labels = Labels.model_validate(yaml.safe_load(EXAMPLE))
    assert labels.runs() == [("news-1", "first_visit")]


@pytest.mark.parametrize(
    ("change", "error"),
    [
        (lambda d: d["flows"][0].update(rule="consent.nonsense"), "unknown rule"),
        (lambda d: d["flows"][0].update(site="nowhere"), "unknown site"),
        (lambda d: d["sites"][0].update(url="http://example.org/"), "https"),
    ],
)
def test_labels_are_checked(change, error):
    data = yaml.safe_load(EXAMPLE)
    change(data)
    with pytest.raises(ValidationError, match=error):
        Labels.model_validate(data)


# --- scoring -----------------------------------------------------------------------------


def labels_for(flows):
    return Labels.model_validate(
        {
            "sites": [{"id": "s1", "url": "https://a.example/", "type": "news"},
                      {"id": "s2", "url": "https://b.example/", "type": "news"}],
            "flows": [{"labelled_on": "2026-11-30", "mission": "first_visit", **f} for f in flows],
        }
    )  # fmt: skip


def test_score_counts_tp_fp_and_unmeasured(tmp_path):
    runs = tmp_path / "runs"
    (runs / "s1--first_visit").mkdir(parents=True)
    shutil.copy(
        FIXTURES / "consent_asymmetry_violating.json", runs / "s1--first_visit" / "trace.json"
    )
    labels = labels_for([
        {"id": "f1", "site": "s1", "rule": "consent.click_asymmetry", "present": True},
        {"id": "f2", "site": "s1", "rule": "consent.click_asymmetry", "present": False},
        {"id": "f3", "site": "s2", "rule": "consent.click_asymmetry", "present": True},
    ])  # fmt: skip
    result = score(labels, runs)
    outcomes = {f["flow"]: f["outcome"] for f in result["flows"]}
    assert outcomes == {"f1": "TP", "f2": "FP", "f3": "not_measured"}
    assert result["tier_a"]["precision"] == 0.5
    assert result["gate_passed"] is False
    assert result["not_measured"] == {"f3": "no run"}


def test_score_reports_measurement_disagreements(tmp_path):
    runs = tmp_path / "runs"
    (runs / "s1--first_visit").mkdir(parents=True)
    shutil.copy(
        FIXTURES / "consent_asymmetry_violating.json", runs / "s1--first_visit" / "trace.json"
    )
    labels = labels_for([
        {"id": "f1", "site": "s1", "rule": "consent.click_asymmetry", "present": True,
         "measurements": {"accept_clicks": 99}},
    ])  # fmt: skip
    result = score(labels, runs)
    assert result["measurement_disagreements"]["f1"]["accept_clicks"]["label"] == 99
    assert result["tier_a"]["precision"] == 1.0 and result["gate_passed"] is True
