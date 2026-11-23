"""The Phase 7 pre-flight: real sites stay off until the owner has signed this checklist.

The file lives in `private/pilot/preflight.yaml` (git-ignored). The owner fills it in by
hand; the tool never writes it. Every item must be `true`, and the file must name the owner
and a date. `tripwire pilot preflight` prints a template.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import yaml
from pydantic import ValidationError

from tripwire.schemas.common import Model, NonEmptyStr

PREFLIGHT_FILE = Path("private/pilot/preflight.yaml")

# Each item quotes the rule it confirms. Keep them short: the owner reads every one.
CHECKS: dict[str, str] = {
    "phase4_targets_met": "Phase 4 detector targets hold on the sandbox and the hold-out.",
    "phase5_report_verified": "Two people verified report findings in under 30 s each.",
    "phase6_gate_passed": "Phase 6: >= 85% completion and 0 red-team violations, live.",
    "sites_chosen_privately": "I chose the 8-10 sites myself; the list stays private.",
    "flows_labelled_before_running": "I labelled every flow before running the tool on it.",
    "public_pages_only": "Only public pages without login (ETHICS 5).",
    "never_accept_never_pay": "The tool never accepts, pays or confirms (ETHICS 1, 6).",
    "findings_stay_private": "Findings on named sites stay private; disclosure first (ETHICS).",
    "throwaway_profile": "Runs use a fresh browser profile with no personal logins.",
}


class PreflightError(Exception):
    pass


class Preflight(Model):
    owner: NonEmptyStr
    signed_on: date
    checks: dict[str, bool]


def template() -> str:
    lines = [
        "# Phase 7 pre-flight. Fill in by hand; every item must be true. Never commit this file.",
        "owner: ''",
        "signed_on: YYYY-MM-DD",
        "checks:",
    ]
    lines += [f"  {key}: false  # {text}" for key, text in CHECKS.items()]
    return "\n".join(lines) + "\n"


def load_preflight(path: Path = PREFLIGHT_FILE) -> Preflight:
    if not path.is_file():
        raise PreflightError(
            f"no pre-flight file at {path}. Run `tripwire pilot preflight` for a template, "
            "fill it in yourself, and keep it out of git."
        )
    try:
        pre = Preflight.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    except (ValidationError, yaml.YAMLError) as err:
        raise PreflightError(f"{path} is not a valid pre-flight file: {err}") from err
    missing = [key for key in CHECKS if pre.checks.get(key) is not True]
    if missing:
        raise PreflightError(
            "the pre-flight is not complete; these items are not true:\n"
            + "\n".join(f"  - {key}: {CHECKS[key]}" for key in missing)
        )
    if pre.signed_on > date.today():
        raise PreflightError("the pre-flight is dated in the future")
    return pre
