"""What the model sees of a page: the compact UI inventory, never raw HTML.

Everything that comes from the page (titles, names, text) is placed inside one untrusted
block. The block's tag carries a per-run nonce, so page text cannot close it early and
pose as instructions: a forged closing tag would need the nonce, which the page never sees.
URLs are shown as paths only (no host or port), which keeps prompts identical across
sandbox runs and makes recorded decisions replayable.
"""

from __future__ import annotations

import hashlib
import re
import secrets
from dataclasses import dataclass
from urllib.parse import urlsplit

from tripwire.browser.ui_inventory import PageObservation
from tripwire.schemas.trace import ControlPurpose, OverlayPurpose, UiElement

MAX_ELEMENTS = 60
MAX_TEXT_CHARS = 800
MAX_NAME_CHARS = 80
INTERACTIVE_ROLES = {
    "button",
    "link",
    "checkbox",
    "switch",
    "radio",
    "textbox",
    "searchbox",
    "combobox",
    "menuitem",
    "tab",
    "option",
    "spinbutton",
}


def new_nonce() -> str:
    """Random per run, so a page cannot know it in advance."""
    return secrets.token_hex(6)


def path_of(url: str) -> str:
    parts = urlsplit(url)
    return (parts.path or "/") + (f"?{parts.query}" if parts.query else "")


def _clean(text: str, limit: int) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


@dataclass(frozen=True)
class Observation:
    text: str  # the untrusted block, ready for the prompt
    shown_ids: frozenset[str]  # the only element ids the model may act on
    controls_sha: str  # identifies the page state for loop detection and replay


def _where(e: UiElement, overlay_of: dict[str, str]) -> str:
    parts = []
    if e.id in overlay_of:
        parts.append(overlay_of[e.id])
    if e.landmark == "contentinfo":
        parts.append("footer")
    elif e.landmark == "navigation":
        parts.append("nav")
    if not e.in_viewport:
        parts.append("below the fold")
    return ", ".join(parts)


def _state(e: UiElement) -> str:
    if e.checked is not None:
        return "checked" if e.checked else "unchecked"
    if e.selected:
        return "selected"
    return ""


def observe(
    obs: PageObservation,
    page_text: str,
    nonce: str,
    path: str,
    filled: frozenset[str] = frozenset(),
    tried: frozenset[str] = frozenset(),
    seen_links: frozenset[str] = frozenset(),
) -> Observation:
    """`filled`: names of text fields the walker has typed into on this page (walker-written
    state, so the model can tell an empty required field from one already done)."""
    required = {f.element_id for form in obs.forms for f in form.fields if f.required}
    overlay_of: dict[str, str] = {}
    for o in obs.overlays:
        label = f"{o.purpose.value} {o.kind.value}"
        if o.purpose == OverlayPurpose.CONSENT:
            label += f" layer {o.layer}"
        for c in o.controls:
            role = "" if c.purpose == ControlPurpose.OTHER else f" ({c.purpose.value} control)"
            overlay_of[c.element_id] = label + role

    candidates = [
        e
        for e in obs.elements
        if e.style.visible and not e.disabled and e.role in INTERACTIVE_ROLES and _name(e)
    ]
    # Overlay controls first (they block the page), then what is on screen, then the rest.
    candidates.sort(key=lambda e: (e.id not in overlay_of, not e.in_viewport))
    shown = candidates[:MAX_ELEMENTS]
    shown.sort(key=lambda e: obs.elements.index(e))

    rows = []
    for e in shown:
        cells = [e.id, e.role, _clean(_name(e), MAX_NAME_CHARS)]
        flags = [_state(e)]
        if e.id in required:
            flags.append("required")
        if _name(e) in tried:
            flags.append("tried, opened nothing")
        elif _name(e) in seen_links:
            flags.append("opens a page you already visited")
        if _name(e) in filled:
            flags.append("filled")
        extra = [x for x in (*flags, _where(e, overlay_of)) if x]
        rows.append(" | ".join(cells + extra))
    controls = "\n".join(rows) or "(no interactive controls found)"
    omitted = len(candidates) - len(shown)
    if omitted:
        controls += f"\n({omitted} more controls not shown)"

    tag = f"untrusted_page_content_{nonce}"
    body = (
        f"Path: {_clean(path, 200)}\n"
        f"Title: {_clean(obs.title, 200)}\n"
        f"Controls (id | role | name | state, where):\n{controls}\n\n"
        + (
            f"Visible text (first {MAX_TEXT_CHARS} characters):\n"
            f"{_clean(page_text, MAX_TEXT_CHARS)}"
            if page_text
            else "Visible text: unchanged since your last turn (not repeated)."
        )
    )
    body = re.sub(r"untrusted_page_content", "untrusted-page-content", body, flags=re.I)
    text = f"<{tag}>\n{body}\n</{tag}>"
    sha = hashlib.sha256(controls.encode("utf-8")).hexdigest()[:16]
    return Observation(text=text, shown_ids=frozenset(e.id for e in shown), controls_sha=sha)


def _name(e: UiElement) -> str:
    return (e.accessible_name or e.text or "").strip()
