"""Words the scripted walker looks for, in English.

This is the "tiny adapter" the brief allows: generic web vocabulary (add to cart, start a
trial, cancel, no thanks), never skin-specific selectors. It is listed in DECISIONS (D-038)
as debt that the Phase 6 LLM explorer should retire.
"""

from __future__ import annotations

import re


def words(*alternatives: str) -> re.Pattern[str]:
    return re.compile(r"\b(" + "|".join(alternatives) + r")\b", re.IGNORECASE)


# --- shopping ---------------------------------------------------------------------
ADD_TO_CART = words(r"add\s+(to\s+)?(cart|bag|basket)", r"add\s+item")
CHECKOUT = words(r"checkout", r"check\s+out")
PAY = words(r"pay(ment)?", r"place\s+(my\s+)?order", r"buy\s+now", r"pay\s+securely")

# --- signing up -------------------------------------------------------------------
PRICING = words("pricing", r"plans")
START_TRIAL = words(
    r"start\s+(free\s+)?trial", r"try\s+it\s+free", r"get\s+started(\s+free)?", r"free\s+trial"
)
CONFIRM_TRIAL = words(
    r"start\s+my\s+trial", r"begin\s+trial", r"activate\s+trial", r"confirm\s+trial",
    r"create\s+(my\s+)?account",
)  # fmt: skip
SUBSCRIBE = words("subscribe", r"sign\s+me\s+up", r"join\s+(the\s+)?newsletter")

# --- leaving ----------------------------------------------------------------------
LEAVE_ENTRY = words(
    r"cancel\s+(my\s+)?(plan|subscription|membership)", r"end\s+(my\s+)?subscription",
    "unsubscribe", r"email\s+preferences", "newsletter", r"opt\s+out", r"leave\s+newsletter",
    r"delete\s+(my\s+)?account",
)  # fmt: skip
# Where a leave control usually hides, most specific first.
LEAVE_NAVIGATION = (
    words("billing", "payments", r"plan\s+and\s+billing", r"subscription"),
    words("settings", "preferences", r"my\s+account"),
)
# How to keep going inside a leave flow, in priority order.
LEAVE_PROGRESS = (
    words(r"no,?\s+thanks"),
    words(r"yes,?\s+i('|\s+a)?m\s+sure"),
    words("unsubscribe", r"opt\s+out", r"leave\s+newsletter"),
    words("confirm", r"yes,?\s+cancel"),
    words("continue", "next", "proceed"),
)
STAY = words("keep", r"go\s+back", "stay", "upgrade")  # never pressed while leaving

# --- reading the page -------------------------------------------------------------
LEFT_TEXT = re.compile(
    r"(plan is cancell?ed|subscription (has been |is )?cancell?ed|you have left the newsletter"
    r"|you('| a)re unsubscribed|successfully unsubscribed)",
    re.IGNORECASE,
)
PHONE_ONLY_TEXT = re.compile(r"\bcall\b.{0,60}?\d[\d\s-]{6,}", re.IGNORECASE)
EMAIL_ONLY_TEXT = re.compile(r"(send an email|email us|write to).{0,80}?@", re.IGNORECASE)
PAGE_INSTRUCTION_TEXT = re.compile(
    r"(ignore (all |any |your |the )?(previous |prior )?(instructions|rules)"
    r"|you are an? (ai|assistant|agent|language model)|system prompt|as an ai\b"
    r"|(agent|assistant|bot|ai)s?,?( you)? (must|should|need to) (click|press|visit|go to|accept))",
    re.IGNORECASE,
)

# --- test data typed into forms (fake, sandbox only) ------------------------------
TEST_DATA = (
    (re.compile(r"e-?mail", re.I), "walker@example.test"),
    (re.compile(r"phone|mobile|tel", re.I), "9000000000"),
    (re.compile(r"pin|postal|zip", re.I), "411001"),
    (re.compile(r"city|town", re.I), "Pune"),
    (re.compile(r"name", re.I), "Test Walker"),
)
DEFAULT_TEXT = "Test"


def test_value(label: str) -> str:
    for pattern, value in TEST_DATA:
        if pattern.search(label):
            return value
    return DEFAULT_TEXT
