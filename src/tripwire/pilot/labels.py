"""The owner's hand labels for the pilot, written before any tool run.

`private/pilot/labels.yaml` (git-ignored) lists the sites, by a private alias and URL, and
the flows the owner checked by hand: for one site and mission, whether a rule's pattern is
present, and optionally the numbers seen (e.g. reject_clicks: 3). `tripwire pilot labels`
prints an example.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Self
from urllib.parse import urlsplit

import yaml
from pydantic import Field, HttpUrl, model_validator

from tripwire.detectors.rules import RULES
from tripwire.schemas.common import Model, NonEmptyStr
from tripwire.schemas.trace import MissionName, SiteType

LABELS_FILE = Path("private/pilot/labels.yaml")
RUNS_DIR = Path("private/pilot/runs")


class Site(Model):
    id: NonEmptyStr  # a private alias used in reports, e.g. "news-1"
    url: HttpUrl
    type: SiteType


class Flow(Model):
    id: NonEmptyStr
    site: NonEmptyStr
    mission: MissionName
    rule: NonEmptyStr
    present: bool  # the owner's judgement, made before running the tool
    measurements: dict[str, int | float | bool | str] = Field(default_factory=dict)
    labelled_on: date
    notes: str = ""


class Labels(Model):
    sites: list[Site] = Field(min_length=1)
    flows: list[Flow] = Field(min_length=1)

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        ids = [s.id for s in self.sites]
        if len(set(ids)) != len(ids):
            raise ValueError("site ids must be unique")
        flow_ids = [f.id for f in self.flows]
        if len(set(flow_ids)) != len(flow_ids):
            raise ValueError("flow ids must be unique")
        for f in self.flows:
            if f.site not in ids:
                raise ValueError(f"flow {f.id}: unknown site {f.site!r}")
            if f.rule not in RULES:
                raise ValueError(f"flow {f.id}: unknown rule {f.rule!r}")
        for s in self.sites:
            if urlsplit(str(s.url)).scheme != "https":
                raise ValueError(f"site {s.id}: use the https URL")
        return self

    def site(self, site_id: str) -> Site:
        return next(s for s in self.sites if s.id == site_id)

    def runs(self) -> list[tuple[str, str]]:
        """(site id, mission) pairs to run, in label order, each once."""
        seen: list[tuple[str, str]] = []
        for f in self.flows:
            if (f.site, f.mission) not in seen:
                seen.append((f.site, f.mission))
        return seen


def load_labels(path: Path = LABELS_FILE) -> Labels:
    return Labels.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


EXAMPLE = """\
# Phase 7 hand labels. Write them BEFORE running the tool on a site. Never commit this file.
# Site URLs stay here only; reports and notes use the alias (id).
sites:
  - id: news-1
    url: https://example.org/
    type: news
flows:
  - id: f01
    site: news-1
    mission: first_visit
    rule: consent.click_asymmetry
    present: true              # rejecting took more clicks than accepting
    measurements:
      accept_clicks: 1
      reject_clicks: 3
    labelled_on: 2026-11-30
    notes: reject is behind "Manage options"
  - id: f02
    site: news-1
    mission: first_visit
    rule: consent.preselected
    present: false
    labelled_on: 2026-11-30
"""
