"""Shop: catalog -> product -> cart -> address -> summary -> fake payment page."""

from __future__ import annotations

from collections.abc import Callable

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from evilweb.patterns.sneaking import CATALOG, DELIVERY_MINOR, Product
from evilweb.plan import Plan


def register(app: FastAPI, render: Callable[..., HTMLResponse], plan: Plan, sim) -> None:
    spec = plan.shop
    products = {p.sku: p for p in (*CATALOG, *spec.sneaked)}

    def protection_on() -> bool:
        chosen = sim().protection
        return spec.protection_preselected if chosen is None else chosen

    def cart_lines() -> list[tuple[Product, int]]:
        return [(products[sku], qty) for sku, qty in sim().cart.items()]

    def totals(*, with_late_fees: bool) -> dict:
        items = sum(p.price_minor * qty for p, qty in cart_lines())
        delivery = DELIVERY_MINOR if items else 0
        protection = spec.protection.minor if items and protection_on() else 0
        fees = sum(f.minor for f in spec.late_fees) if items and with_late_fees else 0
        return {
            "items": items,
            "delivery": delivery,
            "protection": protection,
            "total": items + delivery + protection + fees,
        }

    def cart_count() -> int:
        return sum(sim().cart.values())

    render.env.globals["cart_count"] = cart_count

    @app.get("/")
    def catalog(request: Request) -> HTMLResponse:
        return render(
            request,
            "catalog.html",
            title="Shop",
            products=CATALOG,
        )

    @app.get("/product/{sku}")
    def product(request: Request, sku: str) -> HTMLResponse:
        item = next((p for p in CATALOG if p.sku == sku), None)
        if item is None:
            return render(request, "info.html", title="Not found", body="No such product.")
        return render(
            request,
            "product.html",
            title=item.name,
            product=item,
            delivery=DELIVERY_MINOR,
        )

    @app.post("/cart/add")
    def add(sku: str = Form(...)) -> RedirectResponse:
        cart = sim().cart
        cart[sku] = cart.get(sku, 0) + 1
        if spec.sneaked and not sim().sneaked_added:
            for extra in spec.sneaked:  # added without the shopper choosing it
                cart[extra.sku] = cart.get(extra.sku, 0) + 1
            sim().sneaked_added = True
        return RedirectResponse("/cart", status_code=303)

    @app.post("/cart/protection")
    def set_protection(protection: str | None = Form(None)) -> RedirectResponse:
        sim().protection = protection == "1"
        return RedirectResponse("/cart", status_code=303)

    @app.get("/cart")
    def cart(request: Request) -> HTMLResponse:
        return render(
            request,
            "cart.html",
            title="Cart",
            lines=cart_lines(),
            protection=spec.protection,
            protection_on=protection_on(),
            totals=totals(with_late_fees=False),
        )

    @app.get("/checkout/address")
    def address(request: Request) -> HTMLResponse:
        return render(
            request,
            "address.html",
            title="Delivery address",
            optins=spec.optins,
        )

    @app.post("/checkout/address")
    async def save_address(request: Request) -> RedirectResponse:
        sim().address = dict(await request.form())
        return RedirectResponse("/checkout/summary", status_code=303)

    @app.get("/checkout/summary")
    def summary(request: Request) -> HTMLResponse:
        return render(
            request,
            "summary.html",
            title="Order summary",
            lines=cart_lines(),
            protection=spec.protection,
            totals=totals(with_late_fees=True),
            late_fees=spec.late_fees if sim().cart else (),
        )

    @app.get("/payment")
    def payment(request: Request) -> HTMLResponse:
        return render(
            request,
            "payment.html",
            title="Payment",
        )
