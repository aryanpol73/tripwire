"""Command-line entry point: `uv run tripwire ...`.

  tripwire audit --scenario <id>            run a sandbox scenario with its mission
  tripwire audit <url> --mission <name>     run a mission on a local (sandbox) URL
  tripwire replay <run_dir>                 re-render a saved trace, no browser needed

Real sites are refused until the Phase 7 checklist is confirmed. argparse is enough here.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from contextlib import nullcontext
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

from tripwire import __version__
from tripwire.mission import load_mission
from tripwire.report.replay import render
from tripwire.schemas.io import read_trace, write_model
from tripwire.schemas.trace import SiteType


def _cmd_audit(args: argparse.Namespace) -> int:
    from tripwire.walker.scripted_walker import RealSitesDisabled, RunRequest, ScriptedWalker

    scenario = None
    if args.scenario:
        from evilweb import scenarios
        from evilweb.server import serve

        scenario = scenarios.get(args.scenario)
        mission_name = args.mission or scenario.mission
        server = serve(scenario.id)
    elif args.url:
        if not args.mission:
            print("--mission is required with a URL", file=sys.stderr)
            return 2
        mission_name, server = args.mission, nullcontext(args.url.rstrip("/"))
    else:
        print("give a URL or --scenario", file=sys.stderr)
        return 2

    mission = load_mission(mission_name)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    label = scenario.id if scenario else urlsplit(args.url).hostname
    run_id = f"{mission.name}-{label}-{stamp}"
    run_dir = Path(args.out) if args.out else Path("runs") / run_id
    with server as base:
        walker = ScriptedWalker(
            RunRequest(
                start_url=base + mission.start_path,
                mission=mission,
                run_dir=run_dir,
                run_id=run_id,
                site_type=scenario.site_type if scenario else SiteType(args.site_type),
                scenario_id=scenario.id if scenario else None,
                min_action_interval_s=args.interval,
                headless=not args.headed,
            )
        )
        try:
            trace = walker.run()
        except RealSitesDisabled as err:
            print(err, file=sys.stderr)
            return 2
    write_model(trace, run_dir / "trace.json")
    from tripwire.detectors.base import finding_set, measurements

    write_model(finding_set(trace, measurements(trace)), run_dir / "findings.json")
    print(render(trace))
    print(f"\nSaved {run_dir / 'trace.json'}")
    return 0


def _cmd_replay(args: argparse.Namespace) -> int:
    path = Path(args.run)
    trace = read_trace(path / "trace.json" if path.is_dir() else path)
    print(render(trace))
    return 0


def _cmd_eval(args: argparse.Namespace) -> int:
    if args.holdout:
        from tripwire.eval.holdout import evaluate_holdout

        return evaluate_holdout(Path(args.holdout), args.chromium_executable)

    from tripwire.eval.runner import evaluate

    return evaluate(args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tripwire",
        description="Audit a website for dark patterns and record reproducible evidence.",
    )
    parser.add_argument("--version", action="version", version=f"tripwire {__version__}")
    sub = parser.add_subparsers(dest="command")

    audit = sub.add_parser("audit", help="run a mission and save a trace")
    audit.add_argument("url", nargs="?", help="start URL (sandbox hosts only until Phase 7)")
    audit.add_argument("--scenario", help="an Evil Web scenario id (see: uv run evilweb list)")
    audit.add_argument("--mission", help="first_visit, sign_up_and_leave or reach_payment")
    audit.add_argument("--out", help="run folder (default: runs/<run id>)")
    audit.add_argument("--interval", type=float, default=0.0, help="seconds between actions")
    audit.add_argument("--headed", action="store_true", help="show the browser window")
    audit.add_argument("--site-type", default="other", choices=[s.value for s in SiteType])
    audit.set_defaults(func=_cmd_audit)

    evaluation = sub.add_parser("eval", help="score all 36 labeled sandbox scenarios")
    evaluation.add_argument("--chromium-executable", help="use a local Chromium installation")
    evaluation.add_argument(
        "--repeat",
        type=int,
        choices=(1, 3),
        default=1,
        help="compare findings across independent runs (1 or 3)",
    )
    evaluation.add_argument(
        "--holdout",
        metavar="MANIFEST",
        help="score independent labeled sandbox traces instead of the grid",
    )
    evaluation.add_argument(
        "--jobs",
        type=int,
        choices=range(1, 5),
        default=1,
        help="number of independent grid scenarios to walk concurrently",
    )
    evaluation.set_defaults(func=_cmd_eval)

    replay = sub.add_parser("replay", help="re-render a saved trace without a browser")
    replay.add_argument("run", help="a run folder or a trace.json file")
    replay.set_defaults(func=_cmd_replay)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
