"""Nagging and forced registration (Phase 9 module 3), on the news articles.

  clean   - decoys: the newsletter pop-up remembers being closed (as on every v1 site), and a
            closable "Sign in for a personalised feed" banner with a sign-in link (not a wall).
  subtle  - the pop-up comes back on every article after it was closed.
  blatant - it comes back, and from the second article on, a "Create a free account to keep
            reading" wall (email and password, no close) covers the article.

v1 and other module scenarios get NONE: the pop-up remembers being closed, nothing else.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from tripwire.schemas.ground_truth import Decoy, ScenarioState

FREE_ARTICLES = 1  # the wall appears from article number FREE_ARTICLES + 1


@dataclass(frozen=True)
class NaggingSpec:
    popup: Literal["remembers", "returns"]
    wall: Literal["none", "decoy_banner", "metered"]

    @property
    def planted(self) -> bool:
        return self.popup == "returns" or self.wall != "none"

    def fires(self, rule_id: str) -> bool:
        if rule_id == "nagging.repeat_popup":
            return self.popup == "returns"
        return self.wall == "metered"

    def metrics(self) -> dict[str, dict]:
        if self.popup == "remembers" and self.wall == "none":
            return {}  # v1 and other modules: not measured as part of this module
        return {
            "nagging.repeat_popup": {"popup_returned": self.popup == "returns"},
            "nagging.forced_registration": {"account_wall": self.wall == "metered"},
        }


NONE = NaggingSpec("remembers", "none")


def build(state: ScenarioState) -> NaggingSpec:
    return {
        ScenarioState.CLEAN: NaggingSpec("remembers", "decoy_banner"),
        ScenarioState.SUBTLE: NaggingSpec("returns", "none"),
        ScenarioState.BLATANT: NaggingSpec("returns", "metered"),
    }[state]


def decoys(spec: NaggingSpec) -> list[Decoy]:
    if spec.wall != "decoy_banner":
        return []
    return [
        Decoy(
            id="popup_remembered_and_closable_sign_in_banner",
            description="The newsletter pop-up stays closed once closed; a sign-in banner can "
            "be closed and has no password field.",
            must_not_trigger=["nagging.repeat_popup", "nagging.forced_registration"],
        )
    ]
