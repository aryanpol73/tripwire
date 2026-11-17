"""Trace schema tests: the contract between walkers and detectors."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from tripwire.schemas import ActionKind, Money, Trace, read_trace, write_model

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "traces"
ALL_TRACES = sorted(FIXTURES.glob("*.json"))
FAMILIES = ("consent_asymmetry", "sneaking", "obstruction")
CLICK_ACTIONS = {ActionKind.CLICK, ActionKind.REJECT_CONSENT}


def load(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


# --- Fixtures ----------------------------------------------------------------------


@pytest.mark.parametrize("family", FAMILIES)
def test_every_family_has_a_violating_and_a_clean_fixture(family):
    assert (FIXTURES / f"{family}_violating.json").exists()
    assert (FIXTURES / f"{family}_clean.json").exists()


@pytest.mark.parametrize("path", ALL_TRACES, ids=lambda p: p.stem)
def test_fixture_traces_validate_and_round_trip(path, tmp_path):
    trace = read_trace(path)
    out = write_model(trace, tmp_path / "trace.json")
    assert read_trace(out) == trace


@pytest.mark.parametrize("path", ALL_TRACES, ids=lambda p: p.stem)
def test_fixture_numbers_add_up(path):
    """Hand-written fixtures must be internally consistent, or detector tests built on them
    would test the wrong thing. This is also the rule the Phase 3 walker must satisfy."""
    trace = read_trace(path)
    assert trace.budgets_used.steps == len(trace.steps)
    assert trace.budgets_used.page_loads == sum(s.page_load for s in trace.steps)
    for p in trace.paths:
        if not p.executed:
            continue  # measured structurally from the page; no steps were performed
        steps = [trace.steps[i] for i in p.step_indices]
        assert p.clicks == sum(s.action.kind in CLICK_ACTIONS for s in steps), p.name
        assert p.page_loads == sum(s.page_load for s in steps), p.name


def test_sneaking_fixture_totals_are_exact_paise():
    trace = read_trace(FIXTURES / "sneaking_violating.json")
    ledger = {line.label: line.amount for line in trace.commerce.price_ledger}
    assert ledger["Total payable"] == Money(minor=47600, currency="INR")
    lines_at_summary = [
        line.amount.minor
        for line in trace.commerce.price_ledger
        if 2 in line.seen_steps and line.role != "total"
    ]
    assert sum(lines_at_summary) == ledger["Total payable"].minor


# --- Rules enforced by the schema ------------------------------------------------------


def test_money_rejects_floats():
    with pytest.raises(ValidationError):
        Money(minor=1499.0, currency="INR")
    with pytest.raises(ValidationError):
        Money.model_validate_json('{"minor": 1499.5, "currency": "INR"}')


def test_money_needs_an_iso_currency_code():
    with pytest.raises(ValidationError):
        Money(minor=100, currency="inr")


def test_unknown_fields_are_rejected():
    data = load("consent_asymmetry_clean")
    data["colour"] = "blue"
    with pytest.raises(ValidationError, match="colour"):
        Trace.model_validate(data)


def test_wrong_schema_version_is_rejected():
    data = load("consent_asymmetry_clean")
    data["schema_version"] = "9.9.9"
    with pytest.raises(ValidationError):
        Trace.model_validate(data)


def test_site_url_must_be_absolute_http():
    data = load("consent_asymmetry_clean")
    data["site_url"] = "file:///etc/passwd"
    with pytest.raises(ValidationError, match="http"):
        Trace.model_validate(data)


def test_step_index_must_match_position():
    data = load("obstruction_clean")
    data["steps"][2]["index"] = 7
    with pytest.raises(ValidationError, match="position 2"):
        Trace.model_validate(data)


def test_ended_before_started_is_rejected():
    data = load("consent_asymmetry_clean")
    data["ended_at"] = "2026-11-17T09:00:00+05:30"
    with pytest.raises(ValidationError, match="before"):
        Trace.model_validate(data)


def test_exceeded_budget_must_be_reported_in_status():
    data = load("consent_asymmetry_clean")
    data["budgets_used"]["page_loads"] = 31
    with pytest.raises(ValidationError, match="page_loads"):
        Trace.model_validate(data)
    data["status"] = "budget_exceeded"
    Trace.model_validate(data)


def test_request_ids_are_unique_across_the_trace():
    data = load("consent_asymmetry_violating")
    data["steps"][2]["requests"][0]["id"] = "r0"
    with pytest.raises(ValidationError, match="request ids"):
        Trace.model_validate(data)


def test_overlay_controls_must_point_at_measured_elements():
    data = load("consent_asymmetry_violating")
    data["steps"][0]["overlays"][0]["controls"][0]["element_id"] = "e99"
    with pytest.raises(ValidationError, match="e99"):
        Trace.model_validate(data)


def test_duplicate_element_ids_in_a_step_are_rejected():
    data = load("consent_asymmetry_violating")
    data["steps"][0]["ui"]["elements"][1]["id"] = "e1"
    with pytest.raises(ValidationError, match="duplicate"):
        Trace.model_validate(data)


def test_path_steps_must_exist_and_increase():
    data = load("obstruction_violating")
    data["paths"][1]["step_indices"] = [4, 5, 42]
    with pytest.raises(ValidationError, match="missing step 42"):
        Trace.model_validate(data)
    data["paths"][1]["step_indices"] = [5, 4]
    with pytest.raises(ValidationError, match="increasing"):
        Trace.model_validate(data)


def test_intent_must_name_an_existing_path():
    data = load("obstruction_violating")
    data["intents"][0]["cheapest_path"] = "teleport"
    with pytest.raises(ValidationError, match="teleport"):
        Trace.model_validate(data)


def test_successful_intent_needs_a_path():
    data = load("obstruction_violating")
    data["intents"][0]["cheapest_path"] = None
    with pytest.raises(ValidationError, match="cheapest_path"):
        Trace.model_validate(data)


def test_commerce_references_must_point_at_steps():
    data = load("sneaking_violating")
    data["commerce"]["price_ledger"][0]["first_step"] = 12
    with pytest.raises(ValidationError, match="missing step 12"):
        Trace.model_validate(data)


def test_contrast_ratio_stays_in_the_wcag_range():
    data = load("consent_asymmetry_clean")
    data["steps"][0]["ui"]["elements"][0]["contrast_ratio"] = 0.5
    with pytest.raises(ValidationError):
        Trace.model_validate(data)


@pytest.mark.parametrize("bad", ["/etc/passwd", "../outside.png", "C:\\screens\\0.png"])
def test_artifact_paths_stay_inside_the_run_folder(bad):
    data = load("consent_asymmetry_clean")
    data["steps"][0]["screenshot"] = bad
    with pytest.raises(ValidationError, match="relative"):
        Trace.model_validate(data)


# model_construct() skips validation, so pydantic warns while dumping it. That is the point.
@pytest.mark.filterwarnings("ignore:Pydantic serializer warnings")
def test_write_refuses_an_invalid_model(tmp_path):
    broken = Money.model_construct(minor="not money", currency="INR")
    with pytest.raises(ValidationError):
        write_model(broken, tmp_path / "money.json")
    assert not (tmp_path / "money.json").exists()
