"""Detect pages a human must handle: CAPTCHAs, login walls, one-time codes (ETHICS rule 2).

The walker never tries to get past these. It stops, records a handoff note, and (in a
headed run) prints instructions for the human.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from tripwire.browser.ui_inventory import PageObservation

_CAPTCHA_TEXT = re.compile(
    r"(i('|\s+a)m not a robot|verify (that )?you('|\s+a)re (a )?human|captcha|security check)",
    re.IGNORECASE,
)
_CAPTCHA_FRAME = re.compile(r"recaptcha|hcaptcha|turnstile|captcha", re.IGNORECASE)
_OTP = re.compile(r"\b(otp|one[- ]time (pass)?code|verification code)\b", re.IGNORECASE)


@dataclass(frozen=True)
class Handoff:
    reason: str  # "captcha", "login", "otp"
    instructions: str


def detect_handoff(obs: PageObservation, page_text: str, frame_urls: list[str]) -> Handoff | None:
    if _CAPTCHA_TEXT.search(page_text) or any(_CAPTCHA_FRAME.search(u) for u in frame_urls):
        return Handoff("captcha", "A CAPTCHA or bot check appeared. Tripwire never solves these.")
    fields = [f for form in obs.forms for f in form.fields if not f.hidden]
    if any(_OTP.search(f"{f.name} {f.label or ''}") for f in fields) or _OTP.search(page_text):
        return Handoff("otp", "A one-time code is required. Enter it yourself, or stop the run.")
    if any(f.type == "password" for f in fields):
        return Handoff("login", "A login is required. Tripwire never types passwords.")
    return None
