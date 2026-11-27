"""Phase 9 module 3, nagging and forced registration: detectors on recorded sandbox traces."""

from pathlib import Path

import pytest

from evilweb.ground_truth import build
from tripwire.detectors.base import measurements
from tripwire.report import plain
from tripwire.schemas.io import read_trace
from tripwire.schemas.trace import NoteKind, RunStatus

FIXTURES = Path(__file__).parents[1] / "fixtures" / "traces"


def trace(name):
    return read_trace(FIXTURES / f"nagging_{name}.json")


def test_a_closed_popup_that_comes_back_is_measured():
    obs = measurements(trace("subtle"))
    popup = obs["nagging.repeat_popup"]
    assert popup.flagged and popup.metrics["reappearances"] >= 1
    assert popup.metrics["popup_purpose"] == "newsletter"
    assert obs["nagging.forced_registration"].flagged is False


def test_an_account_wall_on_an_ordinary_article_is_measured():
    t = trace("blatant")
    assert t.status == RunStatus.HANDED_OFF  # the walker never types a password
    obs = measurements(t)
    wall = obs["nagging.forced_registration"]
    assert wall.flagged and wall.metrics["account_wall"] is True
    assert wall.metrics["reached_by"]  # the ordinary link that led to the wall
    assert obs["nagging.repeat_popup"].flagged


def test_a_remembered_popup_and_a_closable_banner_stay_silent():
    obs = measurements(trace("clean"))
    assert obs["nagging.repeat_popup"].flagged is False
    assert obs["nagging.repeat_popup"].metrics["dismissals"] == 1
    assert obs["nagging.forced_registration"].flagged is False


def test_a_wall_reached_through_a_sign_in_link_is_not_forced_registration():
    t = trace("blatant")
    note = next(n for n in t.notes if n.kind == NoteKind.HANDOFF)
    steps = list(t.steps)
    wall = steps[note.step_index]
    target = wall.action.target.model_copy(
        update={"accessible_name": "Sign in", "visible_text": "Sign in"}
    )
    steps[note.step_index] = wall.model_copy(
        update={"action": wall.action.model_copy(update={"target": target})}
    )
    obs = measurements(t.model_copy(update={"steps": steps}))
    assert obs["nagging.forced_registration"].flagged is False


@pytest.mark.parametrize(
    ("scenario", "fires"),
    [
        (
            "nagging-clean-skin1",
            {"nagging.repeat_popup": False, "nagging.forced_registration": False},
        ),
        (
            "nagging-subtle-skin2",
            {"nagging.repeat_popup": True, "nagging.forced_registration": False},
        ),
        (
            "nagging-blatant-skin3",
            {"nagging.repeat_popup": True, "nagging.forced_registration": True},
        ),
    ],
)
def test_ground_truth_plants_each_pattern_on_its_own(scenario, fires):
    truth = build(scenario)
    assert {e.rule: e.should_fire for e in truth.expectations if e.family == "nagging"} == fires
    assert truth.mission == "first_visit"


def test_headlines():
    assert (
        plain.headline("nagging.repeat_popup", {"reappearances": 2, "popup_purpose": "newsletter"})
        == "A newsletter pop-up that was closed came back on 2 later pages."
    )
    assert "create an account" in plain.headline(
        "nagging.forced_registration", {"reached_by": "City"}
    )
