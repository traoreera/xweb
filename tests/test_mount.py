"""mount_xweb_page bout-en-bout via un vrai cycle ASGI (TestClient) — la
seule fonction de xweb qui exige xcore À L'APPEL (docs/mount.py) : on
monkeypatch resolve_user_or_anonymous plutôt que d'installer xcore
entier, même stratégie que xui/tests/test_sans_xcore.py.
"""

from pathlib import Path

from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from xweb.contrib import Contribution, nav
from xweb.engine.registry import QwebRegistry
from xweb.mount import mount_xweb_page

COMPONENTS_DIR = Path(__file__).parent.parent / "xweb" / "components"

TEMPLATE = """<template t-name="test.page">
    <t t-if="user"><p t-esc="'Bonjour ' + user.get('name', user.get('sub', ''))"/></t>
    <t t-else="1"><p>Anonyme</p></t>
</template>"""

# Shell minimal pour les tests — pas xweb/components/shell.xml en entier, juste
# assez pour prouver que content/nav_tree/app_name atteignent bien le
# rendu final (docs/shell.md, xweb/mount.py::render_xweb_template).
TEST_SHELL = """<template t-name="xweb.shell">
    <html>
    <head><title><t t-esc="page_title"/></title></head>
    <body>
        <nav><t t-foreach="nav_tree" t-as="n"><a t-att-href="n['path']"><t t-esc="n['label']"/></a></t></nav>
        <main><t t-out="content"/></main>
    </body>
    </html>
</template>"""


class FakePluginCtx:
    name = "demo"
    tenant_id = None
    caller = None

    def get_service(self, name):
        return None


def make_app(*, view, monkeypatch, user=None, **mount_kwargs):
    async def fake_resolve(request):
        return user

    monkeypatch.setattr("xweb.context.resolve_user_or_anonymous", fake_resolve)

    registry = QwebRegistry()
    registry.register_source(TEMPLATE)
    registry.register_source(TEST_SHELL)

    app = FastAPI()
    router = APIRouter()
    mount_xweb_page(
        router, FakePluginCtx(), registry,
        path="/", template="test.page", view=view, login_path="/login",
        **mount_kwargs,
    )
    app.include_router(router)
    return app


def test_renders_page_for_anonymous_user(monkeypatch):
    app = make_app(view=lambda ctx: {}, monkeypatch=monkeypatch, user=None)
    r = TestClient(app).get("/")
    assert r.status_code == 200
    assert "Anonyme" in r.text


def test_renders_page_with_logged_in_user(monkeypatch):
    user = {"name": "Ada", "roles": []}
    app = make_app(view=lambda ctx: {}, monkeypatch=monkeypatch, user=user)
    r = TestClient(app).get("/")
    assert "Bonjour Ada" in r.text


def test_permission_denied_redirects_anonymous_to_login(monkeypatch):
    def view(ctx):
        ctx.require_role("crm.viewer")
        return {}

    app = make_app(view=view, monkeypatch=monkeypatch, user=None)
    r = TestClient(app, follow_redirects=False).get("/")
    assert r.status_code == 303
    assert r.headers["location"] == "/login?next=/"


def test_403_for_authenticated_user_missing_role(monkeypatch):
    def view(ctx):
        ctx.require_role("crm.viewer")
        return {}

    user = {"name": "Bob", "roles": []}
    app = make_app(view=view, monkeypatch=monkeypatch, user=user)
    r = TestClient(app).get("/")
    assert r.status_code == 403
    assert "crm.viewer" in r.text


def test_view_returning_redirect_is_honoured(monkeypatch):
    def view(ctx):
        return ctx.redirect("/elsewhere")

    app = make_app(view=view, monkeypatch=monkeypatch, user=None)
    r = TestClient(app, follow_redirects=False).get("/")
    assert r.status_code == 303
    assert r.headers["location"] == "/elsewhere"


def test_async_view_is_awaited(monkeypatch):
    async def view(ctx):
        return {}

    user = {"name": "Ada", "roles": []}
    app = make_app(view=view, monkeypatch=monkeypatch, user=user)
    r = TestClient(app).get("/")
    assert "Bonjour Ada" in r.text


def test_post_is_not_allowed_only_get_and_head(monkeypatch):
    """docs/mount.py: une page reste une opération de lecture — jamais
    methods=("GET","POST")."""
    app = make_app(view=lambda ctx: {}, monkeypatch=monkeypatch, user=None)
    r = TestClient(app).post("/")
    assert r.status_code == 405


# ---------------------------------------------------------------------
# xweb.shell (docs/shell.md) — chaque page est enveloppée par défaut
# ---------------------------------------------------------------------


def test_page_is_wrapped_in_the_shell_by_default(monkeypatch):
    app = make_app(view=lambda ctx: {}, monkeypatch=monkeypatch, user=None, app_name="Ma App")
    r = TestClient(app).get("/")
    assert "<html>" in r.text and "<body>" in r.text  # vient du shell, pas de test.page
    assert "Anonyme" in r.text  # le contenu de test.page est bien dedans


def test_nav_tree_reaches_the_shell(monkeypatch):
    nav.register(Contribution(id="test.mount_nav_item", plugin="demo", label="Tableau de bord", path="/dashboard"))
    try:
        app = make_app(view=lambda ctx: {}, monkeypatch=monkeypatch, user=None)
        r = TestClient(app).get("/")
        assert 'href="/dashboard"' in r.text
        assert "Tableau de bord" in r.text
    finally:
        nav.unregister_plugin("demo")  # singleton de module partagé entre tests


def test_authenticated_permission_hides_from_anonymous_and_shows_for_any_logged_in_user(monkeypatch):
    """_base_render_context() injecte AUTHENTICATED (xweb/contrib.py) dans
    user_roles pour TOUT utilisateur connecté, peu importe ses rôles réels
    — trouvé en repérant "Compte" visible même en anonyme sur une capture
    d'écran réelle du shell (docs/shell.md)."""
    from xweb.contrib import AUTHENTICATED

    nav.register(Contribution(id="test.mount_auth_item", plugin="demo", label="Mon compte", path="/mine", permission=AUTHENTICATED))
    try:
        anon = TestClient(make_app(view=lambda ctx: {}, monkeypatch=monkeypatch, user=None)).get("/")
        assert "Mon compte" not in anon.text

        # N'importe quel utilisateur connecté, même sans le moindre rôle propre.
        user = {"sub": "u1", "roles": []}
        logged_in = TestClient(make_app(view=lambda ctx: {}, monkeypatch=monkeypatch, user=user)).get("/")
        assert "Mon compte" in logged_in.text
    finally:
        nav.unregister_plugin("demo")


def test_hx_request_header_skips_the_shell_too(monkeypatch):
    """La navigation boostée (hx-boost dans shell.xml) envoie HX-Request:
    true — le serveur doit répondre avec juste le contenu, jamais le
    shell entier, sinon htmx swap un <html> imbriqué dans #xweb-content."""
    app = make_app(view=lambda ctx: {}, monkeypatch=monkeypatch, user=None)
    r = TestClient(app).get("/", headers={"HX-Request": "true"})
    assert r.status_code == 200
    assert "<html>" not in r.text
    assert "Anonyme" in r.text


def test_direct_navigation_without_hx_request_header_still_gets_full_shell(monkeypatch):
    """Un accès direct (F5, lien copié-collé) n'a pas cet en-tête —
    doit toujours recevoir la page complète, jamais juste le fragment."""
    app = make_app(view=lambda ctx: {}, monkeypatch=monkeypatch, user=None)
    r = TestClient(app).get("/")
    assert "<html>" in r.text


def test_use_shell_false_skips_the_wrapper(monkeypatch):
    app = make_app(view=lambda ctx: {}, monkeypatch=monkeypatch, user=None, use_shell=False)
    r = TestClient(app).get("/")
    assert "<html>" not in r.text
    assert "Anonyme" in r.text


# ---------------------------------------------------------------------
# Widget de compte en bas du sidebar (xweb/components/shell.xml, le vrai —
# pas TEST_SHELL) — contrat AuthPayload vérifié contre le vrai xcore
# (xcore/kernel/api/auth.py : seul `sub` est garanti, `user` est un dict
# optionnel de forme libre).
# ---------------------------------------------------------------------


def make_real_shell_app(*, view, monkeypatch, user=None, **mount_kwargs):
    async def fake_resolve(request):
        return user

    monkeypatch.setattr("xweb.context.resolve_user_or_anonymous", fake_resolve)

    registry = QwebRegistry()
    registry.register_source(TEMPLATE)
    registry.register_dir(COMPONENTS_DIR)  # le vrai xweb.shell, pas le fixture minimal

    app = FastAPI()
    router = APIRouter()
    mount_xweb_page(
        router, FakePluginCtx(), registry,
        path="/", template="test.page", view=view, **mount_kwargs,
    )
    app.include_router(router)
    return app


def test_anonymous_sees_login_link_not_account_widget(monkeypatch):
    app = make_real_shell_app(view=lambda ctx: {}, monkeypatch=monkeypatch, user=None)
    r = TestClient(app).get("/")
    assert "Se connecter" in r.text
    # défaut du SDK : le pont HTML plugins/account (docs/auth.md), avec next= vers la page courante
    assert 'href="/app/account/login?next=/"' in r.text
    assert "avatar" not in r.text
    # Un seul CTA "Se connecter" (topbar) — le doublon en bas de sidebar
    # (repéré sur une capture d'écran réelle) a été retiré, pas juste caché.
    assert r.text.count("Se connecter") == 1


def test_authenticated_sees_account_widget_using_nested_user_dict(monkeypatch):
    """AuthPayload.user (optionnel, forme libre côté backend) — priorité
    à un nom lisible plutôt qu'à `sub` quand il est fourni."""
    user = {"sub": "u_123", "roles": [], "user": {"name": "Ada Lovelace", "email": "ada@example.com"}}
    app = make_real_shell_app(view=lambda ctx: {}, monkeypatch=monkeypatch, user=user)
    r = TestClient(app).get("/")
    assert "Ada Lovelace" in r.text
    assert 'href="/app/account/"' in r.text
    assert ">A<" in r.text  # initiale dans l'avatar-placeholder
    assert "Se connecter" not in r.text


def test_authenticated_falls_back_to_sub_without_nested_user_dict(monkeypatch):
    """Seul `sub` est garanti par AuthPayload (xcore/kernel/api/auth.py)
    — le widget ne doit jamais planter si `user` (le dict optionnel)
    est absent, juste utiliser `sub` tel quel."""
    user = {"sub": "u_456", "roles": []}
    app = make_real_shell_app(view=lambda ctx: {}, monkeypatch=monkeypatch, user=user)
    r = TestClient(app).get("/")
    assert "u_456" in r.text


def test_account_and_login_paths_are_configurable(monkeypatch):
    user = {"sub": "u_1", "roles": [], "user": {"name": "Bob"}}
    app = make_real_shell_app(
        view=lambda ctx: {}, monkeypatch=monkeypatch, user=user,
        account_path="/app/auth/profile", login_path="/app/auth/login",
    )
    r = TestClient(app).get("/")
    assert 'href="/app/auth/profile"' in r.text


# ---------------------------------------------------------------------
# tenant_id — posé par le vrai xcore.kernel.tenancy.middleware.TenantMiddleware
# sur request.state (docs/integration-xcore.md), jamais fabriqué par xweb —
# _base_render_context() ne fait que le relayer dans ctx["tenant_id"].
# ---------------------------------------------------------------------

TENANT_TEMPLATE = """<template t-name="test.tenant_page">
    <t t-if="tenant_id"><p t-esc="'tenant=' + tenant_id"/></t>
    <t t-else="1"><p>sans-tenant</p></t>
</template>"""


def make_tenant_app(*, monkeypatch, user=None, tenant_id_to_set=None):
    """tenant_id_to_set=None simule l'absence du vrai TenantMiddleware
    (request.state.tenant_id jamais posé) — le cas d'un test isolé, pas la
    réalité de l'app (où ce middleware tourne sur CHAQUE requête, câblé au
    niveau module dans main.py). Un middleware factice ici plutôt qu'une
    dépendance sur le vrai xcore.kernel.tenancy.middleware — même stratégie
    que resolve_user_or_anonymous monkeypatché ailleurs dans ce fichier."""

    async def fake_resolve(request):
        return user

    monkeypatch.setattr("xweb.context.resolve_user_or_anonymous", fake_resolve)

    registry = QwebRegistry()
    registry.register_source(TENANT_TEMPLATE)
    registry.register_source(TEST_SHELL)

    app = FastAPI()

    if tenant_id_to_set is not None:
        @app.middleware("http")
        async def set_tenant(request, call_next):
            request.state.tenant_id = tenant_id_to_set
            return await call_next(request)

    router = APIRouter()
    mount_xweb_page(
        router, FakePluginCtx(), registry,
        path="/", template="test.tenant_page", view=lambda ctx: {}, login_path="/login",
    )
    app.include_router(router)
    return app


def test_tenant_id_is_none_when_no_tenant_middleware_ran(monkeypatch):
    app = make_tenant_app(monkeypatch=monkeypatch)
    r = TestClient(app).get("/")
    assert "sans-tenant" in r.text


def test_tenant_id_reaches_the_template_when_tenant_middleware_set_it(monkeypatch):
    app = make_tenant_app(monkeypatch=monkeypatch, tenant_id_to_set="acme")
    r = TestClient(app).get("/")
    assert "tenant=acme" in r.text
