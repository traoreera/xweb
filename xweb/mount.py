"""Dispatcher de page xweb (docs/spec-v1.md §5, porté depuis xui/mount.py).

Différence de fond avec xui/mount.py, pas juste un renommage : le rendu
délègue à QwebRegistry.render(), qui est **synchrone** (Phase 1/2 — un
interpréteur d'arbre pur, aucune E/S). Le jour où xweb gagne un cache
(xweb Blueprint §5, "fonction compilée"), `QwebRegistry.render()`
redeviendra probablement async — pas anticipé tant que ce cache n'existe pas.

## Layouts

Chaque page rendue par mount_xweb_page/render_xweb_template est
enveloppée dans un *layout* (docs/shell.md) : le template `template=`
fourni au montage n'est jamais une page HTML complète, juste le contenu
de la région `content`. Trois cas :

    layout="xweb.shell"          (défaut, use_shell=True) — nav, ribbon,
                                 status bar, palette : l'application.
    layout="xweb.shell_minimal"  (MINIMAL_LAYOUT) — <head> complet
                                 (CSS/htmx/thème) mais aucune nav : les
                                 écrans d'auth (plugins/account), avant
                                 qu'un utilisateur existe.
    use_shell=False              — le fragment brut, sans <html> : pour
                                 une route htmx qui renvoie un morceau.

L'ancien `use_shell=False` du login (plugins/login, remplacé) renvoyait
en réalité un <div> sans <head> — donc sans aucune feuille de style.
Trouvé en reconstruisant le flux d'auth ; MINIMAL_LAYOUT existe pour ça.

## Navigation htmx

shell.xml pose `hx-boost` sur <body> : un clic sur un lien devient une
requête htmx (en-tête `HX-Request: true`) au lieu d'une navigation
navigateur. On renvoie alors juste le contenu (précédé d'un <title>, que
htmx recopie dans document.title), jamais le layout — sinon htmx
swapperait un <html> imbriqué dans #xweb-content. Un accès direct (F5,
lien copié-collé, sans l'en-tête) reçoit toujours la page complète.

Cas particulier : une page en layout *minimal* atteinte en boost (le
lien "Se connecter" du shell, un `next=` vers le login) ne doit pas
finir en fragment dans #xweb-content — elle répond HX-Redirect, htmx fait
alors une vraie navigation (redirect_response ci-dessous).

Aucun dispatcher générique de mutation ici, même principe que xui : une
page xweb ne fait que du GET/rendu. Les mutations htmx pointent vers une
route POST déclarée séparément par le plugin (docs/plugins.md §2).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Awaitable, Callable, Union
from urllib.parse import quote

from fastapi import APIRouter, Request, Response
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, StreamingResponse
from markupsafe import escape
from starlette.staticfiles import StaticFiles

from .context import XwebContext, XwebPermissionDenied, XwebRedirect, user_display
from .contrib import AUTHENTICATED
from .contrib import commands as commands_registry
from .contrib import nav as nav_registry
from .contrib import ribbon as ribbon_registry
from .contrib import status_bar as status_registry
from .i18n import LOCALE_COOKIE, LOCALE_QUERY_PARAM, SOURCE_LOCALE, Translator, resolve_locale
from .paths import plugin_prefix

try:  # import différé — ne pas forcer xweb.engine sur un plugin mode=spa pur
    from .engine.registry import QwebRegistry
except ImportError:  # pragma: no cover
    QwebRegistry = Any  # type: ignore[assignment,misc]

PageView = Callable[[XwebContext], Union[dict, XwebRedirect, Awaitable[Union[dict, XwebRedirect]]]]

DEFAULT_LAYOUT = "xweb.shell"
MINIMAL_LAYOUT = "xweb.shell_minimal"

# Chemins du pont HTML d'auth (plugins/account, docs/auth.md). Défauts du
# SDK plutôt que du kernel : un projet qui monte son propre écran de login
# les surcharge au montage (mount_xweb_page(..., login_path=...)). Dérivés de
# xweb.paths.plugin_prefix() (jamais "/plugins" en dur) — ce module EST le
# SDK générique, un projet qui change app.plugin_prefix dans integration.yaml
# ne doit pas devoir aussi surcharger ces trois défauts pour compenser.
DEFAULT_LOGIN_PATH = f"{plugin_prefix()}/account/login"
DEFAULT_ACCOUNT_PATH = f"{plugin_prefix()}/account/"
DEFAULT_LOGOUT_PATH = f"{plugin_prefix()}/account/logout"


# ---------------------------------------------------------------------
# Helpers htmx
# ---------------------------------------------------------------------


def is_hx_request(request: Request) -> bool:
    return request.headers.get("HX-Request") == "true"


def redirect_response(request: Request, url: str, status_code: int = 303) -> Response:
    """303 classique — ou, si la requête vient d'htmx (hx-boost), un 200
    porteur de `HX-Redirect` : htmx fait alors une vraie navigation vers
    `url`. Un 303 suivi par XHR ferait swapper la cible entière dans
    #xweb-content, cassé dès que cette cible n'est pas une page shell
    (login en layout minimal, page qui pose des cookies…)."""
    if is_hx_request(request):
        return Response(status_code=200, headers={"HX-Redirect": url})
    return RedirectResponse(url, status_code=status_code)


def login_url(login_path: str, next_path: str | None = None) -> str:
    """`login_path?next=<chemin>` — `next` est un chemin relatif (jamais
    une URL absolue, voir plugins/account pour le garde anti-open-redirect
    côté lecture)."""
    if not next_path:
        return login_path
    return f"{login_path}?next={quote(next_path, safe='/?=&')}"


def _request_path_with_query(request: Request) -> str:
    path = request.url.path
    if request.url.query:
        path = f"{path}?{request.url.query}"
    return path


def _csrf_token(plugin_ctx: Any) -> str:
    try:
        ext = plugin_ctx.get_service("ext.xweb")
    except Exception:
        return ""
    return getattr(ext, "csrf_token", "") or ""


def _resolve_translator(plugin_ctx: Any, request: Request) -> tuple[str, Translator, list[str]]:
    """(locale résolue, fonction _(), codes disponibles) — docs/i18n.md.
    Même prudence que _csrf_token : hors xcore (tests, rendu direct) ou
    catalogue absent, replie sur le français identité plutôt que de
    lever — `locales` ne porte alors que "fr", xweb.locale_switcher n'a
    donc rien à proposer et ne s'affiche pas (docs/components.md)."""
    catalog = None
    try:
        catalog = getattr(plugin_ctx.get_service("ext.xweb"), "i18n", None)
    except Exception:
        pass
    if catalog is None:
        return SOURCE_LOCALE, (lambda source: source), [SOURCE_LOCALE]
    locale = resolve_locale(request, catalog)
    return locale, catalog.translator_for(locale), catalog.available


def _set_locale_cookie_if_requested(response: Response, request: Request, locale: str) -> Response:
    """Persiste un choix de langue EXPLICITE (?lang=, xweb.locale_switcher)
    dans un cookie — même principe que le thème (localStorage), côté
    serveur puisque la traduction se décide au rendu, pas en CSS. Ne
    re-pose jamais le cookie sur un rendu "normal" (locale déjà connue via
    le cookie ou l'Accept-Language) — seulement quand l'utilisateur vient
    de cliquer un lien de langue, pour ne pas gonfler chaque réponse d'un
    Set-Cookie inutile."""
    requested = request.query_params.get(LOCALE_QUERY_PARAM)
    if requested and requested == locale:
        response.set_cookie(LOCALE_COOKIE, locale, max_age=365 * 24 * 3600, samesite="lax")
    return response


# ---------------------------------------------------------------------
# Contexte de rendu
# ---------------------------------------------------------------------


def _base_render_context(plugin_ctx: Any, request: Request, user: Any) -> dict:
    """Contexte auto-injecté, partagé entre mount_xweb_page et
    render_xweb_template pour qu'une route de mutation qui ré-affiche la
    même page obtienne le même contexte que le GET normal. Tout ce que le
    shell affiche (docs/shell.md) part d'ici — une page peut le lire aussi."""
    plugin_name = getattr(plugin_ctx, "name", "")
    # AUTHENTICATED : jamais un vrai rôle/permission, juste un marqueur pour
    # qu'une Contribution (docs/shell.md) puisse se déclarer "visible dès
    # qu'on est connecté, peu importe le rôle" via permission=AUTHENTICATED
    # — repéré sur une capture d'écran réelle : "Compte" (et ses sous-pages
    # Mon compte/Sécurité/Sessions) s'affichaient même en anonyme, alors que
    # cliquer dessus ne fait jamais que rebondir vers /login.
    user_roles = (set(user.get("roles", [])) | set(user.get("permissions", [])) | {AUTHENTICATED}) if user else set()
    status_left, status_right = status_registry.sides(user_roles)
    locale, translate, locales = _resolve_translator(plugin_ctx, request)
    return {
        "user": user,
        "account": user_display(user),
        "request": request,
        # Générique — un template qui doit référencer une page d'un AUTRE
        # plugin (ex. xweb.marketing_layout -> plugins/demo) construit son
        # lien avec ceci plutôt qu'un "/plugins/<nom>/" codé en dur
        # (xweb.paths.plugin_prefix(), même règle que "static" juste après).
        "plugin_prefix": plugin_prefix(),
        "static": lambda path: f"{plugin_prefix()}/{plugin_name}/static/{path}",
        "current_path": request.url.path,
        # Posé par le vrai xcore.kernel.tenancy.middleware.TenantMiddleware
        # (câblé au niveau module dans main.py, jamais dans lifespan() —
        # voir "Middleware ordering" dans CLAUDE.md) sur CHAQUE requête,
        # avec repli sur app.tenancy.default_tenant côté xcore lui-même si
        # rien d'autre ne résout un tenant — donc quasi toujours une vraie
        # valeur, jamais None en usage réel. None ici seulement si ce
        # middleware n'a jamais tourné (Request construit à la main, comme
        # dans certains tests) — jamais fabriqué ici, xweb ne fait que
        # relayer la décision déjà prise par xcore, pas la deviner.
        "tenant_id": getattr(request.state, "tenant_id", None),
        "hx_request": is_hx_request(request),
        "csrf_token": _csrf_token(plugin_ctx),
        "nav_tree": nav_registry.tree(user_roles),
        "ribbon": ribbon_registry.list(user_roles),
        "commands": commands_registry.list(user_roles),
        "status_left": status_left,
        "status_right": status_right,
        "locale": locale,
        "locales": locales,
        "_": translate,
    }


def _full_title(page_title: str, app_name: str) -> str:
    return page_title if not app_name or page_title == app_name else f"{page_title} · {app_name}"


def render_xweb_template(
    engine: "QwebRegistry",
    template: str,
    plugin_ctx: Any,
    request: Request,
    user: Any,
    extra: dict | None = None,
    status_code: int = 200,
    *,
    use_shell: bool = True,
    layout: str | None = None,
    app_name: str = "xweb",
    page_title: str | None = None,
    login_path: str = DEFAULT_LOGIN_PATH,
    account_path: str = DEFAULT_ACCOUNT_PATH,
    logout_path: str = DEFAULT_LOGOUT_PATH,
    demo_path: str | None = None,
    headers: dict[str, str] | None = None,
) -> Response:
    """Rend `template` dans son layout (voir docstring du module) — aussi
    utilisable hors du flux mount_xweb_page, typiquement depuis une route
    POST qui doit remontrer la même page avec des erreurs de validation
    (xweb.forms.parse_form) plutôt que rediriger.

    `extra["page_title"]` (posé par la vue) l'emporte sur `page_title` —
    un titre dynamique ("Contact — Ada") sans rien changer au montage.

    `demo_path=None` par défaut, PAS de valeur calculée à partir de
    plugin_prefix() comme login_path/account_path/logout_path —
    contrairement à eux, "un plugin demo existe" n'est jamais garanti
    (know/features/marketing-layout-hardcoded-links.md, le lien "Démo" de
    xweb.marketing_layout était codé en dur sans condition). Un appelant
    qui a réellement un plugin demo passe son chemin explicitement."""
    extra = dict(extra or {})
    title = _full_title(str(extra.get("page_title") or page_title or app_name), app_name)

    ctx_dict = _base_render_context(plugin_ctx, request, user)
    ctx_dict.update({
        "app_name": app_name,
        "page_title": title,
        "login_path": login_path,
        "account_path": account_path,
        "logout_path": logout_path,
        "demo_path": demo_path,
        "login_url": login_url(login_path, _request_path_with_query(request)),
    })
    ctx_dict.update(extra)
    ctx_dict["page_title"] = title
    body = engine.render(template, ctx_dict)  # synchrone — voir docstring du module

    locale = ctx_dict["locale"]

    layout_name = layout if layout is not None else (DEFAULT_LAYOUT if use_shell else None)
    if layout_name is None:
        return _set_locale_cookie_if_requested(HTMLResponse(body, status_code=status_code, headers=headers), request, locale)

    if is_hx_request(request):
        if layout_name != DEFAULT_LAYOUT and request.method in ("GET", "HEAD"):
            # Page hors shell atteinte en boost — vraie navigation, jamais un fragment.
            resp = Response(status_code=200, headers={"HX-Redirect": _request_path_with_query(request)})
            return _set_locale_cookie_if_requested(resp, request, locale)
        fragment = f"<title>{escape(title)}</title>{body}"
        return _set_locale_cookie_if_requested(HTMLResponse(fragment, status_code=status_code, headers=headers), request, locale)

    ctx_dict["content"] = body
    resp = HTMLResponse(engine.render(layout_name, ctx_dict), status_code=status_code, headers=headers)
    return _set_locale_cookie_if_requested(resp, request, locale)


def _render_403(
    engine: "QwebRegistry", plugin_ctx: Any, request: Request, user: Any, required_roles: tuple[str, ...], **kw,
) -> Response:
    roles = ", ".join(required_roles)
    try:
        return render_xweb_template(
            engine, "xweb.error_page", plugin_ctx, request, user, status_code=403,
            extra={
                "code": "403", "title": "Accès refusé",
                "message": f"Rôle(s) requis : {roles}" if roles else "Vous n'avez pas accès à cette page.",
                "page_title": "Accès refusé",
            },
            **kw,
        )
    except KeyError:  # registre sans les composants xweb (tests, projet minimal) — repli brut
        return HTMLResponse(f"<h1>403 — Accès refusé</h1><p>Rôle(s) requis : {escape(roles)}</p>", status_code=403)


# ---------------------------------------------------------------------
# Montage d'une page
# ---------------------------------------------------------------------


def mount_xweb_page(
    router: APIRouter,
    plugin_ctx: Any,
    engine: "QwebRegistry",
    *,
    path: str,
    template: str,
    view: PageView,
    login_path: str = DEFAULT_LOGIN_PATH,
    account_path: str = DEFAULT_ACCOUNT_PATH,
    logout_path: str = DEFAULT_LOGOUT_PATH,
    demo_path: str | None = None,
    use_shell: bool = True,
    layout: str | None = None,
    app_name: str = "xweb",
    page_title: str | None = None,
    name: str | None = None,
) -> None:
    """Monte UNE page server-rendue sur `path`.

    Toujours GET (+ HEAD) — une mutation reste une route POST explicite
    déclarée à côté, jamais un mount_xweb_page avec methods=("GET","POST").

    `view(ctx)` reçoit un XwebContext déjà résolu et retourne soit un
    dict de contexte de template, soit un XwebRedirect. Anonyme sur une
    page qui exige un utilisateur (ctx.require_user/require_role) →
    redirection vers `login_path?next=<page>` ; connecté sans le rôle →
    page 403 (xweb.error_page, dans le shell).

    Seule entrée de xweb qui exige xcore à l'appel (pas à l'import) —
    `resolve_user_or_anonymous` importe `xcore.kernel.api.rbac`
    paresseusement à l'intérieur de la fonction.
    """
    from .context import resolve_user_or_anonymous

    render_kw = dict(
        use_shell=use_shell, layout=layout, app_name=app_name, page_title=page_title,
        login_path=login_path, account_path=account_path, logout_path=logout_path, demo_path=demo_path,
    )

    @router.api_route(path, methods=["GET", "HEAD"], response_class=HTMLResponse, name=name)
    async def render_page(request: Request):
        user = await resolve_user_or_anonymous(request)

        ctx = XwebContext(plugin_ctx=plugin_ctx, request=request, user=user)
        try:
            result = view(ctx)
            if hasattr(result, "__await__"):
                result = await result
        except XwebPermissionDenied as exc:
            if user is None:
                return redirect_response(request, login_url(login_path, _request_path_with_query(request)))
            return _render_403(engine, plugin_ctx, request, user, exc.required_roles, **render_kw)

        if isinstance(result, XwebRedirect):
            return RedirectResponse(result.path, status_code=result.code)

        return render_xweb_template(engine, template, plugin_ctx, request, user, extra=result, **render_kw)


# ---------------------------------------------------------------------
# Statics / SPA — inchangés depuis xui
# ---------------------------------------------------------------------


class _RevalidateStaticFiles(StaticFiles):
    """`StaticFiles` de Starlette ne pose aucun `Cache-Control` par défaut —
    un navigateur applique alors sa propre heuristique (souvent basée sur
    `Last-Modified`) et peut réutiliser une copie en cache sans même
    revalider, y compris sur un rechargement simple. Constaté en vrai : après
    `npm run build:css`, un navigateur affichait encore l'ancien `app.css`
    (icônes non dimensionnées) malgré un fichier serveur à jour — le serveur
    servait la bonne réponse (vérifié par curl), seul le cache du navigateur
    était en cause.

    `no-cache` (pas `no-store`) force une requête conditionnelle
    (`If-None-Match`) à chaque chargement : toujours à jour, mais un fichier
    inchangé répond encore en 304 sans re-télécharger le contenu — pas de
    coût réel en dev, et les fichiers ici sont de toute façon petits/peu
    nombreux (htmx, _hyperscript, app.css)."""

    def file_response(self, *args, **kwargs):
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "no-cache"
        return response


def mount_builtin_assets(app: "FastAPI", url_prefix: str = "/xweb-static") -> None:
    """Sert les assets statiques livrés avec le SDK (app.css, htmx.min.js,
    _hyperscript.min.js — docs/theming.md). Un seul appel au niveau app."""
    static_dir = Path(__file__).parent / "static"
    if static_dir.is_dir():
        app.mount(url_prefix, _RevalidateStaticFiles(directory=str(static_dir)), name="xweb-static")


def mount_plugin_static(router: APIRouter, static_dir: Path, url_path: str = "/static") -> None:
    """Monte le dossier statique propre à CE plugin, sous son propre
    routeur — atterrit sous <préfixe plugin>/<name>/static/... (xweb.paths.plugin_prefix())
    grâce au préfixage déjà appliqué par le kernel. Silencieux si static_dir
    n'existe pas encore."""
    static_dir = Path(static_dir).resolve()
    if static_dir.is_dir():
        router.mount(url_path, _RevalidateStaticFiles(directory=str(static_dir)), name="plugin-static")


def mount_spa(router: APIRouter, dist_dir: Path) -> None:
    """Sert un build SPA statique déjà compilé — zéro dépendance à xweb.engine
    ou xweb.context. Toute route API doit être déclarée AVANT cet appel."""
    dist_dir = Path(dist_dir).resolve()
    if not dist_dir.exists():
        raise FileNotFoundError(f"dist_dir introuvable : {dist_dir} — build requis avant packaging")

    assets_dir = dist_dir / "assets"
    if assets_dir.is_dir():
        router.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    index_path = dist_dir / "index.html"

    @router.get("/{full_path:path}", response_class=HTMLResponse)
    async def spa_fallback(full_path: str):
        return FileResponse(index_path)


_PROXY_EXCLUDED_REQUEST_HEADERS = {"host", "content-length"}
_PROXY_EXCLUDED_RESPONSE_HEADERS = {"content-length", "transfer-encoding", "connection"}
_PROXY_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"]


def mount_dev_proxy(router: APIRouter, dev_server: str) -> None:
    """Reverse-proxy vers un dev server front vivant (Vite/webpack --host)
    au lieu de servir un dist/ pré-compilé. HTTP seulement — pas de proxy
    des upgrades WebSocket (HMR ne fonctionnera pas tel quel), même
    limite assumée que dans xui/mount.py."""
    import httpx

    client = httpx.AsyncClient(base_url=dev_server.rstrip("/"))

    @router.api_route("/{full_path:path}", methods=_PROXY_METHODS)
    async def proxy(full_path: str, request: Request):
        body = await request.body()
        headers = {
            k: v for k, v in request.headers.items() if k.lower() not in _PROXY_EXCLUDED_REQUEST_HEADERS
        }
        url_kwargs: dict = {"path": f"/{full_path}"}
        if request.url.query:
            url_kwargs["query"] = request.url.query.encode("utf-8")
        upstream_req = client.build_request(
            request.method, httpx.URL(**url_kwargs), headers=headers, content=body,
        )
        upstream_resp = await client.send(upstream_req, stream=True)

        async def _stream():
            async for chunk in upstream_resp.aiter_raw():
                yield chunk
            await upstream_resp.aclose()

        resp_headers = {
            k: v for k, v in upstream_resp.headers.items() if k.lower() not in _PROXY_EXCLUDED_RESPONSE_HEADERS
        }
        return StreamingResponse(_stream(), status_code=upstream_resp.status_code, headers=resp_headers)


def mount_spa_or_proxy(
    router: APIRouter, *, dist_dir: Path | None = None, dev_server: str | None = None,
) -> None:
    """Bascule entre les deux modes spa du manifeste : dev_server si
    présent, sinon dist_dir."""
    if dev_server:
        mount_dev_proxy(router, dev_server)
    elif dist_dir is not None:
        mount_spa(router, dist_dir)
    else:
        raise ValueError("mount_spa_or_proxy : dist_dir ou dev_server requis")
