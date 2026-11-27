"""Build one self-contained, offline report.html from a run folder.

Everything the reader needs is inside the file: screenshots as data URIs, inline CSS, no
scripts or external assets. Boxes are drawn from the trace's measured bounding boxes, so a
reviewer can see which control a number refers to without opening the trace.
"""

from __future__ import annotations

import base64
import json
import struct
import tomllib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from jinja2 import Environment, PackageLoader, select_autoescape

from tripwire import __version__
from tripwire.detectors.rules import RULES
from tripwire.report import plain
from tripwire.schemas.finding import Finding, FindingSet, Tier
from tripwire.schemas.io import read_findings, read_trace
from tripwire.schemas.trace import (
    ControlPurpose,
    OverlayPurpose,
    PathGoal,
    Step,
    Trace,
    UiElement,
)
from tripwire.walker.vocab import LEAVE_ENTRY

THRESHOLDS = Path(__file__).resolve().parents[1] / "detectors" / "thresholds.toml"
_THRESHOLD_FAMILY = {"consent": "consent", "sneaking": "sneaking", "obstruction": "obstruction"}

JOIN_GOALS = {PathGoal.SIGN_UP, PathGoal.ACCEPT_CONSENT}
LEAVE_GOALS = {
    PathGoal.UNSUBSCRIBE,
    PathGoal.CANCEL,
    PathGoal.DELETE_ACCOUNT,
    PathGoal.REJECT_CONSENT,
}


@dataclass
class Box:
    label: str
    left: float  # percentages of the screenshot, so the box scales with the image
    top: float
    width: float
    height: float
    kind: str = "focus"  # focus | accept | reject


@dataclass
class Shot:
    step: int
    caption: str
    data_uri: str | None
    boxes: list[Box] = field(default_factory=list)


def png_size(path: Path) -> tuple[int, int] | None:
    with path.open("rb") as f:
        head = f.read(24)
    if len(head) < 24 or head[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    return struct.unpack(">II", head[16:24])


def _data_uri(path: Path, mime: str) -> str:
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def _box(element: UiElement, size: tuple[int, int], label: str, kind: str = "focus") -> Box:
    w, h = size
    b = element.bbox
    return Box(
        label=label,
        left=round(100 * b.x / w, 3),
        top=round(100 * b.y / h, 3),
        width=round(100 * max(b.width, 4) / w, 3),
        height=round(100 * max(b.height, 4) / h, 3),
        kind=kind,
    )


def _name(e: UiElement) -> str:
    return (e.accessible_name or e.text or "").strip()


def _clicked_next(trace: Trace, step: Step) -> list[tuple[UiElement, str]]:
    """The element on this step that the walker clicked to reach the next one."""
    nxt = next((s for s in trace.steps if s.index == step.index + 1), None)
    if nxt is None or nxt.action.target is None:
        return []
    want = {
        (nxt.action.target.accessible_name or "").strip().lower(),
        (nxt.action.target.visible_text or "").strip().lower(),
    } - {""}
    verb = "Typed next" if nxt.action.kind.value == "type" else "Clicked next"
    for e in step.ui.elements:
        if e.style.visible and _name(e).lower() in want:
            return [(e, f"{verb}: {_name(e)[:40]}")]
    return []


def _targets(trace: Trace, finding: Finding, step: Step) -> list[tuple[UiElement, str, str]]:
    rule = finding.detector
    by_id = {e.id: e for e in step.ui.elements}
    out: list[tuple[UiElement, str, str]] = []
    if rule.startswith("consent."):
        for o in step.overlays:
            if o.purpose != OverlayPurpose.CONSENT:
                continue
            for c in o.controls:
                e = by_id.get(c.element_id)
                if e is None:
                    continue
                if c.purpose == ControlPurpose.ACCEPT and rule != "consent.confirmshaming":
                    out.append((e, f"Accept: {_name(e)[:30]}", "accept"))
                elif c.purpose == ControlPurpose.REJECT:
                    out.append((e, f"Reject: {_name(e)[:30]}", "reject"))
        if rule == "consent.preselected":
            out += [
                (e, f"Already on: {_name(e)[:30]}", "focus")
                for e in step.ui.elements
                # Same filter as the detector: a disabled toggle ("always on") is not a choice.
                if e.role in ("checkbox", "switch")
                and e.checked
                and e.style.visible
                and not e.disabled
            ]
    elif rule == "obstruction.buried_control":
        out += [
            (e, f"Way out: {_name(e)[:30]}", "focus")
            for e in step.ui.elements
            if e.style.visible and LEAVE_ENTRY.search(_name(e))
        ]
    elif rule == "sneaking.preadded_extras" and trace.commerce:
        for addon in trace.commerce.default_addons:
            e = by_id.get(addon.element_id or "")
            if addon.preselected and addon.step_index == step.index and e is not None:
                out.append((e, f"Pre-added: {addon.label[:30]}", "focus"))
    elif rule.startswith("nagging."):
        for o in step.overlays:
            if o.purpose.value != "consent":
                for c in o.controls:
                    e = by_id.get(c.element_id)
                    if e is not None and c.purpose.value in ("close", "reject"):
                        out.append((e, f"Closed here: {_name(e)[:30]}", "focus"))
    elif rule == "wire.flipped_choice":
        sent = str(finding.evidence.measurements.get("flipped_fields") or "")
        names = {pair.split("=", 1)[0] for pair in sent.split(", ") if pair}
        for form in step.forms:
            for f in form.fields:
                e = by_id.get(f.element_id or "")
                if f.name in names and e is not None:
                    out.append((e, f"Shown unticked, sent ticked: {f.name}", "focus"))
    elif rule.startswith("urgency."):
        want = "only N left" if rule == "urgency.stock_flux" else None
        for t in step.timers:
            e = by_id.get(t.element_id or "")
            if e is not None and (want is None) == (t.pattern != "only N left"):
                out.append((e, f"Read: {t.text[:30]}", "focus"))
    elif rule in ("obstruction.roach_motel", "obstruction.interposed_friction"):
        out += [(e, label, "focus") for e, label in _clicked_next(trace, step)]
    return out


def _shots(run_dir: Path, trace: Trace, finding: Finding, cache: dict[int, str | None]):
    steps = {s.index: s for s in trace.steps}
    shots: list[Shot] = []
    for index in finding.evidence.step_indices:
        step = steps.get(index)
        if step is None:
            continue
        uri, boxes = None, []
        path = run_dir / step.screenshot if step.screenshot else None
        if path and path.is_file():
            if index not in cache:
                cache[index] = _data_uri(path, "image/png")
            uri = cache[index]
            size = png_size(path)
            if size:
                seen: set[str] = set()
                for e, label, kind in _targets(trace, finding, step):
                    if e.id not in seen:
                        seen.add(e.id)
                        boxes.append(_box(e, size, label, kind))
        caption = f"Step {index}: {_step_words(step)}"
        shots.append(Shot(step=index, caption=caption, data_uri=uri, boxes=boxes))
    return shots


def _step_words(step: Step) -> str:
    a = step.action
    target = ""
    if a.target:
        target = a.target.accessible_name or a.target.visible_text or a.target.role or ""
    verb = {
        "navigate": "Opened",
        "click": "Clicked",
        "type": "Typed into",
        "scroll": "Scrolled",
        "wait": "Waited on",
        "reject_consent": "Rejected cookies via",
        "handoff": "Handed to a human at",
        "reload": "Reloaded the page",
    }.get(a.kind.value, a.kind.value)
    if a.kind.value == "navigate":
        return f"{verb} {step.url_after}"
    return f"{verb} “{target}”" if target else verb


def _price_timeline(trace: Trace, finding: Finding) -> list[dict[str, Any]]:
    if finding.detector != "sneaking.price_drift" or not trace.commerce:
        return []
    advertised, final = min(finding.evidence.step_indices), max(finding.evidence.step_indices)
    rows = []
    for line in sorted(trace.commerce.price_ledger, key=lambda pl: (pl.first_step, pl.label)):
        # Same window as the detector: a mandatory fee first shown after the advertised price.
        late = line.mandatory and line.role.value == "fee" and advertised < line.first_step <= final
        rows.append(
            {
                "label": line.label,
                "amount": plain.money(line.amount.minor, line.amount.currency),
                "role": line.role.value,
                "mandatory": line.mandatory,
                "first_step": line.first_step,
                "seen": ", ".join(str(s) for s in line.seen_steps),
                "late": late,
            }
        )
    return rows


def _paths(trace: Trace, finding: Finding) -> dict[str, list[dict[str, Any]]]:
    if finding.detector not in ("obstruction.roach_motel", "consent.click_asymmetry"):
        return {}
    steps = {s.index: s for s in trace.steps}

    def rows(goals: set[PathGoal]):
        return [
            {
                "name": p.name,
                "clicks": p.clicks,
                "page_loads": p.page_loads,
                "channel": p.exit_channel,
                "completed": p.completed,
                "executed": p.executed,
                "steps": [f"{i}. {_step_words(steps[i])}" for i in p.step_indices if i in steps],
            }
            for p in trace.paths
            if p.goal in goals
        ]

    return {"join": rows(JOIN_GOALS), "leave": rows(LEAVE_GOALS)}


def _hidden_fields(trace: Trace, finding: Finding) -> list[dict[str, Any]]:
    if finding.detector != "sneaking.bundled_optins":
        return []
    steps = {s.index: s for s in trace.steps}
    out = []
    for index in finding.evidence.step_indices:
        for form in steps[index].forms if index in steps else []:
            for f in form.fields:
                if f.hidden or f.off_screen:
                    out.append(
                        {
                            "step": index,
                            "form": form.action_url or form.id,
                            "name": f.name,
                            "type": f.type,
                            "how": "off-screen" if f.off_screen else "hidden",
                            "value": f.default_value
                            if f.default_value is not None
                            else ("checked" if f.prechecked else ""),
                        }
                    )
    return out


def _requests(trace: Trace, finding: Finding) -> list[dict[str, Any]]:
    wanted = set(finding.evidence.request_ids)
    steps = set(finding.evidence.step_indices)
    out = []
    for s in trace.steps:
        for r in s.requests:
            if r.id in wanted or (not wanted and s.index in steps and r.method != "GET"):
                out.append(
                    {
                        "step": s.index,
                        "method": r.method,
                        "url": r.url,
                        "status": r.status,
                        "blocked": r.blocked_by_gate,
                        "body": r.post_data_redacted,
                    }
                )
    return out


def _thresholds_for(rule: str) -> dict[str, Any]:
    try:
        data = tomllib.loads(THRESHOLDS.read_text(encoding="utf-8"))
    except OSError:
        return {}
    return data.get(_THRESHOLD_FAMILY.get(rule.split(".")[0], ""), {})


def _card(run_dir: Path, trace: Trace, f: Finding, cache: dict[int, str | None]) -> dict:
    metrics = dict(f.evidence.measurements)
    rule = RULES.get(f.detector)
    return {
        "id": f.id,
        "rule": f.detector,
        "title": plain.RULE_TITLES.get(f.detector, f.detector),
        "headline": plain.headline(f.detector, metrics),
        "summary": f.summary,
        "family": plain.FAMILY_NAMES.get(f.family.value, f.family.value),
        "tier": f.tier.value,
        "severity": f.severity.value,
        "confidence": f"{f.confidence:.2f}",
        "metrics": [
            (plain.METRIC_LABELS.get(k, k), plain.metric_value(k, v, metrics), k)
            for k, v in metrics.items()
        ],
        "shots": _shots(run_dir, trace, f, cache),
        "reproduce": f.reproduce,
        "requests": _requests(trace, f),
        "prices": _price_timeline(trace, f),
        "paths": _paths(trace, f),
        "hidden_fields": _hidden_fields(trace, f),
        "false_positive_notes": f.false_positive_notes,
        "question": rule.question if rule else "",
        "thresholds": _thresholds_for(f.detector),
        "steps": ", ".join(str(i) for i in f.evidence.step_indices),
        "taxonomy": f.taxonomy,
    }


def _timeline(trace: Trace) -> list[dict[str, Any]]:
    return [
        {
            "index": s.index,
            "what": _step_words(s),
            "url": s.url_after,
            "page_load": s.page_load,
            "requests": len(s.requests),
            "blocked": sum(r.blocked_by_gate for r in s.requests),
            "overlays": ", ".join(f"{o.purpose.value} {o.kind.value}" for o in s.overlays),
        }
        for s in trace.steps
    ]


def load_findings(run_dir: Path, trace: Trace) -> FindingSet:
    path = run_dir / "findings.json"
    if path.is_file():
        return read_findings(path)
    from tripwire.detectors.base import finding_set, measurements

    return finding_set(trace, measurements(trace))


def context(run_dir: Path) -> dict[str, Any]:
    trace = read_trace(run_dir / "trace.json")
    fs = load_findings(run_dir, trace)
    cache: dict[int, str | None] = {}
    cards = [_card(run_dir, trace, f, cache) for f in fs.findings]
    measured = [c for c in cards if c["tier"] == Tier.A.value]
    experimental = [c for c in cards if c["tier"] != Tier.A.value]

    summary: dict[str, dict[str, int]] = {}
    for c in cards:
        row = summary.setdefault(c["family"], {"A": 0, "B": 0, "C": 0})
        row[c["tier"]] += 1

    review = [
        {
            "rule": rule,
            "title": plain.RULE_TITLES.get(rule, rule),
            "question": RULES[rule].question if rule in RULES else "",
            "steps": ", ".join(str(i) for i in steps),
        }
        for rule, steps in sorted(fs.review_steps_by_rule.items())
    ]
    findings_json = json.dumps(fs.model_dump(mode="json"), indent=2, ensure_ascii=False)
    return {
        "trace": trace,
        "version": __version__,
        "generated": datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
        "duration_s": round((trace.ended_at - trace.started_at).total_seconds(), 1),
        "measured": measured,
        "experimental": experimental,
        "summary": summary,
        "review": review,
        "timeline": _timeline(trace),
        "rules_checked": [
            {"id": r.id, "title": plain.RULE_TITLES.get(r.id, r.id), "question": r.question}
            for r in RULES.values()
        ],
        "notes": trace.notes,
        "paths": trace.paths,
        "intents": trace.intents,
        "findings_href": "data:application/json;base64,"
        + base64.b64encode(findings_json.encode("utf-8")).decode("ascii"),
        "findings_count": len(cards),
    }


_ENV = Environment(
    loader=PackageLoader("tripwire.report", "templates"),
    autoescape=select_autoescape(["html"]),
    trim_blocks=True,
    lstrip_blocks=True,
)


def build_report(run_dir: Path, out: Path | None = None) -> Path:
    run_dir = Path(run_dir)
    out = out or run_dir / "report.html"
    html = _ENV.get_template("report.html").render(**context(run_dir))
    out.write_text(html, encoding="utf-8")
    return out
