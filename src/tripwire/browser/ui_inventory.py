"""Measure a live page: run the collector in every frame and build Trace models.

The JavaScript only reads raw values. All interpretation (contrast, purposes, redaction)
happens here in Python, where it is unit-tested.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import cache
from importlib.resources import files
from typing import Any

from playwright.sync_api import Frame, Page

from tripwire.browser.color import effective_background, parse_css_color, text_contrast
from tripwire.browser.consent import control_purpose, overlay_purpose
from tripwire.browser.price_parse import ParsedPrice, parse_price
from tripwire.browser.redact import REDACTED, redact_value
from tripwire.schemas.common import BoundingBox
from tripwire.schemas.trace import (
    Form,
    FormField,
    Overlay,
    OverlayControl,
    OverlayKind,
    Style,
    Timer,
    UiElement,
)


@cache
def collector_js() -> str:
    return files("tripwire.browser").joinpath("js/collect.js").read_text(encoding="utf-8")


@dataclass
class PriceCandidate:
    text: str
    row_text: str
    struck: list[str]
    bbox: BoundingBox
    parsed: ParsedPrice | None


@dataclass
class PageObservation:
    url: str
    title: str
    elements: list[UiElement] = field(default_factory=list)
    overlays: list[Overlay] = field(default_factory=list)
    forms: list[Form] = field(default_factory=list)
    timers: list[Timer] = field(default_factory=list)
    prices: list[PriceCandidate] = field(default_factory=list)

    def element(self, element_id: str) -> UiElement:
        return next(e for e in self.elements if e.id == element_id)


def _bbox(raw: dict, dx: float = 0, dy: float = 0) -> BoundingBox:
    return BoundingBox(x=raw["x"] + dx, y=raw["y"] + dy, width=raw["width"], height=raw["height"])


def _rgb_text(rgb: tuple[float, float, float]) -> str:
    r, g, b = (round(c) for c in rgb)
    return f"rgb({r}, {g}, {b})"


def _element(raw: dict, prefix: str, dx: float, dy: float) -> UiElement:
    layers = [parse_css_color(c) for c in raw["bgLayers"]]
    fg = parse_css_color(raw["color"])
    measurable = fg is not None and not raw["bgImage"] and None not in layers and raw["visible"]
    contrast = None
    if measurable:
        contrast = min(21.0, max(1.0, round(text_contrast(fg, layers, raw["opacity"]), 2)))  # type: ignore[arg-type]
    background = _rgb_text(effective_background([c for c in layers if c is not None]))
    return UiElement(
        id=prefix + raw["id"],
        role=raw["role"],
        text=raw["text"],
        accessible_name=raw["name"],
        bbox=_bbox(raw["bbox"], dx, dy),
        style=Style(
            font_size_px=raw["fontSize"],
            color=raw["color"],
            background_color=background,
            opacity=min(1.0, max(0.0, raw["opacity"])),
            visible=raw["visible"],
        ),
        contrast_ratio=contrast,
        checked=raw["checked"],
        selected=raw["selected"],
        disabled=raw["disabled"],
        in_viewport=raw["inViewport"],
        z_order=raw["z"],
        tree_depth=raw["depth"],
        landmark=raw["landmark"],
    )


def _overlay(raw: dict, prefix: str, visible: set[str], names: dict[str, str]) -> Overlay:
    dialog = raw["ariaModal"] or raw["role"] in ("dialog", "alertdialog") or raw["tag"] == "dialog"
    if raw["blocks"]:
        kind = OverlayKind.MODAL if dialog else OverlayKind.INTERSTITIAL
    else:
        kind = OverlayKind.BANNER
    controls = [prefix + c for c in raw["controls"] if prefix + c in visible]
    return Overlay(
        id=prefix + raw["id"],
        kind=kind,
        purpose=overlay_purpose(f"{raw.get('label') or ''} {raw['text']}"),
        bbox=_bbox(raw["bbox"]),
        viewport_coverage=round(raw["coverage"], 4),
        blocks_interaction=raw["blocks"],
        controls=[
            OverlayControl(element_id=c, purpose=control_purpose(names[c])) for c in controls
        ],
    )


def _field_value(raw: dict) -> str | None:
    value = raw["defaultValue"]
    if value is None:
        return None
    if raw["type"] == "password":
        return REDACTED
    return redact_value(raw["name"], value)


def _form(raw: dict, prefix: str, known: set[str]) -> Form:
    def ref(element_id: str | None) -> str | None:
        return prefix + element_id if element_id and prefix + element_id in known else None

    return Form(
        id=prefix + raw["id"],
        action_url=raw["action"],
        method=raw["method"],
        submit_element_id=ref(raw["submitId"]),
        fields=[
            FormField(
                name=f["name"],
                type=f["type"],
                label=f["label"],
                default_value=_field_value(f),
                prechecked=f["prechecked"],
                hidden=f["hidden"],
                off_screen=f["offScreen"],
                required=f["required"],
                element_id=ref(f["elementId"]),
            )
            for f in raw["fields"]
        ],
    )


def _collect_frame(frame: Frame) -> dict[str, Any] | None:
    try:
        return frame.evaluate(collector_js())
    except Exception:  # detached or navigating frame: skip it rather than fail the step
        return None


def collect_page(page: Page) -> PageObservation:
    main = _collect_frame(page.main_frame)
    if main is None:
        raise RuntimeError("could not measure the page")
    obs = PageObservation(url=main["url"], title=main["title"])
    raw_frames: list[tuple[str, dict, float, float]] = [("", main, 0.0, 0.0)]
    scroll = page.evaluate("() => [window.scrollX, window.scrollY]")
    for k, frame in enumerate(page.frames[1:], start=1):
        data = _collect_frame(frame)
        element = frame.frame_element() if data else None
        box = element.bounding_box() if element else None
        if data is None or box is None:
            continue
        raw_frames.append((f"f{k}", data, box["x"] + scroll[0], box["y"] + scroll[1]))

    for prefix, data, dx, dy in raw_frames:
        obs.elements += [_element(e, prefix, dx, dy) for e in data["elements"]]
    known = {e.id for e in obs.elements}
    visible = {e.id for e in obs.elements if e.style.visible}
    names = {e.id: e.accessible_name or e.text for e in obs.elements}

    overlays = [_overlay(o, "", visible, names) for o in main["overlays"]]
    # A consent banner rendered inside an iframe: the iframe element is the overlay in the
    # main frame, and its controls live in the child frame.
    for prefix, data, dx, dy in raw_frames[1:]:
        for i, o in enumerate(overlays):
            b = o.bbox
            if b.x - 1 <= dx <= b.x + b.width and b.y - 1 <= dy <= b.y + b.height:
                extra = [e for e in data["elements"] if prefix + e["id"] in visible]
                text = " ".join(e["text"] or "" for e in data["elements"])
                controls = [
                    OverlayControl(
                        element_id=prefix + e["id"],
                        purpose=control_purpose(names[prefix + e["id"]]),
                    )
                    for e in extra
                ]
                purpose = o.purpose if o.purpose != "other" else overlay_purpose(text)
                overlays[i] = o.model_copy(
                    update={"controls": o.controls + controls, "purpose": purpose}
                )
    obs.overlays = overlays

    for prefix, data, _, _ in raw_frames:
        obs.forms += [_form(f, prefix, known) for f in data["forms"]]
        obs.timers += [
            Timer(
                element_id=prefix + t["elementId"]
                if t["elementId"] and prefix + t["elementId"] in known
                else None,
                text=t["text"],
                pattern=t["pattern"],
                seconds_remaining=t["seconds"],
            )
            for t in data["timers"]
        ]
        obs.prices += [
            PriceCandidate(
                text=p["text"],
                row_text=p["rowText"],
                struck=p["struck"],
                bbox=_bbox(p["bbox"], dx, dy),
                parsed=parse_price(p["text"], struck_texts=p["struck"]),
            )
            for p in data["prices"]
        ]
    return obs
