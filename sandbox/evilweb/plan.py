"""A Plan is everything one scenario renders: the skin plus one spec per pattern surface.

Only the scenario's own family is planted. Every other surface uses its clean spec, so a
scenario tests one family while the other families' detectors must stay silent.
The web apps and the ground-truth generator both read the same Plan, so what is rendered
and what is expected cannot drift apart.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache

from evilweb import scenarios
from evilweb.patterns import consent, obstruction, sneaking, urgency, wire
from evilweb.skins import SKINS, Skin
from tripwire.schemas.finding import Family
from tripwire.schemas.ground_truth import ScenarioState


@dataclass(frozen=True)
class Plan:
    scenario: scenarios.Scenario
    skin: Skin
    consent: consent.ConsentSpec
    shop: sneaking.ShopSpec
    saas_trial: sneaking.SaasTrialSpec
    saas_leave: obstruction.LeaveSpec
    news_leave: obstruction.LeaveSpec
    urgency: urgency.UrgencySpec = urgency.NONE
    wire: wire.WireSpec = wire.NONE

    def module(self, family: Family):
        """The Phase 9 module spec for a family (each knows which of its rules fire)."""
        return {Family.URGENCY: self.urgency, Family.WIRE: self.wire}[family]


@cache
def build_plan(scenario_id: str) -> Plan:
    scenario = scenarios.get(scenario_id)
    skin = SKINS[scenario.skin]

    def state(family: Family) -> ScenarioState:
        return scenario.state if scenario.family == family else ScenarioState.CLEAN

    return Plan(
        scenario=scenario,
        skin=skin,
        consent=consent.build(state(Family.CONSENT_ASYMMETRY), skin),
        shop=sneaking.build_shop(state(Family.SNEAKING)),
        saas_trial=sneaking.build_saas(state(Family.SNEAKING), skin),
        saas_leave=obstruction.build_saas(state(Family.OBSTRUCTION), skin),
        news_leave=obstruction.build_news(state(Family.OBSTRUCTION), skin),
        # Only urgency-module scenarios show the widget; v1 scenarios render as before.
        urgency=(
            urgency.build(scenario.state) if scenario.family == Family.URGENCY else urgency.NONE
        ),
        wire=wire.build(scenario.state) if scenario.family == Family.WIRE else wire.NONE,
    )
