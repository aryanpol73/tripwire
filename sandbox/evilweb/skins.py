"""Four skins: same patterns, different theme, class names, ids, nesting, order and wording.

A detector or walker that depends on a class name, an element order or exact button text
will break on at least one skin. That is the point.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from tripwire.browser.color import RGB, css_rgb


@dataclass(frozen=True)
class Palette:
    page: RGB  # page background
    surface: RGB  # cards, banners, dialogs
    text: RGB
    primary: RGB  # the "yes" button
    on_primary: RGB  # text on the primary button (>= 4.5:1 on every skin)
    muted: RGB  # faint text (< 3:1 on surface on every skin)
    border: RGB


@dataclass(frozen=True)
class Skin:
    number: int
    name: str
    prefix: str  # prepended to every class and id
    font: str
    palette: Palette
    banner_position: Literal["bottom", "top", "center", "side"]
    nesting: int  # extra wrapper divs around interactive groups
    reverse_buttons: bool  # flip the order of button groups
    nav_in_sidebar: bool
    words: Mapping[str, str]

    def c(self, *names: str) -> str:
        return " ".join(f"{self.prefix}{n}" for n in names)

    def id(self, name: str) -> str:
        return f"{self.prefix}{name}"

    def w(self, key: str) -> str:
        return self.words[key]


_WORDS_1 = {
    "accept": "Accept all",
    "reject": "Reject all",
    "manage": "Manage options",
    "more": "Legitimate interest",
    "save": "Save choices",
    "add_to_cart": "Add to cart",
    "checkout": "Checkout",
    "continue": "Continue",
    "proceed_payment": "Proceed to payment",
    "start_trial": "Start free trial",
    "confirm_trial": "Start my trial",
    "upgrade": "Upgrade",
    "cancel_plan": "Cancel plan",
    "subscribe": "Subscribe",
    "unsubscribe": "Unsubscribe",
    "confirm": "Confirm",
    "settings": "Settings",
    "billing": "Billing",
}

SKINS: dict[int, Skin] = {
    1: Skin(
        1,
        "Harbor",
        "hb-",
        "Georgia, 'Times New Roman', serif",
        Palette(
            page=(246, 247, 249),
            surface=(255, 255, 255),
            text=(17, 17, 17),
            primary=(0, 82, 204),
            on_primary=(255, 255, 255),
            muted=(170, 170, 170),
            border=(210, 214, 220),
        ),
        "bottom",
        0,
        False,
        False,
        _WORDS_1,
    ),
    2: Skin(
        2,
        "Ember",
        "em_",
        "'Segoe UI', Roboto, Arial, sans-serif",
        Palette(
            page=(24, 24, 27),
            surface=(39, 39, 42),
            text=(244, 244, 245),
            primary=(194, 65, 12),
            on_primary=(255, 255, 255),
            muted=(90, 90, 96),
            border=(63, 63, 70),
        ),
        "center",
        2,
        True,
        True,
        {
            **_WORDS_1,
            "accept": "Allow all",
            "reject": "Decline all",
            "manage": "Cookie settings",
            "more": "Vendor preferences",
            "save": "Save preferences",
            "add_to_cart": "Add to bag",
            "checkout": "Go to checkout",
            "continue": "Next",
            "proceed_payment": "Continue to payment",
            "start_trial": "Try it free",
            "confirm_trial": "Begin trial",
            "upgrade": "Go Pro",
            "cancel_plan": "End subscription",
            "subscribe": "Sign me up",
            "unsubscribe": "Opt out",
            "confirm": "Yes, confirm",
            "settings": "Preferences",
            "billing": "Payments",
        },
    ),
    3: Skin(
        3,
        "Moss",
        "ms",
        "Verdana, Geneva, sans-serif",
        Palette(
            page=(236, 238, 230),
            surface=(250, 250, 245),
            text=(30, 41, 59),
            primary=(21, 128, 61),
            on_primary=(255, 255, 255),
            muted=(168, 170, 160),
            border=(200, 204, 190),
        ),
        "top",
        1,
        False,
        False,
        {
            **_WORDS_1,
            "accept": "Agree",
            "reject": "Disagree",
            "manage": "Customise",
            "more": "More choices",
            "save": "Confirm my choices",
            "add_to_cart": "Add to basket",
            "checkout": "Proceed to checkout",
            "proceed_payment": "Pay securely",
            "start_trial": "Get started free",
            "confirm_trial": "Activate trial",
            "upgrade": "Upgrade plan",
            "cancel_plan": "Cancel subscription",
            "subscribe": "Join newsletter",
            "unsubscribe": "Leave newsletter",
            "settings": "Account settings",
            "billing": "Billing and plan",
        },
    ),
    4: Skin(
        4,
        "Slate",
        "sl-x-",
        "'Courier New', Courier, monospace",
        Palette(
            page=(226, 232, 240),
            surface=(241, 245, 249),
            text=(15, 23, 42),
            primary=(15, 23, 42),
            on_primary=(255, 255, 255),
            muted=(160, 166, 176),
            border=(203, 213, 225),
        ),
        "side",
        3,
        True,
        True,
        {
            **_WORDS_1,
            "accept": "Accept cookies",
            "reject": "Only necessary",
            "manage": "Preferences",
            "more": "Advanced",
            "save": "Apply",
            "add_to_cart": "Add item",
            "checkout": "Checkout now",
            "continue": "Proceed",
            "proceed_payment": "Go to payment",
            "start_trial": "Start trial",
            "confirm_trial": "Confirm trial",
            "cancel_plan": "Cancel membership",
            "settings": "Settings",
            "billing": "Plan and billing",
        },
    ),
}


def stylesheet(skin: Skin) -> str:
    """Cosmetic CSS for a skin. Measured controls carry their exact size and colours inline,
    so ground truth never depends on this stylesheet."""
    p = skin.palette
    c = skin.prefix
    banner_pos = {
        "bottom": "left:0;right:0;bottom:0;",
        "top": "left:0;right:0;top:0;",
        "center": "left:50%;top:50%;transform:translate(-50%,-50%);width:640px;",
        "side": "right:0;top:0;bottom:0;width:460px;",
    }[skin.banner_position]
    return f"""
*{{box-sizing:border-box}}
body{{margin:0;font-family:{skin.font};background:{css_rgb(p.page)};color:{css_rgb(p.text)}}}
a{{color:{css_rgb(p.text)}}}
.{c}layout{{display:flex;flex-direction:{"row" if skin.nav_in_sidebar else "column"};min-height:100vh}}
.{c}header{{background:{css_rgb(p.surface)};border-bottom:1px solid {css_rgb(p.border)};padding:12px 24px;display:flex;gap:16px;align-items:center;flex-direction:{"column" if skin.nav_in_sidebar else "row"};{"width:200px;align-items:flex-start;border-right:1px solid " + css_rgb(p.border) if skin.nav_in_sidebar else ""}}}
.{c}brand{{font-weight:bold;font-size:20px}}
.{c}nav{{display:flex;gap:12px;flex-direction:{"column" if skin.nav_in_sidebar else "row"}}}
.{c}body{{flex:1;display:flex;flex-direction:column}}
.{c}main{{flex:1;padding:24px;max-width:960px}}
.{c}card{{background:{css_rgb(p.surface)};border:1px solid {css_rgb(p.border)};padding:16px;margin:12px 0;border-radius:6px}}
.{c}row{{display:flex;gap:12px;align-items:center;flex-wrap:wrap;flex-direction:{"row-reverse" if skin.reverse_buttons else "row"};justify-content:flex-end}}
.{c}ctl{{border:1px solid {css_rgb(p.border)};border-radius:6px;cursor:pointer;display:inline-flex;align-items:center;justify-content:center;padding:0;text-decoration:none;font-family:inherit}}
.{c}btn{{background:{css_rgb(p.primary)};color:{css_rgb(p.on_primary)};border:none;border-radius:6px;padding:10px 18px;font-size:15px;cursor:pointer;text-decoration:none;display:inline-block;font-family:inherit}}
.{c}linkctl{{border:none;background:none;cursor:pointer;padding:0;text-decoration:underline;font-family:inherit;display:inline-flex;align-items:center}}
.{c}footer{{border-top:1px solid {css_rgb(p.border)};padding:16px 24px;font-size:13px;display:flex;gap:16px;flex-wrap:wrap}}
.{c}banner{{position:fixed;{banner_pos}background:{css_rgb(p.surface)};border:1px solid {css_rgb(p.border)};padding:20px;z-index:1000;box-shadow:0 4px 24px rgba(0,0,0,.25)}}
.{c}layer[hidden]{{display:none}}
.{c}toggle{{display:flex;gap:8px;align-items:center;margin:6px 0}}
.{c}field{{display:flex;flex-direction:column;gap:4px;margin:10px 0;max-width:420px}}
.{c}field input,.{c}field select{{padding:8px;font-size:15px}}
.{c}price{{display:flex;justify-content:space-between;max-width:420px;padding:4px 0}}
.{c}total{{font-weight:bold;border-top:1px solid {css_rgb(p.border)};margin-top:6px;padding-top:6px}}
.{c}modal{{position:fixed;inset:0;background:rgba(0,0,0,.45);display:flex;align-items:center;justify-content:center;z-index:900}}
.{c}modal-box{{background:{css_rgb(p.surface)};padding:24px;border-radius:8px;width:440px}}
.{c}offscreen{{position:absolute;left:-9999px;top:auto}}
.{c}sandbox{{background:#b91c1c;color:#fff;font-size:40px;font-weight:bold;text-align:center;padding:40px}}
"""
