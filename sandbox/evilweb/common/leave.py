"""The leave flow (cancel a plan, leave a newsletter), shared by saas and news.

Each step of a LeaveSpec is its own page, so every click is also a page load the walker can
count. The pages are generic; the spec decides which ones appear and in what order.
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from evilweb.patterns.obstruction import SUPPORT_EMAIL, SUPPORT_PHONE, LeaveSpec


def register_leave(
    app: FastAPI,
    render: Callable[..., HTMLResponse],
    spec: LeaveSpec,
    *,
    base: str,
    done_url: str,
    on_done: Callable[[], None],
    keep_url: str,
) -> None:
    def next_url(index: int) -> str:
        if index + 1 < len(spec.steps):
            return f"{base}/{index + 1}"
        return done_url

    @app.get(base + "/{index}")
    def step(request: Request, index: int) -> HTMLResponse:
        if not 0 <= index < len(spec.steps):
            return RedirectResponse(done_url, status_code=303)
        return render(
            request,
            "leave_step.html",
            title="Leaving",
            kind=spec.steps[index],
            action=f"{base}/{index}",
            keep_url=keep_url,
            phone=SUPPORT_PHONE,
            email=SUPPORT_EMAIL,
        )

    @app.post(base + "/{index}")
    def advance(index: int) -> RedirectResponse:
        target = next_url(index)
        if target == done_url:
            on_done()
        return RedirectResponse(target, status_code=303)
