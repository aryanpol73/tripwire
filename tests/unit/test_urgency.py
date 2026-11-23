"""Phase 9 module 1, false urgency: detectors on recorded sandbox traces, no browser."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from evilweb.ground_truth import build
from tripwire.detectors.base import measurements
from tripwire.report import plain
from tripwire.schemas.ground_truth import GroundTruth
from tripwire.schemas.io import read_trace
from tripwire.schemas.trace import ActionKind

FIXTURES = Path(__file__).parents[1] / "fixtures" / "traces"


def trace(name):
    return read_trace(FIXTURES / f"urgency_{name}.json")


def test_restarting_countdown_and_refilling_stock_are_measured():
    obs = measurements(trace("violating"))
    reset = obs["urgency.countdown_reset"]
    assert reset.flagged and reset.metrics["timer_restarted"] is True
    assert reset.metrics["excess_s"] > 3.0
    flux = obs["urgency.stock_flux"]
    assert flux.flagged
    assert (flux.metrics["stock_before"], flux.metrics["stock_after"]) == (2, 4)


def test_real_deadline_and_steady_stock_stay_silent():
    obs = measurements(trace("clean"))
    assert obs["urgency.countdown_reset"].flagged is False
    assert abs(obs["urgency.countdown_reset"].metrics["excess_s"]) <= 3.0
    assert obs["urgency.stock_flux"].flagged is False
    assert obs["urgency.stock_flux"].metrics["stock_before"] == 3


def test_a_clock_that_does_not_tick_is_not_a_countdown():
    t = trace("violating")
    steps = list(t.steps)
    wait = next(i for i, s in enumerate(steps) if s.action.kind == ActionKind.WAIT)
    frozen = [x.model_copy() for x in steps[wait - 1].timers]  # same reading 2 s later
    steps[wait] = steps[wait].model_copy(update={"timers": frozen})
    obs = measurements(t.model_copy(update={"steps": steps}))
    assert "urgency.countdown_reset" not in obs  # opening hours, not a timer


def test_the_probe_is_a_wait_then_one_reload_on_the_same_page():
    kinds = [s.action.kind for s in trace("violating").steps]
    i = kinds.index(ActionKind.RELOAD)
    assert kinds[i - 1] == ActionKind.WAIT and kinds.count(ActionKind.RELOAD) == 1


def test_headlines_are_plain_sentences():
    assert (
        plain.headline(
            "urgency.countdown_reset",
            {"seconds_before": 597, "seconds_after": 599, "elapsed_s": 4.2},
        )
        == "The countdown showed 09:57; after a reload 4 s later it showed 09:59, not 09:53."
    )
    assert plain.clock(7199) == "1:59:59"


@pytest.mark.parametrize(
    ("scenario", "fires"),
    [
        ("urgency-clean-skin1", {"urgency.countdown_reset": False, "urgency.stock_flux": False}),
        ("urgency-subtle-skin1", {"urgency.countdown_reset": True, "urgency.stock_flux": False}),
        ("urgency-blatant-skin2", {"urgency.countdown_reset": True, "urgency.stock_flux": True}),
    ],
)
def test_ground_truth_plants_each_pattern_on_its_own(scenario, fires):
    truth = build(scenario)
    got = {e.rule: e.should_fire for e in truth.expectations if e.family == "urgency"}
    assert got == fires
    assert all(not e.should_fire for e in truth.expectations if e.family != "urgency")


def test_a_planted_module_scenario_must_fire_something():
    data = build("urgency-subtle-skin1").model_dump()
    for e in data["expectations"]:
        e["should_fire"] = False
    with pytest.raises(ValidationError, match="at least one"):
        GroundTruth.model_validate(data)
