"""Hold-out v2 web apps: an electronics store, an online-courses site and a forum.

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

from holdout2 import design
from holdout2.design import Case, Ctl, Skin, rgb

TEMPLATES = Path(__file__).parent / "templates"
COOKIE = "v2_privacy"


def inr(minor: int) -> str:
    rupees, paise = divmod(minor, 100)
    return f"₹{rupees:,}" + (f".{paise:02d}" if paise else "")


def stylesheet(s: Skin) -> str:
    p = s.prefix
    place = {
        "drawer": "position:fixed;left:0;top:0;bottom:0;width:400px;overflow:auto;",
        "sheet": "position:fixed;left:0;right:0;bottom:0;border-radius:22px 22px 0 0;",
        "toast": "position:fixed;top:16px;right:16px;width:400px;",
    }[s.banner]
    return f"""
*{{box-sizing:border-box}}
body{{margin:0;font-family:{s.font};background:{rgb(s.page)};color:{rgb(s.text)};line-height:1.45}}
a{{color:{rgb(s.text)}}}
.{p}bar{{display:flex;justify-content:space-between;align-items:center;padding:12px 28px;background:{rgb(s.surface)};border-bottom:1px solid {rgb(s.border)}}}
.{p}brand{{font-weight:800;font-size:20px;text-decoration:none}}
.{p}links{{display:flex;gap:16px}}
.{p}page{{max-width:1000px;margin:0 auto;padding:24px 28px}}
.{p}card{{background:{rgb(s.surface)};border:1px solid {rgb(s.border)};border-radius:{s.radius}px;padding:16px 18px;margin:12px 0}}
.{p}cards{{display:flex;gap:16px;flex-wrap:wrap}}
.{p}cards > *{{flex:1 1 220px}}
.{p}row{{display:flex;justify-content:space-between;gap:16px;padding:6px 0;border-bottom:1px dashed {rgb(s.border)}}}
.{p}cta{{display:inline-block;background:{rgb(s.primary)};color:#fff;border:0;border-radius:{s.radius}px;padding:10px 18px;font-size:15px;text-decoration:none;cursor:pointer;font-family:inherit}}
.{p}link{{background:none;border:0;padding:0;cursor:pointer;text-decoration:underline;font-family:inherit;font-size:14px;color:{rgb(s.text)}}}
.{p}m{{display:inline-flex;align-items:center;justify-content:center;border:1px solid {rgb(s.border)};border-radius:{s.radius}px;padding:0;cursor:pointer;text-decoration:none;font-family:inherit;overflow:hidden;white-space:nowrap}}
.{p}grid3{{width:100%;border-collapse:collapse}}
.{p}grid3 th,.{p}grid3 td{{text-align:left;padding:6px 8px;border-bottom:1px solid {rgb(s.border)}}}
.{p}input{{display:block;margin:8px 0 14px}}
.{p}input input{{display:block;width:100%;max-width:360px;padding:8px;font-size:15px}}
.{p}side{{display:grid;grid-template-columns:200px 1fr;gap:24px}}
.{p}foot{{padding:18px 28px;border-top:1px solid {rgb(s.border)};font-size:13px;display:flex;gap:16px;flex-wrap:wrap}}
.{p}privacy{{{place}background:{rgb(s.surface)};border:1px solid {rgb(s.border)};padding:20px;z-index:40;box-shadow:0 10px 30px rgba(0,0,0,.25)}}
.{p}actions{{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-top:10px}}
.{p}offscreen{{position:absolute;left:-12000px;top:0}}
.{p}fake{{background:#7f1d1d;color:#fff;padding:32px;font-size:28px;text-align:center}}
"""


@dataclass
class State:
    consent: dict[str, Any] | None = None
    cart: dict[str, int] = field(default_factory=dict)
    extra_added: bool = False
    care: bool | None = None
    join: dict[str, str] = field(default_factory=dict)
    cancelled: bool = False


def create_app(case: Case) -> FastAPI:
    skin = design.SKINS[case.skin]
    env = Environment(
        loader=FileSystemLoader(TEMPLATES),
        autoescape=select_autoescape(["html"]),
        undefined=StrictUndefined,
    )
    env.globals.update(
        skin=skin,
        p=skin.prefix,
        css=stylesheet(skin),
        inr=inr,
        consent=design.CONSENT[case.state if case.layout == "forum" else "clean"],
        toggles=design.TOGGLES,
        ms=lambda c: c.style(skin),
        site_name={"store": "Voltcart", "courses": "Learnly", "forum": "Threadline"}[case.layout],
    )
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.state.s = State()

    def st() -> State:
        return app.state.s

    def page(request: Request, template: str, **ctx: Any) -> HTMLResponse:
        chose = COOKIE in request.cookies and st().consent is not None
        ctx.setdefault("show_banner", not chose)
        return HTMLResponse(env.get_template(template).render(**ctx))

    @app.post("/privacy-choice")
    async def choice(request: Request) -> Response:
        st().consent = await request.json()
        response = Response(status_code=204)
        response.set_cookie(COOKIE, str(st().consent.get("choice")), samesite="lax")
        return response

    @app.post("/__reset")
    def reset() -> Response:
        app.state.s = State()
        return Response(status_code=204)

    @app.get("/terms")
    def terms(request: Request) -> HTMLResponse:
        return page(request, "text.html", title="Terms", text="Test site. Nothing is sold.")

    {"store": _store, "courses": _courses, "forum": _forum}[case.layout](app, page, st, case)
    return app


def _store(app: FastAPI, page, st, case: Case) -> None:
    cfg = design.STORE[case.state]
    names = {sku: (name, price) for sku, name, price in design.PRODUCTS}
    if cfg["extra"]:
        names[cfg["extra"][0]] = cfg["extra"][1:]

    def care_on() -> bool:
        return cfg["care_on"] if st().care is None else bool(st().care)

    def lines() -> list[tuple[str, int, int]]:
        return [(names[s][0], q, names[s][1] * q) for s, q in st().cart.items()]

    def items_total() -> int:
        return sum(t for _, _, t in lines())

    @app.get("/")
    def home(request: Request) -> HTMLResponse:
        return page(request, "store/home.html", title="Deals", products=design.PRODUCTS)

    @app.get("/p/{sku}")
    def product(request: Request, sku: str) -> HTMLResponse:
        name, price = names[sku]
        return page(
            request,
            "store/product.html",
            title=name,
            sku=sku,
            name=name,
            price=price,
            delivery=design.DELIVERY,
        )

    @app.post("/cart")
    def add(sku: str = Form(...)) -> RedirectResponse:
        st().cart[sku] = st().cart.get(sku, 0) + 1
        if cfg["extra"] and not st().extra_added:
            st().cart[cfg["extra"][0]] = 1
            st().extra_added = True
        return RedirectResponse("/cart", status_code=303)

    @app.post("/cart/care")
    def care(care: str | None = Form(None)) -> RedirectResponse:
        st().care = care == "on"
        return RedirectResponse("/cart", status_code=303)

    @app.get("/cart")
    def cart(request: Request) -> HTMLResponse:
        total = items_total() + design.DELIVERY + (cfg["care"] if care_on() else 0)
        return page(
            request,
            "store/cart.html",
            title="Cart",
            lines=lines(),
            care=cfg["care"],
            care_on=care_on(),
            delivery=design.DELIVERY,
            total=total,
        )

    @app.get("/shipping")
    def shipping(request: Request) -> HTMLResponse:
        return page(request, "store/shipping.html", title="Shipping", hidden=cfg["hidden"])

    @app.post("/shipping")
    def save_shipping() -> RedirectResponse:
        return RedirectResponse("/summary", status_code=303)

    @app.get("/summary")
    def summary(request: Request) -> HTMLResponse:
        care_amount = cfg["care"] if care_on() else 0
        total = items_total() + design.DELIVERY + care_amount + sum(m for _, m in cfg["fees"])
        return page(
            request,
            "store/summary.html",
            title="Summary",
            lines=lines(),
            delivery=design.DELIVERY,
            care=care_amount,
            fees=cfg["fees"],
            total=total,
        )

    @app.post("/pay")
    def pay(request: Request) -> HTMLResponse:
        return page(request, "fake.html", title="Sandbox")


def _courses(app: FastAPI, page, st, case: Case) -> None:
    cfg = design.COURSES[case.state]
    plan_name, plan_price = design.CHOSEN

    def extras() -> list[tuple[str, int]]:
        form = st().join
        picked = (
            {k for k, _, _ in design.EXTRAS if form.get(k) == "on"} if form else cfg["extras_on"]
        )
        return [(label, price) for k, label, price in design.EXTRAS if k in picked]

    def monthly() -> int:
        return plan_price + sum(p for _, p in extras())

    def renewal() -> dict | None:
        if cfg["renewal"] is None:
            return None
        kind, font = cfg["renewal"]
        style = Ctl("", 0, 0, font, kind).style(design.SKINS[case.skin]).split(";", 2)[2]
        text = (
            f"Billed monthly at {inr(monthly())} after your 7-day trial ends on {design.TRIAL_END}."
        )
        return {"text": text, "style": style}

    @app.get("/")
    def home(request: Request) -> HTMLResponse:
        return page(request, "courses/home.html", title="Learn anything")

    @app.get("/pricing")
    def pricing(request: Request) -> HTMLResponse:
        return page(request, "courses/pricing.html", title="Pricing", plans=design.PLANS)

    @app.get("/sales")
    def sales(request: Request) -> HTMLResponse:
        return page(request, "text.html", title="Sales", text="Our team will contact you.")

    @app.get("/start")
    def start(request: Request, plan: str = "Pro") -> HTMLResponse:
        return page(
            request,
            "courses/start.html",
            title="Create your account",
            plan=plan_name,
            price=plan_price,
            extras=design.EXTRAS,
            extras_on=cfg["extras_on"],
            hidden=cfg["hidden"],
            renewal=renewal(),
        )

    @app.post("/start")
    async def save(request: Request) -> RedirectResponse:
        st().join = {k: str(v) for k, v in (await request.form()).items()}
        return RedirectResponse("/start/confirm", status_code=303)

    @app.get("/start/confirm")
    def confirm(request: Request) -> HTMLResponse:
        return page(
            request,
            "courses/confirm.html",
            title="Confirm",
            plan=design.CHOSEN,
            extras=extras(),
            fees=cfg["fees"],
            monthly=monthly(),
            renewal=renewal(),
        )

    @app.post("/start/go")
    def go() -> RedirectResponse:
        st().cancelled = False
        return RedirectResponse("/me", status_code=303)

    @app.get("/me")
    def me(request: Request) -> HTMLResponse:
        return page(
            request,
            "courses/me.html",
            title="My account",
            cfg=cfg,
            change=Ctl("Change plan", 180, 40, 14, "plain"),
            cancelled=st().cancelled,
        )

    @app.get("/me/billing")
    def billing(request: Request) -> HTMLResponse:
        return page(request, "courses/billing.html", title="Billing", cfg=cfg, plan=design.CHOSEN)

    @app.get("/me/notifications")
    def notifications(request: Request) -> HTMLResponse:
        return page(request, "text.html", title="Notifications", text="No notifications.")

    @app.get("/me/leave/{i}")
    def leave(request: Request, i: int) -> HTMLResponse:
        return page(
            request,
            "courses/leave.html",
            title="Cancel",
            kind=cfg["steps"][i],
            i=i,
            email=design.SUPPORT_EMAIL,
        )

    @app.post("/me/leave/{i}")
    def leave_next(i: int) -> RedirectResponse:
        if i + 1 < len(cfg["steps"]):
            return RedirectResponse(f"/me/leave/{i + 1}", status_code=303)
        st().cancelled = True
        return RedirectResponse("/me/cancelled", status_code=303)

    @app.get("/me/cancelled")
    def cancelled(request: Request) -> HTMLResponse:
        return page(
            request, "text.html", title="Cancelled", text="Your subscription has been cancelled."
        )


THREADS = [
    ("rust-vs-go", "Rust or Go for a first backend?", "programming"),
    ("sourdough", "My sourdough keeps collapsing", "cooking"),
    ("budget-trek", "Budget trek ideas near Pune", "travel"),
]


def _forum(app: FastAPI, page, st, case: Case) -> None:
    @app.get("/")
    def home(request: Request) -> HTMLResponse:
        return page(request, "forum/home.html", title="Latest threads", threads=THREADS)

    @app.get("/c/{topic}")
    def topic(request: Request, topic: str) -> HTMLResponse:
        rows = [t for t in THREADS if t[2] == topic]
        return page(request, "forum/topic.html", title=topic.title(), threads=rows)

    @app.get("/t/{slug}")
    def thread(request: Request, slug: str) -> HTMLResponse:
        title = next((t for s, t, _ in THREADS if s == slug), "Thread")
        return page(request, "forum/thread.html", title=title)
