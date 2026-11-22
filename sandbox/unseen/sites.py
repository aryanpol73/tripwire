"""Three site layouts the LLM explorer was not developed against (Phase 6 exit check).

They differ from the Evil Web sandbox in site type, page structure and, deliberately, in
wording: "Reserve this tour" instead of "add to cart", "Count me in" instead of
"subscribe", "End membership" behind "Membership & billing" instead of "Cancel
subscription" under "Billing". The scripted walker's vocabulary does not cover them.

Each layout declares its own end-state text (what the site says when the leave flow is
over) and its payment control, as ground truth for the completion check.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse, RedirectResponse

from tripwire.schemas.trace import SiteType


def _doc(title: str, css: str, body: str) -> str:
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>{title}</title><style>{css}</style></head><body>{body}</body></html>"
    )


def _app() -> FastAPI:
    return FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


def _see(path: str) -> RedirectResponse:
    return RedirectResponse(path, status_code=303)


# --- 1. Wanderly: tour booking ----------------------------------------------------------

WANDERLY_CSS = """
body{margin:0;font-family:Verdana,sans-serif;background:#f4f7f6;color:#1d2b2a}
.top{background:#0f5c55;color:#fff;padding:10px 20px;display:flex;gap:18px;align-items:center}
.top a{color:#d9f2ee}.wrap{max-width:900px;margin:20px auto;padding:0 16px}
.tours{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}
.tour{background:#fff;border-radius:8px;padding:14px;box-shadow:0 1px 3px #0002}
.cta{background:#e07a1f;color:#fff;border:0;padding:10px 16px;border-radius:6px;font-size:15px}
table{border-collapse:collapse}td{padding:4px 12px}
#cmp{position:fixed;right:16px;bottom:16px;width:330px;background:#fff;z-index:50;
 border-radius:10px;box-shadow:0 4px 18px #0004;padding:14px}
#cmp .agree{background:#0f5c55;color:#fff;border:0;padding:10px 18px;font-size:15px}
#cmp .nec{background:none;border:0;color:#999;font-size:11px;text-decoration:underline}
"""
TOURS = {
    "coastal-walk": ("Coastal cliff walk", 320000),
    "hill-fort": ("Hill fort day trip", 245000),
    "food-tour": ("Old town food tour", 180000),
}


def _rs(minor: int) -> str:
    return f"\u20b9{minor // 100:,}"


def _wanderly_page(title: str, body: str) -> str:
    cmp = (
        "<div id='cmp' role='dialog' aria-label='Privacy choices'>"
        "<p>Wanderly and our partners use cookies to personalise trips and measure ads.</p>"
        "<button class='agree' onclick='cmpDone()'>Agree and close</button> "
        "<button class='nec' onclick='cmpDone()'>Only necessary</button></div>"
        "<script>function cmpDone(){document.cookie='wl_cmp=1;path=/';"
        "document.getElementById('cmp').remove()}"
        "if(document.cookie.includes('wl_cmp=1'))document.getElementById('cmp').remove()"
        "</script>"
    )
    nav = (
        "<div class='top'><strong><a href='/'>Wanderly</a></strong>"
        "<a href='/destinations'>Destinations</a><a href='/journal'>Travel journal</a>"
        "<a href='/help'>Help centre</a><a href='/about'>About us</a></div>"
    )
    return _doc(title, WANDERLY_CSS, nav + f"<div class='wrap'>{body}</div>" + cmp)


def wanderly() -> FastAPI:
    app = _app()

    @app.get("/", response_class=HTMLResponse)
    def home() -> str:
        cards = "".join(
            f"<div class='tour'><h3><a href='/tour/{slug}'>{name}</a></h3>"
            f"<p>From <b>{_rs(price)}</b> per person</p></div>"
            for slug, (name, price) in TOURS.items()
        )
        return _wanderly_page(
            "Wanderly - small group tours",
            f"<h1>Small group tours</h1><div class='tours'>{cards}</div>",
        )

    @app.get("/tour/{slug}", response_class=HTMLResponse)
    def tour(slug: str) -> str:
        name, price = TOURS[slug]
        return _wanderly_page(
            name,
            f"<h1>{name}</h1><p>Six hours, small group, local guide."
            f"</p><p>Price: <b>{_rs(price)}</b></p>"
            f"<form method='post' action='/trip/add'><input type='hidden' "
            f"name='slug' value='{slug}'><button class='cta'>Reserve this "
            f"tour</button></form>",
        )

    @app.post("/trip/add")
    def add(slug: str = Form(...)) -> RedirectResponse:
        return _see(f"/trip?tour={slug}")

    @app.get("/trip", response_class=HTMLResponse)
    def trip(tour: str = "food-tour") -> str:
        name, price = TOURS[tour]
        return _wanderly_page(
            "Your trip",
            f"<h1>Your trip</h1><table><tr><td>{name} \u00d7 1"
            f"</td><td>{_rs(price)}</td></tr><tr><td>Total</td><td>"
            f"{_rs(price)}</td></tr></table><p><a class='cta' href='/"
            f"travellers?tour={tour}'>Continue to traveller details</a></p>",
        )

    @app.get("/travellers", response_class=HTMLResponse)
    def travellers(tour: str = "food-tour") -> str:
        return _wanderly_page(
            "Traveller details",
            "<h1>Who is travelling?</h1>"
            f"<form method='post' action='/travellers?tour={tour}'>"
            "<p><label>Full name <input name='full_name' required></label></p>"
            "<p><label>Email <input type='email' name='email' required>"
            "</label></p><p><label>Mobile number <input type='tel' "
            "name='mobile' required></label></p>"
            "<button class='cta'>Review booking</button></form>",
        )

    @app.post("/travellers")
    def travellers_post(tour: str = "food-tour") -> RedirectResponse:
        return _see(f"/review?tour={tour}")

    @app.get("/review", response_class=HTMLResponse)
    def review(tour: str = "food-tour") -> str:
        name, price = TOURS[tour]
        total = price + 24000 + 19900
        return _wanderly_page(
            "Review and pay",
            f"<h1>Review your booking</h1><table>"
            f"<tr><td>{name} \u00d7 1</td><td>{_rs(price)}</td></tr>"
            f"<tr><td>Service charge</td><td>{_rs(24000)}</td></tr>"
            f"<tr><td><label><input type='checkbox' checked> Booking "
            f"protection ({_rs(19900)})</label></td><td>{_rs(19900)}</td></tr>"
            f"<tr><td><b>Total</b></td><td><b>{_rs(total)}</b></td></tr>"
            f"</table><p><button class='cta' type='button'>Pay {_rs(total)} "
            f"securely</button></p>",
        )

    for path, heading in (
        ("/destinations", "Destinations: coast, hills and old towns"),
        ("/journal", "Travel journal: notes from our guides"),
        ("/help", "Help centre: booking questions"),
        ("/about", "About Wanderly"),
    ):

        def info(heading: str = heading) -> str:
            return _wanderly_page(heading, f"<h1>{heading}</h1><p>Placeholder text.</p>")

        app.add_api_route(path, info, methods=["GET"], response_class=HTMLResponse)
    return app


# --- 2. Kettle & Kin: recipe community with a weekly letter -----------------------------

KETTLE_CSS = """
body{margin:0;font-family:'Trebuchet MS',sans-serif;background:#fffaf2;color:#3b2a1a}
header{padding:16px 24px;border-bottom:3px double #c49a6c}
header nav a{margin-right:16px;color:#8a4f1d}
main{max-width:760px;margin:0 auto;padding:20px}
.letter{background:#f3e3cc;padding:14px;border-radius:12px;margin-top:24px}
footer{margin-top:40px;padding:16px 24px;font-size:12px;color:#a58a6d;border-top:1px solid #eee}
footer a{color:#a58a6d}
#ck{position:fixed;inset:0;background:#0007;z-index:99;display:flex;align-items:center;
 justify-content:center}
#ck .box{background:#fff;padding:20px;width:420px;border-radius:12px}
#ck .main{background:#8a4f1d;color:#fff;border:0;padding:10px 20px}
"""
RECIPES = {
    "lemon-dal": "Lemon dal with crispy shallots",
    "chai-loaf": "Spiced chai loaf",
    "green-pulao": "Green herb pulao",
}


def _kettle_page(title: str, body: str, consent: bool = True) -> str:
    modal = (
        "<div id='ck' role='dialog' aria-modal='true' aria-label='Cookie consent'>"
        "<div class='box' id='ck1'><h2>We value your privacy</h2><p>We use cookies for "
        "analytics and personalised ads with our partners.</p>"
        "<button class='main' onclick='ckDone()'>Accept &amp; continue</button> "
        "<button onclick='ckMore()'>Manage choices</button></div></div>"
        "<script>function ckDone(){document.cookie='kk_ck=1;path=/';"
        "document.getElementById('ck').remove()}"
        "function ckMore(){document.querySelector('#ck .box').innerHTML="
        '"<h2>Your choices</h2><label><input type=checkbox checked> Analytics</label><br>'
        "<label><input type=checkbox checked> Advertising</label><br><br>"
        "<button onclick=ckDone()>Reject non-essential</button> "
        '<button onclick=ckDone()>Save choices</button>"}'
        "if(document.cookie.includes('kk_ck=1'))document.getElementById('ck').remove()"
        "</script>"
        if consent
        else ""
    )
    head = (
        "<header><a href='/'><b>Kettle &amp; Kin</b></a> <nav><a href='/recipes'>Recipes</a>"
        "<a href='/kitchen-notes'>Kitchen notes</a><a href='/community'>Community</a></nav>"
        "</header>"
    )
    foot = (
        "<footer><a href='/about'>About</a> \u00b7 <a href='/privacy'>Privacy</a> \u00b7 "
        "<a href='/mailing'>Mailing settings</a></footer>"
    )
    return _doc(title, KETTLE_CSS, head + f"<main>{body}</main>" + foot + modal)


def kettle() -> FastAPI:
    app = _app()
    letter = (
        "<div class='letter'><h3>Get one recipe a week</h3><form method='post' "
        "action='/letter'><label>Your email <input type='email' name='email' required>"
        "</label> <button>Count me in</button></form></div>"
    )

    @app.get("/", response_class=HTMLResponse)
    def home() -> str:
        items = "".join(f"<li><a href='/recipes/{s}'>{t}</a></li>" for s, t in RECIPES.items())
        return _kettle_page("Kettle & Kin", f"<h1>Cook something kind</h1><ul>{items}</ul>")

    @app.get("/recipes", response_class=HTMLResponse)
    def recipes() -> str:
        items = "".join(f"<li><a href='/recipes/{s}'>{t}</a></li>" for s, t in RECIPES.items())
        return _kettle_page("Recipes", f"<h1>All recipes</h1><ul>{items}</ul>{letter}")

    @app.get("/recipes/{slug}", response_class=HTMLResponse)
    def recipe(slug: str) -> str:
        title = RECIPES[slug]
        return _kettle_page(title, f"<h1>{title}</h1><p>Serves four. Method below.</p>{letter}")

    @app.post("/letter")
    def join_letter() -> RedirectResponse:
        return _see("/letter/thanks")

    @app.get("/letter/thanks", response_class=HTMLResponse)
    def thanks() -> str:
        return _kettle_page(
            "Thanks", "<h1>You're on the list</h1><p>Your first recipe arrives on Sunday.</p>"
        )

    @app.get("/mailing", response_class=HTMLResponse)
    def mailing() -> str:
        return _kettle_page(
            "Mailing settings",
            "<h1>Mailing settings</h1><p>Weekly recipe "
            "letter: <b>on</b></p><p><a href='/mailing/stop'>Stop the weekly "
            "letter</a></p>",
        )

    @app.get("/mailing/stop", response_class=HTMLResponse)
    def stop() -> str:
        return _kettle_page(
            "Before you go",
            "<h1>Before you go</h1><p>Would a monthly "
            "digest suit you better?</p><p><a href='/mailing'>Switch to "
            "monthly</a></p><form method='post' action='/mailing/stop'>"
            "<button>No, stop all letters</button></form>",
        )

    @app.post("/mailing/stop")
    def stop_post() -> RedirectResponse:
        return _see("/mailing/stopped")

    @app.get("/mailing/stopped", response_class=HTMLResponse)
    def stopped() -> str:
        return _kettle_page(
            "Done", "<h1>Done</h1><p>You will no longer receive the recipe letter.</p>"
        )

    for path, heading in (
        ("/kitchen-notes", "Kitchen notes"),
        ("/community", "Community cookbook"),
        ("/about", "About Kettle & Kin"),
        ("/privacy", "Privacy notice"),
    ):

        def info(heading: str = heading) -> str:
            return _kettle_page(heading, f"<h1>{heading}</h1><p>Placeholder text.</p>")

        app.add_api_route(path, info, methods=["GET"], response_class=HTMLResponse)
    return app


# --- 3. Streamly: a streaming trial and its membership ------------------------------------

STREAM_CSS = """
body{margin:0;background:#0d0d12;color:#e8e8f0;font-family:Arial,sans-serif}
a{color:#9db4ff}.bar{display:flex;gap:20px;padding:14px 24px;background:#16161f}
.page{max-width:860px;margin:0 auto;padding:24px}
.plans{display:flex;gap:16px}.plan{border:1px solid #333;border-radius:10px;padding:16px;flex:1}
.go{display:inline-block;background:#5b6cff;color:#fff;padding:10px 18px;border-radius:20px;
 text-decoration:none;border:0;font-size:15px}
.small{font-size:12px;color:#777}
"""


def _stream_page(title: str, body: str, signed_in: bool = False) -> str:
    links = (
        "<a href='/browse'>Home</a><a href='/originals'>Originals</a><a href='/profile'>Profile</a>"
        if signed_in
        else "<a href='/plans'>See plans</a><a href='/originals'>Originals</a>"
        "<a href='/devices'>Devices</a><a href='/help'>Help</a>"
    )
    return _doc(
        title,
        STREAM_CSS,
        f"<div class='bar'><b><a href='/'>Streamly</a></b>{links}</div>"
        f"<div class='page'>{body}</div>",
    )


def streamly() -> FastAPI:
    app = _app()

    @app.get("/", response_class=HTMLResponse)
    def home() -> str:
        return _stream_page(
            "Streamly",
            "<h1>Watch anything, anywhere</h1><p><a class='go' href='/plans'>See plans</a></p>",
        )

    @app.get("/plans", response_class=HTMLResponse)
    def plans() -> str:
        cards = "".join(
            f"<div class='plan'><h2>{name}</h2><p>\u20b9{price}/month after 7 days</p>"
            f"<a class='go' href='/join?plan={slug}'>Try 7 days free</a></div>"
            for slug, name, price in (("basic", "Basic", 199), ("premium", "Premium", 499))
        )
        return _stream_page("Plans", f"<h1>Choose a plan</h1><div class='plans'>{cards}</div>")

    @app.get("/join", response_class=HTMLResponse)
    def join(plan: str = "basic") -> str:
        return _stream_page(
            "Join",
            f"<h1>Create your profile</h1><form method='post' "
            f"action='/join?plan={plan}'><p><label>Email <input type='email' "
            "name='email' required></label></p><p><label>Profile name "
            "<input name='profile_name' required></label></p><p><label>"
            "<input type='checkbox' name='news' checked> Send me what's new"
            "</label></p><button class='go'>Start watching</button></form>",
        )

    @app.post("/join")
    def join_post() -> RedirectResponse:
        return _see("/browse")

    @app.get("/browse", response_class=HTMLResponse)
    def browse() -> str:
        return _stream_page("Home", "<h1>Continue watching</h1><p>Nothing yet.</p>", True)

    @app.get("/profile", response_class=HTMLResponse)
    def profile() -> str:
        return _stream_page(
            "Profile",
            "<h1>Profile</h1><ul><li><a href='/profile/devices'>"
            "Signed-in devices</a></li><li><a href='/profile/membership'>"
            "Membership &amp; billing</a></li><li><a href='/profile/language'>"
            "Language</a></li></ul>",
            True,
        )

    @app.get("/profile/membership", response_class=HTMLResponse)
    def membership() -> str:
        return _stream_page(
            "Membership",
            "<h1>Membership &amp; billing</h1><p>Basic, "
            "\u20b9199/month. Renews on 1 Dec 2026.</p><p class='small'><a "
            "href='/profile/membership/end'>End membership</a></p>",
            True,
        )

    @app.get("/profile/membership/end", response_class=HTMLResponse)
    def end_reason() -> str:
        return _stream_page(
            "Tell us why",
            "<h1>Tell us why</h1><form method='post' "
            "action='/profile/membership/end'><label><input type='radio' "
            "name='why' value='price'> Too expensive</label><br><label><input "
            "type='radio' name='why' value='time'> No time</label><br><br>"
            "<button class='go'>Next</button></form>",
            True,
        )

    @app.post("/profile/membership/end")
    def end_reason_post() -> RedirectResponse:
        return _see("/profile/membership/end/offer")

    @app.get("/profile/membership/end/offer", response_class=HTMLResponse)
    def offer() -> str:
        return _stream_page(
            "An offer",
            "<h1>Stay for half price?</h1><p>Three months at "
            "\u20b999.</p><p><a class='go' href='/browse'>Stay for half price"
            "</a></p><p class='small'><a href='/profile/membership/end/confirm'>"
            "Continue ending</a></p>",
            True,
        )

    @app.get("/profile/membership/end/confirm", response_class=HTMLResponse)
    def confirm() -> str:
        return _stream_page(
            "Confirm",
            "<h1>Last step</h1><form method='post' "
            "action='/profile/membership/end/confirm'><button>Finish ending "
            "membership</button></form>",
            True,
        )

    @app.post("/profile/membership/end/confirm")
    def confirm_post() -> RedirectResponse:
        return _see("/profile/membership/ended")

    @app.get("/profile/membership/ended", response_class=HTMLResponse)
    def ended() -> str:
        return _stream_page(
            "Ended", "<h1>Your membership has ended</h1><p>You won't be billed again.</p>", True
        )

    for path, heading, signed in (
        ("/originals", "Streamly originals", False),
        ("/devices", "Watch on any device", False),
        ("/help", "Help", False),
        ("/profile/devices", "Signed-in devices", True),
        ("/profile/language", "Language", True),
    ):

        def info(heading: str = heading, signed: bool = signed) -> str:
            return _stream_page(heading, f"<h1>{heading}</h1><p>Placeholder text.</p>", signed)

        app.add_api_route(path, info, methods=["GET"], response_class=HTMLResponse)
    return app


# --- the set ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Layout:
    id: str
    site_type: SiteType
    missions: tuple[str, ...]
    create_app: Callable[[], FastAPI]
    left_text: re.Pattern[str] | None = None  # the site's own "you have left" wording
    pay_control: re.Pattern[str] | None = None  # the control that would pay


LAYOUTS: tuple[Layout, ...] = (
    Layout(
        "wanderly-tours",
        SiteType.SHOP,
        ("reach_payment", "first_visit"),
        wanderly,
        pay_control=re.compile(r"\bpay\b.*\bsecurely\b", re.I),
    ),
    Layout(
        "kettle-recipes",
        SiteType.NEWS,
        ("sign_up_and_leave", "first_visit"),
        kettle,
        left_text=re.compile(r"no longer receive the recipe letter", re.I),
    ),
    Layout(
        "streamly-video",
        SiteType.SAAS,
        ("sign_up_and_leave", "first_visit"),
        streamly,
        left_text=re.compile(r"membership has ended", re.I),
    ),
)


def get(layout_id: str) -> Layout:
    for layout in LAYOUTS:
        if layout.id == layout_id:
            return layout
    raise KeyError(f"unknown layout {layout_id!r}")
