"""Did a run finish its mission? Decided from the Trace, never from the model's own claim.

The same check applies to the scripted and the LLM walker, so their completion rates are
comparable.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit

from tripwire.schemas.trace import IntentGoal, OverlayPurpose, PathGoal, RunStatus, Trace

LEAVE_GOALS = {PathGoal.CANCEL, PathGoal.UNSUBSCRIBE, PathGoal.DELETE_ACCOUNT}


@dataclass(frozen=True)
class Completion:
    completed: bool
    reason: str


def _consent_ok(trace: Trace) -> tuple[bool, str]:
    saw_banner = any(o.purpose == OverlayPurpose.CONSENT for s in trace.steps for o in s.overlays)
    if not saw_banner:
        return True, "no consent banner"
    rejected = any(i.goal == IntentGoal.REJECT_CONSENT and i.success for i in trace.intents)
    return rejected, "consent rejected" if rejected else "consent banner not rejected"


def mission_completed(trace: Trace, internal_pages: int = 3) -> Completion:
    if trace.status in (RunStatus.BUDGET_EXCEEDED, RunStatus.ERROR, RunStatus.BLOCKED):
        return Completion(False, f"run ended with status {trace.status.value}")
    ok, why = _consent_ok(trace)
    if not ok:
        return Completion(False, why)
    if trace.mission == "first_visit":
        start = urlsplit(str(trace.site_url)).path or "/"
        pages = {urlsplit(s.url_after).path or "/" for s in trace.steps} - {start}
        if len(pages) >= internal_pages:
            return Completion(True, f"{why}; {len(pages)} internal pages opened")
        return Completion(False, f"{why}; only {len(pages)} internal pages opened")
    if trace.mission == "reach_payment":
        reached = any(p.goal == PathGoal.REACH_PAYMENT and p.completed for p in trace.paths)
        return Completion(reached, "reached the page before payment" if reached else "did not")
    if trace.mission == "sign_up_and_leave":
        joined = any(p.goal == PathGoal.SIGN_UP for p in trace.paths)
        left = [p for p in trace.paths if p.goal in LEAVE_GOALS]
        ended = any(p.completed or p.exit_channel != "web" for p in left)
        if joined and ended:
            return Completion(True, "signed up, then followed the leave path to its end")
        return Completion(False, f"signed up: {joined}; leave path ended: {ended}")
    return Completion(False, f"unknown mission {trace.mission}")
