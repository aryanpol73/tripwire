"""News: home -> article with a newsletter pop-up; a newsletter leave flow."""

from __future__ import annotations

from collections.abc import Callable

from fastapi import FastAPI, Form, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse

from evilweb.common.leave import register_leave
from evilweb.patterns import nagging
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
        # v1: no pop-up on the home page. Nagging module: a returning pop-up is site-wide.
        returns = plan.nagging.popup == "returns" and not sim().newsletter
        return page(request, "home.html", title="Home", articles=ARTICLES, show_popup=returns)

    @app.get("/article/{slug}")
    def article(request: Request, slug: str) -> HTMLResponse:
        if slug not in ARTICLES:
            return render(request, "info.html", title="Not found", body="No such article.")
        headline, body = ARTICLES[slug]
        # Nagging module: count article views; the metered wall starts after the free ones.
        request.app.state.article_views = getattr(request.app.state, "article_views", 0) + 1
        show_wall = (
            plan.nagging.wall == "metered"
            and request.app.state.article_views > nagging.FREE_ARTICLES
        )
        return page(
            request,
            "article.html",
            title=headline,
            headline=headline,
            body=body,
            show_popup=not sim().newsletter
            and (plan.nagging.popup == "returns" or not sim().popup_dismissed),
            show_wall=show_wall,
            show_signin_banner=plan.nagging.wall == "decoy_banner",
        )

    @app.get("/signin")
    def signin(request: Request) -> HTMLResponse:
        # The nagging decoy's banner links here: an ordinary page, no password field.
        return render(request, "info.html", title="Sign in", body="Sign in from our app.")

    @app.post("/newsletter/dismiss", status_code=204)
    def dismiss() -> Response:
        # Closing the pop-up is remembered, so a v1 news page does not nag (Phase 9).
        sim().popup_dismissed = True
        return Response(status_code=204)

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
