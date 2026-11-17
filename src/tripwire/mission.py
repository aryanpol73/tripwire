"""Mission specs: small YAML files in missions/ describing a user journey."""

from __future__ import annotations

from pathlib import Path
from typing import Literal, Self

import yaml
from pydantic import Field, model_validator

from tripwire.detectors.rules import RULES
from tripwire.schemas.common import Model, NonEmptyStr
from tripwire.schemas.trace import Budgets, MissionName

MISSIONS_DIR = Path(__file__).resolve().parents[2] / "missions"


class StopCondition(Model):
    kind: Literal["internal_pages", "left_or_blocked", "before_payment"]
    count: int | None = Field(default=None, ge=1)


class Mission(Model):
    name: MissionName
    goal: NonEmptyStr
    start_path: str = "/"
    budgets: Budgets
    stop: StopCondition
    detectors: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def _known_detectors(self) -> Self:
        unknown = [d for d in self.detectors if d not in RULES]
        if unknown:
            raise ValueError(f"unknown detectors {unknown}")
        return self


def load_mission(name: str, directory: Path = MISSIONS_DIR) -> Mission:
    path = directory / f"{name}.yaml"
    if not path.exists():
        known = sorted(p.stem for p in directory.glob("*.yaml"))
        raise FileNotFoundError(f"no mission {name!r}; known missions: {known}")
    mission = Mission.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    if mission.name != name:
        raise ValueError(f"{path.name} declares name {mission.name!r}")
    return mission
