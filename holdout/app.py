"""Hold-out web apps: grocery delivery, video streaming and a magazine.

One FastAPI app per case. In-memory, single-visitor state; POST /__reset starts over.
Served on 127.0.0.1 only, no external assets, fake data only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Form, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

from holdout import design
from holdout.design import Case, Ctl, Skin, rgb

TEMPLATES = Path(__file__).parent / "templates"
COOKIE = "hx_cookie_choice"


def inr(minor: int) -> str:
    rupees, paise = divmod(minor, 100)
    return f"₹{rupees:,}" + (f".{paise:02d}" if paise else "")


def stylesheet(s: Skin) -> str:
    p = s.prefix
    banner = {
        "corner": "position:fixed;left:24px;bottom:24px;width:480px;z-index:50;",
        "topbar": "position:fixed;left:0;right:0;top:0;z-index:50;",
        "modal": "",
    }[s.banner]
    return f"""
*{{box-sizing:border-box}}
body{{margin:0;font-family:{s.font};background:{rgb(s.page)};color:{rgb(s.text)};line-height:1.5}}
a{{color:{rgb(s.text)}}}
.{p}top{{display:grid;grid-template-columns:auto 1fr;gap:24px;align-items:center;padding:14px 32px;background:{rgb(s.surface)};border-bottom:2px solid {rgb(s.border)}}}
.{p}logo{{font-size:22px;font-weight:700;text-decoration:none}}
.{p}menu{{display:flex;gap:18px;list-style:none;margin:0;padding:0}}
.{p}wrap{{display:grid;grid-template-columns:minmax(0,1fr) 260px;gap:28px;padding:28px 32px;max-width:1180px}}
.{p}panel{{background:{rgb(s.surface)};border:1px solid {rgb(s.border)};border-radius:{s.radius}px;padding:18px;margin-bottom:16px}}
.{p}grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}}
.{p}btn{{display:inline-block;background:{rgb(s.primary)};color:#fff;border:0;border-radius:{s.radius}px;padding:11px 20px;font-size:15px;text-decoration:none;cursor:pointer;font-family:inherit}}
.{p}quiet{{background:none;border:0;padding:0;text-decoration:underline;cursor:pointer;font-family:inherit;font-size:14px;color:{rgb(s.text)}}}
.{p}ctl{{display:inline-flex;align-items:center;justify-content:center;border:1px solid {rgb(s.border)};border-radius:{s.radius}px;padding:0;cursor:pointer;text-decoration:none;font-family:inherit;overflow:hidden;white-space:nowrap}}
.{p}lines{{width:100%;border-collapse:collapse}}
.{p}lines td{{padding:6px 0;border-bottom:1px solid {rgb(s.border)}}}
.{p}lines td:last-child{{text-align:right}}
.{p}field{{display:block;margin:10px 0}}
.{p}field input{{display:block;width:100%;max-width:380px;padding:8px;font-size:15px}}
.{p}choices{{display:flex;flex-wrap:wrap;gap:12px;align-items:center;margin-top:12px}}
.{p}foot{{padding:20px 32px;border-top:2px solid {rgb(s.border)};font-size:14px;display:flex;gap:18px;flex-wrap:wrap}}
.{p}cookie{{{banner}background:{rgb(s.surface)};border:1px solid {rgb(s.border)};padding:18px 22px;box-shadow:0 8px 30px rgba(0,0,0,.3)}}
.{p}backdrop{{position:fixed;inset:0;background:rgba(0,0,0,.55);display:flex;align-items:center;justify-content:center;z-index:60}}
.{p}backdrop .{p}cookie{{width:620px}}
.{p}hide{{position:absolute;left:-10000px;width:1px;height:1px;overflow:hidden}}
.{p}stage[hidden]{{display:none}}
.{p}sandbox{{background:#7f1d1d;color:#fff;padding:36px;font-size:32px;text-align:center;font-weight:700}}
.{p}aside h2{{font-size:16px}}
"""


@dataclass
class State:
    consent: dict[str, Any] | None = None
    basket: dict[str, int] = field(default_factory=dict)
    bag_added: bool = False
    tip: bool | None = None
    join: dict[str, str] = field(default_factory=dict)
    member: bool = False
    cancelled: bool = False


def create_app(case: Case) -> FastAPI:
    skin = design.SKINS[case.skin]
    env = Environment(
        loader=FileSystemLoader(TEMPLATES),
        autoescape=select_autoescape(["html"]),
        undefined=StrictUndefined,
    )
    consent_state = case.state if case.layout == "magazine" else "clean"
    env.globals.update(
        skin=skin,
        p=skin.prefix,
        css=stylesheet(skin),
        inr=inr,
        case=case,
        consent=design.CONSENT[consent_state],
        toggles=design.TOGGLES,
        ctl_style=lambda c: c.style(skin),
        site_name={"grocery": "Basketly", "streaming": "Flickbox", "magazine": "The Long Read"}[
            case.layout
        ],
    )
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.state.s = State()

    def st() -> State:
        return app.state.s

    def page(request: Request, template: str, **ctx: Any) -> HTMLResponse:
        chose = COOKIE in request.cookies and st().consent is not None
        ctx.setdefault("show_banner", not chose)
        return HTMLResponse(env.get_template(template).render(**ctx))

    @app.post("/consent")
    async def consent(request: Request) -> Response:
        st().consent = await request.json()
        response = Response(status_code=204)
        response.set_cookie(COOKIE, str(st().consent.get("choice")), samesite="lax")
        return response

    @app.post("/__reset")
    def reset() -> Response:
        app.state.s = State()
        return Response(status_code=204)

    @app.get("/privacy")
    def privacy(request: Request) -> HTMLResponse:
        return page(request, "common/text.html", title="Privacy", text="No real data is kept.")

    @app.get("/help")
    def help_page(request: Request) -> HTMLResponse:
        return page(request, "common/text.html", title="Help", text="This is a test site.")

    {"grocery": _grocery, "streaming": _streaming, "magazine": _magazine}[case.layout](
        app, page, st, case
    )
    return app


# --- grocery -----------------------------------------------------------------------


def _grocery(app: FastAPI, page, st, case: Case) -> None:
    cfg = design.GROCERY[case.state]
    names = {sku: (name, price) for sku, name, price in design.PRODUCTS}
    if cfg["bag"]:
        sku, name, price = cfg["bag"]
        names[sku] = (name, price)

    def tip_on() -> bool:
        return cfg["tip_on"] if st().tip is None else bool(st().tip)

    def lines() -> list[tuple[str, int, int]]:
        return [(names[sku][0], qty, names[sku][1] * qty) for sku, qty in st().basket.items()]

    def subtotal() -> int:
        return sum(total for _, _, total in lines())

    @app.get("/")
    def home(request: Request) -> HTMLResponse:
        return page(
            request, "grocery/home.html", title="Groceries in 20 minutes", products=design.PRODUCTS
        )

    @app.get("/item/{sku}")
    def item(request: Request, sku: str) -> HTMLResponse:
        name, price = names[sku]
        return page(
            request,
            "grocery/item.html",
            title=name,
            sku=sku,
            name=name,
            price=price,
            delivery=design.DELIVERY,
        )

    @app.post("/basket/add")
    def add(sku: str = Form(...)) -> RedirectResponse:
        st().basket[sku] = st().basket.get(sku, 0) + 1
        if cfg["bag"] and not st().bag_added:
            st().basket[cfg["bag"][0]] = 1  # added for the shopper, unasked
            st().bag_added = True
        return RedirectResponse("/basket", status_code=303)

    @app.post("/basket/tip")
    def tip(tip: str | None = Form(None)) -> RedirectResponse:
        st().tip = tip == "yes"
        return RedirectResponse("/basket", status_code=303)

    @app.get("/basket")
    def basket(request: Request) -> HTMLResponse:
        total = subtotal() + design.DELIVERY + (cfg["tip"] if tip_on() else 0)
        return page(
            request,
            "grocery/basket.html",
            title="Your basket",
            lines=lines(),
            delivery=design.DELIVERY,
            tip=cfg["tip"],
            tip_on=tip_on(),
            total=total,
        )

    @app.get("/checkout")
    def checkout(request: Request) -> HTMLResponse:
        return page(
            request, "grocery/checkout.html", title="Delivery details", hidden=cfg["hidden"]
        )

    @app.post("/checkout")
    def save_checkout() -> RedirectResponse:
        return RedirectResponse("/review", status_code=303)

    @app.get("/review")
    def review(request: Request) -> HTMLResponse:
        tip_amount = cfg["tip"] if tip_on() else 0
        total = subtotal() + design.DELIVERY + tip_amount + sum(m for _, m in cfg["fees"])
        return page(
            request,
            "grocery/review.html",
            title="Review your order",
            lines=lines(),
            delivery=design.DELIVERY,
            tip=tip_amount,
            fees=cfg["fees"],
            total=total,
        )

    @app.post("/order")
    def order(request: Request) -> HTMLResponse:
        return page(request, "common/sandbox.html", title="Sandbox")


# --- streaming ---------------------------------------------------------------------


def _streaming(app: FastAPI, page, st, case: Case) -> None:
    cfg = design.STREAMING[case.state]
    _, plan_price = design.CHOSEN_PLAN

    def chosen_addons() -> list[tuple[str, int]]:
        form = st().join
        picked = (
            {key for key, _, _ in design.ADDONS if form.get(key) == "yes"}
            if form
            else cfg["addons_on"]
        )
        return [(label, price) for key, label, price in design.ADDONS if key in picked]

    def monthly() -> int:
        return plan_price + sum(p for _, p in chosen_addons())

    def renewal_text(amount: int) -> str:
        return (
            f"Your free month ends on {design.RENEWAL_DATE}, then {inr(amount)} per month. "
            "Cancel anytime."
        )

    def renewal() -> dict | None:
        if cfg["renewal"] is None:
            return None
        kind, font = cfg["renewal"]
        style = Ctl("", 0, 0, font, kind).style(design.SKINS[case.skin])
        style = style.split(";", 2)[2]  # keep font and colours, drop the fixed box
        return {"text": renewal_text(monthly()), "style": style}

    @app.get("/")
    def home(request: Request) -> HTMLResponse:
        return page(request, "streaming/home.html", title="Watch anything")

    @app.get("/plans")
    def plans(request: Request) -> HTMLResponse:
        return page(request, "streaming/plans.html", title="Plans", plans=design.PLANS)

    @app.get("/join")
    def join(request: Request) -> HTMLResponse:
        return page(
            request,
            "streaming/join.html",
            title="Create your account",
            addons=design.ADDONS,
            addons_on=cfg["addons_on"],
            hidden=cfg["hidden"],
            renewal=renewal(),
        )

    @app.post("/join")
    async def save_join(request: Request) -> RedirectResponse:
        st().join = {k: str(v) for k, v in (await request.form()).items()}
        return RedirectResponse("/join/review", status_code=303)

    @app.get("/join/review")
    def review(request: Request) -> HTMLResponse:
        return page(
            request,
            "streaming/review.html",
            title="Review",
            plan=design.CHOSEN_PLAN,
            addons=chosen_addons(),
            fees=cfg["fees"],
            monthly=monthly(),
            renewal=renewal(),
        )

    @app.post("/join/activate")
    def activate() -> RedirectResponse:
        st().member, st().cancelled = True, False
        return RedirectResponse("/account", status_code=303)

    @app.get("/account")
    def account(request: Request) -> HTMLResponse:
        return page(
            request,
            "streaming/account.html",
            title="Your account",
            cfg=cfg,
            change=Ctl("Change plan", 170, 42, 15, "plain"),
            cancelled=st().cancelled,
        )

    @app.get("/account/subscription")
    def subscription(request: Request) -> HTMLResponse:
        return page(
            request,
            "streaming/subscription.html",
            title="Subscription",
            cfg=cfg,
            plan=design.CHOSEN_PLAN,
        )

    @app.get("/account/devices")
    def devices(request: Request) -> HTMLResponse:
        return page(request, "common/text.html", title="Devices", text="No devices yet.")

    @app.get("/account/cancel/{i}")
    def cancel_step(request: Request, i: int) -> HTMLResponse:
        kind = cfg["steps"][i]
        return page(
            request,
            "streaming/cancel.html",
            title="Cancel",
            kind=kind,
            i=i,
            phone=design.SUPPORT_PHONE,
        )

    @app.post("/account/cancel/{i}")
    def cancel_next(i: int) -> RedirectResponse:
        if i + 1 < len(cfg["steps"]):
            return RedirectResponse(f"/account/cancel/{i + 1}", status_code=303)
        st().cancelled = True
        return RedirectResponse("/account/cancelled", status_code=303)

    @app.get("/account/cancelled")
    def cancelled(request: Request) -> HTMLResponse:
        return page(
            request,
            "common/text.html",
            title="Cancelled",
            text="Your subscription is cancelled. You will not be charged.",
        )


# --- magazine ----------------------------------------------------------------------

STORIES = {
    "culture": [("night-markets", "The night markets that never sleep")],
    "science": [("glacier-sounds", "Listening to a glacier melt")],
    "opinion": [("slow-trains", "In praise of slow trains")],
}


def _magazine(app: FastAPI, page, st, case: Case) -> None:
    @app.get("/")
    def home(request: Request) -> HTMLResponse:
        return page(request, "magazine/home.html", title="This week", stories=STORIES)

    @app.get("/section/{name}")
    def section(request: Request, name: str) -> HTMLResponse:
        return page(
            request,
            "magazine/section.html",
            title=name.title(),
            name=name,
            stories=STORIES.get(name, []),
        )

    @app.get("/story/{slug}")
    def story(request: Request, slug: str) -> HTMLResponse:
        title = next((t for items in STORIES.values() for s, t in items if s == slug), "Story")
        return page(request, "magazine/story.html", title=title)
