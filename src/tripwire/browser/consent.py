"""Words that tell what an overlay is for and what each of its controls does.

Keyword matching is a Tier A input only for *locating* controls. Detectors measure what the
located controls look like and cost; they never judge the wording itself (that is Tier B).
Order matters: "Disagree" must be read as reject before "agree" is read as accept.
"""

from __future__ import annotations

import re

from tripwire.schemas.trace import ControlPurpose, OverlayPurpose

_CONTROL_RULES: list[tuple[ControlPurpose, re.Pattern[str]]] = [
    (
        ControlPurpose.REJECT,
        re.compile(
            r"\b(reject|decline|disagree|refuse|deny|only\s+(strictly\s+)?necessary"
            r"|necessary\s+only|essential\s+only|no,?\s+thanks|continue\s+without|opt\s+out)\b",
            re.IGNORECASE,
        ),
    ),
    (
        ControlPurpose.ACCEPT,
        re.compile(r"\b(accept|agree|allow|i\s+consent|got\s+it|ok(ay)?|yes)\b", re.IGNORECASE),
    ),
    # "Save preferences" / "Apply" / "Confirm my choices" keep the toggles as they are: not
    # a settings link, not an accept. Reported as OTHER so it is never mistaken for either.
    (ControlPurpose.OTHER, re.compile(r"\b(save|apply|confirm\s+my\s+choices)\b", re.I)),
    (
        ControlPurpose.SETTINGS,
        re.compile(
            r"\b(manage|settings|customi[sz]e|preferences|options|more\s+choices|advanced"
            r"|vendors?|partners|purposes|legitimate\s+interest|details)\b",
            re.IGNORECASE,
        ),
    ),
    (ControlPurpose.CLOSE, re.compile(r"^\s*(close|dismiss|x|\u00d7|\u2715)\s*$", re.IGNORECASE)),
    (ControlPurpose.CONTINUE, re.compile(r"\b(continue|next|proceed)\b", re.IGNORECASE)),
]

_OVERLAY_RULES: list[tuple[OverlayPurpose, re.Pattern[str]]] = [
    (
        OverlayPurpose.CONSENT,
        re.compile(r"\b(cookies?|consent|tracking|gdpr|our\s+partners|privacy\s+choices)\b", re.I),
    ),
    (OverlayPurpose.SURVEY, re.compile(r"\b(why\s+are\s+you\s+leaving|survey|feedback)\b", re.I)),
    (
        OverlayPurpose.RETENTION,
        re.compile(r"\b(special\s+offer|stay\s+with\s+us|\d+%\s+off|before\s+you\s+go)\b", re.I),
    ),
    (OverlayPurpose.CONFIRM, re.compile(r"\b(are\s+you\s+sure|please\s+confirm)\b", re.I)),
    (
        OverlayPurpose.NEWSLETTER,
        re.compile(r"\b(newsletter|subscribe|briefing|in\s+your\s+inbox|sign\s+up)\b", re.I),
    ),
]


def has_mixed_choice_cues(label: str) -> bool:
    purposes = {purpose for purpose, pattern in _CONTROL_RULES if pattern.search(label)}
    return {ControlPurpose.ACCEPT, ControlPurpose.REJECT} <= purposes


def control_purpose(label: str) -> ControlPurpose:
    for purpose, pattern in _CONTROL_RULES:
        if pattern.search(label or ""):
            return purpose
    return ControlPurpose.OTHER


def overlay_purpose(text: str) -> OverlayPurpose:
    for purpose, pattern in _OVERLAY_RULES:
        if pattern.search(text or ""):
            return purpose
    return OverlayPurpose.OTHER
