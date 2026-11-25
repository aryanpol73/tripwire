"""Wire-level form changes (Phase 9 module 2), on the saas sign-up and the shop address form.

Every state shows the same visible, unticked "Email me deals from partners" checkbox.
  clean   - decoy: at submit a script adds a security nonce (`xsrf_nonce`); the form is
            otherwise sent exactly as shown (the box stays unticked, so it is not sent).
  subtle  - at submit a script ticks the box: the visitor saw it unticked.
  blatant - at submit it ticks the box and adds `partner_data_sharing=1`, a field that was
            never in the form.

v1 and other module scenarios get NONE: no box, no script.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from tripwire.schemas.ground_truth import Decoy, ScenarioState

BOX = "partner_deals"
INJECTED = "partner_data_sharing"


@dataclass(frozen=True)
class WireSpec:
    mode: Literal["none", "honest", "flips", "flips_and_injects"]

    @property
    def shown(self) -> bool:
        return self.mode != "none"

    @property
    def flips(self) -> bool:
        return self.mode in ("flips", "flips_and_injects")

    @property
    def injects(self) -> bool:
        return self.mode == "flips_and_injects"

    def fires(self, rule_id: str) -> bool:
        return {"wire.flipped_choice": self.flips, "wire.injected_optin": self.injects}[rule_id]

    def metrics(self) -> dict[str, dict]:
        """Exact expectations for one submission of the planted form."""
        if not self.shown:
            return {}
        return {
            "wire.flipped_choice": {
                "flipped_count": int(self.flips),
                "flipped_fields": f"{BOX}=1" if self.flips else "",
            },
            "wire.injected_optin": {
                "injected_optin_count": int(self.injects),
                "injected_fields": f"{INJECTED}=1" if self.injects else "",
                "unclassified_added_fields": 0,
            },
        }


NONE = WireSpec("none")


def build(state: ScenarioState) -> WireSpec:
    return {
        ScenarioState.CLEAN: WireSpec("honest"),
        ScenarioState.SUBTLE: WireSpec("flips"),
        ScenarioState.BLATANT: WireSpec("flips_and_injects"),
    }[state]


def decoys(spec: WireSpec) -> list[Decoy]:
    if spec.mode != "honest":
        return []
    return [
        Decoy(
            id="nonce_added_at_submit",
            description="A security nonce added by script at submit, and an unticked box "
            "that is sent as unticked.",
            must_not_trigger=["wire.flipped_choice", "wire.injected_optin"],
        )
    ]
