"""The scripted walker: runs a mission on a site and returns a Trace.

It locates controls by role and visible words (walker/vocab.py), never by CSS selectors, so
the same code works across all four sandbox skins. Every action goes through the Phase 2
BrowserSession, so the safety gate, budgets and capture apply to each step.

Paths record the *cheapest chain* found: if the walker explores a link that leads nowhere,
it goes back, and those detour steps stay in the trace but not in the path.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
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
    ControlPurpose,
    Intent,
    IntentGoal,
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
TEXT_INPUTS = {"text", "email", "tel", "number", "search", "url", "textarea"}


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


class ScriptedWalker:
    def __init__(self, request: RunRequest) -> None:
        self.req = request
        self.paths: list[MeasuredPath] = []
        self.intents: list[Intent] = []
        self.notes: list[Note] = []
        self.commerce = CommerceRecorder()
        self.status = RunStatus.COMPLETED

    # --- running --------------------------------------------------------------------

    def run(self) -> Trace:
        req = self.req
        host = urlsplit(req.start_url).hostname or ""
        if host not in LOCAL_HOSTS:
            raise RealSitesDisabled(
                "Real sites are disabled until the Phase 7 pre-flight checklist is confirmed."
            )
        gate = GateConfig(
            mode=Mode.SANDBOX,
            allowed_hosts=(host,),
            limits=req.mission.budgets,
            min_action_interval_s=req.min_action_interval_s,
        )
        started = datetime.now(UTC)
        config = SessionConfig(gate=gate, run_dir=req.run_dir, headless=req.headless)
        with BrowserSession(config, browser=req.browser) as session:
            self.s = session
            try:
                getattr(self, f"_mission_{req.mission.name}")()
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
        if used.exceeds(req.mission.budgets):
            self.status = RunStatus.BUDGET_EXCEEDED
        return Trace(
            run_id=req.run_id,
            site_url=req.start_url,
            site_type=req.site_type,
            mission=req.mission.name,
            mode=Mode.SANDBOX,
            scenario_id=req.scenario_id,
            started_at=started,
            ended_at=datetime.now(UTC),
            status=self.status,
            budget_limits=req.mission.budgets,
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

    def find(self, pattern, roles=("link", "button"), exclude=None) -> list[UiElement]:
        """Visible controls whose name matches, in document order."""
        obs = self.s.last
        assert obs is not None
        found = []
        for e in obs.elements:
            label = e.accessible_name or e.text
            if e.role not in roles or not e.style.visible or e.disabled or not label:
                continue
            if pattern.search(label) and not (exclude and exclude.search(label)):
                found.append(e)
        return found

    def _link_named(self, name: str) -> UiElement:
        return next(
            e for e in self.find(vocab.words(".+"), roles=("link",)) if e.accessible_name == name
        )

    def _first_match(self, patterns) -> UiElement | None:
        """The first visible control matching the highest-priority pattern."""
        for pattern in patterns:
            found = self.find(pattern, exclude=vocab.STAY)
            if found:
                return found[0]
        return None

    def _record_path(self, name: str, goal: PathGoal, chain: list[int], **extra) -> MeasuredPath:
        steps = [self.s.steps[i] for i in chain]
        counts = {
            "clicks": sum(s.action.kind in CLICKS for s in steps),
            "page_loads": sum(s.page_load for s in steps),
        }
        path = MeasuredPath(name=name, goal=goal, step_indices=chain, **(counts | extra))
        self.paths.append(path)
        return path

    def _internal_links(self, exclude) -> list[tuple[str, str]]:
        """(accessible name, path) of visible same-site links, in document order."""
        visible = {e.accessible_name for e in self.find(vocab.words(".+"), roles=("link",))}
        pairs = self.s.page.evaluate(
            "() => [...document.querySelectorAll('a[href]')].map(a => [a.innerText.trim(), a.href])"
        )
        host = urlsplit(self.s.page.url).netloc
        links = []
        for name, href in pairs:
            parts = urlsplit(href)
            if parts.netloc == host and name in visible and not exclude.search(name):
                links.append((name, parts.path))
        return links

    def _fill_and_submit(self, chain: list[int]) -> bool:
        """Fill required (or email) text fields of the first such form with test data, keep
        every default choice, and submit it. Returns False if there is no such form."""
        obs = self.s.last
        assert obs is not None
        for form in obs.forms:
            fields = [
                f
                for f in form.fields
                if f.type in TEXT_INPUTS
                and not f.hidden
                and not f.off_screen
                and f.element_id
                and (f.required or f.type == "email")
            ]
            if not fields or not form.submit_element_id:
                continue
            for f in fields:
                element = obs.element(f.element_id)  # type: ignore[arg-type]
                chain.append(self.type_into(element, vocab.test_value(f"{f.name} {f.label}")).index)
            chain.append(self.click(obs.element(form.submit_element_id)).index)
            return True
        return False

    def _clear_way(self) -> None:
        """Close blocking pop-ups that are not part of the mission (e.g. a newsletter modal on
        an article). Not counted in any path; the pop-up itself stays in the trace."""
        for _ in range(3):
            obs = self.s.last
            assert obs is not None
            blocking = [
                o
                for o in obs.overlays
                if o.blocks_interaction and o.purpose != OverlayPurpose.CONSENT
            ]
            if not blocking:
                return
            close = [
                c
                for c in blocking[0].controls
                if c.purpose in (ControlPurpose.CLOSE, ControlPurpose.REJECT)
            ]
            if not close:
                return
            self.click(obs.element(close[0].element_id))

    # --- consent --------------------------------------------------------------------

    def _consent_overlay(self):
        obs = self.s.last
        assert obs is not None
        return next((o for o in obs.overlays if o.purpose == OverlayPurpose.CONSENT), None)

    def _handle_consent(self) -> None:
        overlay = self._consent_overlay()
        if overlay is None:
            return
        banner_step = len(self.s.steps) - 1
        if any(c.purpose == ControlPurpose.ACCEPT for c in overlay.controls):
            # Rule 6: the accept path is measured from the page, never taken.
            # One click on the layer-1 accept control, no page load: read off the page.
            self._record_path(
                "accept_consent",
                PathGoal.ACCEPT_CONSENT,
                [banner_step],
                executed=False,
                clicks=1,
                page_loads=0,
            )
        chain: list[int] = []
        layer, done = 1, False
        for _ in range(4):
            overlay = self._consent_overlay()
            if overlay is None:
                break
            by_purpose: dict[ControlPurpose, str] = {}
            for c in overlay.controls:
                by_purpose.setdefault(c.purpose, c.element_id)
            obs = self.s.last
            assert obs is not None
            if ControlPurpose.REJECT in by_purpose:
                element = obs.element(by_purpose[ControlPurpose.REJECT])
                chain.append(self.click(element, ActionKind.REJECT_CONSENT).index)
                done = True
                break
            if ControlPurpose.SETTINGS not in by_purpose:
                break
            step = self.click(obs.element(by_purpose[ControlPurpose.SETTINGS]))
            chain.append(step.index)
            layer += 1
            self._set_consent_layer(step.index, layer)
        self._record_path("reject_consent", PathGoal.REJECT_CONSENT, chain, completed=done)
        self.intents.append(
            Intent(
                goal=IntentGoal.REJECT_CONSENT,
                success=done,
                cheapest_path="reject_consent" if done else None,
            )
        )
        if not done:
            self._note(NoteKind.INFO, "No way to reject consent was found.", banner_step)

    def _set_consent_layer(self, index: int, layer: int) -> None:
        """The collector cannot know which banner layer it sees; the walker does."""
        step = self.s.steps[index]
        overlays = [
            o.model_copy(update={"layer": layer}) if o.purpose == OverlayPurpose.CONSENT else o
            for o in step.overlays
        ]
        self.s.steps[index] = step.model_copy(update={"overlays": overlays})

    # --- missions -------------------------------------------------------------------

    def _mission_first_visit(self) -> None:
        start = self.goto(self.req.start_url)
        self._handle_consent()
        self._after(self.s.scroll())
        visited = {urlsplit(start.url_after).path}
        avoid = vocab.words(
            *(p.pattern for p in (vocab.LEAVE_ENTRY, vocab.PAY, vocab.SUBSCRIBE, vocab.STAY))
        )
        count = self.req.mission.stop.count or 3
        for _ in range(count):
            self._clear_way()
            links = [(n, p) for n, p in self._internal_links(avoid) if p not in visited]
            if not links:
                break
            name, path = links[0]
            visited.add(path)
            self.click(self._link_named(name))

    def _mission_sign_up_and_leave(self) -> None:
        self.goto(self.req.start_url)
        self._handle_consent()
        pricing = self.find(vocab.PRICING, roles=("link",))
        if pricing:
            self.click(pricing[0])  # the offer page: where the advertised price is shown
        if self.find(vocab.START_TRIAL):
            joined = self._sign_up_trial()
        else:
            joined = self._sign_up_newsletter()
        if joined:
            self._leave()

    def _sign_up_trial(self) -> bool:
        self.commerce.plan_intent = True
        chain = [self.click(self.find(vocab.START_TRIAL)[0]).index]
        if not self._fill_and_submit(chain):
            self._note(NoteKind.INFO, "No sign-up form was found.")
            return False
        for _ in range(3):
            confirm = self.find(vocab.CONFIRM_TRIAL, roles=("button",))
            if not confirm:
                break
            chain.append(self.click(confirm[0]).index)
        self._record_path("sign_up", PathGoal.SIGN_UP, chain)
        return True

    def _newsletter_overlay(self):
        obs = self.s.last
        assert obs is not None
        return next((o for o in obs.overlays if o.purpose == OverlayPurpose.NEWSLETTER), None)

    def _sign_up_newsletter(self) -> bool:
        avoid = vocab.words(*(p.pattern for p in (vocab.LEAVE_ENTRY, vocab.PAY, vocab.STAY)))
        visited = {urlsplit(self.s.page.url).path}
        for _ in range(3):
            if self._newsletter_overlay():
                break
            links = [(n, p) for n, p in self._internal_links(avoid) if p not in visited]
            if not links:
                break
            name, path = links[0]
            visited.add(path)
            self.click(self._link_named(name))
        overlay = self._newsletter_overlay()
        if overlay is None:
            self._note(NoteKind.INFO, "No sign-up or newsletter offer was found.")
            return False
        obs = self.s.last
        assert obs is not None
        controls = [obs.element(c.element_id) for c in overlay.controls]
        chain: list[int] = []
        for e in controls:
            if e.role == "textbox":
                value = vocab.test_value(e.accessible_name or "email")
                chain.append(self.type_into(e, value).index)
        subscribe = [e for e in controls if vocab.SUBSCRIBE.search(e.accessible_name or e.text)]
        if not subscribe:
            return False
        chain.append(self.click(subscribe[0]).index)
        self._record_path("sign_up", PathGoal.SIGN_UP, chain)
        return True

    def _search_leave(self, depth: int, tried: set[str]) -> list[int] | None:
        """Depth-first search for a leave control, backtracking out of dead ends."""
        if self.find(vocab.LEAVE_ENTRY, exclude=vocab.STAY):
            return []
        if depth == 0:
            return None
        for pattern in vocab.LEAVE_NAVIGATION:
            for e in self.find(pattern, exclude=vocab.STAY):
                label = e.accessible_name or e.text
                if label in tried:
                    continue
                tried.add(label)
                back_to = self.s.page.url
                step = self.click(e)
                rest = self._search_leave(depth - 1, tried)
                if rest is not None:
                    return [step.index, *rest]
                self.goto(back_to)  # detour: kept in the trace, not in the path
        return None

    def _leave(self) -> None:
        self._clear_way()
        route = self._search_leave(3, set())
        if route is None:
            self.goto(self.req.start_url)
            route = self._search_leave(3, set())
        if route is None:
            self._note(NoteKind.INFO, "No way to cancel, unsubscribe or delete was found.")
            self.intents.append(Intent(goal=IntentGoal.CANCEL, success=False))
            return
        entry = self.find(vocab.LEAVE_ENTRY, exclude=vocab.STAY)[0]
        entry_label = entry.accessible_name or entry.text
        newsletter = vocab.words("unsubscribe", "newsletter", r"email\s+preferences", r"opt\s+out")
        goal = IntentGoal.UNSUBSCRIBE if newsletter.search(entry_label) else IntentGoal.CANCEL
        chain = [*route, self.click(entry).index]
        completed, channel = False, "web"
        for _ in range(12):
            text = self.s.page.inner_text("body")
            if vocab.LEFT_TEXT.search(text):
                completed = True
                break
            if vocab.PHONE_ONLY_TEXT.search(text):
                channel = "phone"
                break
            if vocab.EMAIL_ONLY_TEXT.search(text):
                channel = "email"
                break
            obs = self.s.last
            assert obs is not None
            required = [
                obs.element(f.element_id)
                for form in obs.forms
                for f in form.fields
                if f.type == "checkbox" and f.required and not f.prechecked and f.element_id
            ]
            if required:
                chain.append(self.click(required[0]).index)
                continue
            progress = self._first_match(vocab.LEAVE_PROGRESS)
            if progress is None:
                break
            chain.append(self.click(progress).index)
        path = self._record_path(
            goal.value, PathGoal(goal.value), chain, completed=completed, exit_channel=channel
        )
        self.intents.append(
            Intent(goal=goal, success=completed and channel == "web", cheapest_path=path.name)
        )

    def _mission_reach_payment(self) -> None:
        self.goto(self.req.start_url)
        self._handle_consent()
        obs = self.s.last
        assert obs is not None
        priced = []
        for e in self.find(vocab.words(".+"), roles=("link",)):
            name = e.accessible_name or ""
            prices = [
                p.parsed.minor
                for p in obs.prices
                if p.parsed and p.parsed.kind == "amount" and name and name in p.row_text
            ]
            if prices:
                priced.append((min(prices), e))
        if not priced:
            self._note(NoteKind.INFO, "No priced item was found on the start page.")
            return
        _, cheapest = min(priced, key=lambda pair: pair[0])
        chain = [self.click(cheapest).index]
        add = self.find(vocab.ADD_TO_CART, roles=("button",))
        if not add:
            self._note(NoteKind.INFO, "No add-to-cart control was found.")
            return
        self.commerce.record_add(cheapest.accessible_name or cheapest.text)
        chain.append(self.click(add[0]).index)
        checkout = self.find(vocab.CHECKOUT, exclude=vocab.PAY)
        if checkout:
            chain.append(self.click(checkout[0]).index)
        for _ in range(3):
            if self.find(vocab.PAY):
                break
            if not self._fill_and_submit(chain):
                break
        reached = bool(self.find(vocab.PAY))
        self._record_path("reach_payment", PathGoal.REACH_PAYMENT, chain, completed=reached)
        if reached:
            self._note(
                NoteKind.INFO, "Stopped on the last page before payment.", len(self.s.steps) - 1
            )
