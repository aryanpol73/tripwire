"""BrowserSession: one throwaway Playwright context per run, every action through the gate.

Each public action (goto, click, type_into, scroll, wait) checks the gate and the budgets,
waits out the pacing interval, acts, and returns a captured Step. The walker (Phase 3)
decides *what* to do; this class decides *whether* it may and records *what happened*.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType

from playwright.sync_api import Browser, Locator, Page, Request, Route, sync_playwright

from tripwire.browser.capture import capture_step
from tripwire.browser.redact import redact_har, redact_post_data, redact_url
from tripwire.browser.safety_gate import (
    BudgetTracker,
    GateConfig,
    Pacer,
    RobotsPolicy,
    SafetyBlocked,
    SafetyGate,
)
from tripwire.browser.ui_inventory import PageObservation
from tripwire.schemas.trace import Action, ActionKind, RequestRecord, Step, Target

SETTLE_MS = 300  # let scripts react after load before measuring
ACTION_TIMEOUT_MS = 10_000  # fail fast when something covers or hides the target


@dataclass
class SessionConfig:
    gate: GateConfig
    run_dir: Path
    viewport: tuple[int, int] = (1280, 720)
    headless: bool = True
    record_har: bool = True


@dataclass
class _RequestLog:
    records: list[RequestRecord] = field(default_factory=list)
    by_request: dict[int, int] = field(default_factory=dict)  # id(request) -> index
    counter: itertools.count = field(default_factory=lambda: itertools.count(1))

    def take(self) -> list[RequestRecord]:
        taken, self.records, self.by_request = self.records, [], {}
        return taken


class BrowserSession:
    def __init__(self, config: SessionConfig, browser: Browser | None = None) -> None:
        """browser: reuse an already-launched Chromium (each session still gets its own
        fresh context, so nothing is shared between runs)."""
        self.config = config
        self._shared_browser = browser
        self.gate = SafetyGate(config.gate)
        self.budget = BudgetTracker(config.gate.limits)
        self.pacer = Pacer(config.gate.min_action_interval_s)
        self.steps: list[Step] = []
        self.last: PageObservation | None = None
        self._log = _RequestLog()
        self._loads = 0

    # --- lifecycle ------------------------------------------------------------------

    def __enter__(self) -> BrowserSession:
        cfg = self.config
        cfg.run_dir.mkdir(parents=True, exist_ok=True)
        if self._shared_browser is not None:
            self._pw = None
            self._browser = self._shared_browser
        else:
            self._pw = sync_playwright().start()
            self._browser = self._pw.chromium.launch(headless=cfg.headless)
        # new_context() is a fresh, throwaway profile: no cookies, storage or history.
        self._context = self._browser.new_context(
            viewport={"width": cfg.viewport[0], "height": cfg.viewport[1]},
            record_har_path=str(self.har_path) if cfg.record_har else None,
            # Response bodies are not stored: pages contain tokens. The scrubbed DOM
            # snapshot per step is the saved copy of what was on screen.
            record_har_content="omit",
            service_workers="block",  # a service worker could bypass request routing
        )
        self._context.set_default_timeout(ACTION_TIMEOUT_MS)
        self._context.route("**/*", self._route)
        self.page: Page = self._context.new_page()
        self.page.on("request", self._on_request)
        self.page.on("requestfinished", self._on_finished)
        self.page.on("requestfailed", self._on_finished)
        self.page.on("load", lambda _: self._count_load())
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self._context.close()  # writes the HAR
        if self._pw is not None:  # only close what this session launched
            self._browser.close()
            self._pw.stop()
        if self.config.record_har and self.har_path.exists():
            redact_har(self.har_path)

    @property
    def har_path(self) -> Path:
        return self.config.run_dir / "network.har"

    # --- network --------------------------------------------------------------------

    def _route(self, route: Route, request: Request) -> None:
        allowed = self.gate.allows_request(
            request.url, request.method, is_navigation=request.is_navigation_request()
        )
        if allowed:
            route.continue_()
        else:
            self._record(request, blocked=True)
            route.abort("blockedbyclient")

    def _record(self, request: Request, *, blocked: bool = False) -> None:
        key = id(request)
        if key in self._log.by_request:
            return
        self._log.by_request[key] = len(self._log.records)
        self._log.records.append(
            RequestRecord(
                id=f"r{next(self._log.counter)}",
                method=request.method,
                url=redact_url(request.url),
                resource_type=request.resource_type,
                timestamp=datetime.now(UTC),
                post_data_redacted=redact_post_data(
                    request.post_data, request.headers.get("content-type")
                ),
                blocked_by_gate=blocked,
            )
        )

    def _on_request(self, request: Request) -> None:
        self._record(request)

    def _on_finished(self, request: Request) -> None:
        index = self._log.by_request.get(id(request))
        if index is None:
            return
        response = request.response() if request.failure is None else None
        if response is not None:
            record = self._log.records[index]
            self._log.records[index] = record.model_copy(update={"status": response.status})

    def _count_load(self) -> None:
        self._loads += 1
        self.budget.add_page_load()

    # --- robots.txt (real sites only) ----------------------------------------------

    def load_robots(self, origin: str) -> None:
        response = self._context.request.get(origin.rstrip("/") + "/robots.txt")
        text = response.text() if response.ok else ""
        host = origin.split("://", 1)[-1].split("/", 1)[0].split(":", 1)[0]
        self.gate.robots[host] = RobotsPolicy(text)

    # --- actions --------------------------------------------------------------------

    def _before_action(self) -> None:
        self.budget.check()
        self.pacer.wait()

    def _finish(self, action: Action, url_before: str | None, loads_before: int) -> Step:
        self.page.wait_for_load_state("load")
        self.page.wait_for_timeout(SETTLE_MS)
        self.budget.add_step()
        step, obs = capture_step(
            self.page,
            index=len(self.steps),
            action=action,
            url_before=url_before,
            page_load=self._loads > loads_before,
            run_dir=self.config.run_dir,
            requests=self._log.take(),
        )
        self.steps.append(step)
        self.last = obs
        return step

    def goto(self, url: str) -> Step:
        self.gate.check_navigation(url)  # raises SafetyBlocked before any request is made
        self._before_action()
        url_before, loads = (self.page.url if self.steps else None), self._loads
        self.page.goto(url, wait_until="load")
        return self._finish(Action(kind=ActionKind.NAVIGATE, value=url), url_before, loads)

    def locate(self, target: Target) -> Locator:
        """Find an element by role and accessible name; never by a skin-specific selector."""
        if target.role and target.role != "generic" and target.accessible_name:
            return self.page.get_by_role(
                target.role,  # type: ignore[arg-type]
                name=target.accessible_name,
                exact=True,
            ).first
        if target.visible_text:
            return self.page.get_by_text(target.visible_text, exact=True).first
        if target.selector:
            return self.page.locator(target.selector).first
        raise ValueError("a target needs a role and name, visible text, or a selector")

    def _in_consent_overlay(self, locator: Locator) -> bool:
        return bool(
            locator.evaluate(
                "el => !!el.closest('[role=dialog],[aria-modal=true],dialog') && "
                "/cookie|consent|tracking|partners/i.test("
                "(el.closest('[role=dialog],[aria-modal=true],dialog').innerText || ''))"
            )
        )

    def click(self, target: Target, *, kind: ActionKind = ActionKind.CLICK) -> Step:
        label = target.accessible_name or target.visible_text
        role = target.role or ""
        # Judge the words first, before touching the page: a forbidden control is refused
        # even if it does not exist or never becomes clickable.
        if label:
            self.gate.check_click(text=label, role=role)
        locator = self.locate(target)
        label = label or locator.inner_text()
        if self._in_consent_overlay(locator):
            self.gate.check_click(text=label, role=role, in_consent_overlay=True)
        elif not target.accessible_name and not target.visible_text:
            self.gate.check_click(text=label, role=role)
        self._before_action()
        url_before, loads = self.page.url, self._loads
        events_before = len(self.gate.events)
        locator.click()
        self._restore_after_blocked_navigation(url_before, events_before)
        return self._finish(Action(kind=kind, target=target), url_before, loads)

    def _restore_after_blocked_navigation(self, url_before: str, events_before: int) -> None:
        """A click that tried to leave the allowlist was aborted by routing. Chromium then
        shows its own error page; go back to where we were and report the block."""
        self.page.wait_for_load_state("load")
        blocked = [e for e in self.gate.events[events_before:] if e.kind == "navigation_blocked"]
        if blocked and not self.page.url.startswith(("http://", "https://")):
            self.page.goto(url_before, wait_until="load")
            raise SafetyBlocked(blocked[-1])

    def type_into(self, target: Target, value: str) -> Step:
        locator = self.locate(target)
        hint = " ".join(
            filter(
                None,
                [
                    locator.get_attribute("type"),
                    locator.get_attribute("autocomplete"),
                    locator.get_attribute("name"),
                ],
            )
        )
        self.gate.check_type(field_hint=hint)
        self._before_action()
        url_before, loads = self.page.url, self._loads
        locator.fill(value)
        return self._finish(
            Action(kind=ActionKind.TYPE, target=target, value=value), url_before, loads
        )

    def scroll(self, dy: int = 600) -> Step:
        self._before_action()
        url_before, loads = self.page.url, self._loads
        self.page.mouse.wheel(0, dy)
        return self._finish(Action(kind=ActionKind.SCROLL, value=str(dy)), url_before, loads)

    def wait(self, ms: int = 1000) -> Step:
        """A step with no interaction: re-measure the page after some time."""
        self._before_action()
        url_before, loads = self.page.url, self._loads
        self.page.wait_for_timeout(ms)
        return self._finish(Action(kind=ActionKind.WAIT, value=str(ms)), url_before, loads)
