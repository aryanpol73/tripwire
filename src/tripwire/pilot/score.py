"""Compare the tool with the owner's hand labels: Tier A precision is the Phase 7 gate.

For each labelled flow the scorer reads the run for that site and mission, recomputes the
detector observations from its trace, and records whether the rule fired. A flow whose run
did not reach the measurement (hand-off, block, error, no run) is "not measured": it does
not count for precision, and it goes into the failure taxonomy instead.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from tripwire.detectors.base import measurements
from tripwire.detectors.rules import RULES
from tripwire.pilot.labels import RUNS_DIR, Labels
from tripwire.schemas.finding import Tier
from tripwire.schemas.io import read_trace
from tripwire.schemas.trace import RunStatus

PRECISION_TARGET = 0.80


def run_dir(runs: Path, site: str, mission: str) -> Path:
    return runs / f"{site}--{mission}"


@dataclass
class FlowResult:
    flow: str
    site: str
    rule: str
    tier: str
    label: bool
    fired: bool | None  # None: not measured
    outcome: str  # TP, FP, TN, FN, or not_measured
    run_status: str
    measurement_diffs: dict[str, Any] = field(default_factory=dict)
    why_not_measured: str = ""


def _outcome(label: bool, fired: bool) -> str:
    return {(True, True): "TP", (False, True): "FP", (False, False): "TN", (True, False): "FN"}[
        (label, fired)
    ]


def score(labels: Labels, runs: Path = RUNS_DIR) -> dict[str, Any]:
    results: list[FlowResult] = []
    for f in labels.flows:
        tier = RULES[f.rule].tier.value
        trace_file = run_dir(runs, f.site, f.mission) / "trace.json"
        if not trace_file.is_file():
            results.append(
                FlowResult(
                    f.id,
                    f.site,
                    f.rule,
                    tier,
                    f.present,
                    None,
                    "not_measured",
                    "no run",
                    why_not_measured="no run",
                )
            )
            continue
        trace = read_trace(trace_file)
        obs = measurements(trace).get(f.rule)
        if (
            trace.status in (RunStatus.HANDED_OFF, RunStatus.BLOCKED, RunStatus.ERROR)
            or obs is None
        ):
            why = trace.status.value if obs else f"{trace.status.value}; rule not measured"
            results.append(
                FlowResult(
                    f.id,
                    f.site,
                    f.rule,
                    tier,
                    f.present,
                    None,
                    "not_measured",
                    trace.status.value,
                    why_not_measured=why,
                )
            )
            continue
        diffs = {
            k: {"label": v, "tool": obs.metrics.get(k)}
            for k, v in f.measurements.items()
            if obs.metrics.get(k) != v
        }
        results.append(
            FlowResult(
                f.id,
                f.site,
                f.rule,
                tier,
                f.present,
                obs.flagged,
                _outcome(f.present, obs.flagged),
                trace.status.value,
                diffs,
            )
        )

    def rates(rows: list[FlowResult]) -> dict[str, Any]:
        tp = sum(r.outcome == "TP" for r in rows)
        fp = sum(r.outcome == "FP" for r in rows)
        fn = sum(r.outcome == "FN" for r in rows)
        return {
            "flows": len(rows),
            "measured": sum(r.outcome != "not_measured" for r in rows),
            "TP": tp,
            "FP": fp,
            "FN": fn,
            "precision": round(tp / (tp + fp), 3) if tp + fp else None,
            "recall": round(tp / (tp + fn), 3) if tp + fn else None,
        }

    tier_a = [r for r in results if r.tier == Tier.A.value]
    headline = rates(tier_a)
    gate = headline["precision"] is not None and headline["precision"] >= PRECISION_TARGET
    return {
        "tier_a": headline,
        "all_tiers": rates(results),
        "gate_passed": gate,
        "not_measured": {
            r.flow: r.why_not_measured for r in results if r.outcome == "not_measured"
        },
        "measurement_disagreements": {
            r.flow: r.measurement_diffs for r in results if r.measurement_diffs
        },
        "flows": [asdict(r) for r in results],
    }
