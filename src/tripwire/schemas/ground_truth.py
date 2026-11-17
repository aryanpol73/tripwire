"""Ground truth for one Evil Web scenario: which rules must fire, with the exact numbers.

The eval harness (Phase 4) compares detector findings against this file.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal, Self

from pydantic import Field, model_validator

from tripwire.detectors.rules import RULES
from tripwire.schemas.common import Model, NonEmptyStr
from tripwire.schemas.finding import Family, Measurement, Tier
from tripwire.schemas.trace import MissionName, SiteType

GROUND_TRUTH_SCHEMA_VERSION = "0.1.0"


class ScenarioState(StrEnum):
    CLEAN = "clean"  # no pattern; legitimate look-alikes (decoys) are present
    SUBTLE = "subtle"  # pattern present, just past the threshold
    BLATANT = "blatant"  # pattern present, far past the threshold


class RuleExpectation(Model):
    rule: NonEmptyStr
    family: Family
    tier: Tier
    should_fire: bool
    # Exact values a correct measurement must produce: click counts, paise, contrast (2 dp).
    metrics: dict[str, Measurement] = Field(default_factory=dict)


class Decoy(Model):
    id: NonEmptyStr
    description: NonEmptyStr
    must_not_trigger: list[NonEmptyStr] = Field(min_length=1)


class GroundTruth(Model):
    schema_version: Literal["0.1.0"] = GROUND_TRUTH_SCHEMA_VERSION
    scenario_id: NonEmptyStr
    family: Family
    state: ScenarioState
    skin: int = Field(ge=1, le=4)
    site_type: SiteType
    mission: MissionName
    expectations: list[RuleExpectation] = Field(min_length=1)
    decoys: list[Decoy] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        expected_id = f"{self.family}-{self.state}-skin{self.skin}"
        if self.scenario_id != expected_id:
            raise ValueError(f"scenario_id should be {expected_id!r}")

        rules = [e.rule for e in self.expectations]
        if len(set(rules)) != len(rules):
            raise ValueError("each rule may appear only once")
        for e in self.expectations:
            known = RULES.get(e.rule)
            if known is None:
                raise ValueError(f"unknown rule {e.rule!r}")
            if (known.family, known.tier) != (e.family, e.tier):
                raise ValueError(f"{e.rule}: family/tier do not match the rule catalog")

        # Planting rule (NOTEBOOK Phase 0, proposal P1): a non-clean scenario plants every
        # applicable Tier A rule of its family; a clean scenario plants none. Rules of other
        # families never fire here, because only one family is planted per scenario.
        for e in self.expectations:
            planted = e.family == self.family and self.state != ScenarioState.CLEAN
            if e.tier == Tier.A and e.should_fire != planted:
                raise ValueError(f"{e.rule}: should_fire must be {planted} in this scenario")
            if e.family != self.family and e.should_fire:
                raise ValueError(f"{e.rule}: only the scenario's own family may fire")

        if self.state == ScenarioState.CLEAN and not self.decoys:
            raise ValueError("clean scenarios must list the decoys that must stay silent")
        for decoy in self.decoys:
            unknown = set(decoy.must_not_trigger) - set(rules)
            if unknown:
                raise ValueError(f"decoy {decoy.id}: guards rules not in expectations {unknown}")
        return self
