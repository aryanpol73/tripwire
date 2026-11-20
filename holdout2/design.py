"""Hold-out v2 design: skins, cases and what each page renders.

Expected detector results are NOT computed from here: they are typed by hand into
manifest.json (arithmetic in README.md).
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
    banner: str  # "drawer" (left, full height), "sheet" (bottom, full width), "toast" (top right)
    radius: int


SKINS = {
    "forest": Skin(
        "forest",
        "fr_",
        "Verdana, sans-serif",
        (16, 32, 24),
        (22, 44, 33),
        (232, 240, 234),
        (21, 128, 61),
        (74, 100, 86),
        (40, 70, 54),
        "drawer",
        6,
    ),
    "candy": Skin(
        "candy",
        "cy-",
        "'Comic Sans MS', 'Segoe UI', sans-serif",
        (255, 245, 250),
        (255, 255, 255),
        (60, 20, 45),
        (190, 24, 93),
        (214, 178, 198),
        (240, 210, 225),
        "sheet",
        22,
    ),
    "mono": Skin(
        "mono",
        "mo-k-",
        "'Courier New', monospace",
        (255, 255, 255),
        (250, 250, 250),
        (0, 0, 0),
        (0, 0, 0),
        (168, 168, 168),
        (0, 0, 0),
        "toast",
        0,
    ),
}


@dataclass(frozen=True)
class Case:
    id: str
    layout: str  # store, courses, forum
    skin: str
    state: str
    port: int


CASES = [
    Case("holdout2-store-forest-clean", "store", "forest", "clean", 8301),
    Case("holdout2-store-candy-subtle", "store", "candy", "subtle", 8302),
    Case("holdout2-store-mono-blatant", "store", "mono", "blatant", 8303),
    Case("holdout2-courses-candy-clean", "courses", "candy", "clean", 8304),
    Case("holdout2-courses-mono-subtle", "courses", "mono", "subtle", 8305),
    Case("holdout2-courses-forest-blatant", "courses", "forest", "blatant", 8306),
    Case("holdout2-forum-mono-clean", "forum", "mono", "clean", 8307),
    Case("holdout2-forum-forest-subtle", "forum", "forest", "subtle", 8308),
    Case("holdout2-forum-candy-blatant", "forum", "candy", "blatant", 8309),
]


@dataclass(frozen=True)
class Ctl:
    label: str
    w: int
    h: int
    font: int
    kind: str  # primary, plain, faint

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


# Consent: the settings expand inside the same banner (an accordion), so the first-layer
# buttons stay visible after "Manage" is pressed.
CONSENT = {
    "clean": {
        "accept": Ctl("Allow all", 200, 44, 15, "primary"),
        "reject": Ctl("Decline all", 200, 44, 15, "primary"),
        "manage": Ctl("Manage choices", 150, 34, 14, "plain"),
        "hidden_reject": None,
        "on": set(),
    },
    "subtle": {
        "accept": Ctl("Allow all", 280, 48, 16, "primary"),
        "reject": None,
        "manage": Ctl("Manage choices", 150, 34, 14, "plain"),
        "hidden_reject": Ctl("Decline all", 170, 34, 14, "plain"),
        "on": {"analytics", "personalisation"},
    },
    "blatant": {
        "accept": Ctl("Allow all", 340, 54, 18, "primary"),
        "reject": None,
        "manage": Ctl("Manage choices", 120, 18, 11, "faint"),
        "hidden_reject": Ctl("Decline and accept a worse experience", 240, 18, 11, "faint"),
        "on": {"analytics", "ads", "personalisation"},
    },
}
TOGGLES = [
    ("required", "Required (cannot be turned off)"),
    ("analytics", "Analytics"),
    ("ads", "Ads based on your interests"),
    ("personalisation", "Personalised feed"),
]

# --- electronics store -----------------------------------------------------------------
PRODUCTS = [
    ("EAR1", "Wireless earbuds", 149900),
    ("CHG1", "Fast charger", 89900),
    ("USB1", "USB-C cable", 29900),
    ("PWR1", "Power bank", 129900),
]
DELIVERY = 4900
STORE = {
    "clean": {"care": 9900, "care_on": False, "extra": None, "fees": [], "hidden": []},
    "subtle": {
        "care": 9900,
        "care_on": True,
        "extra": None,
        "fees": [("Convenience fee", 1900)],
        "hidden": [("partner_share", "Share my details with partner brands", "offscreen")],
    },
    "blatant": {
        "care": 14900,
        "care_on": True,
        "extra": ("ORG1", "Cable organiser", 7900),
        "fees": [("Packaging fee", 2500), ("Payment handling fee", 3000)],
        "hidden": [
            ("promo_emails", "", "hidden"),
            ("partner_share", "Share my details with partner brands", "offscreen"),
        ],
    },
}

# --- online courses --------------------------------------------------------------------
PLANS = [
    ("Basic", 19900, "Choose Basic"),
    ("Pro", 49900, "Start free trial"),
    ("Team", 99900, "Talk to sales"),
]
CHOSEN = ("Pro", 49900)
EXTRAS = [("certificates", "Certificate pack", 15000), ("mentor", "Mentor sessions", 25000)]
COURSES = {
    "clean": {
        "extras_on": set(),
        "fees": [],
        "renewal": ("plain", 16),
        "hidden": [],
        "entry": "account",
        "entry_ctl": Ctl("Cancel subscription", 180, 40, 14, "plain"),
        "steps": ["confirm"],
    },
    "subtle": {
        "extras_on": {"certificates"},
        "fees": [("Onboarding fee", 9900)],
        "renewal": ("faint", 10),
        "hidden": [("share_progress", "Share my progress with partner universities", "offscreen")],
        "entry": "billing_body",  # small and faint, inside the Billing page body
        "entry_ctl": Ctl("Cancel subscription", 120, 16, 11, "faint"),
        "steps": ["survey", "pause", "confirm"],
    },
    "blatant": {
        "extras_on": {"certificates", "mentor"},
        "fees": [("Onboarding fee", 19900), ("Platform fee", 4900)],
        "renewal": None,
        "hidden": [
            ("marketing_updates", "", "hidden"),
            ("share_progress", "Share my progress with partner universities", "offscreen"),
        ],
        "entry": "billing_footer",
        "entry_ctl": Ctl("Cancel subscription", 110, 14, 10, "faint"),
        "steps": ["survey", "pause", "sure", "email"],
    },
}
TRIAL_END = "27 Nov 2026"
SUPPORT_EMAIL = "support@learnly.example"
