from pathlib import Path

import pytest

from tripwire.detectors.base import detect
from tripwire.schemas.io import read_trace

FIXTURES = Path(__file__).parents[1] / "fixtures" / "traces"


@pytest.mark.parametrize(
    ("family", "ids"),
    [
        (
            "consent_asymmetry",
            {"consent.click_asymmetry", "consent.visual_asymmetry", "consent.preselected"},
        ),
        (
            "obstruction",
            {
                "obstruction.roach_motel",
                "obstruction.buried_control",
                "obstruction.interposed_friction",
            },
        ),
        ("sneaking", {"sneaking.price_drift", "sneaking.preadded_extras"}),
    ],
)
def test_measured_findings_and_clean_decoys(family, ids):
    trace = read_trace(FIXTURES / f"{family}_violating.json")
    findings = detect(trace)
    assert {f.detector for f in findings} == ids
    assert all(f.evidence.measurements and f.reproduce for f in findings)
    assert detect(read_trace(FIXTURES / f"{family}_clean.json")) == []


@pytest.mark.parametrize(
    "phrase,expected", [("I prefer a worse experience", True), ("Decline optional cookies", False)]
)
def test_decline_wording(phrase, expected):
    trace = read_trace(FIXTURES / "consent_asymmetry_violating.json")
    trace.steps[1].ui.elements[-1] = (
        trace.steps[1].ui.elements[-1].model_copy(update={"text": phrase})
    )
    assert ("consent.confirmshaming" in [f.detector for f in detect(trace)]) == expected


def test_signup_consent_works_without_banner():
    trace = read_trace(FIXTURES / "consent_asymmetry_violating.json")
    for step in trace.steps:
        step.overlays.clear()
    result = detect(trace)
    assert [f.detector for f in result] == ["consent.preselected"]
    assert result[0].evidence.measurements["preselected_count"] == 1


def test_unreachable_reject_does_not_invent_a_click_cost():
    trace = read_trace(FIXTURES / "consent_asymmetry_violating.json")
    trace.paths[1] = trace.paths[1].model_copy(update={"completed": False})
    f = next(f for f in detect(trace) if f.detector == "consent.click_asymmetry")
    assert f.evidence.measurements["reject_on_first_layer"] is False
    assert f.evidence.measurements["reject_clicks"] is None


@pytest.mark.parametrize(
    ("kind", "name", "offscreen", "checked", "fires"),
    [
        ("hidden", "csrf_token", False, False, False),
        ("checkbox", "remember_me", False, True, False),
        ("checkbox", "marketing", True, False, False),
        ("checkbox", "marketing", True, True, True),
        ("hidden", "share_with_partners", False, False, True),
    ],
)
def test_bundled_agreement_decoys(kind, name, offscreen, checked, fires):
    from tripwire.schemas.trace import Form, FormField

    trace = read_trace(FIXTURES / "sneaking_clean.json")
    trace.steps[0].forms.append(
        Form(
            id="f1",
            fields=[
                FormField(
                    name=name,
                    type=kind,
                    default_value="1",
                    off_screen=offscreen,
                    hidden=kind == "hidden",
                    prechecked=checked,
                )
            ],
        )
    )
    assert ("sneaking.bundled_optins" in {f.detector for f in detect(trace)}) == fires


@pytest.mark.parametrize(
    ("date", "size", "contrast", "fires"),
    [(True, 12, 3, False), (True, 11, 4.5, True), (True, 16, 2.9, True), (False, 16, 4.5, True)],
)
def test_measured_trial_disclosure(date, size, contrast, fires):
    from tripwire.schemas.trace import Commerce, TermsNotice

    trace = read_trace(FIXTURES / "obstruction_violating.json")
    notice = TermsNotice(
        step_index=1,
        text="Trial renewal terms",
        font_size_px=size,
        contrast_ratio=contrast,
        mentions_date=date,
        mentions_price=True,
    )
    trace = trace.model_copy(update={"commerce": Commerce(terms=[notice])})
    assert ("sneaking.renewal_disclosure" in {f.detector for f in detect(trace)}) == fires


def test_deep_leave_control_in_normal_text():
    trace = read_trace(FIXTURES / "obstruction_clean.json")
    for step in trace.steps:
        for pos, element in enumerate(step.ui.elements):
            if element.text == "Cancel plan":
                step.ui.elements[pos] = element.model_copy(update={"tree_depth": 14})
    assert "obstruction.buried_control" in {f.detector for f in detect(trace)}


def test_an_unchecked_hidden_preference_is_not_an_agreement():
    from tripwire.schemas.trace import Form, FormField

    trace = read_trace(FIXTURES / "sneaking_clean.json")
    trace.steps[0].forms.append(
        Form(
            id="f1",
            fields=[
                FormField(
                    name="share_with_partners", type="hidden", hidden=True, default_value="false"
                )
            ],
        )
    )
    assert "sneaking.bundled_optins" not in {f.detector for f in detect(trace)}
