"""Unseen layouts v2 (Phase 6, gate 3): written after the walker was frozen (commit 60db3b0)
and not walked by the LLM before the gate.

The first three unseen layouts (sites.py) informed walker fixes, so they now run as
development layouts. These three are new site types with new wording and new flows:

- Pagewise, a book subscription: the way out is "Account" -> "Plan & payments" -> a small
  "Make changes to my plan" link -> "Stop membership" -> a discount offer -> a required
  acknowledgement -> "Stop my membership". The cookie banner's reject is on a settings page.
- Fresco, grocery delivery: items are added from the listing; checkout asks for details and
  a delivery slot with none preselected; fees appear late; the last page has "Pay ... now".
- Ledgerline, a finance newsletter: the sign-up is at the end of an article; the way out is
  "Manage subscriptions" in the footer, which asks for an email, then lists newsletters.

Each layout states its own end-state text and pay control, as ground truth for completion.
"""

from __future__ import annotations

import re

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from tripwire.schemas.trace import SiteType
from unseen.sites import Layout, _app, _doc, _see

RS = chr(0x20B9)


def _rs(rupees: int) -> str:
    return f"{RS}{rupees:,}"


# --- 4. Pagewise: a book subscription -----------------------------------------------------

PAGEWISE_CSS = """
body{margin:0;font-family:Georgia,serif;background:#fbf8f3;color:#2b2420}
.nav{display:flex;gap:22px;padding:14px 28px;border-bottom:1px solid #e5dccf;background:#fff}
.nav a{color:#5a3e2b;text-decoration:none}.main{max-width:820px;margin:28px auto;padding:0 18px}
.btn{background:#7a4b2a;color:#fff;border:0;padding:11px 20px;border-radius:4px;font-size:15px;
 text-decoration:none;display:inline-block}
.quiet{font-size:12px;color:#9b8b7d}
.ck{position:fixed;left:0;right:0;bottom:0;background:#2b2420;color:#f4ede4;padding:14px 28px;
 z-index:40;display:flex;gap:18px;align-items:center}
.ck a{color:#f4ede4}
"""
BOOKS = {
    "salt-roads": "The Salt Roads",
    "quiet-orchard": "A Quiet Orchard",
    "river-clock": "The River Clock",
}


def _pagewise_page(request: Request, title: str, body: str, member: bool = False) -> str:
    banner = (
        ""
        if request.cookies.get("pw_ck")
        else "<div class='ck' role='region' aria-label='Cookies'>We use cookies to improve "
        "recommendations and to measure our ads with partners. "
        "<button class='btn' onclick=\"document.cookie='pw_ck=all;path=/';"
        'this.parentNode.remove()">OK, got it</button>'
        "<a href='/cookies'>Cookie preferences</a></div>"
    )
    links = (
        "<a href='/shelf'>My shelf</a><a href='/books'>Browse books</a><a href='/account'>"
        "Account</a>"
        if member
        else "<a href='/books'>Browse books</a><a href='/how-it-works'>How it works</a>"
        "<a href='/membership'>Membership</a><a href='/help'>Help</a>"
    )
    nav = f"<div class='nav'><b><a href='/'>Pagewise</a></b>{links}</div>"
    return _doc(title, PAGEWISE_CSS, nav + f"<div class='main'>{body}</div>" + banner)


def pagewise() -> FastAPI:
    app = _app()

    @app.get("/", response_class=HTMLResponse)
    def home(request: Request) -> str:
        return _pagewise_page(
            request,
            "Pagewise",
            "<h1>A new book at your door each month</h1>"
            "<p><a class='btn' href='/membership'>See membership</a></p>",
        )

    @app.get("/cookies", response_class=HTMLResponse)
    def cookies(request: Request) -> str:
        return _pagewise_page(
            request,
            "Cookie preferences",
            "<h1>Cookie preferences</h1>"
            "<p>Analytics and advertising cookies are on.</p>"
            "<form method='post' action='/cookies'><button class='btn'>"
            "Turn off optional cookies</button></form>",
        )

    @app.post("/cookies")
    def cookies_off() -> RedirectResponse:
        response = _see("/")
        response.set_cookie("pw_ck", "necessary")
        return response

    @app.get("/membership", response_class=HTMLResponse)
    def membership(request: Request) -> str:
        return _pagewise_page(
            request,
            "Membership",
            "<h1>Reader membership</h1><p>One hand"
            f"picked book a month, {_rs(299)}/month after your first free "
            "month.</p><p><a class='btn' href='/join'>Start my free month"
            "</a></p>",
        )

    @app.get("/join", response_class=HTMLResponse)
    def join(request: Request) -> str:
        return _pagewise_page(
            request,
            "Join",
            "<h1>Create your shelf</h1><form method='post' "
            "action='/join'><p><label>Email <input type='email' name='email' "
            "required></label></p><p><label>First name <input name="
            "'first_name' required></label></p><p><label><input type="
            "'checkbox' name='tips'> Send me reading tips</label></p>"
            "<button class='btn'>Create my shelf</button></form>",
        )

    @app.post("/join")
    def join_post() -> RedirectResponse:
        return _see("/shelf")

    @app.get("/shelf", response_class=HTMLResponse)
    def shelf(request: Request) -> str:
        return _pagewise_page(
            request,
            "My shelf",
            "<h1>Your shelf</h1><p>Your first book ships on Friday.</p>",
            member=True,
        )

    @app.get("/account", response_class=HTMLResponse)
    def account(request: Request) -> str:
        items = "".join(
            f"<li><a href='/account/{slug}'>{name}</a></li>"
            for slug, name in (
                ("details", "Personal details"),
                ("address", "Delivery address"),
                ("credits", "Reading credits"),
                ("plan", "Plan &amp; payments"),
            )
        )
        return _pagewise_page(request, "Account", f"<h1>Account</h1><ul>{items}</ul>", True)

    @app.get("/account/plan", response_class=HTMLResponse)
    def plan(request: Request) -> str:
        return _pagewise_page(
            request,
            "Plan",
            "<h1>Plan &amp; payments</h1><p>Reader plan, "
            f"{_rs(299)}/month. Renews on 25 Dec 2026.</p><p><a class='btn' "
            "href='/account/plan/upgrade'>Upgrade to Collector</a></p><p "
            "class='quiet'><a href='/account/plan/change'>Make changes to my "
            "plan</a></p>",
            True,
        )

    @app.get("/account/plan/change", response_class=HTMLResponse)
    def change(request: Request) -> str:
        return _pagewise_page(
            request,
            "Change plan",
            "<h1>What would you like to do?</h1>"
            "<p><a class='btn' href='/account/plan/pause'>Pause for 3 months"
            "</a></p><p><a class='btn' href='/account/plan/digital'>Switch to "
            "e-books only</a></p><p class='quiet'><a href='/account/plan/stop'>"
            "Stop membership</a></p>",
            True,
        )

    @app.get("/account/plan/stop", response_class=HTMLResponse)
    def stop(request: Request) -> str:
        return _pagewise_page(
            request,
            "Before you go",
            "<h1>We'd hate to see you go</h1><p>"
            "Here is 50% off your next month.</p><p><a class='btn' href="
            "'/shelf'>Keep my membership at 50% off</a></p><p class='quiet'>"
            "<a href='/account/plan/stop/confirm'>No thanks, continue</a></p>",
            True,
        )

    @app.get("/account/plan/stop/confirm", response_class=HTMLResponse)
    def stop_confirm(request: Request) -> str:
        return _pagewise_page(
            request,
            "Confirm",
            "<h1>Confirm</h1><form method='post' "
            "action='/account/plan/stop/confirm'><p><label><input type="
            "'checkbox' name='ack' required> I understand unused reading "
            "credits will be lost</label></p><button class='btn'>Stop my "
            "membership</button></form>",
            True,
        )

    @app.post("/account/plan/stop/confirm")
    def stop_post() -> RedirectResponse:
        return _see("/account/plan/stopped")

    @app.get("/account/plan/stopped", response_class=HTMLResponse)
    def stopped(request: Request) -> str:
        return _pagewise_page(
            request,
            "Stopped",
            "<h1>Your membership is stopped</h1><p>You won't be charged again.</p>",
            True,
        )

    for path, heading, member in (
        ("/books", "Browse books", False),
        ("/how-it-works", "How it works", False),
        ("/help", "Help centre", False),
        ("/account/details", "Personal details", True),
        ("/account/address", "Delivery address", True),
        ("/account/credits", "Reading credits", True),
        ("/account/plan/upgrade", "Collector plan", True),
        ("/account/plan/pause", "Pause your membership", True),
        ("/account/plan/digital", "E-books only", True),
    ):

        def info(request: Request, heading: str = heading, member: bool = member) -> str:
            extra = ""
            if heading == "Browse books":
                extra = (
                    "<ul>"
                    + "".join(f"<li><a href='/books/{s}'>{t}</a></li>" for s, t in BOOKS.items())
                    + "</ul>"
                )
            return _pagewise_page(request, heading, f"<h1>{heading}</h1>{extra}", member)

        app.add_api_route(path, info, methods=["GET"], response_class=HTMLResponse)

    @app.get("/books/{slug}", response_class=HTMLResponse)
    def book(request: Request, slug: str) -> str:
        return _pagewise_page(request, BOOKS[slug], f"<h1>{BOOKS[slug]}</h1><p>A novel.</p>")

    return app


# --- 5. Fresco: grocery delivery -------------------------------------------------------------

FRESCO_CSS = """
body{margin:0;font-family:'Segoe UI',sans-serif;background:#f6fbf4;color:#1f3320}
.bar{display:flex;gap:18px;align-items:center;padding:12px 24px;background:#2f7d32;color:#fff}
.bar a{color:#fff}.wrap{max-width:900px;margin:20px auto;padding:0 16px}
.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}
.item{background:#fff;border-radius:10px;padding:12px;border:1px solid #d7e8d3}
.go{background:#ff8f00;color:#fff;border:0;padding:9px 16px;border-radius:18px;font-size:14px}
table{border-collapse:collapse}td{padding:4px 14px}
#pv{position:fixed;inset:0;background:#0006;z-index:60;display:flex;align-items:center;
 justify-content:center}#pv .box{background:#fff;padding:22px;border-radius:12px;width:420px}
"""
ITEMS = {
    "bananas": ("Bananas (6)", 48),
    "bread": ("Wholewheat bread", 55),
    "curd": ("Curd 400 g", 60),
}


def _fresco_page(request: Request, title: str, body: str, basket: int = 0) -> str:
    privacy = (
        ""
        if request.cookies.get("fr_pv")
        else "<div id='pv' role='dialog' aria-modal='true' aria-label='Your privacy'>"
        "<div class='box'><h2>Your privacy</h2><p>We and our partners use cookies for "
        "analytics and personalised offers.</p><div id='pv1'><button class='go' "
        "onclick='pvSet(\"all\")'>Accept all</button> <button onclick='pvMore()'>Customise"
        "</button></div></div></div><script>function pvSet(v){document.cookie='fr_pv='+v+"
        "';path=/';document.getElementById('pv').remove()}function pvMore(){document."
        "getElementById('pv1').innerHTML=\"<label><input type=checkbox checked> Analytics"
        "</label><br><label><input type=checkbox checked> Offers</label><br><br><button "
        "onclick=pvSet('selected')>Allow selected</button> <button onclick=pvSet('none')>"
        'Deny all</button>"}</script>'
    )
    bar = (
        "<div class='bar'><b><a href='/'>Fresco</a></b><a href='/fruit'>Fruit</a>"
        "<a href='/bakery'>Bakery</a><a href='/dairy'>Dairy</a><a href='/about'>About</a>"
        f"<a href='/basket'>Basket ({basket})</a></div>"
    )
    return _doc(title, FRESCO_CSS, bar + f"<div class='wrap'>{body}</div>" + privacy)


def fresco() -> FastAPI:
    app = _app()
    app.state.basket = {}

    def count() -> int:
        return sum(app.state.basket.values())

    def lines() -> tuple[str, int]:
        rows, total = "", 0
        for slug, qty in app.state.basket.items():
            name, price = ITEMS[slug]
            rows += f"<tr><td>{name} \u00d7 {qty}</td><td>{_rs(price * qty)}</td></tr>"
            total += price * qty
        return rows, total

    @app.get("/", response_class=HTMLResponse)
    def home(request: Request) -> str:
        cards = "".join(
            f"<div class='item'><h3>{name}</h3><p>{_rs(price)}</p><form method='post' "
            f"action='/basket/add'><input type='hidden' name='item' value='{slug}'><button "
            f"class='go'>Add</button></form></div>"
            for slug, (name, price) in ITEMS.items()
        )
        return _fresco_page(
            request, "Fresco", f"<h1>Fresh today</h1><div class='grid'>{cards}</div>", count()
        )

    @app.post("/basket/add")
    def add(item: str = Form(...)) -> RedirectResponse:
        app.state.basket[item] = app.state.basket.get(item, 0) + 1
        return _see("/basket")

    @app.get("/basket", response_class=HTMLResponse)
    def basket(request: Request) -> str:
        rows, total = lines()
        return _fresco_page(
            request,
            "Basket",
            f"<h1>Your basket</h1><table>{rows}<tr><td>"
            f"Items total</td><td>{_rs(total)}</td></tr></table><p><a class="
            "'go' href='/checkout/details'>Checkout</a></p>",
            count(),
        )

    @app.get("/checkout/details", response_class=HTMLResponse)
    def details(request: Request) -> str:
        return _fresco_page(
            request,
            "Your details",
            "<h1>Where should we deliver?</h1><form "
            "method='post' action='/checkout/details'><p><label>Full name <input "
            "name='full_name' required></label></p><p><label>Mobile number "
            "<input type='tel' name='mobile' required></label></p><p><label>"
            "Flat or house <input name='house' required></label></p><p><label>"
            "Area <input name='area' required></label></p><p><label>PIN code "
            "<input name='pin' required></label></p><button class='go'>Continue"
            "</button></form>",
            count(),
        )

    @app.post("/checkout/details")
    def details_post() -> RedirectResponse:
        return _see("/checkout/slot")

    @app.get("/checkout/slot", response_class=HTMLResponse)
    def slot(request: Request) -> str:
        options = "".join(
            f"<p><label><input type='radio' name='slot' value='{v}' required> {t}</label></p>"
            for v, t in (
                ("am", "Today, 9 to 11 am"),
                ("pm", "Today, 5 to 7 pm"),
                ("next", "Tomorrow, 9 to 11 am"),
            )
        )
        return _fresco_page(
            request,
            "Delivery slot",
            "<h1>Choose a delivery slot</h1><form "
            f"method='post' action='/checkout/slot'>{options}<button class="
            "'go'>Continue to payment</button></form>",
            count(),
        )

    @app.post("/checkout/slot")
    def slot_post() -> RedirectResponse:
        return _see("/checkout/pay")

    @app.get("/checkout/pay", response_class=HTMLResponse)
    def pay(request: Request) -> str:
        rows, total = lines()
        grand = total + 25 + 30
        return _fresco_page(
            request,
            "Payment",
            f"<h1>Review and pay</h1><table>{rows}<tr><td>"
            f"Small basket fee</td><td>{_rs(25)}</td></tr><tr><td>Delivery</td>"
            f"<td>{_rs(30)}</td></tr><tr><td><b>Total</b></td><td><b>"
            f"{_rs(grand)}</b></td></tr></table><p><button class='go' type="
            f"'button'>Pay {_rs(grand)} now</button></p>",
            count(),
        )

    for path, heading in (
        ("/fruit", "Fruit"),
        ("/bakery", "Bakery"),
        ("/dairy", "Dairy"),
        ("/about", "About Fresco"),
    ):

        def info(request: Request, heading: str = heading) -> str:
            return _fresco_page(request, heading, f"<h1>{heading}</h1><p>Placeholder.</p>", count())

        app.add_api_route(path, info, methods=["GET"], response_class=HTMLResponse)
    return app


# --- 6. Ledgerline: a finance newsletter ------------------------------------------------------

LEDGER_CSS = """
body{margin:0;font-family:Helvetica,Arial,sans-serif;background:#fff;color:#14213d}
.top{padding:16px 26px;border-bottom:4px solid #14213d}.top a{margin-right:18px;color:#14213d}
.col{max-width:700px;margin:24px auto;padding:0 18px;line-height:1.6}
.brief{border:2px solid #fca311;padding:14px;margin-top:28px}
.foot{max-width:700px;margin:40px auto;padding:12px 18px;border-top:1px solid #ddd;font-size:12px}
.foot a{color:#777}.cb{background:#e5e5e5;padding:10px 26px}
"""
STORIES = {
    "rate-pause": "Central bank holds rates for a third month",
    "chip-exports": "Chip exports rise for the fifth quarter",
    "rupee-week": "The rupee's quiet week",
}


def _ledger_page(request: Request, title: str, body: str) -> str:
    banner = (
        ""
        if request.cookies.get("ll_cb")
        else "<div class='cb' role='region' aria-label='Cookie notice' style='position:"
        "fixed;top:0;left:0;right:0;z-index:20'>Ledgerline uses cookies for analytics and partner "
        "advertising. <button onclick=\"document.cookie='ll_cb=yes;path=/';"
        'this.parentNode.remove()">I agree</button> <button onclick="document.cookie='
        "'ll_cb=no;path=/';this.parentNode.remove()\">Disagree</button></div>"
    )
    top = (
        "<div class='top'><b><a href='/'>Ledgerline</a></b><a href='/markets'>Markets</a>"
        "<a href='/economy'>Economy</a><a href='/about'>About</a></div>"
    )
    foot = (
        "<div class='foot'><a href='/terms'>Terms</a> \u00b7 <a href='/privacy'>Privacy</a> "
        "\u00b7 <a href='/subscriptions'>Manage subscriptions</a></div>"
    )
    return _doc(title, LEDGER_CSS, banner + top + f"<div class='col'>{body}</div>" + foot)


def ledgerline() -> FastAPI:
    app = _app()
    brief = (
        "<div class='brief'><h3>Morning Brief: markets in five minutes</h3><form method='post' "
        "action='/brief'><label>Email address <input type='email' name='email' required>"
        "</label> <button>Get the brief</button></form></div>"
    )

    @app.get("/", response_class=HTMLResponse)
    def home(request: Request) -> str:
        items = "".join(f"<li><a href='/story/{s}'>{t}</a></li>" for s, t in STORIES.items())
        return _ledger_page(request, "Ledgerline", f"<h1>Today</h1><ul>{items}</ul>")

    @app.get("/story/{slug}", response_class=HTMLResponse)
    def story(request: Request, slug: str) -> str:
        return _ledger_page(
            request,
            STORIES[slug],
            f"<h1>{STORIES[slug]}</h1><p>Analysts said the move was expected.</p>{brief}",
        )

    @app.post("/brief")
    def brief_post() -> RedirectResponse:
        return _see("/brief/welcome")

    @app.get("/brief/welcome", response_class=HTMLResponse)
    def welcome(request: Request) -> str:
        return _ledger_page(
            request,
            "Welcome",
            "<h1>You're on the list</h1><p>Your first Morning Brief arrives tomorrow at 7 am.</p>",
        )

    @app.get("/subscriptions", response_class=HTMLResponse)
    def subscriptions(request: Request) -> str:
        return _ledger_page(
            request,
            "Manage subscriptions",
            "<h1>Manage subscriptions</h1>"
            "<form method='post' action='/subscriptions'><label>Email address "
            "<input type='email' name='email' required></label> <button>Find "
            "my subscriptions</button></form>",
        )

    @app.post("/subscriptions")
    def find() -> RedirectResponse:
        return _see("/subscriptions/list")

    @app.get("/subscriptions/list", response_class=HTMLResponse)
    def listing(request: Request) -> str:
        return _ledger_page(
            request,
            "Your subscriptions",
            "<h1>Your subscriptions</h1><ul>"
            "<li>Morning Brief, daily <a href='/subscriptions/morning-brief/"
            "leave'>Unsubscribe</a></li><li>Weekend Long Read, weekly <a "
            "href='/subscriptions/long-read/leave'>Unsubscribe</a></li></ul>",
        )

    @app.get("/subscriptions/{name}/leave", response_class=HTMLResponse)
    def leave(request: Request, name: str) -> str:
        title = "Morning Brief" if name == "morning-brief" else "Weekend Long Read"
        return _ledger_page(
            request,
            "Unsubscribe",
            f"<h1>Unsubscribe from {title}</h1><form "
            f"method='post' action='/subscriptions/{name}/leave'><p><label>Tell"
            " us why (optional) <textarea name='why'></textarea></label></p>"
            "<button>Unsubscribe me</button></form>",
        )

    @app.post("/subscriptions/{name}/leave")
    def leave_post(name: str) -> RedirectResponse:
        return _see(f"/subscriptions/{name}/done")

    @app.get("/subscriptions/{name}/done", response_class=HTMLResponse)
    def done(request: Request, name: str) -> str:
        title = "Morning Brief" if name == "morning-brief" else "Weekend Long Read"
        return _ledger_page(
            request, "Done", f"<h1>Done</h1><p>You've been removed from {title}.</p>"
        )

    for path, heading in (
        ("/markets", "Markets"),
        ("/economy", "Economy"),
        ("/about", "About Ledgerline"),
        ("/terms", "Terms"),
        ("/privacy", "Privacy"),
    ):

        def info(request: Request, heading: str = heading) -> str:
            return _ledger_page(request, heading, f"<h1>{heading}</h1><p>Placeholder.</p>")

        app.add_api_route(path, info, methods=["GET"], response_class=HTMLResponse)
    return app


LAYOUTS_V2: tuple[Layout, ...] = (
    Layout(
        "pagewise-books",
        SiteType.SAAS,
        ("sign_up_and_leave", "first_visit"),
        pagewise,
        left_text=re.compile(r"membership is stopped", re.I),
    ),
    Layout(
        "fresco-grocery",
        SiteType.SHOP,
        ("reach_payment", "first_visit"),
        fresco,
        pay_control=re.compile(r"\bpay\b.*\bnow\b", re.I),
    ),
    Layout(
        "ledgerline-news",
        SiteType.NEWS,
        ("sign_up_and_leave", "first_visit"),
        ledgerline,
        left_text=re.compile(r"removed from morning brief", re.I),
    ),
)
