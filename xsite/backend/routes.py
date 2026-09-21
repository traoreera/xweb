"""xsite/backend/routes.py — les routes du site, montées directement sur
`app` par xsite/backend/main.py (mount(app, engine), appelé après xcore.boot()
puisque l'engine n'existe qu'une fois l'extension initialisée).

Pas de mount_xweb_page ici : ce site est entièrement public/anonyme (pas de
plugin_ctx réel, pas de RBAC à résoudre) — le contexte du shell est construit
à la main, même patron que contacts_demo_app.py/docs_site_app.py (racine du
dépôt, sessions précédentes), mais l'ENGINE vient cette fois du vrai
`ext.xweb` chargé par xcore.boot(), pas d'un QwebRegistry() maison.
"""

from __future__ import annotations

import asyncio
import itertools
import json
import re
import time
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from markupsafe import Markup, escape

from xweb.contrib import Contribution, nav
from xweb.engine.registry import QwebRegistry

from .catalog import build_catalog

_SHELL_CTX: dict = {
    "app_name": "xweb + xdsl",
    "page_title": "xweb + xdsl",
    "csrf_token": "site-demo-csrf-token",
    "locale": "fr",
    "locales": [],
    "commands": [],
    "status_left": [],
    "status_right": [],
    "user": None,
    "account": None,
    "current_path": "/",
    "login_url": "/login",
    "account_path": "/account/",
    "logout_path": "/account/logout",
    "_": lambda s: s,
}

_TAG_RE = re.compile(r"<[^>]+>")


def _summary(html: str, length: int = 90) -> str:
    text = re.sub(r"\s+", " ", _TAG_RE.sub(" ", html)).strip()
    return (text[:length] + "…") if len(text) > length else text


def mount(app: FastAPI, engine: QwebRegistry) -> None:
    """Enregistre nav + toutes les routes. Appelé une fois, après boot —
    voir xsite/backend/main.py::lifespan."""

    for section_id, label, path, icon in [
        ("site-home", "Accueil", "/", "home"),
        ("site-syntax", "Syntaxe xdsl", "/syntax", "document"),
        ("site-directives", "Directives QWeb", "/directives", "list"),
        ("site-components", "Composants", "/components", "grid"),
        ("site-guides", "Guides", "/guides", "sparkles"),
        ("site-demo", "Démo", "/demo", "bolt"),
    ]:
        nav.register(Contribution(plugin="site", id=section_id, label=label, path=path, icon=icon, order=100))

    syntax_pages = _index("syntax", ["component", "control-flow", "class-style", "text", "hyperscript", "data", "endpoint", "channel", "inherit", "filters"], engine, "site.syntax_")
    directive_pages = _index("directives", ["t-name", "t-if", "t-foreach", "t-esc", "t-att", "t-call", "t-set", "filters", "t-inherit", "passthrough"], engine, "site.directives_")
    guide_pages = _index("guides", ["styling", "hyperscript", "htmx", "architecture", "assets"], engine, "site.guides_")

    catalog, stats = build_catalog(engine)
    components_by_short = {c["short"]: c for c in catalog}

    def render_page(request: Request, title: str, content_html: str) -> HTMLResponse:
        content = Markup(content_html)
        if request.headers.get("HX-Request") == "true":
            return HTMLResponse(f"<title>{escape(title)}</title>{content}")
        ctx = dict(_SHELL_CTX)
        ctx["content"] = content
        ctx["page_title"] = title
        ctx["request"] = request
        ctx["nav_tree"] = nav.tree(None)
        return HTMLResponse(engine.render("xweb.shell", ctx))

    _mount_static_pages(app, engine, render_page, syntax_pages, directive_pages, guide_pages, catalog, components_by_short, stats)
    _mount_demo(app, engine, render_page)


def _index(section_key: str, ids: list[str], engine: QwebRegistry, template_prefix: str) -> dict:
    """Rend chaque page de texte UNE fois au boot (contenu statique, jamais
    par requête utilisateur) pour en extraire titre/résumé côté Python sans
    dupliquer les libellés — le titre affiché EST le <h1> du template lui-même."""
    pages = {}
    for pid in ids:
        t_name = template_prefix + pid.replace("-", "_")
        html = engine.render(t_name, {})
        title_match = re.search(r'class="[^"]*text-3xl[^"]*"[^>]*>([^<]+)<', html)
        title = title_match.group(1).strip() if title_match else pid
        pages[pid] = {"id": pid, "template": t_name, "title": title, "summary": _summary(html)}
    return pages


def _mount_static_pages(app, engine, render_page, syntax_pages, directive_pages, guide_pages, catalog, components_by_short, stats):
    @app.get("/", response_class=HTMLResponse)
    def home(request: Request) -> HTMLResponse:
        return render_page(request, "xweb + xdsl", engine.render("site.home", {}))

    @app.get("/syntax", response_class=HTMLResponse)
    def syntax_index(request: Request) -> HTMLResponse:
        return render_page(request, "Syntaxe xdsl", engine.render("site.syntax_index", {}))

    @app.get("/syntax/{page_id}", response_class=HTMLResponse)
    def syntax_detail(request: Request, page_id: str) -> HTMLResponse:
        page = syntax_pages.get(page_id)
        if page is None:
            return HTMLResponse("Page introuvable.", status_code=404)
        return render_page(request, page["title"], engine.render(page["template"], {}))

    @app.get("/directives", response_class=HTMLResponse)
    def directives_index(request: Request) -> HTMLResponse:
        return render_page(request, "Directives QWeb", engine.render("site.directives_index", {
    "hello": "Bonjour", "directives": directive_pages.values()
        }))

    @app.get("/directives/{page_id}", response_class=HTMLResponse)
    def directives_detail(request: Request, page_id: str) -> HTMLResponse:
        page = directive_pages.get(page_id)
        if page is None:
            return HTMLResponse("Directive introuvable.", status_code=404)
        return render_page(request, page["title"], engine.render(page["template"], {}))

    @app.get("/guides", response_class=HTMLResponse)
    def guides_index(request: Request) -> HTMLResponse:
        return render_page(request, "Guides", engine.render("site.guides_index", {}))

    @app.get("/guides/{page_id}", response_class=HTMLResponse)
    def guides_detail(request: Request, page_id: str) -> HTMLResponse:
        page = guide_pages.get(page_id)
        if page is None:
            return HTMLResponse("Guide introuvable.", status_code=404)
        return render_page(request, page["title"], engine.render(page["template"], {}))

    @app.get("/components", response_class=HTMLResponse)
    def components_index(request: Request) -> HTMLResponse:
        html = engine.render("site.components_index", {
            "components": catalog,
            "ok_count": f"{stats['ok']}/{len(catalog)} ok",
        })
        return render_page(request, "Composants", html)

    @app.get("/components/{short}", response_class=HTMLResponse)
    def component_detail(request: Request, short: str) -> HTMLResponse:
        comp = components_by_short.get(short)
        if comp is None:
            return HTMLResponse("Composant introuvable.", status_code=404)
        html = engine.render("site.component_detail", {
            "name": comp["name"], "short": comp["short"], "docstring": comp["docstring"],
            "rendered": Markup(comp["rendered"]), "status": comp["status"],
            "props_rows": comp["props_rows"], "xdsl_usage": comp["xdsl_usage"],
            "xweb_usage": comp["xweb_usage"], "shorthand_usage": comp["shorthand_usage"],
            "source": comp["source"],
        })
        return render_page(request, comp["name"], html)


def _mount_demo(app, engine, render_page):
    """La page de démo + son backend : un compteur htmx en mémoire, et un
    flux SSE alimentant `channel site_clock` (xsite/templates/demo.dsl)."""

    _counter = itertools.count(0)
    _count = 0

    def _counter_fragment() -> str:
        return engine.render("site.demo_counter", {"count": _count, "last_render": time.strftime("%H:%M:%S")})

    @app.get("/demo", response_class=HTMLResponse)
    def demo_page(request: Request) -> HTMLResponse:
        return render_page(request, "Démo interactive", engine.render("site.demo_page", {}))

    @app.get("/demo/counter", response_class=HTMLResponse)
    def demo_counter_get() -> HTMLResponse:
        return HTMLResponse(_counter_fragment())

    @app.post("/demo/counter", response_class=HTMLResponse)
    def demo_counter_incr() -> HTMLResponse:
        nonlocal _count
        _count += 1
        return HTMLResponse(_counter_fragment())

    @app.post("/demo/counter/reset", response_class=HTMLResponse)
    def demo_counter_reset() -> HTMLResponse:
        nonlocal _count
        _count = 0
        return HTMLResponse(_counter_fragment())

    # --- SSE — un tick par seconde, consommé par `channel site_clock` -----
    # SÉCURITÉ : endpoint public sans authentification, comme le reste de ce
    # site de démo. Un vrai flux applicatif authentifierait la connexion et
    # vérifierait le droit d'écouter CHAQUE channel demandé — ?channels= est
    # une demande du client, jamais une autorisation (voir
    # xweb/static/live_channel.js, §Sécurité, et xsite/templates/guides.dsl).
    @app.get("/demo/sse")
    async def demo_sse(request: Request, channels: str = "") -> StreamingResponse:
        wanted = {c for c in channels.split(",") if c}

        async def gen() -> AsyncIterator[str]:
            ticks = 0
            try:
                while not await request.is_disconnected():
                    ticks += 1
                    if not wanted or "clock" in wanted:
                        payload = {"time": time.strftime("%H:%M:%S"), "ticks": ticks}
                        yield f"event: clock\ndata: {json.dumps(payload)}\n\n"
                    await asyncio.sleep(1)
            except asyncio.CancelledError:
                pass

        return StreamingResponse(
            gen(), media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
