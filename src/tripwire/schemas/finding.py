"""The Finding: one measured asymmetry a detector reported, with the evidence to check it."""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import AfterValidator, Field, NonNegativeInt, StrictInt, model_validator

from tripwire.schemas.common import ArtifactPath, Fraction, HttpUrl, Model, NonEmptyStr
from tripwire.schemas.trace import MissionName

FINDING_SCHEMA_VERSION = "0.1.0"

# ETHICS rule 7, enforced in code: findings report a measured asymmetry. They never claim
# illegality or intent. A detector that writes one of these words cannot save its finding.
FORBIDDEN_WORDS = (
    # verdicts
    "illegal",
    "unlawful",
    "fraud",
    "fraudulent",
    "scam",
    "lying",
    "liar",
    "cheat",
    "cheating",
    "criminal",
    # intent claims
    "deliberate",
    "deliberately",
    "intentional",
    "intentionally",
    "on purpose",
)
_FORBIDDEN_RE = re.compile(r"\b(" + "|".join(FORBIDDEN_WORDS) + r")\b", re.IGNORECASE)


def _no_verdicts(text: str) -> str:
    match = _FORBIDDEN_RE.search(text)
    if match:
        raise ValueError(
            f"findings report measurements, not verdicts or intent; remove {match.group(0)!r}"
        )
    return text


def _one_sentence(text: str) -> str:
    if "\n" in text:
        raise ValueError("must be a single line")
    if len(text) > 300:
        raise ValueError("must be one short sentence (300 characters at most)")
    return text


Sentence = Annotated[NonEmptyStr, AfterValidator(_one_sentence), AfterValidator(_no_verdicts)]
Prose = Annotated[NonEmptyStr, AfterValidator(_no_verdicts)]


class Family(StrEnum):
    CONSENT_ASYMMETRY = "consent_asymmetry"
    SNEAKING = "sneaking"
    OBSTRUCTION = "obstruction"


class Tier(StrEnum):
    A = "A"  # deterministic measurement
    B = "B"  # heuristic, optionally LLM-assisted
    C = "C"  # LLM judgement only: experimental, never a headline finding


# The most confidence each tier may claim. A Tier C finding can never look as sure as a
# measured Tier A one, whatever the detector computes.
TIER_MAX_CONFIDENCE: dict[Tier, float] = {Tier.A: 1.0, Tier.B: 0.75, Tier.C: 0.4}


class Severity(StrEnum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

    @property
    def rank(self) -> int:
        return list(Severity).index(self)


# Counts, ratios, deltas. Money stays integer minor units (StrictInt); ratios may be floats.
Measurement = StrictInt | float | str | bool | None


class Evidence(Model):
    step_indices: list[NonNegativeInt] = Field(min_length=1)
    screenshots: list[ArtifactPath] = Field(default_factory=list)  # annotated, boxes drawn
    measurements: dict[str, Measurement] = Field(default_factory=dict)
    request_ids: list[str] = Field(default_factory=list)


class ReproStep(Model):
    url: HttpUrl
    action: NonEmptyStr  # plain words: "Click 'Manage options' in the cookie banner"


class TaxonomyLabel(Model):
    """Informational only. Never presented as a legal classification."""

    scheme: NonEmptyStr  # e.g. "Gray et al. 2018"
    label: NonEmptyStr
    informational: Literal[True] = True
    verified_against_official_text: bool = False


class Finding(Model):
    schema_version: Literal["0.1.0"] = FINDING_SCHEMA_VERSION
    id: NonEmptyStr
    run_id: NonEmptyStr
    family: Family
    detector: NonEmptyStr  # rule id, e.g. "consent.click_asymmetry"
    tier: Tier
    severity: Severity
    confidence: Fraction
    mission: MissionName
    site_url: HttpUrl
    summary: Sentence  # plain language a non-expert understands
    evidence: Evidence
    reproduce: list[ReproStep] = Field(min_length=1)
    taxonomy: list[TaxonomyLabel] = Field(default_factory=list)
    false_positive_notes: Prose  # what a human should check before trusting this

    @model_validator(mode="after")
    def _tier_rules(self) -> Self:
        cap = TIER_MAX_CONFIDENCE[self.tier]
        if self.confidence > cap:
            raise ValueError(f"tier {self.tier} findings cannot exceed confidence {cap}")
        if self.tier == Tier.A and not self.evidence.measurements:
            raise ValueError("tier A findings must carry measured values")
        return self


class FindingSet(Model):
    """All findings for one run. An empty list is valid, and is always shown with coverage."""

    schema_version: Literal["0.1.0"] = FINDING_SCHEMA_VERSION
    run_id: NonEmptyStr
    findings: list[Finding] = Field(default_factory=list)
