"""The model's tool set, and the code that checks each call before anything happens.

The model only proposes. A proposal becomes an action only if it refers to a control the
model was shown, that control is visible and enabled, and it is not on a list of things
the walker never does (accept consent, type into a secret field, leave the site). After
that the safety gate still decides. Typed values are chosen by the walker from test data,
never by the model, so page text cannot steer what gets typed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from tripwire.browser.safety_gate import _SECRET_FIELD
from tripwire.browser.ui_inventory import PageObservation
from tripwire.schemas.trace import ControlPurpose, UiElement

TEXT_ROLES = {"textbox", "searchbox", "combobox", "spinbutton"}


class Purpose(StrEnum):
    REJECT_CONSENT = "reject_consent"
    SIGN_UP = "sign_up"
    LEAVE = "leave"
    ADD_TO_CART = "add_to_cart"
    REACH_PAYMENT = "reach_payment"
    BROWSE = "browse"
    OTHER = "other"


class Outcome(StrEnum):
    COMPLETED = "completed"
    IMPOSSIBLE = "impossible"


def _schema(properties: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


# Kept short on purpose: these schemas are sent with every call, and the system prompt
# already explains purposes and rules. Field names and enums are unchanged.
_PURPOSE = {"type": "string", "enum": [p.value for p in Purpose]}
_REASON = {"type": "string"}
_ELEMENT = {"type": "string"}

TOOLS: list[dict[str, Any]] = [
    {
        "name": "click",
        "description": "Click a control by id.",
        "strict": True,
        "input_schema": _schema({"element_id": _ELEMENT, "purpose": _PURPOSE, "reason": _REASON}),
    },
    {
        "name": "type",
        "description": "Fill a text field by id; the walker picks the test value.",
        "strict": True,
        "input_schema": _schema({"element_id": _ELEMENT, "purpose": _PURPOSE, "reason": _REASON}),
    },
    {
        "name": "scroll",
        "description": "Scroll down one screen.",
        "strict": True,
        "input_schema": _schema({"purpose": _PURPOSE, "reason": _REASON}),
    },
    {
        "name": "navigate",
        "description": "Open a path on this site, e.g. /pricing.",
        "strict": True,
        "input_schema": _schema(
            {
                "path": {"type": "string"},
                "purpose": _PURPOSE,
                "reason": _REASON,
            }
        ),
    },
    {
        "name": "handoff",
        "description": "Hand over to a human (CAPTCHA, login, code, real data needed).",
        "strict": True,
        "input_schema": _schema({"reason": _REASON}),
    },
    {
        "name": "done",
        "description": "Stop: mission finished, or impossible here.",
        "strict": True,
        "input_schema": _schema(
            {
                "outcome": {"type": "string", "enum": [o.value for o in Outcome]},
                "reason": _REASON,
            }
        ),
    },
]
TOOL_NAMES = {t["name"] for t in TOOLS}


class Refused(Exception):
    """A proposal the walker will not carry out. The reason is shown to the model."""


@dataclass(frozen=True)
class Checked:
    tool: str
    purpose: Purpose
    element: UiElement | None = None
    path: str | None = None
    control: ControlPurpose | None = None  # the element's role in an overlay, if any


def check(
    tool: str,
    args: dict[str, Any],
    obs: PageObservation,
    shown_ids: frozenset[str],
    pay_control: re.Pattern[str] | None = None,
) -> Checked:
    """pay_control: on the reach_payment mission, the pattern of a control that would start
    payment. Such a control marks the end of the mission, so clicking it is refused."""
    if tool not in TOOL_NAMES or tool in ("done", "handoff"):
        raise Refused(f"unknown or non-action tool {tool!r}")
    try:
        purpose = Purpose(args.get("purpose", "other"))
    except ValueError:
        raise Refused("purpose must be one of the listed values") from None
    if tool == "scroll":
        return Checked(tool, purpose)
    if tool == "navigate":
        path = str(args.get("path", ""))
        if not path.startswith("/") or path.startswith("//") or "\\" in path:
            raise Refused("navigate takes a path on this site starting with a single /")
        return Checked(tool, purpose, path=path)

    element_id = str(args.get("element_id", ""))
    if element_id not in shown_ids:
        raise Refused(f"{element_id!r} is not in the current Controls list")
    element = next((e for e in obs.elements if e.id == element_id), None)
    if element is None or not element.style.visible or element.disabled:
        raise Refused(f"{element_id} is not visible and enabled")
    control = next(
        (c.purpose for o in obs.overlays for c in o.controls if c.element_id == element_id),
        None,
    )
    if tool == "click":
        if element.role in TEXT_ROLES:
            raise Refused("that is a text field; use type")
        if control == ControlPurpose.ACCEPT and _in_consent(obs, element_id):
            raise Refused("accepting consent is never done; reject it or open its settings")
        if pay_control and pay_control.search(element.accessible_name or element.text or ""):
            raise Refused("that would start payment: this is the last page, so call done")
    if tool == "type":
        if element.role not in TEXT_ROLES:
            raise Refused("type works only on text fields")
        name = (element.accessible_name or element.text or "").lower()
        if _SECRET_FIELD.search(name):  # the gate's own definition, so they agree
            raise Refused("secret fields are typed by a human; use handoff")
    return Checked(tool, purpose, element=element, control=control)


def _in_consent(obs: PageObservation, element_id: str) -> bool:
    return any(
        o.purpose.value == "consent" and any(c.element_id == element_id for c in o.controls)
        for o in obs.overlays
    )
