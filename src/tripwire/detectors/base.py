"""Convert independent trace measurements to findings with replayable evidence."""

from __future__ import annotations

import tomllib
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from importlib.resources import files
from typing import Protocol

from tripwire.browser.redact import redact_url
from tripwire.detectors.rules import RULES
from tripwire.mission import load_mission
from tripwire.schemas.finding import Evidence, Finding, FindingSet, Measurement, ReproStep
from tripwire.schemas.trace import Trace


@dataclass
class Observation:
    rule: str
    flagged: bool
    steps: list[int]
    metrics: dict[str, Measurement]
    summary: str
    caveat: str
    review_steps: list[int] = field(default_factory=list)
    confidence: float | None = None


class Detector(Protocol):
    def __call__(self, trace: Trace, config: Mapping) -> Iterator[Observation]: ...


def measurements(trace: Trace) -> dict[str, Observation]:
    from tripwire.detectors.consent import consent
    from tripwire.detectors.obstruction import obstruction
    from tripwire.detectors.sneaking import sneaking

    config = tomllib.loads(files(__package__).joinpath("thresholds.toml").read_text())
    applicable = load_mission(trace.mission).detectors
    observations = {}
    families: dict[str, Detector] = {
        "consent": consent,
        "obstruction": obstruction,
        "sneaking": sneaking,
    }
    for family, detector in families.items():
        if any(rule.startswith(family + ".") for rule in applicable):
            for observation in detector(trace, config[family]):
                if observation.rule in applicable:
                    observations[observation.rule] = observation
    return observations


def findings_for(trace: Trace, observations: Mapping[str, Observation]) -> list[Finding]:
    findings = []
    for obs in observations.values():
        if not obs.flagged:
            continue
        rule = RULES[obs.rule]
        indices = sorted(set(obs.steps))
        steps = [trace.steps[i] for i in indices]
        reproduce = []
        for step in trace.steps[: indices[-1] + 1]:
            action = step.action
            target = action.target
            label = (target.accessible_name or target.visible_text or "") if target else ""
            reproduce.append(
                ReproStep(
                    url=redact_url(step.url_before or step.url_after),
                    action=f"{action.kind} {label}".strip(),
                )
            )
        findings.append(
            Finding(
                id=f"{trace.run_id}/{rule.id}",
                run_id=trace.run_id,
                detector=rule.id,
                family=rule.family,
                tier=rule.tier,
                severity="medium",
                confidence=obs.confidence
                if obs.confidence is not None
                else (0.7 if rule.tier == "B" else 0.95),
                mission=trace.mission,
                site_url=redact_url(trace.site_url),
                summary=obs.summary,
                reproduce=reproduce,
                false_positive_notes=obs.caveat,
                evidence=Evidence(
                    step_indices=indices,
                    screenshots=[s.screenshot for s in steps if s.screenshot],
                    measurements=obs.metrics,
                    request_ids=[r.id for s in steps for r in s.requests],
                ),
            )
        )
    return findings


def finding_set(trace: Trace, observations: Mapping[str, Observation]) -> FindingSet:
    return FindingSet(
        run_id=trace.run_id,
        findings=findings_for(trace, observations),
        review_steps_by_rule={
            rule: sorted(set(o.review_steps)) for rule, o in observations.items() if o.review_steps
        },
    )


def detect(trace: Trace) -> list[Finding]:
    return findings_for(trace, measurements(trace))
