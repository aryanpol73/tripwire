"""`uv run evilweb list | serve <scenario_id> | ground-truth`."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from evilweb import scenarios
from evilweb.ground_truth import GROUND_TRUTH_DIR, write_all


def _cmd_list(_: argparse.Namespace) -> int:
    print(f"{'scenario id':<34} {'site':<5} mission")
    for s in scenarios.grid():
        print(f"{s.id:<34} {s.site_type.value:<5} {s.mission}")
    print(
        f"\n{len(scenarios.grid())} scenarios. Start one with: uv run evilweb serve <scenario id>"
    )
    return 0


def _cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    from evilweb.app import create_app

    try:
        scenario = scenarios.get(args.scenario_id)
    except KeyError as err:
        print(err.args[0], file=sys.stderr)
        return 2
    print(f"Serving {scenario.id} ({scenario.site_type.value}, mission {scenario.mission})")
    print(f"Open http://127.0.0.1:{args.port}/  (POST /__reset to start over; Ctrl+C to stop)")
    # Bound to localhost only: the sandbox is never reachable from other machines.
    uvicorn.run(create_app(scenario.id), host="127.0.0.1", port=args.port, log_level="warning")
    return 0


def _cmd_ground_truth(args: argparse.Namespace) -> int:
    paths = write_all(args.out)
    print(f"wrote {len(paths)} ground-truth files to {args.out}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(prog="evilweb", description="Evil Web sandbox scenarios.")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="list all scenario ids").set_defaults(func=_cmd_list)
    serve = sub.add_parser("serve", help="serve one scenario on 127.0.0.1")
    serve.add_argument("scenario_id")
    serve.add_argument("--port", type=int, default=8100)
    serve.set_defaults(func=_cmd_serve)
    gt = sub.add_parser("ground-truth", help="regenerate every ground_truth.json")
    gt.add_argument("--out", type=Path, default=GROUND_TRUTH_DIR)
    gt.set_defaults(func=_cmd_ground_truth)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
