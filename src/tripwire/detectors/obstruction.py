"""Measure friction on the recorded leave path, excluding exploratory detours."""

import re

from tripwire.detectors.base import Observation
from tripwire.walker.vocab import LEAVE_ENTRY


def _declined_offer(step, action):
    if not action.target:
        return False
    choice = action.target.accessible_name or action.target.visible_text or ""
    if not re.search(r"\b(?:decline|reject|no thanks|no, thanks)\b", choice, re.I):
        return False
    return any(
        e.role in {"link", "button"}
        and e.style.visible
        and not e.disabled
        and re.search(
            r"\b(?:accept|take|claim|redeem)\b.*\b(?:offer|discount|deal|savings)\b",
            e.accessible_name or e.text,
            re.I,
        )
        for e in step.ui.elements
        if (e.accessible_name or e.text) != choice
    )


def obstruction(trace, config):
    join = next((p for p in trace.paths if p.goal == "sign_up" and p.completed), None)
    leave = next(
        (p for p in trace.paths if p.goal in {"cancel", "unsubscribe", "delete_account"}), None
    )
    if not join or not leave or not leave.step_indices:
        return
    offline = leave.exit_channel != "web"
    if leave.completed or offline:
        extra = leave.clicks - join.clicks
        yield Observation(
            "obstruction.roach_motel",
            offline or extra >= config["extra_clicks"],
            join.step_indices + leave.step_indices,
            dict(
                sign_up_clicks=join.clicks,
                leave_clicks=leave.clicks,
                extra_clicks_to_leave=extra,
                exit_channel=leave.exit_channel,
                sign_up_page_loads=join.page_loads,
                leave_page_loads=leave.page_loads,
            ),
            f"Joining took {join.clicks} clicks and leaving took {leave.clicks} clicks.",
            "Verify that the two paths start at comparable points.",
        )
    entry_index = None
    for depth, i in enumerate(leave.step_indices):
        target = trace.steps[i].action.target
        name = target.accessible_name if target else None
        if not name or not LEAVE_ENTRY.search(name) or i == 0:
            continue
        entries = [
            e
            for e in trace.steps[i - 1].ui.elements
            if e.style.visible and LEAVE_ENTRY.search(e.accessible_name or e.text)
        ]
        control = next((e for e in entries if (e.accessible_name or e.text) == name), None)
        if not control:
            continue
        entry_index = i
        footer = all(e.landmark == "contentinfo" for e in entries)
        small = control.style.font_size_px < config["small_font"] and (
            control.contrast_ratio is not None and control.contrast_ratio < config["low_contrast"]
        )
        deep = all(
            e.tree_depth is not None and e.tree_depth >= config["deep_tree_level"] for e in entries
        )
        yield Observation(
            "obstruction.buried_control",
            footer or small or deep,
            [i - 1],
            dict(
                footer_only=footer,
                click_depth=depth,
                font_px=control.style.font_size_px,
                contrast=control.contrast_ratio,
                tree_depth=control.tree_depth,
            ),
            "The observed leave control met the threshold for a buried or hard-to-read control.",
            "Look for another equally accessible exit elsewhere on the page.",
        )
        break
    friction = []
    confirmations = []
    for i in leave.step_indices:
        if i == 0 or (entry_index is not None and i <= entry_index):
            continue
        step = trace.steps[i - 1]
        if any(f.required for form in step.forms for f in form.fields):
            continue
        overlays = {o.purpose for o in step.overlays}
        names = " ".join((e.accessible_name or e.text) for e in step.ui.elements if e.style.visible)
        if (
            overlays & {"survey", "retention"}
            or _declined_offer(step, trace.steps[i].action)
            or re.search(r"% off|no thanks, continue", names, re.I)
            or any(f.type == "radio" for form in step.forms for f in form.fields)
        ):
            friction.append(step.index)
        elif "confirm" in overlays or re.search(r"yes,? i am sure|yes,? i'm sure", names, re.I):
            confirmations.append(step.index)
    # Keep one ordinary final confirmation. An offline terminal still requires the person
    # to confirm outside the web flow, so repeated web prompts are additional steps.
    friction += confirmations if offline else confirmations[:-1]
    yield Observation(
        "obstruction.interposed_friction",
        bool(friction),
        friction or leave.step_indices,
        dict(unneeded_interstitials=len(friction)),
        f"The leave flow added {len(friction)} optional prompts.",
        "Check whether the intermediate steps require information needed for leaving.",
    )
