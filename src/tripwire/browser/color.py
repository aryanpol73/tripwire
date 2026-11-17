"""Colour maths for contrast measurements. Pure functions.

Phase 1 needs only opaque sRGB colours (the sandbox computes its own ground truth).
Phase 2 adds parsing computed CSS colours and alpha compositing over ancestors.
"""

from __future__ import annotations

RGB = tuple[int, int, int]


def _linear(channel: int) -> float:
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
