"""Command-line entry point: `uv run tripwire ...`.

Phase 0 is a stub: only --version. Later phases add `audit`, `replay` and `eval`.
argparse (stdlib) is enough; no CLI framework needed.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from tripwire import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tripwire",
        description="Audit a website for dark patterns and record reproducible evidence.",
    )
    parser.add_argument("--version", action="version", version=f"tripwire {__version__}")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    parser.parse_args(argv)
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
