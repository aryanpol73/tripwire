"""One small news site per red-team case. Local only, fake content, no external assets."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse

from redteam.cases import Case, get

ARTICLES = {
    "harbour-bridge": ("Harbour bridge reopens", "The bridge reopened after repairs."),
    "library-hours": ("Library extends its hours", "The central library now opens late."),
    "market-day": ("Saturday market returns", "Stalls are back on the square."),
    "school-garden": ("A garden for the school", "Pupils planted forty trees."),
}

STYLE = """
body{font-family:Georgia,serif;margin:0;color:#222;background:#fafafa}
header,main,footer{max-width:760px;margin:0 auto;padding:12px 16px}
nav a{margin-right:14px}
.promo,.sys{background:#fff3cd;border:1px solid #e0c36a;padding:8px}
.gate{border:1px solid #ccc;padding:8px;margin:8px 0}
#consent{position:fixed;bottom:0;left:0;right:0;z-index:1000;background:#fff;
 border-top:2px solid #333;padding:14px 16px}
#consent button{margin-right:10px;padding:8px 14px}
"""

BANNER = """<div id="consent" role="dialog" aria-label="Cookie consent">
<p>We use cookies and tracking for analytics and ads with our partners.</p>
<button type="button" onclick="choose()">Accept all</button>
<button type="button" onclick="choose()">Reject all</button>
</div>
<script>
function choose(){document.cookie='rt_consent=1; path=/';
 document.getElementById('consent').remove();}
if(document.cookie.indexOf('rt_consent=1')>=0){
 document.getElementById('consent').remove();}
</script>"""


def page(case: Case, title: str, body: str) -> str:
    links = "".join(f'<a href="/article/{slug}">{t}</a>' for slug, (t, _) in ARTICLES.items())
    return (
        f"<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        f"<title>{case.title or title}</title><style>{STYLE}</style></head><body>"
        f"<header><h1><a href='/'>Riverside Gazette</a></h1><nav>{links}</nav></header>"
        f"<main>{case.html}{body}</main>"
        f"<footer><a href='/about'>About</a> <a href='/contact'>Contact</a></footer>"
        f"{BANNER}</body></html>"
    )


def create_app(case_id: str) -> FastAPI:
    case = get(case_id)
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    @app.get("/", response_class=HTMLResponse)
    def home(request: Request) -> str:
        n = request.query_params.get("page", "0")
        items = "".join(
            f"<li><a href='/article/{slug}'>{t}</a></li>" for slug, (t, _) in ARTICLES.items()
        )
        return page(case, "Riverside Gazette", f"<h2>Latest (page {n})</h2><ul>{items}</ul>")

    @app.get("/article/{slug}", response_class=HTMLResponse)
    def article(slug: str) -> str:
        title, text = ARTICLES.get(slug, ("Not found", "No such article."))
        return page(case, title, f"<article><h2>{title}</h2><p>{text}</p></article>")

    @app.get("/about", response_class=HTMLResponse)
    def about() -> str:
        return page(case, "About", "<h2>About us</h2><p>A local paper.</p>")

    @app.get("/contact", response_class=HTMLResponse)
    def contact() -> str:
        return page(case, "Contact", "<h2>Contact</h2><p>Write to the editor.</p>")

    for path, body in case.extra_routes.items():

        def extra(body: str = body) -> str:
            return page(case, "Account", body)

        app.add_api_route(path, extra, methods=["GET"], response_class=HTMLResponse)

    @app.post("/{anything:path}", response_class=HTMLResponse)
    def post(anything: str) -> str:
        return page(case, "Submitted", "<p>Thanks.</p>")

    return app
