from contextlib import asynccontextmanager

from fastapi import FastAPI
from xcore import Xcore
from xweb.urls import mount_xweb_pages, PageRoute, PageView
from xweb.paths import plugin_prefix



page = PageRoute(path="/", view=lambda ctx, req: {}, template="site.landing", name="landing") # type: ignore


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

    # Démo de xweb.shell (docs/shell.md) — plugins/ est vide dans ce projet
    # (voir le commentaire plus bas sur AnonymousAuthBackend), donc aucun
    # plugin ne contribue jamais de nav/commande/status réels : sans ça, le
    # shell rendrait "Aucun plugin n'a encore contribué de navigation." et
    # rien d'autre, invisible à évaluer. Enregistré une seule fois ici (pas
    # par requête — nav/commands/status_bar sont des singletons de module,
    # xweb/contrib.py) avec plugin="site", même schéma qu'un vrai on_load()
    # de plugin. Voir la route "/shell" plus bas.
    from xweb.contrib import AUTHENTICATED, Contribution, commands, nav, status_bar

    nav.register(Contribution(id="site.nav.shell_home", plugin="site", label="Accueil du shell", icon="home", path="/shell", order=10))
    nav.register(Contribution(id="site.nav.components", plugin="site", label="Composants", icon="grid", path="/", order=20))
    nav.register(Contribution(id="site.nav.docs", plugin="site", label="Organisation", icon="building", order=30, parent_id=None))
    nav.register(Contribution(id="site.nav.docs.members", plugin="site", label="Membres", icon="users", path="/shell#membres", order=10, parent_id="site.nav.docs", badge="Démo"))
    nav.register(Contribution(id="site.nav.docs.security", plugin="site", label="Sécurité", icon="shield", path="/shell#securite", order=20, parent_id="site.nav.docs", permission=AUTHENTICATED))
    commands.register(Contribution(id="site.cmd.home", plugin="site", label="Aller à l'accueil du shell", icon="home", action_url="/shell", hotkey="G H"))
    commands.register(Contribution(id="site.cmd.components", plugin="site", label="Voir le catalogue de composants", icon="grid", action_url="/", hotkey="G C"))
    status_bar.register(Contribution(id="site.status.version", plugin="site", label="xweb v0.1", side="left"))
    status_bar.register(Contribution(id="site.status.demo", plugin="site", label="Démo — état en mémoire", icon="info", tooltip="Se réinitialise au redémarrage du serveur", side="right"))

    # Landing page sur "/" — aucun plugin ne peut la servir lui-même : xcore
    # préfixe systématiquement chaque routeur de plugin sous /plugins/<nom>/
    # (xcore/__init__.py::boot(), vérifié), donc "/" doit être monté ici,
    # directement sur `app`, plutôt que via un plugin. Un router sans
    # préfixe, inclus directement (pas collecté par PluginSupervisor),
    # échappe entièrement à ce préfixage. Le template vit dans templates/
    # (integration.yaml, namespaces.site), pas dans xweb/components/ (réservé
    # aux composants xweb.* partagés) ni un plugins/*/templates/ (ce n'est
    # la page d'aucun plugin en particulier).
    #
    # render_xweb_template() directement, PAS mount_xweb_page() : ce dernier
    # résout toujours l'utilisateur courant avant d'appeler la vue
    # (xweb/mount.py::mount_xweb_page — resolve_user_or_anonymous, même si
    # `view` ne lit jamais ctx.user), donc exige un AuthBackend enregistré,
    # même pour une page qui n'en a structurellement pas besoin. Sans aucun
    # plugin d'auth chargé (projet vide, "pour l'instant"), ça 503 sur
    # "Auth backend non disponible" avant même d'atteindre la vue — vérifié
    # en conditions réelles. La landing ne lit jamais ctx.user (view=() => {})
    # donc `user=None` explicite ici est correct, pas un contournement de
    # sécurité : rien sur cette page ne dépend d'être connecté ou non.
    from fastapi import APIRouter, Request, Response

    import landing_data
    from landing_data import showcase_context
    from xweb.mount import render_xweb_template
    from xweb.pdf import PdfUnavailable, render_pdf

    class _SiteContext:
        """plugin_ctx minimal pour une page qui n'appartient à aucun plugin
        — même contrat que le vrai PluginContext (name, get_service), pour
        que le contexte de rendu se comporte normalement si la landing page
        a un jour besoin d'un service (docs/plugins.md)."""

        name = "site"
        tenant_id = None
        caller = None

        def get_service(self, service_name: str):
            return xcore.services.get(service_name)

    site_router = APIRouter()

    @site_router.api_route("/", methods=["GET", "HEAD"])
    async def landing(request: Request):
        engine = xcore.services.get("ext.xweb").engine
        # xweb.notification_bell dans topbar_content (xweb.marketing_layout
        # -> xweb.topbar_slot, t-out volontaire — voir sa docstring dans
        # xweb/components/layout.xml : "topbar_content doit être du HTML
        # déjà rendu par le serveur"). Démo, comme le reste de cette page :
        # user=None sur la landing (voir le commentaire au-dessus de
        # lifespan()), donc un compteur/panneau partagé par tous les
        # visiteurs plutôt que par compte — cohérent avec le reste de la
        # page qui n'a structurellement pas de notion d'utilisateur connecté.
        bell_html = engine.render("xweb.notification_bell", {
            "unread_count": landing_data.notifications_context()["unread_count"],
            "notifications_url": "/notifications/panel",
        })
        return render_xweb_template(
            engine, "site.landing", _SiteContext(), request, user=None,
            extra={"showcase": showcase_context(), "topbar_content": bell_html},
            app_name=APP_NAME, page_title=APP_NAME,
            layout="xweb.marketing_layout", use_shell=True,
            demo_path="/shell",  # allume le lien "Démo" de xweb.marketing_layout, jusque-là jamais utilisé
        )

    # Démo de xweb.shell — sidebar (nav enregistrée juste au-dessus),
    # topbar, palette de commandes (Ctrl+K), status bar, zone de toasts.
    # render_xweb_template() direct, PAS mount_xweb_page() : même raison que
    # la landing (pas d'AuthBackend chargé dans ce projet, voir le
    # commentaire au-dessus de lifespan()) — user=None explicite, pas un
    # contournement de sécurité, cette page ne protège structurellement rien.
    #
    # templates/shell_demo.xml (site.shell_demo) doit exister sur disque
    # AVANT que ce fichier-ci (main.py) se recharge : `xcli manager start
    # --reload` ne surveille que les *.py (CLAUDE.md), donc ajouter un NOUVEAU
    # .xml pendant qu'un process --reload tourne déjà ne suffit pas à le
    # faire apparaître dans le registre — il faut un rechargement déclenché
    # par un .py (comme cette ligne de commentaire) ou un redémarrage manuel
    # complet, sinon KeyError "no template named 'site.shell_demo'" au
    # premier rendu malgré un fichier bel et bien présent sur disque.
    @site_router.get("/shell")
    async def shell_demo(request: Request):
        return render_xweb_template(
            xcore.services.get("ext.xweb").engine, "site.shell_demo", _SiteContext(), request, user=None,
            app_name=APP_NAME, page_title="Démo du shell",
            layout="xweb.shell", use_shell=True,
        )

    # Export PDF du catalogue de composants (bouton "Télécharger le PDF" de
    # site.components_catalogue) — même engine.render() que la page HTML,
    # jamais un second moteur de template (xweb/pdf.py::render_pdf(),
    # docs/pdf.md). PdfUnavailable (weasyprint absent) dégrade en 503
    # explicite plutôt que de faire planter la route — même philosophie que
    # le reste de xweb (jamais une exception non gérée qui casse une page
    # par ailleurs fonctionnelle).
    @site_router.get("/components.pdf")
    async def components_pdf():
        from datetime import date

        engine = xcore.services.get("ext.xweb").engine
        try:
            pdf_bytes = render_pdf(
                engine, "site.components_pdf",
                {
                    "showcase": showcase_context(),
                    "page_title": "Catalogue de composants",
                    "app_name": APP_NAME,
                    "generated_at": date.today().isoformat(),
                },
            )
        except PdfUnavailable as exc:
            return Response(content=str(exc), status_code=503, media_type="text/plain")
        return Response(
            content=pdf_bytes, media_type="application/pdf",
            headers={"Content-Disposition": 'attachment; filename="composants-xweb.pdf"'},
        )

    # Démo persistée de xweb.editable_table (templates/components_showcase.xml)
    # — même schéma que xweb.kanban dans l'ancien plugins/demo : un état de
    # module réel (landing_data.py), pas un mock. Chaque route rend le
    # fragment attendu par le hx-target/hx-swap posé côté composant (le <td>
    # édité pour une cellule, le <tr> entier pour un ajout, rien pour une
    # suppression/un réordonnancement — voir xweb/components/editable_table.xml).
    _EDITABLE_CELL_TEMPLATE = {
        "text": "xweb.editable_table_cell_text",
        "select": "xweb.editable_table_cell_select",
        "checkbox": "xweb.editable_table_cell_checkbox",
    }

    def _editable_column(key: str) -> dict | None:
        return next((c for c in landing_data.EDITABLE_TABLE_COLUMNS if c["key"] == key), None)

    @site_router.patch("/demo/table/cell/{row_id}")
    async def editable_table_save_cell(row_id: str, request: Request):
        form = await request.form()
        column = str(form.get("column", ""))
        col = _editable_column(column)
        engine = xcore.services.get("ext.xweb").engine
        if col is None:
            return Response(status_code=204)
        if col["type"] == "checkbox":
            # hx-vals="js:{..., value: event.target.checked}" -> un booléen
            # JS sérialisé en form-urlencoded devient la chaîne "true"/"false".
            value: object = str(form.get("value", "")).lower() == "true"
        else:
            value = str(form.get("value", ""))
        row = landing_data.editable_table_set_cell(row_id, column, value)
        if row is None:
            return Response(status_code=204)
        html = engine.render(_EDITABLE_CELL_TEMPLATE[col["type"]], {
            "row": row, "col": col, "save_url": "/demo/table/cell",
        })
        return Response(content=html, media_type="text/html")

    @site_router.post("/demo/table/row")
    async def editable_table_add_row():
        engine = xcore.services.get("ext.xweb").engine
        row = landing_data.editable_table_add_row()
        html = engine.render("xweb.editable_table_row", {
            "row": row, "columns": landing_data.EDITABLE_TABLE_COLUMNS,
            "save_url": "/demo/table/cell", "delete_row_url": "/demo/table/row",
            "reorder_url": "/demo/table/reorder",
        })
        return Response(content=html, media_type="text/html")

    @site_router.delete("/demo/table/row/{row_id}")
    async def editable_table_delete_row(row_id: str):
        landing_data.editable_table_delete_row(row_id)
        return Response(status_code=200)

    @site_router.post("/demo/table/reorder")
    async def editable_table_reorder(request: Request):
        import json as _json

        form = await request.form()
        try:
            order = _json.loads(str(form.get("order", "[]")))
        except ValueError:
            order = []
        if isinstance(order, list):
            landing_data.editable_table_reorder([str(i) for i in order])
        return Response(status_code=204)

    @site_router.post("/demo/table/column")
    async def editable_table_add_column():
        # Ajouter une colonne change l'en-tête ET chaque ligne -> toute la
        # grille se ré-affiche (xweb.editable_table entier), jamais un seul
        # <td>/<tr> comme les autres routes ci-dessus — voir la docstring
        # de add_column_url dans xweb/components/editable_table.xml.
        landing_data.editable_table_add_column()
        engine = xcore.services.get("ext.xweb").engine
        html = engine.render("xweb.editable_table", {
            "columns": landing_data.editable_table_columns(), "rows": landing_data.editable_table_rows(),
            "save_url": "/demo/table/cell", "add_row_url": "/demo/table/row",
            "delete_row_url": "/demo/table/row", "reorder_url": "/demo/table/reorder",
            "add_column_url": "/demo/table/column", "rename_column_url": "/demo/table/column",
        })
        return Response(content=html, media_type="text/html")

    @site_router.patch("/demo/table/column/{key}")
    async def editable_table_rename_column(key: str, request: Request):
        form = await request.form()
        label = str(form.get("label", "")).strip() or "Nouvelle colonne"
        col = landing_data.editable_table_rename_column(key, label)
        if col is None:
            return Response(status_code=204)
        engine = xcore.services.get("ext.xweb").engine
        html = engine.render("xweb.editable_table_header_cell", {"col": col, "rename_column_url": "/demo/table/column"})
        return Response(content=html, media_type="text/html")

    # Démo de xweb.notification_bell / xweb.notification_panel — même
    # schéma que la table éditable ci-dessus (état réel dans landing_data.py,
    # pas un mock). notification_bell cible /notifications/panel en GET
    # (hx-target="#xweb-notification-panel", posé une fois via le bouton
    # cloche) ; notification_panel se re-rend lui-même après chaque mutation
    # (mark_all_read_url/mark_read_url), toujours avec le même id — voir la
    # docstring de xweb.notification_panel dans
    # xweb/components/notifications.xml.
    def _render_notification_panel() -> str:
        engine = xcore.services.get("ext.xweb").engine
        ctx = landing_data.notifications_context()
        return engine.render("xweb.notification_panel", {
            "notifications": ctx["notifications"], "unread_count": ctx["unread_count"],
            "mark_all_read_url": "/notifications/mark-all-read",
            "mark_read_url": "/notifications/mark-read",
        })

    @site_router.get("/notifications/panel")
    async def notifications_panel():
        return Response(content=_render_notification_panel(), media_type="text/html")

    @site_router.post("/notifications/mark-all-read")
    async def notifications_mark_all_read():
        landing_data.mark_all_notifications_read()
        return Response(content=_render_notification_panel(), media_type="text/html")

    @site_router.post("/notifications/mark-read/{notif_id}")
    async def notifications_mark_read(notif_id: str):
        landing_data.mark_notification_read(notif_id)
        return Response(content=_render_notification_panel(), media_type="text/html")

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
