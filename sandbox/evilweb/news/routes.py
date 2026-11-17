"""News: home -> article with a newsletter pop-up; a newsletter leave flow."""

from __future__ import annotations

from collections.abc import Callable

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from evilweb.common.leave import register_leave
from evilweb.plan import Plan

ARTICLES = {
    "monsoon-markets": (
        "Monsoon arrives early, markets shrug",
        "Rain arrived a week ahead of schedule across the southern states. Traders said the "
        "early onset was already priced in, and vegetable prices held steady.",
    ),
    "metro-line-four": (
        "Metro line four opens to riders",
        "The new line links the airport to the old city in 34 minutes. Officials expect 2 lakh "
        "riders a day once all stations open next month.",
    ),
    "chess-prodigy": (
        "Local chess prodigy wins national title",
        "The 14-year-old won the final round with a quiet endgame and said she will now focus "
        "on her school exams.",
    ),
}


def register(app: FastAPI, render: Callable[..., HTMLResponse], plan: Plan, sim) -> None:
    leave = plan.news_leave
    leave_entry = "/newsletter/leave/0"

    render.env.globals.update(leave=leave, leave_entry=leave_entry)
    page = render

    @app.get("/")
    def home(request: Request) -> HTMLResponse:
        return page(request, "home.html", title="Home", articles=ARTICLES)

    @app.get("/article/{slug}")
    def article(request: Request, slug: str) -> HTMLResponse:
        if slug not in ARTICLES:
            return render(request, "info.html", title="Not found", body="No such article.")
        headline, body = ARTICLES[slug]
        return page(
            request,
            "article.html",
            title=headline,
            headline=headline,
            body=body,
            show_popup=not sim().newsletter,
        )

    @app.post("/newsletter/subscribe")
    def subscribe(email: str = Form(...)) -> RedirectResponse:
        sim().newsletter = True
        sim().unsubscribed = False
        return RedirectResponse("/newsletter/thanks", status_code=303)

    @app.get("/newsletter/thanks")
    def thanks(request: Request) -> HTMLResponse:
        return page(request, "message.html", title="Subscribed", message="You are subscribed.")

    @app.get("/newsletter/unsubscribed")
    def unsubscribed(request: Request) -> HTMLResponse:
        return page(
            request,
            "message.html",
            title="Unsubscribed",
            message="You have left the newsletter. We will not email you again.",
        )

    def mark_done() -> None:
        sim().newsletter = False
        sim().unsubscribed = True

    register_leave(
        app,
        page,
        leave,
        base="/newsletter/leave",
        done_url="/newsletter/unsubscribed",
        on_done=mark_done,
        keep_url="/",
    )
