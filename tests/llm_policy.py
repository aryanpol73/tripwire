"""A crude, deterministic stand-in for the model, used only in tests.

It reads the Controls list from the prompt the walker built, so it exercises the real
observation format. It is not meant to be good at missions; it lets the loop, the checks,
the gate and record/replay be tested without an API key.
"""

from __future__ import annotations

import re

from tripwire.llm.client import Request

ROW = re.compile(r"^(e\d+|f\d+e\d+|f\w+) \| (\w+) \| (.*)$", re.MULTILINE)


def controls(prompt: str) -> list[tuple[str, str, str]]:
    return [(m[1], m[2], m[3]) for m in ROW.finditer(prompt)]


def first_visit_policy(pages: int = 3):
    clicked: list[str] = []

    def policy(req: Request):
        rows = controls(req.prompt)
        for eid, _role, rest in rows:
            if "(reject control)" in rest:
                return "click", {"element_id": eid, "purpose": "reject_consent", "reason": "r"}
        for eid, _role, rest in rows:
            if "consent" in rest and "(settings control)" in rest:
                return "click", {"element_id": eid, "purpose": "reject_consent", "reason": "r"}
        if len(clicked) >= pages:
            return "done", {"outcome": "completed", "reason": "r"}
        for eid, role, rest in rows:
            name = rest.split(" | ")[0]
            if role == "link" and name not in clicked and "footer" not in rest:
                if re.search(r"subscribe|sign|pay|cancel|account|home|log", name, re.I):
                    continue
                clicked.append(name)
                return "click", {"element_id": eid, "purpose": "browse", "reason": "r"}
        return "done", {"outcome": "impossible", "reason": "r"}

    return policy


def scripted(actions: list[tuple[str, dict]]):
    """Return the given tool calls in order, then done."""
    queue = list(actions)

    def policy(_req: Request):
        return queue.pop(0) if queue else ("done", {"outcome": "completed", "reason": "r"})

    return policy
