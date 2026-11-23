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
    REAL_SITE_MIN_INTERVAL_S,
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
    # Phase 7. REAL applies every real-site rule (2 s pacing, robots.txt, 30 page loads,
    # never accept, nothing irreversible). On a non-local host it also needs the signed
    # pre-flight. On a local host it is a rehearsal: same rules, no pre-flight.
    mode: Mode = Mode.SANDBOX
    preflight: Path | None = None
    approved_account_flows: bool = False  # ETHICS 10: the owner approved this run


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

    def _check_real_site(self, host: str) -> None:
        """Refuse a real-site run unless every Phase 7 condition holds."""
        from tripwire.pilot.preflight import PREFLIGHT_FILE, PreflightError, load_preflight

        req = self.req
        if req.mode != Mode.REAL:
            raise RealSitesDisabled(
                f"{host} is not a local host. Real sites are Phase 7 only: run them with "
                "`tripwire pilot run` after signing the pre-flight (see docs/PILOT.md)."
            )
        try:
            load_preflight(req.preflight or PREFLIGHT_FILE)
        except PreflightError as err:
            raise RealSitesDisabled(str(err)) from err
        if req.mission.name == "sign_up_and_leave" and not req.approved_account_flows:
            raise RealSitesDisabled(
                "sign_up_and_leave changes accounts: on a real site it needs the owner's "
                "approval for this run (ETHICS 10)."
            )

    def run(self) -> Trace:
        req = self.req
        host = urlsplit(req.start_url).hostname or ""
        real = req.mode == Mode.REAL
        if host not in LOCAL_HOSTS:
            self._check_real_site(host)
        self.mode = req.mode
        limits = self._limits()
        if real:  # ETHICS 5: at most 30 page loads, one action per 2 seconds
            limits = limits.model_copy(update={"page_loads": min(limits.page_loads, 30)})
        gate = GateConfig(
            mode=req.mode,
            allowed_hosts=(host,),
            limits=limits,
            min_action_interval_s=(
                max(req.min_action_interval_s, REAL_SITE_MIN_INTERVAL_S)
                if real
                else req.min_action_interval_s
            ),
            enforce_real_action_rules=req.enforce_real_action_rules,
            approved_account_flows=req.approved_account_flows,
        )
        started = datetime.now(UTC)
        config = SessionConfig(gate=gate, run_dir=req.run_dir, headless=req.headless)
        with BrowserSession(config, browser=req.browser) as session:
            self.s = session
            if real:
                parts = urlsplit(req.start_url)
                session.load_robots(f"{parts.scheme}://{parts.netloc}")
                if host in LOCAL_HOSTS:
                    self._note(NoteKind.INFO, "Rehearsal: real-site rules on a local host.")
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
