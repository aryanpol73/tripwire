"""Phase 9 module 2, wire-level form checks: detectors on recorded sandbox traces."""

from pathlib import Path

import pytest

from evilweb.ground_truth import build
from tripwire.detectors.base import measurements
from tripwire.report import plain
from tripwire.schemas.io import read_trace

FIXTURES = Path(__file__).parents[1] / "fixtures" / "traces"


def trace(name):
    return read_trace(FIXTURES / f"wire_{name}.json")


def body_step(t):
    return next(
        s
        for s in t.steps
        if any(
            r.method == "POST" and "partner_deals" in (r.post_data_redacted or "")
            for r in s.requests
        )
    )


def test_flipped_box_and_injected_optin_are_measured_from_the_request():
    obs = measurements(trace("violating"))
    flipped = obs["wire.flipped_choice"]
    assert flipped.flagged and flipped.metrics["flipped_fields"] == "partner_deals=1"
    injected = obs["wire.injected_optin"]
    assert injected.flagged and injected.metrics["injected_fields"] == "partner_data_sharing=1"


def test_the_box_was_unticked_in_the_form_measured_just_before_submit():
    t = trace("violating")
    submit = body_step(t)
    form = next(f for f in t.steps[submit.index - 1].forms if f.action_url.endswith("/signup"))
    box = next(f for f in form.fields if f.name == "partner_deals")
    assert box.prechecked is False and not box.hidden and not box.off_screen
    assert all(f.name != "partner_data_sharing" for f in form.fields)  # added only at submit


def test_a_security_nonce_added_at_submit_is_not_a_choice():
    obs = measurements(trace("clean"))
    assert obs["wire.flipped_choice"].flagged is False
    assert obs["wire.injected_optin"].flagged is False
    assert obs["wire.injected_optin"].metrics["unclassified_added_fields"] == 0


def test_an_added_field_with_an_unclear_value_goes_to_review():
    t = trace("violating")
    submit = body_step(t)
    steps = list(t.steps)
    requests = [
        r.model_copy(update={"post_data_redacted": r.post_data_redacted.replace(
            "partner_data_sharing=1", "partner_ref=abc")})
        if r.post_data_redacted and "partner_data_sharing" in r.post_data_redacted
        else r
        for r in submit.requests
    ]  # fmt: skip
    steps[submit.index] = submit.model_copy(update={"requests": requests})
    obs = measurements(t.model_copy(update={"steps": steps}))
    injected = obs["wire.injected_optin"]
    assert injected.flagged is False
    assert injected.metrics["unclassified_added_fields"] == 1
    assert injected.review_steps == [submit.index]


@pytest.mark.parametrize(
    ("scenario", "fires"),
    [
        ("wire-clean-skin1", {"wire.flipped_choice": False, "wire.injected_optin": False}),
        ("wire-subtle-skin2", {"wire.flipped_choice": True, "wire.injected_optin": False}),
        ("wire-blatant-skin1", {"wire.flipped_choice": True, "wire.injected_optin": True}),
    ],
)
def test_ground_truth_plants_each_pattern_on_its_own(scenario, fires):
    truth = build(scenario)
    assert {e.rule: e.should_fire for e in truth.expectations if e.family == "wire"} == fires
    assert all(not e.should_fire for e in truth.expectations if e.family != "wire")


def test_headlines():
    assert plain.headline("wire.injected_optin", {"injected_fields": "x=1"}).startswith(
        "The submitted form sent x=1"
    )
    assert "1 box the visitor saw unticked was" in plain.headline(
        "wire.flipped_choice", {"flipped_count": 1, "flipped_fields": "a=1"}
    )
