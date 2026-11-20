from tripwire.detectors.base import Observation
from tripwire.eval.runner import check_targets
from tripwire.eval.scoring import Score
from tripwire.schemas.ground_truth import RuleExpectation


def test_measurement_errors_are_visible_even_when_classification_matches():
    score = Score()
    rule = "consent.visual_asymmetry"
    expected = RuleExpectation(
        rule=rule,
        family="consent_asymmetry",
        tier="A",
        should_fire=True,
        metrics={"accept_contrast": 5.0, "area_ratio": 4},
    )
    observed = Observation(rule, True, [0], {"accept_contrast": 5.1, "area_ratio": 5}, "", "")
    score.record("fixture", 1, "news", [expected], {rule: observed})
    assert score.report()["groups"]["A/overall"]["precision"] == 1
    assert [(d["metric"], d["delta"]) for d in score.differences] == [("area_ratio", 1)]
    score.record("missing", 2, "saas", [expected], {})
    assert score.errors == [f"missing {rule} miss"]
    assert score.report()["groups"]["A/overall"]["recall"] == 0.5


def test_ci_two_point_boundary(monkeypatch):
    from tripwire.eval import runner

    monkeypatch.setattr(runner, "read_baseline", lambda: {"A/overall": {"recall": 1.0}})
    report = {
        "groups": {"A/overall": {"recall": 0.98}},
        "classification_errors": [],
        "decoy_false_positives": [],
    }
    assert not check_targets(report)
    report["groups"]["A/overall"]["recall"] = 0.979
    assert check_targets(report)


def test_holdout_runner_keeps_misses_and_outputs(tmp_path, monkeypatch, capsys):
    import json
    from pathlib import Path

    from tripwire.eval.holdout import evaluate_holdout

    reference = Path(__file__).parents[1] / "fixtures/traces/consent_asymmetry_clean.json"
    cases = []
    for i in range(3):
        cases.append(
            dict(
                id=f"reader-{i}",
                layout=f"layout-{i}",
                skin=f"skin-{i}",
                source=str(reference),
                expectations=[
                    dict(
                        rule="consent.click_asymmetry",
                        tier="A",
                        family="consent_asymmetry",
                        should_fire=True,
                    )
                ],
            )
        )
    manifest = tmp_path / "labels.json"
    manifest.write_text(json.dumps({"cases": cases}))
    monkeypatch.chdir(tmp_path)
    assert evaluate_holdout(manifest) == 1
    report = json.loads(capsys.readouterr().out)
    assert len(report["classification_errors"]) == 3
    assert report["groups"]["A/overall"]["recall"] == 0
    assert (Path(report["artifacts"]) / "score.json").is_file()


def test_holdout_only_accepts_local_live_fixtures():
    import pytest
    from pydantic import ValidationError

    from tripwire.eval.holdout import LocalFixture

    with pytest.raises(ValidationError, match="loopback"):
        LocalFixture(url="https://example.org", mission="first_visit", site_type="news")
