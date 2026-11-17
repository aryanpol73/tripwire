"""The 36-scenario grid: 3 families x 3 states x 4 skins.

Each family has a main site type and a second one. Odd skins run on the main site, even
skins on the second, so every site type gets scenarios from more than one family and the
eval can report per site type (DECISIONS D-015).
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product

from tripwire.schemas.finding import Family
from tripwire.schemas.ground_truth import ScenarioState
from tripwire.schemas.trace import SiteType

SKIN_NUMBERS = (1, 2, 3, 4)

FAMILY_SITES: dict[Family, tuple[SiteType, SiteType]] = {
    Family.CONSENT_ASYMMETRY: (SiteType.NEWS, SiteType.SAAS),  # banner; saas sign-up page
    Family.SNEAKING: (SiteType.SHOP, SiteType.SAAS),  # checkout; saas trial page
    Family.OBSTRUCTION: (SiteType.SAAS, SiteType.NEWS),  # cancel; newsletter unsubscribe
}


def mission_for(family: Family, site: SiteType) -> str:
    if site == SiteType.SHOP:
        return "reach_payment"
    if site == SiteType.NEWS and family == Family.CONSENT_ASYMMETRY:
        return "first_visit"
    return "sign_up_and_leave"


@dataclass(frozen=True)
class Scenario:
    family: Family
    state: ScenarioState
    skin: int

    @property
    def id(self) -> str:
        return f"{self.family}-{self.state}-skin{self.skin}"

    @property
    def site_type(self) -> SiteType:
        main, second = FAMILY_SITES[self.family]
        return main if self.skin % 2 == 1 else second

    @property
    def mission(self) -> str:
        return mission_for(self.family, self.site_type)


def grid() -> list[Scenario]:
    return [
        Scenario(family, state, skin)
        for family, state, skin in product(Family, ScenarioState, SKIN_NUMBERS)
    ]


def get(scenario_id: str) -> Scenario:
    for scenario in grid():
        if scenario.id == scenario_id:
            return scenario
    raise KeyError(f"unknown scenario {scenario_id!r}; run `evilweb list` to see all ids")
