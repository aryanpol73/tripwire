"""Run every labelled (site, mission) once, under the real-site rules.

Each run gets its own folder in `private/pilot/runs/<site>--<mission>/` with the trace,
findings and report. Nothing here is committed: real-site traces stay on the owner's
machine (ETHICS, data handling).
"""

from __future__ import annotations

import sys
from pathlib import Path

from tripwire.pilot.labels import RUNS_DIR, Labels
from tripwire.pilot.score import run_dir
from tripwire.schemas.trace import Mode


def run_pilot(
    labels: Labels,
    *,
    walker: str = "scripted",
    runs: Path = RUNS_DIR,
    approve_account_flows: bool = False,
    only: str | None = None,
    headed: bool = False,
) -> int:
    from tripwire.detectors.base import finding_set, measurements
    from tripwire.mission import load_mission
    from tripwire.report.builder import build_report
    from tripwire.schemas.io import write_model
    from tripwire.walker.base import RealSitesDisabled, RunRequest
    from tripwire.walker.scripted_walker import ScriptedWalker

    source = None
    if walker == "llm":
        from tripwire.cli import load_dotenv
        from tripwire.llm.client import model_source

        load_dotenv()
        source = model_source()

    failures = 0
    for site_id, mission_name in labels.runs():
        if only and only not in (site_id, f"{site_id}--{mission_name}"):
            continue
        site = labels.site(site_id)
        out = run_dir(runs, site_id, mission_name)
        request = RunRequest(
            start_url=str(site.url),
            mission=load_mission(mission_name),
            run_dir=out,
            run_id=f"{site_id}--{mission_name}",
            site_type=site.type,
            mode=Mode.REAL,
            approved_account_flows=approve_account_flows,
            headless=not headed,
        )
        if source is not None:
            from tripwire.llm.client import RecordingSource
            from tripwire.llm.walker import LlmWalker, cap_from_env

            explorer = LlmWalker(
                request, RecordingSource(source, out / "llm_decisions.jsonl"), cap_from_env()
            )
        else:
            explorer = ScriptedWalker(request)
        try:
            trace = explorer.run()
        except RealSitesDisabled as err:
            print(f"refused: {err}", file=sys.stderr)
            return 2
        except Exception as err:  # record and continue: one site must not stop the pilot
            failures += 1
            print(f"{site_id}--{mission_name}: error {type(err).__name__}", file=sys.stderr)
            continue
        write_model(trace, out / "trace.json")
        write_model(finding_set(trace, measurements(trace)), out / "findings.json")
        build_report(out)
        print(f"{site_id}--{mission_name}: {trace.status.value}, {len(trace.steps)} steps")
    return 1 if failures else 0
