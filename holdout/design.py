"""The hold-out design: skins, cases and the values each page renders.

These are the *page* settings. The expected detector results are NOT computed from here:
they are typed by hand into manifest.json (see README.md for the arithmetic).
"""

from __future__ import annotations

from dataclasses import dataclass

RGB = tuple[int, int, int]


def rgb(c: RGB) -> str:
    return f"rgb({c[0]}, {c[1]}, {c[2]})"


@dataclass(frozen=True)
class Skin:
    name: str
    prefix: str
    font: str
    page: RGB
    surface: RGB
    text: RGB
    primary: RGB
    muted: RGB
    border: RGB
    banner: str  # "corner" (floating bottom-left card), "topbar", "modal" (with backdrop)
    radius: int


SKINS = {
    "dune": Skin(
        "dune",
        "dn-",
        "'Trebuchet MS', Tahoma, sans-serif",
        (250, 246, 240),
        (255, 252, 247),
        (51, 38, 25),
        (154, 52, 18),
        (190, 178, 164),
        (226, 214, 198),
        "corner",
        14,
    ),
    "ocean": Skin(
        "ocean",
        "oc__",
        "Tahoma, Geneva, sans-serif",
        (10, 25, 41),
        (16, 42, 67),
        (226, 236, 245),
        (3, 105, 161),
        (62, 92, 118),
        (35, 64, 92),
        "topbar",
        2,
    ),
    "paper": Skin(
        "paper",
        "pp-",
        "'Palatino Linotype', Palatino, serif",
        (245, 245, 245),
        (255, 255, 255),
        (33, 33, 33),
        (21, 94, 117),
        (178, 178, 178),
        (220, 220, 220),
        "modal",
        0,
    ),
}


@dataclass(frozen=True)
class Case:
    id: str
    layout: str  # grocery, streaming, magazine
    skin: str
    state: str  # clean, subtle, blatant
    port: int


# Latin square: each layout meets each skin once and each state once.
CASES = [
    Case("holdout-grocery-dune-clean", "grocery", "dune", "clean", 8201),
    Case("holdout-grocery-ocean-subtle", "grocery", "ocean", "subtle", 8202),
    Case("holdout-grocery-paper-blatant", "grocery", "paper", "blatant", 8203),
    Case("holdout-streaming-ocean-clean", "streaming", "ocean", "clean", 8204),
    Case("holdout-streaming-paper-subtle", "streaming", "paper", "subtle", 8205),
    Case("holdout-streaming-dune-blatant", "streaming", "dune", "blatant", 8206),
    Case("holdout-magazine-paper-clean", "magazine", "paper", "clean", 8207),
    Case("holdout-magazine-dune-subtle", "magazine", "dune", "subtle", 8208),
    Case("holdout-magazine-ocean-blatant", "magazine", "ocean", "blatant", 8209),
]


# --- a measured control: exact size and colours, rendered inline -------------------


@dataclass(frozen=True)
class Ctl:
    label: str
    w: int
    h: int
    font: int
    kind: str  # "primary" (white on primary), "plain" (text on surface), "faint" (muted)

    def style(self, skin: Skin) -> str:
        fg, bg = {
            "primary": ((255, 255, 255), skin.primary),
            "plain": (skin.text, skin.surface),
            "faint": (skin.muted, skin.surface),
        }[self.kind]
        return (
            f"width:{self.w}px;height:{self.h}px;font-size:{self.font}px;"
            f"color:{rgb(fg)};background-color:{rgb(bg)}"
        )


# --- consent banner, per state ------------------------------------------------------
# Layer 1 and 2 controls. Clean is used on every layout where consent is not planted.

CONSENT = {
    "clean": {
        "layer1": {
            "accept": Ctl("Accept all cookies", 220, 46, 15, "primary"),
            "reject": Ctl("Reject all cookies", 220, 46, 15, "primary"),
            "more": Ctl("Cookie settings", 140, 30, 14, "plain"),
        },
        "layer2": {
            "accept": Ctl("Accept all cookies", 220, 46, 15, "primary"),
            "reject": Ctl("Reject all cookies", 220, 46, 15, "primary"),
            "save": Ctl("Save selection", 140, 30, 14, "plain"),
        },
        "on": set(),
    },
    "subtle": {
        "layer1": {
            "accept": Ctl("Accept all cookies", 300, 50, 16, "primary"),
            "more": Ctl("Customise", 150, 36, 14, "plain"),
        },
        "layer2": {
            "accept": Ctl("Accept all cookies", 300, 50, 16, "primary"),
            "reject": Ctl("Refuse all", 160, 32, 14, "plain"),
            "save": Ctl("Save selection", 160, 32, 14, "plain"),
        },
        "on": {"audience"},
    },
    "blatant": {
        "layer1": {
            "accept": Ctl("Accept all cookies", 360, 56, 18, "primary"),
            "more": Ctl("More options", 110, 18, 11, "faint"),
        },
        "layer2": {
            "accept": Ctl("Accept all cookies", 360, 56, 18, "primary"),
            "reject": Ctl("No thanks, I don't care about my privacy", 220, 18, 11, "faint"),
            "save": Ctl("Save selection", 110, 18, 11, "faint"),
        },
        "on": {"audience", "advertising", "social"},
    },
}

TOGGLES = [
    ("essential", "Essential (always on)"),
    ("audience", "Audience measurement"),
    ("advertising", "Advertising"),
    ("social", "Social media features"),
]


# --- grocery (reach_payment, sneaking planted) ---------------------------------------

PRODUCTS = [
    ("BAN6", "Bananas (6)", 4500),
    ("BRD1", "Brown bread", 5500),
    ("MLK1", "Milk 1 L", 6800),
    ("EGG12", "Eggs (12)", 9600),
]
DELIVERY = 2500

GROCERY = {
    "clean": {"tip": 2000, "tip_on": False, "bag": None, "fees": [], "hidden": []},
    "subtle": {
        "tip": 1000,
        "tip_on": True,
        "bag": None,
        "fees": [("Platform fee", 400)],
        "hidden": [("share_order_data", "Share my order data with partners", "offscreen")],
    },
    "blatant": {
        "tip": 3000,
        "tip_on": True,
        "bag": ("BAG1", "Reusable bag", 1500),
        "fees": [("Small cart fee", 3000), ("Platform fee", 800), ("Surge fee", 1200)],
        "hidden": [
            ("marketing_optin", "", "hidden"),
            ("share_order_data", "Share my order data with partners", "offscreen"),
        ],
    },
}


# --- streaming (sign_up_and_leave, obstruction + sneaking planted) --------------------

PLANS = [("Basic", 14900), ("Standard", 29900), ("Premium", 49900)]
CHOSEN_PLAN = ("Standard", 29900)
ADDONS = [("uhd", "4K Ultra HD", 10000), ("screen", "Extra screen", 5000)]

STREAMING = {
    "clean": {
        "addons_on": set(),
        "fees": [],
        "renewal": ("plain", 16),
        "hidden": [],
        "entry": "account",  # Cancel next to Change plan on the account page
        "entry_ctl": Ctl("Cancel membership", 170, 42, 15, "plain"),
        "steps": ["confirm"],
    },
    "subtle": {
        "addons_on": {"uhd"},
        "fees": [("Activation fee", 4900)],
        "renewal": ("faint", 11),
        "hidden": [("share_history", "Share my viewing history with partners", "offscreen")],
        "entry": "footer",  # only in the footer of the Subscription page
        "entry_ctl": Ctl("Cancel membership", 140, 18, 13, "plain"),
        "steps": ["survey", "retention", "confirm"],
    },
    "blatant": {
        "addons_on": {"uhd", "screen"},
        "fees": [("Activation fee", 9900), ("Service fee", 2000)],
        "renewal": None,  # no renewal price or date anywhere before confirming
        "hidden": [
            ("marketing_consent", "", "hidden"),
            ("share_history", "Share my viewing history with partners", "offscreen"),
        ],
        "entry": "footer",
        "entry_ctl": Ctl("Cancel membership", 110, 14, 10, "faint"),
        "steps": ["survey", "retention", "sure", "phone"],
    },
}
RENEWAL_DATE = "20 Dec 2026"
SUPPORT_PHONE = "1800 200 3000"
