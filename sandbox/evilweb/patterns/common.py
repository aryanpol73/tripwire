"""Building blocks shared by the pattern modules."""

from __future__ import annotations

from dataclasses import dataclass

from evilweb.skins import Skin
from tripwire.browser.color import RGB, contrast_ratio, css_rgb
from tripwire.schemas.trace import SiteType


@dataclass(frozen=True)
class Control:
    """A measured control. Its size and colours are rendered inline, so what the browser
    computes is exactly what the ground truth says."""

    label: str
    width: int
    height: int
    font_px: int
    fg: RGB
    bg: RGB

    @property
    def area(self) -> int:
        return self.width * self.height

    @property
    def contrast(self) -> float:
        return round(contrast_ratio(self.fg, self.bg), 2)

    @property
    def style(self) -> str:
        return (
            f"width:{self.width}px;height:{self.height}px;font-size:{self.font_px}px;"
            f"color:{css_rgb(self.fg)};background-color:{css_rgb(self.bg)}"
        )


def primary(skin: Skin, label: str, width: int, height: int, font_px: int) -> Control:
    p = skin.palette
    return Control(label, width, height, font_px, p.on_primary, p.primary)


def secondary(skin: Skin, label: str, width: int, height: int, font_px: int) -> Control:
    p = skin.palette
    return Control(label, width, height, font_px, p.text, p.surface)


def muted(skin: Skin, label: str, width: int, height: int, font_px: int) -> Control:
    p = skin.palette
    return Control(label, width, height, font_px, p.muted, p.surface)


@dataclass(frozen=True)
class FormOptIn:
    """An opt-in a form submits. Visible ones are rendered as checkboxes; hidden and
    off-screen ones are what sneaking.bundled_optins looks for."""

    name: str
    label: str
    checked: bool
    visibility: str  # "visible", "hidden" (type=hidden input) or "offscreen"


CSRF_DECOY = FormOptIn("csrf_token", "", True, "hidden")  # value redacted in traces
REMEMBER_ME_DECOY = FormOptIn("remember_me", "Remember me on this device", True, "visible")


def format_inr(minor: int) -> str:
    """12345650 -> '₹1,23,456.50'; whole rupees drop the paise."""
    sign = "-" if minor < 0 else ""
    rupees, paise = divmod(abs(minor), 100)
    digits = str(rupees)
    if len(digits) > 3:
        head, tail = digits[:-3], digits[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        digits = ",".join([*groups, tail])
    text = f"{sign}₹{digits}"
    return f"{text}.{paise:02d}" if paise else text


SITE_NAMES = {
    SiteType.SHOP: "Kirana Goods",
    SiteType.NEWS: "The Daily Ledger",
    SiteType.SAAS: "TaskForge",
}
