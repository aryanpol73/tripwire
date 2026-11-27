"""Execute the scripted sandbox and score against its independent on-disk labels."""

import json
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from pathlib import Path
from tempfile import TemporaryDirectory

from playwright.sync_api import sync_playwright

from evilweb import scenarios
from evilweb.ground_truth import GROUND_TRUTH_DIR
from evilweb.server import serve
from tripwire.detectors.base import findings_for, measurements
from tripwire.eval.scoring import Score, incomplete_reason
from tripwire.mission import load_mission
from tripwire.schemas.finding import Family
from tripwire.schemas.ground_truth import GroundTruth
from tripwire.walker.scripted_walker import RunRequest, ScriptedWalker


def grid_expectations(truth: GroundTruth):
    # The committed labels count clicks. The sandbox consent layers change in place.
    # Join/leave actions navigate except for the required acknowledgement checkbox.
    for label in truth.expectations:
        metrics = dict(label.metrics)
        if label.rule == "consent.click_asymmetry":
            metrics.update(accept_page_loads=0, reject_page_loads=0)
        if label.rule == "obstruction.roach_motel":
            acknowledgement = any(d.id == "required_notice_step" for d in truth.decoys)
            metrics.update(
                sign_up_page_loads=metrics["sign_up_clicks"],
                leave_page_loads=metrics["leave_clicks"] - int(acknowledgement),
            )
        yield label.model_copy(update={"metrics": metrics})


def _login_wall(trace) -> bool:
    return trace.status == "handed_off" and any(
        n.kind == "handoff" and n.message.startswith("login") for n in trace.notes
    )


def walk_case(sc, *, repeat, executable):
    failures = []
    observations = {}
    previous = None
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=executable)
            for _ in range(repeat):
                with TemporaryDirectory() as directory, serve(sc.id) as url:
                    trace = ScriptedWalker(
                        RunRequest(
                            start_url=url + "/",
                            mission=load_mission(sc.mission),
                            run_dir=Path(directory),
                            run_id=sc.id,
                            site_type=sc.site_type,
                            scenario_id=sc.id,
                            browser=browser,
                        )
                    ).run()
                reason = incomplete_reason(trace)
                if reason and not (sc.family == Family.NAGGING and _login_wall(trace)):
                    # A nagging scenario that stops at its planted account wall did its job.
                    failures.append(f"{sc.id}: {reason}")
                observations = measurements(trace)
                findings = findings_for(trace, observations)
                # Caller-assigned ports change even when every observation is identical.
                current = [
                    f.model_dump_json().replace(url + "/", "http://sandbox/") for f in findings
                ]
                if previous is not None and current != previous:
                    failures.append(f"{sc.id}: findings differed between runs")
                previous = current
            browser.close()
    except Exception as error:
        failures.append(f"{sc.id}: {type(error).__name__}: {error}")
        observations = {}
    return sc, observations, failures


def evaluate(args):
    score = Score()
    failures = []
    walk = partial(walk_case, repeat=args.repeat, executable=args.chromium_executable)
    module = getattr(args, "module", None)
    cases = scenarios.module_grid(module) if module else scenarios.grid()
    with ThreadPoolExecutor(max_workers=args.jobs) as workers:
        for sc, observations, errors in workers.map(walk, cases):
            failures.extend(errors)
            truth = GroundTruth.model_validate_json(
                (GROUND_TRUTH_DIR / f"{sc.id}.json").read_text()
            )
            score.record(sc.id, sc.skin, sc.site_type, grid_expectations(truth), observations)
            score.check_decoys(
                sc.id,
                {d.id: d.must_not_trigger for d in truth.decoys},
                truth.expectations,
                observations,
            )
    report = score.report()
    report["module"] = module or "v1"
    report["scenario_count"] = len(cases)
    report["runs_per_scenario"] = args.repeat
    report["run_failures"] = failures
    gates = check_targets(report, compare_baseline=not module)
    report["gate_failures"] = gates
    print(json.dumps(report, indent=2))
    return int(bool(failures or gates or score.differences))


def read_baseline():
    return json.loads(Path(__file__).with_name("baseline.json").read_text())


def check_targets(report, compare_baseline: bool = True):
    """The v1 grid is held to CI's baseline; a Phase 9 module has its own groups, so only
    the per-detector targets and the decoy rule apply to it."""
    baseline = read_baseline() if compare_baseline else {}
    failures = []
    for group, reference in baseline.items():
        current = report["groups"].get(group, {})
        for metric, previous in reference.items():
            rate = current.get(metric)
            if rate is None or rate + 0.02 + 1e-12 < previous:
                failures.append(f"{group} {metric} regressed from {previous} to {rate}")
    for group, values in report["groups"].items():
        if not compare_baseline and not (
            values.get("tp", 0) + values.get("fp", 0) + values.get("fn", 0)
        ):
            continue  # a module grid plants nothing for this detector, and it flagged nothing
        if group.startswith("A/detector/"):
            for key, minimum in (("precision", 0.95), ("recall", 0.90)):
                if values[key] is None or values[key] < minimum:
                    failures.append(f"{group} {key} below {minimum}")
    if report["decoy_false_positives"]:
        failures.append("A labeled decoy triggered a guarded rule.")
    return failures
