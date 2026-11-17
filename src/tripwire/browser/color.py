"""Colour maths for contrast measurements. Pure functions.

The sandbox uses opaque sRGB colours to write ground truth. The browser layer parses
computed CSS colours and composites transparent backgrounds before measuring contrast.
"""

from __future__ import annotations

import re

RGB = tuple[int, int, int]


def _linear(channel: float) -> float:
    if not 0 <= channel <= 255:
        raise ValueError(f"colour channel out of range 0-255: {channel}")
    c = channel / 255
    # sRGB gamma expansion, as defined by WCAG 2.x.
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def relative_luminance(rgb: RGB) -> float:
    r, g, b = (_linear(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(a: RGB, b: RGB) -> float:
    """WCAG contrast ratio, from 1.0 (identical) to 21.0 (black on white)."""
    lighter, darker = sorted((relative_luminance(a), relative_luminance(b)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def css_rgb(rgb: RGB) -> str:
    r, g, b = rgb
    return f"rgb({r}, {g}, {b})"


# --- Computed CSS colours and alpha compositing ------------------------------------

RGBA = tuple[float, float, float, float]  # r, g, b in 0-255; alpha in 0-1
CANVAS = (255.0, 255.0, 255.0)  # browsers paint an unstyled page white

_NUM = r"\s*([\d.]+%?)\s*"
_RGB_RE = re.compile(rf"^rgba?\({_NUM}[,\s]{_NUM}[,\s]{_NUM}(?:[,/]{_NUM})?\)$")


def _channel(token: str) -> float:
    return float(token[:-1]) * 2.55 if token.endswith("%") else float(token)


def _alpha(token: str | None) -> float:
    if token is None:
        return 1.0
    return float(token[:-1]) / 100 if token.endswith("%") else float(token)


def parse_css_color(text: str) -> RGBA | None:
    """Parse a computed colour: rgb()/rgba() (comma or space syntax), #hex or transparent.
    Returns None for anything else (named colours, gradients, images): the caller then
    treats the contrast as unmeasurable instead of guessing."""
    value = text.strip().lower()
    if value == "transparent":
        return (0.0, 0.0, 0.0, 0.0)
    if value.startswith("#") and len(value) in (4, 7, 9):
        digits = value[1:]
        if len(digits) == 3:
            digits = "".join(d * 2 for d in digits)
        try:
            parts = [int(digits[i : i + 2], 16) for i in range(0, len(digits), 2)]
        except ValueError:
            return None
        alpha = parts[3] / 255 if len(parts) == 4 else 1.0
        return (float(parts[0]), float(parts[1]), float(parts[2]), alpha)
    m = _RGB_RE.match(value.replace(" / ", "/").replace(", ", ","))
    if not m:
        return None
    r, g, b, a = m.groups()
    return (_channel(r), _channel(g), _channel(b), _alpha(a))


def composite(top: RGBA, bottom: tuple[float, float, float]) -> tuple[float, float, float]:
    """Paint a (possibly transparent) colour over an opaque one."""
    a = top[3]
    return tuple(a * t + (1 - a) * b for t, b in zip(top[:3], bottom, strict=True))  # type: ignore[return-value]


def effective_background(layers: list[RGBA]) -> tuple[float, float, float]:
    """The colour actually behind an element.

    layers: background colours from the element itself outward to <html>. They are painted
    from the outermost inward over the white canvas.
    """
    colour = CANVAS
    for layer in reversed(layers):
        colour = composite(layer, colour)
    return colour


def text_contrast(fg: RGBA, bg_layers: list[RGBA], opacity: float = 1.0) -> float:
    """WCAG contrast of text colour fg over the composited background.

    opacity is the element's own effective opacity. It is applied to the text only, which
    slightly overstates contrast when a whole faded element sits on a different colour.
    """
    bg = effective_background(bg_layers)
    text = composite((fg[0], fg[1], fg[2], fg[3] * opacity), bg)
    return contrast_ratio(text, bg)  # type: ignore[arg-type]
