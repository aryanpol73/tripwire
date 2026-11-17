"""Read and write schema files. Validation happens on both sides, every time."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

from tripwire.schemas.finding import FindingSet
from tripwire.schemas.trace import Trace


def write_model(model: BaseModel, path: Path) -> Path:
    """Validate, then write as pretty JSON with LF line endings.

    Re-validating catches models built with model_construct() or changed in ways that
    skipped validation, so nothing invalid ever reaches disk.
    """
    validated = type(model).model_validate(model.model_dump())
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        fh.write(validated.model_dump_json(indent=2) + "\n")
    return path


def read_trace(path: Path) -> Trace:
    return Trace.model_validate_json(path.read_text(encoding="utf-8"))


def read_findings(path: Path) -> FindingSet:
    return FindingSet.model_validate_json(path.read_text(encoding="utf-8"))
