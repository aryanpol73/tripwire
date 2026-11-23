"""False urgency (Phase 9 module 1): countdowns that restart and stock that refills.

Both rules compare one page before and after a reload the walker makes on purpose (a
`reload` step, a few seconds after the page was first measured). Nothing is bought between
the two, so a real deadline keeps counting down and a real stock count cannot go up.
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Mapping
from urllib.parse import urlsplit

from tripwire.detectors.base import Observation
from tripwire.schemas.trace import ActionKind, Step, Trace

CLOCKS = ("mm:ss", "hh:mm:ss")
STOCK = re.compile(r"(\d+)\s+left", re.IGNORECASE)


def _path(step: Step) -> str:
    return urlsplit(step.url_after).path


def _probes(trace: Trace) -> Iterator[tuple[Step, Step, Step]]:
    """(first measurement, the same page 2 s later, the same page after a reload)."""
    for i, step in enumerate(trace.steps):
        if step.action.kind == ActionKind.RELOAD and i > 1:
            first, later = trace.steps[i - 2], trace.steps[i - 1]
            if later.action.kind == ActionKind.WAIT and _path(first) == _path(step):
                yield first, later, step


def urgency(trace: Trace, config: Mapping) -> Iterator[Observation]:
    tolerance = float(config["reset_tolerance_s"])
    for first, before, after in _probes(trace):
        elapsed = (after.timestamp - before.timestamp).total_seconds()
        clocks_first = [t for t in first.timers if t.pattern in CLOCKS and t.seconds_remaining]
        clocks_before = [t for t in before.timers if t.pattern in CLOCKS and t.seconds_remaining]
        clocks_after = [t for t in after.timers if t.pattern in CLOCKS and t.seconds_remaining]
        # A countdown must tick: a clock that did not go down in 2 s is a time, not a timer.
        ticking = bool(clocks_first and clocks_before) and (
            clocks_before[0].seconds_remaining < clocks_first[0].seconds_remaining
        )
        if ticking and clocks_after:
            b, a = clocks_before[0].seconds_remaining, clocks_after[0].seconds_remaining
            excess = a - (b - elapsed)  # how much more time is shown than a real clock allows
            restarted = excess > tolerance
            yield Observation(
                "urgency.countdown_reset",
                restarted,
                [first.index, before.index, after.index],
                dict(
                    seconds_before=b,
                    seconds_after=a,
                    elapsed_s=round(elapsed, 1),
                    excess_s=round(excess, 1),
                    timer_restarted=restarted,
                ),
                f"The countdown showed {b} seconds, then {a} seconds after a reload "
                f"{round(elapsed)} seconds later.",
                "Check whether the deadline is per visitor by design and stated as such.",
            )
        stock_before = [_stock(t.text) for t in first.timers if t.pattern == "only N left"]
        stock_after = [_stock(t.text) for t in after.timers if t.pattern == "only N left"]
        stock_before = [n for n in stock_before if n is not None]
        stock_after = [n for n in stock_after if n is not None]
        if stock_before and stock_after:
            b, a = stock_before[0], stock_after[0]
            yield Observation(
                "urgency.stock_flux",
                a > b,
                [first.index, after.index],
                dict(stock_before=b, stock_after=a, stock_went_up=a > b),
                f"The page said {b} left, then {a} left after a reload with nothing bought.",
                "Check whether stock was restocked or the count is per variant.",
            )
        if ticking or stock_before:
            break  # one probe per run is enough evidence; later pages repeat the same widget


def _stock(text: str) -> int | None:
    m = STOCK.search(text)
    return int(m[1]) if m else None
