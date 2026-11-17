"""App factory: one FastAPI app serves one scenario on its site type.

State lives in memory and is shared by every visitor, which is fine for a single-user
sandbox. POST /__reset starts a scenario over. Nothing is ever sent off the machine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse
from jinja2 import ChoiceLoader, Environment, FileSystemLoader, StrictUndefined, select_autoescape

from evilweb.patterns.common import SITE_NAMES, format_inr
from evilweb.plan import Plan, build_plan
from evilweb.skins import stylesheet
from tripwire.schemas.trace import SiteType

HERE = Path(__file__).parent
CONSENT_COOKIE = "ew_consent"


@dataclass
class Sim:
    """Everything a visitor has done so far in this scenario."""

    consent: dict[str, Any] | None = None
    cart: dict[str, int] = field(default_factory=dict)
    sneaked_added: bool = False
    protection: bool | None = None  # None = the page default (pre-checked or not)
    address: dict[str, str] = field(default_factory=dict)
    signup: dict[str, Any] = field(default_factory=dict)
    signed_up: bool = False
    cancelled: bool = False
    newsletter: bool = False
    unsubscribed: bool = False


class Renderer:
    def __init__(self, plan: Plan) -> None:
        site = plan.scenario.site_type
        self.env = Environment(
            loader=ChoiceLoader(
                [
                    FileSystemLoader(HERE / site.value / "templates"),
                    FileSystemLoader(HERE / "common" / "templates"),
                ]
            ),
            autoescape=select_autoescape(["html"]),
            undefined=StrictUndefined,
        )
        skin = plan.skin
        self.env.globals.update(
            plan=plan,
            skin=skin,
            c=skin.c,
            sid=skin.id,
            w=skin.w,
            inr=format_inr,
            css=stylesheet(skin),
            site_name=SITE_NAMES[site],
            site_base=f"{site.value}_base.html",
        )

    def __call__(self, request: Request, template: str, **context: Any) -> HTMLResponse:
        # Cookies ignore the port, so a choice made on another scenario's server would leak
        # in. The banner therefore needs both the cookie and this server's own record.
        chose = CONSENT_COOKIE in request.cookies and request.app.state.sim.consent is not None
        context.setdefault("show_banner", not chose)
        html = self.env.get_template(template).render(request=request, **context)
        return HTMLResponse(html)


def create_app(scenario_id: str) -> FastAPI:
    plan = build_plan(scenario_id)
    app = FastAPI(title=f"Evil Web: {scenario_id}", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.sim = Sim()
    render = Renderer(plan)

    def sim() -> Sim:
        return app.state.sim

    @app.post("/consent", status_code=204)
    async def consent(request: Request) -> Response:
        body = await request.json()
        sim().consent = body
        response = Response(status_code=204)
        response.set_cookie(CONSENT_COOKIE, str(body.get("choice", "custom")), samesite="lax")
        return response

    @app.post("/__reset", status_code=204)
    def reset() -> Response:
        app.state.sim = Sim()
        return Response(status_code=204)

    @app.get("/__scenario")
    def scenario() -> JSONResponse:
        # The id only: a walker must discover patterns, never read them from the server.
        return JSONResponse({"scenario_id": scenario_id, "site_type": plan.scenario.site_type})

    @app.get("/about")
    def about(request: Request) -> HTMLResponse:
        return render(request, "info.html", title="About", body="A fake site for testing.")

    @app.get("/privacy")
    def privacy(request: Request) -> HTMLResponse:
        return render(request, "info.html", title="Privacy", body="No real data is collected.")

    site = plan.scenario.site_type
    if site == SiteType.SHOP:
        from evilweb.shop.routes import register
    elif site == SiteType.NEWS:
        from evilweb.news.routes import register
    else:
        from evilweb.saas.routes import register
    register(app, render, plan, sim)
    return app
