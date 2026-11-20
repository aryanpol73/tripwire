"""Measure the available choices on the observed consent layers."""

import re

from tripwire.browser.consent import has_mixed_choice_cues
from tripwire.detectors.base import Observation

MARKETING = re.compile(r"newsletter|marketing|product news|promotional", re.I)


# First-person disavowal of a personal interest as the price of declining.
# A literal refusal of data collection ("I do not want to share ...") is different.
_DISAVOWAL = re.compile(r"\bi (?:do not|don['\u2019]t) (?:value|care (?:for|about)) my \w+", re.I)


def consent(trace, config):
    layers = [(s, o) for s in trace.steps for o in s.overlays if o.purpose == "consent"]
    paths = {p.goal: p for p in trace.paths}
    reject, accept = paths.get("reject_consent"), paths.get("accept_consent")
    if layers and accept and reject:
        first, overlay = layers[0]
        direct = any(c.purpose == "reject" for c in overlay.controls)
        delta = reject.clicks - accept.clicks if reject.completed else None
        yield Observation(
            "consent.click_asymmetry",
            not direct or (delta is not None and delta >= config["extra_clicks"]),
            [first.index, *reject.step_indices],
            dict(
                accept_clicks=accept.clicks,
                reject_clicks=reject.clicks if reject.completed else None,
                extra_clicks_to_reject=delta,
                reject_on_first_layer=direct,
                accept_page_loads=accept.page_loads,
                reject_page_loads=reject.page_loads if reject.completed else None,
            ),
            (
                f"Rejecting took {reject.clicks} clicks and accepting took {accept.clicks}."
                if reject.completed
                else "The first consent layer offered no measured reject control."
            ),
            "Check for an alternative reject control on the first layer.",
        )
    for step, layer in layers:
        elements = {e.id: e for e in step.ui.elements if e.style.visible}
        choices = {
            c.purpose: elements[c.element_id] for c in layer.controls if c.element_id in elements
        }
        yes, no = choices.get("accept"), choices.get("reject")
        if not (yes and no):
            continue
        text = no.accessible_name or no.text
        yield Observation(
            "consent.confirmshaming",
            any(p in text.casefold() for p in config["decline_phrases"])
            or bool(_DISAVOWAL.search(text)),
            [step.index],
            dict(decline_text=text),
            "The decline option uses wording associated with shaming.",
            "Read the whole sentence in context.",
            review_steps=[step.index] if has_mixed_choice_cues(text) else [],
        )
        area = no.bbox.width * no.bbox.height
        if area:
            ratio = yes.bbox.width * yes.bbox.height / area
            dim = (
                no.contrast_ratio is not None
                and yes.contrast_ratio is not None
                and no.contrast_ratio < config["low_contrast"]
                and yes.contrast_ratio >= config["high_contrast"]
            )
            yield Observation(
                "consent.visual_asymmetry",
                ratio >= config["area_ratio"] or dim,
                [step.index],
                dict(
                    compared_on_layer=layer.layer,
                    area_ratio=round(ratio, 2),
                    accept_contrast=yes.contrast_ratio,
                    reject_contrast=no.contrast_ratio,
                    accept_font_px=yes.style.font_size_px,
                    reject_font_px=no.style.font_size_px,
                ),
                "The consent buttons differ in area or contrast.",
                "Check their rendered size and background at the recorded viewport.",
            )
        break
    seen = set()
    enabled = []
    for step in trace.steps:
        for e in step.ui.elements:
            name = e.accessible_name or e.text
            if e.disabled or not e.style.visible or e.role not in {"switch", "checkbox"}:
                continue
            in_banner = any(
                o.purpose == "consent"
                and (
                    any(c.element_id == e.id for c in o.controls)
                    or (
                        e.bbox.x >= o.bbox.x
                        and e.bbox.y >= o.bbox.y
                        and e.bbox.x + e.bbox.width <= o.bbox.x + o.bbox.width
                        and e.bbox.y + e.bbox.height <= o.bbox.y + o.bbox.height
                    )
                )
                for o in step.overlays
            )
            if not (in_banner or MARKETING.search(name)) or name in seen:
                continue
            seen.add(name)
            if e.checked:
                enabled.append(step.index)
    yield Observation(
        "consent.preselected",
        bool(enabled),
        enabled,
        dict(preselected_count=len(enabled)),
        f"{len(enabled)} optional consent choices were already on.",
        "Verify each choice was optional and observed before interaction.",
    )
