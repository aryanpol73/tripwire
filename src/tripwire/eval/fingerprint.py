"""What detectors will read from a trace, minus everything that legitimately varies between
runs (timestamps, ports, request ids, wall time). Two runs of the same scenario must give the
same fingerprint: that is the Phase 3 determinism check.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any
from urllib.parse import urlsplit

from tripwire.schemas.trace import Step, Trace


def _step(step: Step) -> dict[str, Any]:
    elements = {e.id: e for e in step.ui.elements}

    def measured(element_id: str) -> list[Any]:
        e = elements[element_id]
        return [
            e.role,
            e.accessible_name,
            round(e.bbox.width),
            round(e.bbox.height),
            e.style.font_size_px,
            e.contrast_ratio,
        ]

    target = step.action.target
    return {
        "action": step.action.kind,
        "target": target.accessible_name if target else None,
        "url": urlsplit(step.url_after).path,
        "page_load": step.page_load,
        "overlays": [
            {
                "kind": o.kind,
                "purpose": o.purpose,
                "layer": o.layer,
                "coverage": round(o.viewport_coverage, 2),
                "blocks": o.blocks_interaction,
                "controls": [[c.purpose, *measured(c.element_id)] for c in o.controls],
            }
            for o in step.overlays
        ],
        "forms": [
            [
                [f.name, f.type, f.prechecked, f.hidden, f.off_screen, f.required]
                for f in form.fields
            ]
            for form in step.forms
        ],
        "elements": sorted(
            [
                e.role,
                e.accessible_name,
                round(e.bbox.width),
                round(e.bbox.height),
                e.style.font_size_px,
                e.contrast_ratio,
                e.checked,
                e.landmark,
                e.tree_depth,
            ]
            for e in step.ui.elements
            if e.style.visible
        ),
    }


def detector_inputs(trace: Trace) -> dict[str, Any]:
    return {
        "status": trace.status,
        "steps": [_step(s) for s in trace.steps],
        "paths": [p.model_dump(mode="json") for p in trace.paths],
        "intents": [i.model_dump(mode="json") for i in trace.intents],
        "commerce": trace.commerce.model_dump(mode="json") if trace.commerce else None,
        "notes": [[n.kind, n.step_index, n.message] for n in trace.notes],
    }


def fingerprint(trace: Trace) -> str:
    canonical = json.dumps(detector_inputs(trace), sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
