"""SaaS: landing -> sign-up form -> review -> account; settings, billing, and a cancel flow."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from evilweb.common.leave import register_leave
from evilweb.patterns.common import secondary
from evilweb.patterns.sneaking import PLAN_MINOR, PLAN_NAME, RENEWAL_DATE, SUPPORT, TRIAL_DAYS
from evilweb.plan import Plan


def register(app: FastAPI, render, plan: Plan, sim) -> None:
    trial = plan.saas_trial
    leave = plan.saas_leave
    leave_entry = "/account/cancel/0"
    # The Upgrade control is measured too: in clean scenarios Cancel must match it.
    upgrade = secondary(plan.skin, plan.skin.w("upgrade"), 180, 44, 16)
    render.env.globals.update(
        leave=leave,
        leave_entry=leave_entry,
        upgrade=upgrade,
        plan_name=PLAN_NAME,
        plan_minor=PLAN_MINOR,
        trial_days=TRIAL_DAYS,
    )

    def chosen() -> dict:
        """What the sign-up form submitted; the page defaults if nothing was submitted yet."""
        form = sim().signup
        seats = int(form.get("seats", trial.default_seats))
        support = form.get("support", "1" if trial.support_preselected else None) == "1"
        return {"seats": seats, "support": support}

    @app.get("/")
    def landing(request: Request) -> HTMLResponse:
        return render(request, "landing.html", title="Home")

    @app.get("/pricing")
    def pricing(request: Request) -> HTMLResponse:
        return render(
            request, "pricing.html", title="Pricing", urgency=plan.urgency.widget(request.app.state)
        )

    @app.get("/signup")
    def signup(request: Request) -> HTMLResponse:
        return render(
            request,
            "signup.html",
            title="Start your trial",
            trial=trial,
            support=SUPPORT,
            newsletter_prechecked=plan.consent.newsletter_prechecked,
        )

    @app.post("/signup")
    async def save_signup(request: Request) -> RedirectResponse:
        sim().signup = dict(await request.form())
        return RedirectResponse("/signup/review", status_code=303)

    @app.get("/signup/review")
    def review(request: Request) -> HTMLResponse:
        c = chosen()
        monthly = PLAN_MINOR * c["seats"] + (SUPPORT.minor if c["support"] else 0)
        return render(
            request,
            "review.html",
            title="Review your trial",
            seats=c["seats"],
            support=SUPPORT if c["support"] else None,
            late_fees=trial.late_fees,
            monthly=monthly,
            renewal=trial.renewal,
            renewal_date=RENEWAL_DATE,
        )

    @app.post("/signup/confirm")
    def confirm() -> RedirectResponse:
        sim().signed_up = True
        sim().cancelled = False
        return RedirectResponse("/account", status_code=303)

    @app.get("/account")
    def account(request: Request) -> HTMLResponse:
        return render(request, "account.html", title="Your account", cancelled=sim().cancelled)

    @app.get("/account/settings")
    def settings(request: Request) -> HTMLResponse:
        return render(request, "settings.html", title=plan.skin.w("settings"))

    @app.get("/account/billing")
    def billing(request: Request) -> HTMLResponse:
        return render(request, "billing.html", title=plan.skin.w("billing"))

    @app.get("/account/cancelled")
    def cancelled(request: Request) -> HTMLResponse:
        return render(
            request,
            "info.html",
            title="Cancelled",
            body="Your plan is cancelled. You will not be charged again.",
        )

    def mark_cancelled() -> None:
        sim().cancelled = True

    register_leave(
        app,
        render,
        leave,
        base="/account/cancel",
        done_url="/account/cancelled",
        on_done=mark_cancelled,
        keep_url="/account",
    )
