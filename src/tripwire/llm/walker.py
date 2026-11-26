"""The LLM walker: runs a mission on a site it was never scripted for.

Each turn: observe the page (compact inventory in an untrusted block), ask the decision
source for one tool call, check that call in code (tools.check), then act through the same
helpers as the scripted walker, so the session's safety gate and budgets apply unchanged.
The model never sees or sets the allowlist, the budgets or the gate.

Paths and intents are built afterwards from the purpose the model tagged on each action;
whether the mission completed is decided by code from the Trace (completion.py).
"""

from __future__ import annotations

import json
import os
from collections import Counter
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from tripwire.browser.safety_gate import BudgetExceeded, SafetyBlocked
from tripwire.llm import tools
from tripwire.llm.client import (
    Decision,
    DecisionSource,
    ReplayExhausted,
    ReplaySource,
    Request,
    worst_case,
)
from tripwire.llm.observe import new_nonce, observe, path_of
from tripwire.llm.prompt import SYSTEM, step_prompt
from tripwire.llm.tools import Purpose, Refused
from tripwire.schemas.trace import (
    ActionKind,
    Budgets,
    ControlPurpose,
    Intent,
    IntentGoal,
    NoteKind,
    PathGoal,
    RunStatus,
)
from tripwire.walker import vocab
from tripwire.walker.base import ExplorerBase, HandedOff, RunRequest

DEFAULT_CAP_MICROS = 500_000  # US$0.50 per audit
WALL_FACTOR = 4  # model calls take seconds; the mission's wall budget assumes a script
MAX_REFUSALS = 6
LOOP_REPEATS = 3
STALL_TURNS = 5  # clicks, scrolls or navigations in a row that change nothing


def page_status(step) -> int | None:
    """The HTTP status of the page a step loaded (its last document request), if any."""
    docs = [r for r in step.requests if r.resource_type == "document" and r.status is not None]
    return docs[-1].status if docs else None


def cap_from_env() -> int:
    value = os.environ.get("TRIPWIRE_MAX_LLM_USD")
    return round(float(value) * 1_000_000) if value else DEFAULT_CAP_MICROS


@dataclass
class CallLog:
    seq: int
    tool: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_micros: int


@dataclass
class LlmRunStats:
    calls: list[CallLog] = field(default_factory=list)
    refusals: int = 0
    gate_blocks: int = 0
    stopped_by: str = ""
    divergences: int = 0

    @property
    def spend_micros(self) -> int:
        return sum(c.cost_micros for c in self.calls)


class LlmWalker(ExplorerBase):
    def __init__(
        self, request: RunRequest, source: DecisionSource, cap_micros: int = DEFAULT_CAP_MICROS
    ) -> None:
        super().__init__(request)
        self.source = source
        self.cap_micros = cap_micros
        self.stats = LlmRunStats()
        self.purpose_of: dict[int, Purpose] = {}
        self.history: list[str] = []
        self.nonce = getattr(source, "nonce", None) or new_nonce()
        if hasattr(source, "start"):
            source.start(self.nonce)
        self._added_item: str | None = None
        self._consent_layer = 1
        self._filled: dict[str, set[str]] = {}  # page path -> text fields typed into
        self._last_text: str | None = None  # page text last shown to the model
        self._tried: dict[str, set[str]] = {}  # page path -> controls that opened nothing
        self._dest: dict[str, str] = {}  # link name -> path it opened (walker-observed)

    def _limits(self) -> Budgets:
        b = self.req.mission.budgets
        return b.model_copy(
            update={
                "llm_spend_usd_micros": self.cap_micros,
                "wall_seconds": b.wall_seconds * WALL_FACTOR,
            }
        )

    # --- the loop -------------------------------------------------------------------

    def _explore(self) -> None:
        try:
            self.goto(self.req.start_url)
            self._measure_accept_path()
            self._loop()
        finally:
            self._build_paths()
            if isinstance(self.source, ReplaySource):
                self.stats.divergences = self.source.divergences
            self._note(NoteKind.INFO, self._summary())
            self._write_call_log()

    def _loop(self) -> None:
        seen: Counter[tuple] = Counter()
        stall, last_sha = 0, None
        limits = self._limits()
        for _ in range(limits.steps * 2):
            self.s.budget.check()  # steps, time, page loads and spend, before every call
            obs = self.s.last
            assert obs is not None
            here = path_of(obs.url)
            text = self.s.page.inner_text("body")
            shown_text = "" if text == self._last_text else text
            self._last_text = text
            page = observe(
                obs,
                shown_text,
                self.nonce,
                here,
                frozenset(self._filled.get(here, ())),
                frozenset(self._tried.get(here, ())),
                frozenset(self._leads_to_visited()),
            )
            request = Request(
                SYSTEM,
                step_prompt(self.req.mission, self.history, page.text, self._pages_opened()),
                tools.TOOLS,
            )
            budget = self.s.budget
            if (
                budget.spend_micros + worst_case(self.source, request)
                > budget.limits.llm_spend_usd_micros
            ):
                self.stats.stopped_by = "spend cap (the next call could exceed it)"
                self._note(
                    NoteKind.BUDGET, "Stopped before a model call that could exceed the spend cap."
                )
                return
            try:
                decision = self.source.decide(request)
            except ReplayExhausted:
                self.stats.stopped_by = "replay ended"
                return
            self._account(decision)
            n = len(self.history) + 1
            if decision.tool == "done":
                unmet = self._unmet_order(decision.input.get("outcome") == "completed")
                if unmet:
                    self.stats.refusals += 1
                    self.history.append(f"{n}. done refused by the walker: {unmet}")
                    if self.stats.refusals > MAX_REFUSALS:
                        self.stats.stopped_by = "too many refused actions"
                        return
                    continue
                self.stats.stopped_by = f"done ({decision.input.get('outcome', '')})"
                return
            if decision.tool == "handoff":
                self.stats.stopped_by = "handoff"
                self.status = RunStatus.HANDED_OFF
                self._note(
                    NoteKind.HANDOFF, f"Model asked for a human: {decision.input.get('reason', '')}"
                )
                return
            if decision.tool == "none":
                self.stats.stopped_by = f"no tool call ({decision.stop_reason or 'text only'})"
                return
            try:
                pay = (
                    (self.req.pay_control or vocab.PAY)
                    if self.req.mission.name == "reach_payment"
                    else None
                )
                checked = tools.check(decision.tool, decision.input, obs, page.shown_ids, pay)
                if checked.purpose == Purpose.LEAVE and (unmet := self._unmet_order(True)):
                    raise Refused(unmet)
            except Refused as err:
                self.stats.refusals += 1
                self.history.append(f"{n}. {decision.tool} refused by the walker: {err}")
                if self.stats.refusals > MAX_REFUSALS:
                    self.stats.stopped_by = "too many refused actions"
                    return
                continue
            key = (
                path_of(obs.url),
                page.controls_sha,
                decision.tool,
                decision.input.get("element_id"),
                decision.input.get("path"),
            )
            seen[key] += 1
            if seen[key] >= LOOP_REPEATS:
                self.stats.stopped_by = "loop detected (same action on the same page state)"
                self._note(NoteKind.INFO, "Stopped: the same action repeated on an unchanged page.")
                return
            self._act(n, checked)
            # Typing is progress even though it leaves the list of controls unchanged.
            sha = (path_of(self.s.last.url), observe(self.s.last, "", self.nonce, "").controls_sha)
            unchanged = sha == last_sha and checked.tool != "type"
            stall = stall + 1 if unchanged else 0
            last_sha = sha
            if stall >= STALL_TURNS:
                self.stats.stopped_by = "no progress (page unchanged for several actions)"
                return
        self.stats.stopped_by = "decision cap"

    def _leads_to_visited(self) -> set[str]:
        """Link names that, when clicked before, opened a page already visited."""
        visited = {path_of(s.url_after).split("?")[0] for s in self.s.steps}
        return {name for name, dest in self._dest.items() if dest in visited}

    def _unmet_order(self, finishing: bool) -> str:
        """sign_up_and_leave joins first, then leaves. Returns why a leave step or a
        completed `done` is out of order, or "" when it is fine. Checked in code, so the
        model cannot skip the sign-up by declaring the mission finished."""
        if self.req.mission.name != "sign_up_and_leave" or not finishing:
            return ""
        if not self._tagged(Purpose.SIGN_UP):
            return (
                "nothing has been joined yet: sign up first (a free trial, or the newsletter if "
                "there is no trial), then look for the way out"
            )
        return ""

    def _pages_opened(self) -> int:
        start = path_of(self.req.start_url).split("?")[0]
        seen = {path_of(s.url_after).split("?")[0] for s in self.s.steps}
        return len(seen - {start})

    def _account(self, d: Decision) -> None:
        self.stats.calls.append(
            CallLog(
                len(self.stats.calls),
                d.tool,
                d.model,
                d.input_tokens,
                d.output_tokens,
                d.cost_micros,
            )
        )
        self.s.budget.add_spend(d.cost_micros)
        if self.s.budget.spend_micros > self.s.budget.limits.llm_spend_usd_micros:
            raise BudgetExceeded(["llm_spend_usd_micros"])

    def _act(self, n: int, c: tools.Checked) -> None:
        before = path_of(self.s.page.url)
        label = f"{n}. {c.tool}"
        if c.element is not None:
            label += f" {c.element.id} ({c.element.role})"
        if c.path:
            label += f" {c.path}"
        label += f" [{c.purpose.value}]"
        try:
            if c.tool == "click":
                assert c.element is not None
                kind = (
                    ActionKind.REJECT_CONSENT
                    if c.control == ControlPurpose.REJECT and c.purpose == Purpose.REJECT_CONSENT
                    else ActionKind.CLICK
                )
                if c.purpose == Purpose.REACH_PAYMENT and c.element.role == "link":
                    self._added_item = c.element.accessible_name or c.element.text
                if c.purpose == Purpose.ADD_TO_CART and self._added_item:
                    self.commerce.record_add(self._added_item)
                if c.purpose == Purpose.SIGN_UP and self.s.last and self.s.last.prices:
                    self.commerce.plan_intent = True
                step = self.click(c.element, kind)
                if c.control == ControlPurpose.SETTINGS:
                    self._consent_layer += 1
                    self._set_consent_layer(step.index, self._consent_layer)
            elif c.tool == "type":
                assert c.element is not None
                value = vocab.test_value(c.element.accessible_name or c.element.text or "")
                step = self.type_into(c.element, value)
                name = c.element.accessible_name or c.element.text or ""
                self._filled.setdefault(path_of(step.url_after), set()).add(name.strip())
            elif c.tool == "scroll":
                step = self._after(self.s.scroll())
            else:  # navigate
                origin = "{0.scheme}://{0.netloc}".format(urlsplit(self.s.page.url))
                step = self.goto(origin + (c.path or "/"))
        except SafetyBlocked as err:
            self.stats.gate_blocks += 1
            self.history.append(f"{label} -> blocked by the safety gate ({err.event.reason})")
            return
        except (BudgetExceeded, HandedOff):
            raise
        except Exception as err:  # the control vanished, timed out, or was covered
            self.history.append(
                f"{label} -> failed ({type(err).__name__}): it could not be used, perhaps "
                "covered by a pop-up; the page has been read again"
            )
            # Re-read the page: what blocked the action (a late pop-up) is usually new.
            self._after(self.s.wait(300))
            return
        self.purpose_of[step.index] = c.purpose
        after = path_of(step.url_after)
        moved = (
            "new page"
            if step.page_load and after != before
            else ("same page, nothing new opened" if after == before else "page changed")
        )
        status = page_status(step)
        if status is not None and status >= 400:
            # Measured by the walker from the page's own response, not read from the page.
            moved = (
                f"page not found (HTTP {status}): this address does not exist here; "
                "use links you can see instead of guessing addresses"
            )
        self.history.append(f"{label} -> {moved}")
        if c.tool == "click" and c.element is not None:
            name = (c.element.accessible_name or c.element.text or "").strip()
            if after == before and not step.page_load:
                self._tried.setdefault(before, set()).add(name)
            elif c.element.role == "link":
                self._dest[name] = after.split("?")[0]

    # --- measurements from the tagged steps -------------------------------------------

    def _measure_accept_path(self) -> None:
        overlay = self._consent_overlay()
        if overlay and any(c.purpose == ControlPurpose.ACCEPT for c in overlay.controls):
            # Rule 6: the accept path is read off the page, never taken.
            self._record_path(
                "accept_consent",
                PathGoal.ACCEPT_CONSENT,
                [len(self.s.steps) - 1],
                executed=False,
                clicks=1,
                page_loads=0,
            )

    def _tagged(self, *purposes: Purpose) -> list[int]:
        return sorted(i for i, p in self.purpose_of.items() if p in purposes)

    def _build_paths(self) -> None:
        if not getattr(self, "s", None) or not self.s.steps:
            return
        steps = self.s.steps
        consent = self._tagged(Purpose.REJECT_CONSENT)
        saw_banner = any(o.purpose.value == "consent" for s in steps for o in s.overlays)
        if saw_banner:
            done = bool(consent) and not any(
                o.purpose.value == "consent" for o in steps[consent[-1]].overlays
            )
            self._record_path("reject_consent", PathGoal.REJECT_CONSENT, consent, completed=done)
            self.intents.append(
                Intent(
                    goal=IntentGoal.REJECT_CONSENT,
                    success=done,
                    cheapest_path="reject_consent" if done else None,
                )
            )
        sign_up = self._tagged(Purpose.SIGN_UP)
        if sign_up:
            self._record_path("sign_up", PathGoal.SIGN_UP, sign_up)
        leave = self._tagged(Purpose.LEAVE)
        if leave:
            text = self.s.page.inner_text("body")
            channel = (
                "phone"
                if vocab.PHONE_ONLY_TEXT.search(text)
                else "email"
                if vocab.EMAIL_ONLY_TEXT.search(text)
                else "web"
            )
            completed = bool((self.req.left_text or vocab.LEFT_TEXT).search(text))
            first = steps[leave[0]].action.target
            entry = (first.accessible_name or first.visible_text or "") if first else ""
            news = vocab.words("unsubscribe", "newsletter", r"email\s+preferences", r"opt\s+out")
            goal = IntentGoal.UNSUBSCRIBE if news.search(entry) else IntentGoal.CANCEL
            path = self._record_path(
                goal.value, PathGoal(goal.value), leave, completed=completed, exit_channel=channel
            )
            self.intents.append(
                Intent(goal=goal, success=completed and channel == "web", cheapest_path=path.name)
            )
        pay = self._tagged(Purpose.REACH_PAYMENT, Purpose.ADD_TO_CART)
        if self.req.mission.name == "reach_payment" and pay:
            # Reached = some page after the first cart step showed a control that would pay.
            marker = self.req.pay_control or vocab.PAY
            reached = any(
                e.style.visible and marker.search(e.accessible_name or e.text or "")
                for s in self.s.steps[pay[0] :]
                for e in s.ui.elements
                if e.role in ("button", "link")
            )
            self._record_path("reach_payment", PathGoal.REACH_PAYMENT, pay, completed=reached)

    def _write_call_log(self) -> None:
        rows = [c.__dict__ for c in self.stats.calls]
        path = self.req.run_dir / "llm_calls.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        total = {
            "calls": len(rows),
            "spend_micros": self.stats.spend_micros,
            "cap_micros": self.cap_micros,
        }
        path.write_text(json.dumps({"total": total, "calls": rows}, indent=2), encoding="utf-8")

    def _summary(self) -> str:
        st = self.stats
        return (
            f"LLM walker: {len(st.calls)} model calls, spend {st.spend_micros} micro-USD, "
            f"{st.refusals} actions refused by the walker, {st.gate_blocks} blocked by the gate, "
            f"stopped by: {st.stopped_by or 'error'}"
            + (f", replay divergences: {st.divergences}" if st.divergences else "")
        )
