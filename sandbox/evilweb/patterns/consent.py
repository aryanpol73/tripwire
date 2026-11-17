"""Consent and choice asymmetry: a cookie banner with up to three layers.

clean   - Accept and Reject on layer 1 with identical size and colour; optional toggles off.
subtle  - no Reject on layer 1; Reject on layer 2 at 1/3.2 of Accept's area; one toggle on.
blatant - Reject only on layer 3, tiny and faint (< 3:1); all optional toggles on; the
          sign-up newsletter box is pre-checked; the decline text shames the user.
"""

from __future__ import annotations

from dataclasses import dataclass

from evilweb.patterns.common import Control, muted, primary, secondary
from evilweb.skins import Skin
from tripwire.schemas.ground_truth import Decoy, ScenarioState
from tripwire.schemas.trace import SiteType


@dataclass(frozen=True)
class Layer:
    accept: Control
    reject: Control | None = None
    deeper: Control | None = None  # opens the next layer ("Manage options", "More")
    save: Control | None = None  # saves the toggles as they are


@dataclass(frozen=True)
class Toggle:
    key: str
    label: str
    essential: bool
    checked: bool


@dataclass(frozen=True)
class ConsentSpec:
    state: ScenarioState
    layers: tuple[Layer, ...]
    toggles: tuple[Toggle, ...]  # shown on layer 2
    newsletter_prechecked: bool  # the "email me product news" box on the saas sign-up form
    shaming: bool

    @property
    def reject_layer(self) -> int:
        return next(i for i, layer in enumerate(self.layers, 1) if layer.reject)

    def metrics(self, site: SiteType) -> dict[str, dict]:
        layer = self.layers[self.reject_layer - 1]
        accept, reject = layer.accept, layer.reject
        assert reject is not None
        preselected = sum(t.checked and not t.essential for t in self.toggles)
        if site == SiteType.SAAS and self.newsletter_prechecked:
            preselected += 1
        return {
            "consent.click_asymmetry": {
                "accept_clicks": 1,
                "reject_clicks": self.reject_layer,  # one click per layer opened, then Reject
                "extra_clicks_to_reject": self.reject_layer - 1,
                "reject_on_first_layer": self.reject_layer == 1,
            },
            "consent.visual_asymmetry": {
                "compared_on_layer": self.reject_layer,
                "area_ratio": round(accept.area / reject.area, 2),
                "accept_contrast": accept.contrast,
                "reject_contrast": reject.contrast,
                "accept_font_px": accept.font_px,
                "reject_font_px": reject.font_px,
            },
            "consent.preselected": {"preselected_count": preselected},
            "consent.confirmshaming": {"decline_text": reject.label},
        }


SHAMING_TEXT = "No thanks, I prefer a worse experience"


def build(state: ScenarioState, skin: Skin) -> ConsentSpec:
    w = skin.w
    if state == ScenarioState.CLEAN:
        same = (200, 44, 16)
        layers = (
            Layer(
                accept=primary(skin, w("accept"), *same),
                reject=primary(skin, w("reject"), *same),
                deeper=secondary(skin, w("manage"), 160, 32, 14),
            ),
            Layer(
                accept=primary(skin, w("accept"), *same),
                reject=primary(skin, w("reject"), *same),
                save=secondary(skin, w("save"), 160, 44, 16),
            ),
        )
        on: set[str] = set()
    elif state == ScenarioState.SUBTLE:
        layers = (
            Layer(
                accept=primary(skin, w("accept"), 320, 48, 16),
                deeper=secondary(skin, w("manage"), 160, 32, 14),
            ),
            Layer(
                accept=primary(skin, w("accept"), 320, 48, 16),
                reject=secondary(skin, w("reject"), 160, 30, 14),  # area ratio 3.2
                save=secondary(skin, w("save"), 160, 30, 14),
            ),
        )
        on = {"personalisation"}
    else:
        big = (400, 56, 18)
        tiny = (120, 20, 11)
        layers = (
            Layer(accept=primary(skin, w("accept"), *big), deeper=muted(skin, w("manage"), *tiny)),
            Layer(
                accept=primary(skin, w("accept"), *big),
                deeper=muted(skin, w("more"), *tiny),
                save=muted(skin, w("save"), *tiny),
            ),
            Layer(accept=primary(skin, w("accept"), *big), reject=muted(skin, SHAMING_TEXT, *tiny)),
        )
        on = {"analytics", "marketing", "personalisation"}

    toggles = (
        Toggle("necessary", "Strictly necessary (always on)", essential=True, checked=True),
        Toggle("analytics", "Analytics", essential=False, checked="analytics" in on),
        Toggle("marketing", "Marketing", essential=False, checked="marketing" in on),
        Toggle(
            "personalisation",
            "Personalised content",
            essential=False,
            checked="personalisation" in on,
        ),
    )
    return ConsentSpec(
        state=state,
        layers=layers,
        toggles=toggles,
        newsletter_prechecked=state == ScenarioState.BLATANT,
        shaming=state == ScenarioState.BLATANT,
    )


def decoys(spec: ConsentSpec) -> list[Decoy]:
    found = [
        Decoy(
            id="locked_necessary_toggle",
            description="A 'strictly necessary' toggle that is on and cannot be changed.",
            must_not_trigger=["consent.preselected"],
        )
    ]
    if spec.state == ScenarioState.CLEAN:
        found += [
            Decoy(
                id="equal_weight_buttons",
                description="Accept and Reject on the first layer with identical size and colour.",
                must_not_trigger=["consent.click_asymmetry", "consent.visual_asymmetry"],
            ),
            Decoy(
                id="optional_toggles_unchecked",
                description="A settings layer whose optional toggles are all off.",
                must_not_trigger=["consent.preselected"],
            ),
        ]
    return found
