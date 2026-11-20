"""Evaluate independently labeled sandbox traces after the detector freeze."""

import json
from contextlib import ExitStack
from pathlib import Path
from tempfile import mkdtemp
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright
from pydantic import Field, model_validator

from tripwire.browser.safety_gate import LOCAL_HOSTS
from tripwire.detectors.base import finding_set, measurements
from tripwire.detectors.rules import RULES
from tripwire.eval.scoring import Score, incomplete_reason
from tripwire.mission import load_mission
from tripwire.schemas.common import Model, NonEmptyStr
from tripwire.schemas.ground_truth import RuleExpectation
from tripwire.schemas.io import read_trace, write_model
from tripwire.schemas.trace import MissionName, SiteType
from tripwire.walker.scripted_walker import RunRequest, ScriptedWalker


class LocalFixture(Model):
    url: NonEmptyStr
    mission: MissionName
    site_type: SiteType

    @model_validator(mode="after")
    def validate_sandbox(self):
        parsed = urlsplit(self.url)
        if parsed.scheme not in {"http", "https"} or parsed.hostname not in LOCAL_HOSTS:
            raise ValueError("Use a loopback HTTP sandbox URL")
        return self


class HoldoutCase(Model):
    id: NonEmptyStr
    skin: NonEmptyStr
    layout: NonEmptyStr
    source: LocalFixture | Path
    decoys: dict[str, list[str]] = Field(default_factory=dict)
    expectations: list[RuleExpectation] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_labels(self):
        seen = set()
        for label in self.expectations:
            rule = RULES.get(label.rule)
            if rule is None or rule.tier != label.tier or rule.family != label.family:
                raise ValueError(f"Invalid rule metadata for {label.rule}")
            if rule.id in seen:
                raise ValueError(f"Repeated expectation for {rule.id}")
            seen.add(rule.id)
        if any(rule not in seen for rules in self.decoys.values() for rule in rules):
            raise ValueError("Decoy rules need matching expectations")
        return self


class Holdout(Model):
    cases: list[HoldoutCase] = Field(min_length=3)

    @model_validator(mode="after")
    def validate_cases(self):
        if len({case.id for case in self.cases}) != len(self.cases):
            raise ValueError("Case IDs must be unique")
        if (
            len({case.skin for case in self.cases}) < 3
            or len({case.layout for case in self.cases}) < 3
        ):
            raise ValueError("Supply at least three unseen skins and three unseen layouts")
        return self


def evaluate_holdout(manifest: Path, executable: str | None = None) -> int:
    suite = Holdout.model_validate_json(manifest.read_text())
    score = Score()
    failures = []
    runs = Path("runs")
    runs.mkdir(exist_ok=True)
    output = Path(mkdtemp(prefix="holdout-", dir=runs))
    with ExitStack() as stack:
        browser = None
        for index, case in enumerate(suite.cases):
            case_dir = output / str(index)
            site = "unknown"
            try:
                if isinstance(case.source, Path):
                    trace = read_trace(manifest.parent / case.source)
                else:
                    if browser is None:
                        pw = stack.enter_context(sync_playwright())
                        browser = pw.chromium.launch(executable_path=executable)
                        stack.callback(browser.close)
                    source = case.source
                    site = source.site_type
                    trace = ScriptedWalker(
                        RunRequest(
                            start_url=source.url,
                            mission=load_mission(source.mission),
                            run_dir=case_dir,
                            run_id=case.id,
                            site_type=site,
                            browser=browser,
                        )
                    ).run()
                    write_model(trace, case_dir / "trace.json")
                site = trace.site_type
                if trace.mode != "sandbox":
                    raise ValueError("Only sandbox traces are eligible")
                if reason := incomplete_reason(trace):
                    failures.append(f"{case.id}: {reason}")
                observations = measurements(trace)
                write_model(finding_set(trace, observations), case_dir / "findings.json")
            except Exception as error:
                failures.append(f"{case.id}: {type(error).__name__}: {error}")
                observations = {}
            score.record(case.id, case.skin, site, case.expectations, observations)
            score.check_decoys(case.id, case.decoys, case.expectations, observations)
    report = score.report()
    overall = report["groups"].get("A/overall", {})
    for metric, target in (("precision", 0.90), ("recall", 0.80)):
        if overall.get(metric) is None or overall[metric] < target:
            failures.append(f"Hold-out Tier A {metric} below {target}")
    report["gate_failures"] = failures
    report["artifacts"] = str(output)
    serialized = json.dumps(report, indent=2)
    (output / "score.json").write_text(serialized + "\n")
    print(serialized)
    return int(bool(failures or score.differences or score.decoy_false_positives))
