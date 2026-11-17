"""Finding schema tests: findings report measurements, never verdicts."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from tripwire.schemas import Finding, FindingSet, Severity, read_findings, write_model

EXAMPLE = (
    Path(__file__).resolve().parents[1] / "fixtures" / "findings" / "consent_click_asymmetry.json"
)


@pytest.fixture
def finding_dict() -> dict:
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))["findings"][0]


def test_example_finding_set_round_trips(tmp_path):
    findings = read_findings(EXAMPLE)
    assert findings.findings[0].evidence.measurements["reject_clicks"] == 2
    out = write_model(findings, tmp_path / "findings.json")
    assert read_findings(out) == findings


def test_empty_finding_set_is_valid():
    assert FindingSet(run_id="r").findings == []


@pytest.mark.parametrize("field", ["summary", "false_positive_notes"])
@pytest.mark.parametrize(
    "phrase", ["is illegal", "a Scam", "fraudulent pricing", "deliberately hidden", "on purpose"]
)
def test_verdicts_and_intent_claims_are_rejected(finding_dict, field, phrase):
    finding_dict[field] = f"The reject button {phrase}."
    with pytest.raises(ValidationError, match="not verdicts"):
        Finding.model_validate(finding_dict)


def test_summary_is_one_line(finding_dict):
    finding_dict["summary"] = "Rejecting takes longer.\nSecond line."
    with pytest.raises(ValidationError, match="single line"):
        Finding.model_validate(finding_dict)


@pytest.mark.parametrize(("tier", "too_high"), [("B", 0.8), ("C", 0.5)])
def test_tier_caps_confidence(finding_dict, tier, too_high):
    finding_dict["tier"] = tier
    finding_dict["confidence"] = too_high
    with pytest.raises(ValidationError, match="cannot exceed"):
        Finding.model_validate(finding_dict)


def test_confidence_is_between_0_and_1(finding_dict):
    finding_dict["confidence"] = 1.5
    with pytest.raises(ValidationError):
        Finding.model_validate(finding_dict)


def test_tier_a_needs_measurements(finding_dict):
    finding_dict["evidence"]["measurements"] = {}
    with pytest.raises(ValidationError, match="measured"):
        Finding.model_validate(finding_dict)


def test_evidence_needs_at_least_one_step(finding_dict):
    finding_dict["evidence"]["step_indices"] = []
    with pytest.raises(ValidationError, match="step_indices"):
        Finding.model_validate(finding_dict)


def test_reproduction_steps_are_required(finding_dict):
    finding_dict["reproduce"] = []
    with pytest.raises(ValidationError, match="reproduce"):
        Finding.model_validate(finding_dict)


def test_taxonomy_labels_are_always_informational(finding_dict):
    finding_dict["taxonomy"][0]["informational"] = False
    with pytest.raises(ValidationError):
        Finding.model_validate(finding_dict)


def test_money_measurements_keep_integer_type(finding_dict):
    finding_dict["evidence"]["measurements"] = {"price_drift_minor": 2900, "area_ratio": 3.4}
    finding = Finding.model_validate(finding_dict)
    assert isinstance(finding.evidence.measurements["price_drift_minor"], int)


def test_severity_has_an_order():
    assert Severity.INFO.rank < Severity.LOW.rank < Severity.MEDIUM.rank < Severity.HIGH.rank
