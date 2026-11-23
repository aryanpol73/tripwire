"""False urgency (Phase 9 module 1), on the shop product page and the saas pricing page.

  clean   - decoys: a real deadline (counts down from the server's fixed end time, so a
            reload keeps the time) and a steady "only 3 left" stock count.
  subtle  - the countdown restarts at 9:59 on every load; the stock count is steady.
  blatant - the countdown restarts on every load, and the stock count goes up on every
            view (2 left, then 4 left, ...), with nothing bought.

v1 scenarios get NONE: no widget at all, so the v1 grid renders exactly as before.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Literal

from tripwire.schemas.ground_truth import Decoy, ScenarioState

DEADLINE_S = 2 * 3600  # the clean decoy's real deadline, from when the server started


@dataclass(frozen=True)
class UrgencySpec:
    countdown: Literal["none", "deadline", "restarts"]
    stock: Literal["none", "steady", "refills"]
    restart_seconds: int = 599
    stock_start: int = 3
    stock_step: int = 2

    @property
    def shown(self) -> bool:
        return self.countdown != "none" or self.stock != "none"

    def widget(self, state: Any) -> dict[str, Any]:
        """Values for one page view. `state` is the app state (start time, view count)."""
        if not self.shown:
            return {"countdown_seconds": None, "stock_left": None}
        state.urgency_views = getattr(state, "urgency_views", 0) + 1
        if self.countdown == "deadline":
            seconds = max(1, int(state.started + DEADLINE_S - time.monotonic()))
        elif self.countdown == "restarts":
            seconds = self.restart_seconds
        else:
            seconds = None
        if self.stock == "steady":
            stock = self.stock_start
        elif self.stock == "refills":
            stock = self.stock_start - 1 + self.stock_step * (state.urgency_views - 1)
        else:
            stock = None
        return {"countdown_seconds": seconds, "stock_left": stock}

    def metrics(self) -> dict[str, dict]:
        """Exact expectations after the walker's probe: one view, then one reload."""
        found: dict[str, dict] = {}
        if self.countdown != "none":
            found["urgency.countdown_reset"] = {"timer_restarted": self.countdown == "restarts"}
        if self.stock == "steady":
            found["urgency.stock_flux"] = {
                "stock_before": self.stock_start,
                "stock_after": self.stock_start,
                "stock_went_up": False,
            }
        elif self.stock == "refills":
            first = self.stock_start - 1
            found["urgency.stock_flux"] = {
                "stock_before": first,
                "stock_after": first + self.stock_step,
                "stock_went_up": True,
            }
        return found


NONE = UrgencySpec("none", "none")


def build(state: ScenarioState) -> UrgencySpec:
    if state == ScenarioState.CLEAN:
        return UrgencySpec("deadline", "steady")
    if state == ScenarioState.SUBTLE:
        return UrgencySpec("restarts", "steady")
    return UrgencySpec("restarts", "refills")


def decoys(spec: UrgencySpec) -> list[Decoy]:
    found = []
    if spec.countdown == "deadline":
        found.append(
            Decoy(
                id="real_deadline_countdown",
                description="A countdown to a fixed end time: it keeps counting across a reload.",
                must_not_trigger=["urgency.countdown_reset"],
            )
        )
    if spec.stock == "steady":
        found.append(
            Decoy(
                id="steady_stock_count",
                description="'Only 3 left' that stays at 3 across a reload.",
                must_not_trigger=["urgency.stock_flux"],
            )
        )
    return found
