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
    "phrase,expected",
    [
        ("I prefer a worse experience", True),
        ("Decline optional cookies", False),
        ("No, I do not value my security", True),
        ("No, I do not want to share my address", False),
    ],
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
        ("hidden", "share_with_partners", False, False, False),
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


@pytest.mark.parametrize("chosen,expected", [("Studio", 1800), ("Solo", 800), (None, None)])
def test_drift_uses_selected_offer_even_when_a_cheaper_plan_is_listed(chosen, expected):
    from tripwire.detectors.base import measurements
    from tripwire.schemas.trace import Form, FormField, PriceLine

    trace = read_trace(FIXTURES / "sneaking_clean.json")

    def line(label, minor, step, role):
        return PriceLine(
            label=label,
            amount={"currency": "GBP", "minor": minor},
            first_step=step,
            seen_steps=[step],
            role=role,
            mandatory=True,
        )

    trace.commerce.price_ledger[:] = [
        line("Solo per month", 800, 0, "other"),
        line("Studio per month", 1800, 0, "other"),
        line("Monthly total", 2200, 2, "total"),
        line("Setup charge", 300, 2, "fee"),
    ]
    trace.steps[1].forms.append(
        Form(
            id="options",
            fields=[
                FormField(type="radio", name="membership", label=label, prechecked=label == chosen)
                for label in ("Studio", "Solo")
            ],
        )
    )
    drift = measurements(trace).get("sneaking.price_drift")
    if expected is None:
        assert drift is None
    else:
        assert drift.metrics["advertised_total_minor"] == expected
        assert drift.metrics["final_total_minor"] == 2500


def test_retention_choice_counts_only_while_leaving():
    from tripwire.detectors.base import measurements

    trace = read_trace(FIXTURES / "obstruction_violating.json")
    offer = trace.steps[6]
    offer.overlays.clear()
    take, decline = offer.ui.elements
    offer.ui.elements[:] = [
        take.model_copy(update={"text": "Claim my discount"}),
        decline.model_copy(update={"text": "Decline and leave"}),
    ]
    target = trace.steps[7].action.target.model_copy(
        update={"accessible_name": "Decline and leave"}
    )
    trace.steps[7] = trace.steps[7].model_copy(
        update={"action": trace.steps[7].action.model_copy(update={"target": target})}
    )
    assert 6 in measurements(trace)["obstruction.interposed_friction"].steps


def test_clicked_offer_is_measured_from_the_originating_price_row():
    from tripwire.detectors.sneaking import _selected_offers
    from tripwire.schemas.trace import PriceLine

    trace = read_trace(FIXTURES / "sneaking_clean.json")
    options = [
        PriceLine(
            label=name,
            amount={"minor": price, "currency": "GBP"},
            role="other",
            mandatory=True,
            first_step=0,
            seen_steps=[0],
        )
        for name, price in [
            ("Entry per month Find out more", 400),
            ("Family per month Subscribe now", 1800),
        ]
    ]
    step = trace.steps[1]
    target = step.action.target.model_copy(update={"accessible_name": "Subscribe now"})
    trace.steps[1] = step.model_copy(
        update={"action": step.action.model_copy(update={"target": target})}
    )
    assert _selected_offers(options, trace.steps[:2]) == [options[1]]
    options[0] = options[0].model_copy(update={"label": "Entry per month Subscribe now"})
    assert _selected_offers(options, trace.steps[:2]) == []


def test_review_keeps_ambiguous_evidence_distinct_from_positive_findings():
    from tripwire.detectors.base import finding_set, measurements
    from tripwire.schemas.trace import Form, FormField

    trace = read_trace(FIXTURES / "consent_asymmetry_violating.json")
    trace.steps[1].ui.elements[-1] = (
        trace.steps[1]
        .ui.elements[-1]
        .model_copy(update={"text": "Reject optional cookies and allow necessary cookies"})
    )
    report = finding_set(trace, measurements(trace))
    assert report.review_steps_by_rule["consent.confirmshaming"] == [1]
    assert all(f.detector != "consent.confirmshaming" for f in report.findings)
    trace.steps[1].ui.elements[-1] = (
        trace.steps[1]
        .ui.elements[-1]
        .model_copy(update={"text": "Decline and accept that I prefer a worse experience"})
    )
    report = finding_set(trace, measurements(trace))
    wording = next(f for f in report.findings if f.detector == "consent.confirmshaming")
    assert wording.confidence == 0.5
    assert report.review_steps_by_rule[wording.detector] == [1]
    trace = read_trace(FIXTURES / "sneaking_clean.json")
    trace.steps[0].forms.append(
        Form(
            id="preferences",
            fields=[
                FormField(
                    name="share_with_partners",
                    type="hidden",
                    hidden=True,
                    hidden_boolean_default=True,
                )
            ],
        )
    )
    report = finding_set(trace, measurements(trace))
    assert report.review_steps_by_rule["sneaking.bundled_optins"] == [0]
    assert not report.findings
    field = trace.steps[0].forms[-1].fields[0]
    trace.steps[0].forms[-1].fields[0] = field.model_copy(update={"label": "Share with partners"})
    report = finding_set(trace, measurements(trace))
    assert not report.review_steps_by_rule
    assert report.findings[0].evidence.measurements["hidden_optin_count"] == 1


@pytest.mark.parametrize("required,expected", [(False, True), (True, False)])
def test_intermediate_choices_measured_on_the_submitted_form(required, expected):
    from tripwire.detectors.base import measurements
    from tripwire.schemas.trace import Form, FormField

    trace = read_trace(FIXTURES / "obstruction_violating.json")
    for i, index in enumerate((5, 6)):
        step = trace.steps[index]
        step.overlays.clear()
        step.ui.elements[:] = [
            step.ui.elements[0].model_copy(
                update={"id": "submit", "text": "Proceed", "accessible_name": "Proceed"}
            )
        ]
        fields = (
            [FormField(type="checkbox", name="use", required=required)]
            if i == 0 or required
            else []
        )
        step.forms[:] = [
            Form(id="flow", submit_element_id="submit", has_alternative_link=i == 1, fields=fields)
        ]
        action = trace.steps[step.index + 1].action
        trace.steps[step.index + 1] = trace.steps[step.index + 1].model_copy(
            update={
                "action": action.model_copy(
                    update={
                        "target": action.target.model_copy(update={"accessible_name": "Proceed"})
                    }
                )
            }
        )
    obs = measurements(trace)["obstruction.interposed_friction"]
    assert obs.metrics["unneeded_interstitials"] == (2 if expected else 0)
