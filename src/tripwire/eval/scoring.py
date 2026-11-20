"""Score one decision per (scenario, rule), keeping heuristic results separate."""

from collections import defaultdict
from dataclasses import dataclass, field

from tripwire.detectors.rules import RULES


@dataclass
class Counts:
    tp: int = 0
    fp: int = 0
    fn: int = 0
    tn: int = 0

    def add(self, expected: bool, actual: bool):
        if expected:
            if actual:
                self.tp += 1
            else:
                self.fn += 1
        elif actual:
            self.fp += 1
        else:
            self.tn += 1

    def rates(self):
        return {
            "precision": self.tp / (self.tp + self.fp) if self.tp + self.fp else None,
            "recall": self.tp / (self.tp + self.fn) if self.tp + self.fn else None,
        }


@dataclass
class Score:
    groups: dict[str, Counts] = field(default_factory=lambda: defaultdict(Counts))
    errors: list[str] = field(default_factory=list)
    decoy_false_positives: list[str] = field(default_factory=list)
    clean_decoy_checks: int = 0
    differences: list[dict] = field(default_factory=list)
    measurement_counts: dict[str, int] = field(default_factory=lambda: defaultdict(int))

    def record(self, scenario, skin, site, expected, observations):
        labels = {e.rule: e for e in expected}
        for rule_id in sorted(set(labels) | {r for r, o in observations.items() if o.flagged}):
            rule = RULES[rule_id]
            label = labels.get(rule_id)
            wanted = bool(label and label.should_fire)
            obs = observations.get(rule_id)
            actual = bool(obs and obs.flagged)
            for group in (
                "overall",
                f"detector/{rule_id}",
                f"family/{rule.family}",
                f"skin/{skin}",
                f"site/{site}",
            ):
                self.groups[f"{rule.tier}/{group}"].add(wanted, actual)
            if wanted != actual:
                self.errors.append(f"{scenario} {rule_id} {'miss' if wanted else 'false positive'}")
            for key, value in label.metrics.items() if label else []:
                self.measurement_counts[rule_id] += 1
                present = obs is not None and key in obs.metrics
                measured = obs.metrics[key] if present else None
                delta = None
                if present and type(value) in (int, float) and type(measured) in (int, float):
                    delta = measured - value
                    equal = abs(delta) <= (0.100000001 if "contrast" in key else 0)
                else:
                    equal = present and type(value) is type(measured) and value == measured
                if not equal:
                    self.differences.append(
                        dict(
                            scenario=scenario,
                            rule=rule_id,
                            metric=key,
                            expected=value,
                            observed=measured,
                            missing=not present,
                            delta=delta,
                        )
                    )

    def check_decoys(self, case, guards, expected, observations):
        positives = {e.rule for e in expected if e.should_fire}
        for decoy, rules in guards.items():
            for rule in rules:
                # A planted positive may coexist with a decoy of the same rule.
                # Those require evidence-level fixture tests, not scenario-level scoring.
                if rule in positives:
                    continue
                self.clean_decoy_checks += 1
                if rule in observations and observations[rule].flagged:
                    self.decoy_false_positives.append(f"{case} {decoy}: {rule}")

    def report(self):
        return dict(
            groups={k: vars(v) | v.rates() for k, v in sorted(self.groups.items())},
            classification_errors=self.errors,
            decoy_false_positives=self.decoy_false_positives,
            negative_decoy_checks=self.clean_decoy_checks,
            measurement_errors=self.differences,
            measurements_compared=dict(self.measurement_counts),
        )


def incomplete_reason(trace):
    """An early walker return can carry completed status without reaching the mission goal."""
    if trace.status != "completed":
        return f"trace status {trace.status}"
    if trace.mission == "first_visit":
        if not any(s.action.kind == "scroll" for s in trace.steps):
            return "first visit stopped before scrolling"
        return None
    if trace.mission == "reach_payment":
        if not any(p.goal == "reach_payment" and p.completed for p in trace.paths):
            return "payment boundary was not reached"
        return None
    if not any(p.goal == "sign_up" and p.completed for p in trace.paths):
        return "join path was not completed"
    if not any(
        p.goal in {"cancel", "unsubscribe", "delete_account"}
        and (p.completed or p.exit_channel != "web")
        for p in trace.paths
    ):
        return "leave path did not reach an observed exit"
    return None
