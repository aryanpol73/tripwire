"""Nagging and forced registration (Phase 9 module 3).

- nagging.repeat_popup: the walker closed a pop-up (its close or decline control), and a
  pop-up with the same purpose came back on a later page.
- nagging.forced_registration: the run was handed to a human at a login wall (a password
  field) on a page the walker reached through an ordinary link, not an account, sign-in or
  sign-up link. Reading a page should not need an account.

Both read only the Trace: overlays and their controls per step, the walker's actions, and
the hand-off note the walker records at a login wall (it never types passwords).
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Mapping
from urllib.parse import urlsplit

from tripwire.detectors.base import Observation
from tripwire.schemas.trace import ActionKind, ControlPurpose, NoteKind, OverlayPurpose, Trace

DISMISS = {ControlPurpose.CLOSE, ControlPurpose.REJECT}


def _dismissed_purpose(trace: Trace, i: int) -> OverlayPurpose | None:
    """If step i clicked a close or decline control of a non-consent pop-up shown on the step
    before, the pop-up's purpose."""
    step, before = trace.steps[i], trace.steps[i - 1]
    target = step.action.target
    if step.action.kind != ActionKind.CLICK or target is None:
        return None
    names = {e.id: (e.accessible_name or e.text or "").strip() for e in before.ui.elements}
    wanted = (target.accessible_name or target.visible_text or "").strip()
    for o in before.overlays:
        if o.purpose == OverlayPurpose.CONSENT:
            continue
        for c in o.controls:
            if c.purpose in DISMISS and names.get(c.element_id) == wanted:
                return o.purpose
    return None


def nagging(trace: Trace, config: Mapping) -> Iterator[Observation]:
    if not trace.steps:
        return
    account = re.compile(config["account_words"], re.IGNORECASE)

    # --- a pop-up that comes back after it was closed ---------------------------------
    dismissed: dict[OverlayPurpose, int] = {}  # purpose -> step that closed it first
    returns: list[int] = []
    for i in range(1, len(trace.steps)):
        purpose = _dismissed_purpose(trace, i)
        if purpose is not None:
            dismissed.setdefault(purpose, i)
            continue
        step = trace.steps[i]
        if not step.page_load:
            continue
        shown = {o.purpose for o in step.overlays}
        if any(p in shown and dismissed[p] < i for p in dismissed):
            returns.append(i)
    if dismissed:
        first = min(dismissed.values())
        yield Observation(
            "nagging.repeat_popup",
            bool(returns),
            [first - 1, first, *returns[:3]],
            dict(
                dismissals=len(dismissed),
                reappearances=len(returns),
                popup_returned=bool(returns),
                popup_purpose=", ".join(sorted(p.value for p in dismissed)),
            ),
            f"A pop-up that was closed came back on {len(returns)} later pages.",
            "Check whether the pop-up came back after a long time or a new session.",
        )

    # --- a login wall on a page reached by an ordinary link ---------------------------
    wall = next(
        (n for n in trace.notes if n.kind == NoteKind.HANDOFF and n.message.startswith("login")),
        None,
    )
    blocked = False
    reached_by = ""
    steps = [trace.steps[-1].index]
    if wall is not None and wall.step_index is not None:
        step = trace.steps[wall.step_index]
        t = step.action.target
        reached_by = (t.accessible_name or t.visible_text or "") if t else step.action.kind.value
        path = urlsplit(step.url_after).path
        blocked = not (account.search(reached_by) or account.search(path))
        steps = [wall.step_index]
    yield Observation(
        "nagging.forced_registration",
        blocked,
        steps,
        dict(account_wall=blocked, reached_by=reached_by),
        "A page reached by an ordinary link asked the visitor to create an account."
        if blocked
        else "No account wall blocked an ordinary page.",
        "Check whether the page holds something that genuinely needs an account.",
    )
