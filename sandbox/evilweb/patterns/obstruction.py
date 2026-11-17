"""Obstruction: leaving is harder than joining.

saas (cancel the plan; joining = 3 clicks from the landing page)
  clean   - "Cancel plan" in the account menu, as prominent as Upgrade; a legally required
            notice (needs a tick) and one confirmation. 4 clicks.
  subtle  - Settings -> Billing -> a footer-only link -> survey -> retention offer -> confirm.
            6 clicks (3 more than joining).
  blatant - the same, with a tiny faint footer link, two "are you sure" steps, and a final
            page that says to phone support. 7 clicks, then offline only.
news (leave the newsletter; joining = 1 click in the pop-up)
  clean   - "Newsletter" in the header -> Unsubscribe -> confirm. 3 clicks.
  subtle  - a footer-only link -> Unsubscribe -> survey -> retention offer. 4 clicks.
  blatant - a tiny faint footer link -> Unsubscribe -> survey -> retention -> are you sure ->
            "email us to unsubscribe". 5 clicks, then email only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from evilweb.patterns.common import Control, muted, secondary
from evilweb.skins import Skin
from tripwire.schemas.ground_truth import Decoy, ScenarioState
from tripwire.schemas.trace import SiteType

StepKind = Literal[
    "notice",
    "preferences",
    "survey",
    "retention",
    "are_you_sure",
    "confirm",
    "phone_only",
    "email_only",
]

# Clicks needed to get past each step. Offline-only steps end the web path.
STEP_CLICKS: dict[str, int] = {
    "notice": 2,  # tick the required box, then continue
    "preferences": 1,
    "survey": 1,
    "retention": 1,
    "are_you_sure": 1,
    "confirm": 1,
    "phone_only": 0,
    "email_only": 0,
}
# Interstitials that add a step without any required input (SPEC 3.3, "unneeded").
UNNEEDED = {"survey", "retention", "are_you_sure"}

SUPPORT_PHONE = "1800-555-0100"
SUPPORT_EMAIL = "unsubscribe@dailyledger.example"


@dataclass(frozen=True)
class LeaveSpec:
    site: SiteType
    state: ScenarioState
    sign_up_clicks: int
    pre_entry: tuple[str, ...]  # pages to open before the leave control is visible
    entry_location: Literal["menu", "footer"]
    entry: Control
    steps: tuple[StepKind, ...]

    @property
    def exit_channel(self) -> str:
        last = self.steps[-1]
        return {"phone_only": "phone", "email_only": "email"}.get(last, "web")

    @property
    def leave_clicks(self) -> int:
        return len(self.pre_entry) + 1 + sum(STEP_CLICKS[s] for s in self.steps)

    def metrics(self) -> dict[str, dict]:
        return {
            "obstruction.roach_motel": {
                "sign_up_clicks": self.sign_up_clicks,
                "leave_clicks": self.leave_clicks,
                "extra_clicks_to_leave": self.leave_clicks - self.sign_up_clicks,
                "exit_channel": self.exit_channel,
            },
            "obstruction.buried_control": {
                "footer_only": self.entry_location == "footer",
                "click_depth": len(self.pre_entry),
                "font_px": self.entry.font_px,
                "contrast": self.entry.contrast,
            },
            "obstruction.interposed_friction": {
                "unneeded_interstitials": sum(s in UNNEEDED for s in self.steps),
            },
        }


def build_saas(state: ScenarioState, skin: Skin) -> LeaveSpec:
    label = skin.w("cancel_plan")
    common = {"site": SiteType.SAAS, "state": state, "sign_up_clicks": 3}
    if state == ScenarioState.CLEAN:
        return LeaveSpec(
            **common,
            pre_entry=(),
            entry_location="menu",
            entry=secondary(skin, label, 180, 44, 16),
            steps=("notice", "confirm"),
        )
    if state == ScenarioState.SUBTLE:
        return LeaveSpec(
            **common,
            pre_entry=("settings", "billing"),
            entry_location="footer",
            entry=secondary(skin, label, 150, 20, 13),
            steps=("survey", "retention", "confirm"),
        )
    return LeaveSpec(
        **common,
        pre_entry=("settings", "billing"),
        entry_location="footer",
        entry=muted(skin, label, 110, 16, 10),
        steps=("survey", "retention", "are_you_sure", "are_you_sure", "phone_only"),
    )


def build_news(state: ScenarioState, skin: Skin) -> LeaveSpec:
    common = {"site": SiteType.NEWS, "state": state, "sign_up_clicks": 1}
    if state == ScenarioState.CLEAN:
        return LeaveSpec(
            **common,
            pre_entry=(),
            entry_location="menu",
            entry=secondary(skin, "Newsletter", 110, 28, 15),
            steps=("preferences", "confirm"),
        )
    if state == ScenarioState.SUBTLE:
        return LeaveSpec(
            **common,
            pre_entry=(),
            entry_location="footer",
            entry=secondary(skin, "Email preferences", 130, 20, 13),
            steps=("preferences", "survey", "retention"),
        )
    return LeaveSpec(
        **common,
        pre_entry=(),
        entry_location="footer",
        entry=muted(skin, "Email preferences", 110, 16, 10),
        steps=("preferences", "survey", "retention", "are_you_sure", "email_only"),
    )


def decoys(spec: LeaveSpec) -> list[Decoy]:
    if spec.state != ScenarioState.CLEAN:
        return []
    found = [
        Decoy(
            id="single_confirmation",
            description="One confirmation step before leaving.",
            must_not_trigger=["obstruction.interposed_friction", "obstruction.roach_motel"],
        ),
        Decoy(
            id="leave_control_as_prominent_as_join",
            description="The leave control sits in the main menu with normal size and colour.",
            must_not_trigger=["obstruction.buried_control"],
        ),
    ]
    if "notice" in spec.steps:
        found.append(
            Decoy(
                id="required_notice_step",
                description="A data-retention notice that needs an acknowledgement tick.",
                must_not_trigger=["obstruction.interposed_friction"],
            )
        )
    return found
