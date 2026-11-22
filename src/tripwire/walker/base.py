"""What every explorer shares: one way to run a mission and one Trace at the end.

`ScriptedWalker` (Phase 3) and `LlmWalker` (Phase 6) differ only in how they choose the next
action (`_explore`). Opening the session, the safety gate, budgets, per-step capture,
hand-off detection, commerce recording and Trace assembly live here, so both produce the
same Trace and neither can skip the gate.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol
from urllib.parse import urlsplit

from playwright.sync_api import Browser

from tripwire.browser.safety_gate import (
    LOCAL_HOSTS,
    BudgetExceeded,
    GateConfig,
    SafetyBlocked,
)
from tripwire.browser.session import BrowserSession, SessionConfig
from tripwire.mission import Mission
from tripwire.schemas.trace import (
    ActionKind,
    Budgets,
    Intent,
    MeasuredPath,
    Mode,
    Note,
    NoteKind,
    OverlayPurpose,
    PathGoal,
    RunStatus,
    SiteType,
    Step,
    Target,
    Trace,
    UiElement,
)
from tripwire.walker import vocab
from tripwire.walker.commerce import CommerceRecorder
from tripwire.walker.handoff import detect_handoff

CLICKS = {ActionKind.CLICK, ActionKind.REJECT_CONSENT}


class HandedOff(Exception):
    pass


class RealSitesDisabled(Exception):
    pass


@dataclass
class RunRequest:
    start_url: str
    mission: Mission
    run_dir: Path
    run_id: str
    site_type: SiteType = SiteType.OTHER
    scenario_id: str | None = None
    min_action_interval_s: float = 0.0
    headless: bool = True
    browser: Browser | None = None
    log: Callable[[str], None] = field(default=lambda m: print(m, file=sys.stderr))
    # Red-team runs apply the real-site action rules (never pay, never accept, ...) on the
    # local sandbox, so a hostile page can be shown to fail against the same gate.
    enforce_real_action_rules: bool = False
    # Ground truth for completion on sites outside the sandbox grid: the site's own wording
    # for "you have left" and for its pay control. None means the generic vocabulary.
    left_text: re.Pattern[str] | None = None
    pay_control: re.Pattern[str] | None = None


class Explorer(Protocol):
    """Runs one mission on one site and returns its Trace."""

    def run(self) -> Trace: ...


class ExplorerBase:
    mode = Mode.SANDBOX

    def __init__(self, request: RunRequest) -> None:
        self.req = request
        self.paths: list[MeasuredPath] = []
        self.intents: list[Intent] = []
        self.notes: list[Note] = []
        self.commerce = CommerceRecorder()
        self.status = RunStatus.COMPLETED

    # --- hooks ----------------------------------------------------------------------

    def _limits(self) -> Budgets:
        return self.req.mission.budgets

    def _explore(self) -> None:
        raise NotImplementedError

    # --- running --------------------------------------------------------------------

    def run(self) -> Trace:
        req = self.req
        host = urlsplit(req.start_url).hostname or ""
        if host not in LOCAL_HOSTS:
            raise RealSitesDisabled(
                "Real sites are disabled until the Phase 7 pre-flight checklist is confirmed."
            )
        limits = self._limits()
        gate = GateConfig(
            mode=Mode.SANDBOX,
            allowed_hosts=(host,),
            limits=limits,
            min_action_interval_s=req.min_action_interval_s,
            enforce_real_action_rules=req.enforce_real_action_rules,
        )
        started = datetime.now(UTC)
        config = SessionConfig(gate=gate, run_dir=req.run_dir, headless=req.headless)
        with BrowserSession(config, browser=req.browser) as session:
            self.s = session
            try:
                self._explore()
            except BudgetExceeded as err:
                self.status = RunStatus.BUDGET_EXCEEDED
                self._note(NoteKind.BUDGET, str(err))
            except HandedOff:
                self.status = RunStatus.HANDED_OFF
            except SafetyBlocked as err:
                self._note(NoteKind.SAFETY_BLOCK, f"Stopped: {err}")
            steps, used = session.steps, session.budget.used()
            for event in session.gate.events:
                self.notes.append(
                    Note(kind=NoteKind.SAFETY_BLOCK, message=f"{event.reason}: {event.target}")
                )
        if used.exceeds(limits):
            self.status = RunStatus.BUDGET_EXCEEDED
        return Trace(
            run_id=req.run_id,
            site_url=req.start_url,
            site_type=req.site_type,
            mission=req.mission.name,
            mode=self.mode,
            scenario_id=req.scenario_id,
            started_at=started,
            ended_at=datetime.now(UTC),
            status=self.status,
            budget_limits=limits,
            budgets_used=used,
            steps=steps,
            paths=self.paths,
            intents=self.intents,
            commerce=self.commerce.build(),
            notes=self.notes,
        )

    # --- step helpers ---------------------------------------------------------------

    def _note(self, kind: NoteKind, message: str, step: int | None = None) -> None:
        self.notes.append(Note(kind=kind, step_index=step, message=message))

    def _after(self, step: Step) -> Step:
        obs = self.s.last
        assert obs is not None
        self.commerce.observe(step.index, obs)
        text = self.s.page.inner_text("body")
        if step.page_load and vocab.PAGE_INSTRUCTION_TEXT.search(text):
            self._note(
                NoteKind.PAGE_INSTRUCTION,
                "Page text addressed the agent; ignored (page content is data).",
                step.index,
            )
        handoff = detect_handoff(obs, text, [f.url for f in self.s.page.frames])
        if handoff:
            self._note(NoteKind.HANDOFF, f"{handoff.reason}: {handoff.instructions}", step.index)
            self.req.log(f"[tripwire] hand-off needed ({handoff.reason}): {handoff.instructions}")
            raise HandedOff(handoff.reason)
        return step

    def goto(self, url: str) -> Step:
        return self._after(self.s.goto(url))

    def click(self, element: UiElement, kind: ActionKind = ActionKind.CLICK) -> Step:
        target = Target(
            role=element.role,
            accessible_name=element.accessible_name,
            visible_text=element.text or None,
        )
        return self._after(self.s.click(target, kind=kind))

    def type_into(self, element: UiElement, value: str) -> Step:
        target = Target(role=element.role, accessible_name=element.accessible_name)
        return self._after(self.s.type_into(target, value))

    def _record_path(self, name: str, goal: PathGoal, chain: list[int], **extra) -> MeasuredPath:
        steps = [self.s.steps[i] for i in chain]
        counts = {
            "clicks": sum(s.action.kind in CLICKS for s in steps),
            "page_loads": sum(s.page_load for s in steps),
        }
        path = MeasuredPath(name=name, goal=goal, step_indices=chain, **(counts | extra))
        self.paths.append(path)
        return path

    def _consent_overlay(self):
        obs = self.s.last
        assert obs is not None
        return next((o for o in obs.overlays if o.purpose == OverlayPurpose.CONSENT), None)

    def _set_consent_layer(self, index: int, layer: int) -> None:
        """The collector cannot know which banner layer it sees; the walker does."""
        step = self.s.steps[index]
        overlays = [
            o.model_copy(update={"layer": layer}) if o.purpose == OverlayPurpose.CONSENT else o
            for o in step.overlays
        ]
        self.s.steps[index] = step.model_copy(update={"overlays": overlays})
