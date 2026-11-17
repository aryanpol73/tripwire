"""Per-step capture: screenshot, accessibility snapshot, scrubbed DOM snapshot, measurements."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from playwright.sync_api import Page

from tripwire.browser.ui_inventory import PageObservation, collect_page
from tripwire.schemas.trace import Action, RequestRecord, Step, UiInventory

# A copy of the DOM with secret field values blanked, so the saved snapshot holds no tokens.
_SCRUBBED_DOM_JS = r"""
() => {
  const copy = document.documentElement.cloneNode(true);
  const secret = /pass|token|csrf|xsrf|secret|session|auth|otp|card|cvv|cvc|upi|iban|key/i;
  copy.querySelectorAll("input").forEach((i) => {
    if (i.type === "password" || i.type === "hidden" || secret.test(i.name || "")) {
      i.setAttribute("value", "[REDACTED]");
    }
  });
  return "<!doctype html>\n" + copy.outerHTML;
}
"""


def capture_step(
    page: Page,
    *,
    index: int,
    action: Action,
    url_before: str | None,
    page_load: bool,
    run_dir: Path,
    requests: list[RequestRecord],
) -> tuple[Step, PageObservation]:
    obs = collect_page(page)
    name = f"{index:03d}"
    paths = {
        "screenshot": f"screens/{name}.png",
        "a11y_snapshot": f"a11y/{name}.yaml",
        "dom_snapshot": f"dom/{name}.html",
    }
    for rel in paths.values():
        (run_dir / rel).parent.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=run_dir / paths["screenshot"])
    (run_dir / paths["a11y_snapshot"]).write_text(
        page.locator("body").aria_snapshot(), encoding="utf-8"
    )
    (run_dir / paths["dom_snapshot"]).write_text(page.evaluate(_SCRUBBED_DOM_JS), encoding="utf-8")
    step = Step(
        index=index,
        timestamp=datetime.now(UTC),
        action=action,
        url_before=url_before,
        url_after=page.url,
        page_load=page_load,
        requests=requests,
        ui=UiInventory(elements=obs.elements),
        overlays=obs.overlays,
        forms=obs.forms,
        timers=obs.timers,
        **paths,
    )
    return step, obs
