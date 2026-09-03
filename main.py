from contextlib import asynccontextmanager

from fastapi import FastAPI
from xcore import Xcore

from xweb.paths import plugin_prefix

# plugins/auth (docs/auth.md) est un vrai plugin trusted qui s'enregistre
# lui-même : `register_auth_backend(XAuthBackend(...))` dans son on_load()
# (plugins/auth/src/main.py). L'AnonymousAuthBackend posé ici avant n'a
# plus lieu d'être — le garder ferait gagner le dernier register_auth_backend
# appelé, par pur hasard d'ordre de chargement des plugins, ce qui masquerait
# silencieusement un vrai bug si plugins/auth échoue à charger (on aurait
# alors un anonyme partout au lieu d'un 503 explicite qui dit clairement
# "le plugin auth n'a pas chargé").

xcore = Xcore()

# Nom affiché (titre de page, en-tête du shell/de la landing page) — pas lu
# depuis integration.yaml (app.name) : Xcore n'expose que _config (privé,
# xcore/__init__.py, vérifié), aucun accesseur public vers la config
# app: chargée. Dupliqué ici plutôt que de dépendre d'un attribut privé qui
# pourrait disparaître sans avertissement entre deux versions de xcore.
APP_NAME = "xweb"


@asynccontextmanager
async def lifespan(app: FastAPI):
    await xcore.boot(app)

    # docs/spec-v1.md §3 — un plugin déchargé/rechargé nettoie QwebRegistry
    # + les 4 registres de contribution. Doit être câblé ICI, après boot() :
    # ExtensionLoader n'expose jamais events/ctx à ext.xweb lui-même
    # (xcore/services/extensions/loader.py, vérifié — voir docstring de
    # bind_hot_reload).
    from xweb.engine.integration.xcore import bind_hot_reload

    bind_hot_reload(xcore, xcore.services.get("ext.xweb"))

    # Landing page sur "/" — aucun plugin ne peut la servir lui-même : xcore
    # préfixe systématiquement chaque routeur de plugin sous /plugins/<nom>/
    # (xcore/__init__.py::boot(), vérifié), donc "/" doit être monté ici,
    # directement sur `app`, plutôt que via un plugin. Un router sans
    # préfixe, inclus directement (pas collecté par PluginSupervisor),
    # échappe entièrement à ce préfixage. Le template vit dans templates/
    # (integration.yaml, namespaces.site), pas dans xweb/components/ (réservé
    # aux composants xweb.* partagés) ni un plugins/*/templates/ (ce n'est
    # la page d'aucun plugin en particulier).
    from fastapi import APIRouter

    from xweb.mount import mount_xweb_page

    class _SiteContext:
        """plugin_ctx minimal pour une page qui n'appartient à aucun plugin
        — même contrat que le vrai PluginContext (name, get_service), pour
        que XwebContext se comporte normalement si la landing page a un
        jour besoin d'un service (docs/plugins.md)."""

        name = "site"
        tenant_id = None
        caller = None

        def get_service(self, service_name: str):
            return xcore.services.get(service_name)

    site_router = APIRouter()
    mount_xweb_page(
        site_router, _SiteContext(), xcore.services.get("ext.xweb").engine,
        path="/", template="site.landing", view=lambda ctx: {},
        app_name=APP_NAME, page_title=APP_NAME,
        layout="xweb.marketing_layout", use_shell=False,
    )
    app.include_router(site_router)

    yield
    await xcore.shutdown()


app = FastAPI(lifespan=lifespan)

# Tout ce qui suit doit être posé AVANT que l'app serve — Starlette refuse
# d'ajouter un middleware une fois démarrée (xcore/__init__.py::setup()
# le documente explicitement ; trouvé jamais appelé du tout ici jusqu'à
# ce tour — TraceContextMiddleware/TenantMiddleware manquaient depuis le
# début du squelette, pas juste CSRF/security).
from xweb.csrf import CSRFMiddleware  # noqa: E402
from xweb.mount import mount_builtin_assets  # noqa: E402
from xweb.security import SecurityHeadersMiddleware  # noqa: E402

xcore.setup(app)
mount_builtin_assets(app)  # sert xweb/static/ (htmx, _hyperscript) sous /xweb-static/

app.add_middleware(SecurityHeadersMiddleware, report_only=True, exclude_paths=("/xweb-static",))

# get_token est un callable, pas la valeur elle-même — ext.xweb n'existe
# qu'après xcore.boot() (dans lifespan(), donc APRÈS ce module-level code),
# mais le corps du lambda ne s'exécute qu'à la requête, bien après boot()
# (docs/csrf.py). Enregistrer le middleware ici, avant boot(), reste donc
# correct malgré cet ordre qui semble à l'envers au premier coup d'œil.
app.add_middleware(
    CSRFMiddleware,
    get_token=lambda: xcore.services.get("ext.xweb").csrf_token,
    # Jamais "/plugins/" en dur : app.plugin_prefix dans integration.yaml
    # décide où xcore monte réellement chaque plugin (xweb.paths.plugin_prefix()) —
    # un oubli ici laisserait CSRFMiddleware ne rien protéger du tout après
    # un changement de préfixe, silencieusement (pas d'erreur au boot).
    protected_paths=(f"{plugin_prefix()}/",),
    # "session" est l'héritage xui ; ici la session navigateur est le cookie
    # access_token posé par plugins/account (docs/auth.md). Sans lui dans
    # cette liste, le middleware ne vérifiait jamais rien en pratique.
    session_cookies=("session", "access_token"),
)
