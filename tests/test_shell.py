"""Le shell reconstruit (docs/shell.md) — les quatre régions + palette,
rendues par le VRAI xweb/components/shell.xml à travers mount_xweb_page, pas
un fixture minimal. Chaque test trace une promesse de shell.md.
"""

import re
from pathlib import Path

from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from xweb.contrib import Contribution, commands, nav, ribbon, status_bar
from xweb.engine.registry import QwebRegistry
from xweb.mount import MINIMAL_LAYOUT, mount_xweb_page, redirect_response, login_url

COMPONENTS_DIR = Path(__file__).parent.parent / "xweb" / "components"

PAGE = """<template t-name="test.page"><p id="hello">Bonjour <t t-esc="who"/></p></template>"""


class FakeExt:
    csrf_token = "csrf-secret-xyz"


class FakePluginCtx:
    name = "demo"
    tenant_id = None
    caller = None

    def get_service(self, name):
        return FakeExt() if name == "ext.xweb" else None


def make_app(monkeypatch, *, user=None, view=None, **mount_kwargs):
    async def fake_resolve(request):
        return user

    monkeypatch.setattr("xweb.context.resolve_user_or_anonymous", fake_resolve)
    registry = QwebRegistry()
    registry.register_source(PAGE)
    registry.register_dir(COMPONENTS_DIR)
    app = FastAPI()
    router = APIRouter()
    mount_xweb_page(
        router, FakePluginCtx(), registry, path="/", template="test.page",
        view=view or (lambda ctx: {"who": "monde"}), app_name="Ma App", **mount_kwargs,
    )
    app.include_router(router)
    return app


def _cleanup():
    for reg in (nav, ribbon, commands, status_bar):
        reg.unregister_plugin("shelltest")


# ---------------------------------------------------------------------
# Les quatre régions + la palette reçoivent bien leurs registres
# ---------------------------------------------------------------------


def test_ribbon_commands_and_status_bar_reach_the_shell(monkeypatch):
    ribbon.register(Contribution(id="st.ribbon", plugin="shelltest", label="Rubans", icon="home", path="/r", tooltip="Le ruban"))
    commands.register(Contribution(id="st.cmd", plugin="shelltest", label="Faire un truc", action_url="/do", hotkey="Ctrl+T"))
    status_bar.register(Contribution(id="st.left", plugin="shelltest", label="prêt", icon="check"))
    status_bar.register(Contribution(id="st.right", plugin="shelltest", label="v0.1", side="right", path="/about"))
    try:
        r = TestClient(make_app(monkeypatch)).get("/")
        html = r.text
        assert 'id="xweb-ribbon"' not in html and 'href="/r"' not in html and 'title="Le ruban"' not in html
        assert 'id="xweb-topbar"' in html and 'title="Ma App"' in html
        assert 'id="command-palette"' in html and "Faire un truc" in html and 'href="/do"' in html and "Ctrl+T" in html
        assert 'id="xweb-status"' in html and "prêt" in html
        assert 'href="/about"' in html and "v0.1" in html  # côté droit, rendu en lien
        assert 'id="xweb-content"' in html and 'id="hello"' in html
    finally:
        _cleanup()


def test_sidebar_toggle_and_labels_are_present_for_the_collapsed_desktop_mode(monkeypatch):
    """Structure attendue par assets/app.css ([data-sidebar="collapsed"]
    .sidebar-label { display: none }) — docs/shell.md. La mécanique
    _hyperscript elle-même (bascule + persistance localStorage) est
    vérifiée pour de vrai dans scripts/verify-hyperscript.mjs."""
    html = TestClient(make_app(monkeypatch)).get("/").text
    assert "xweb.sidebar_toggle" not in html  # jamais le nom du template, juste son rendu
    assert 'aria-label="Replier/déplier le panneau de navigation"' in html
    assert 'class="sidebar-label"' in html  # titre "Ma App" en tête de sidebar


def test_nav_tree_renders_nested_children_and_marks_current_path(monkeypatch):
    nav.register(Contribution(id="st.parent", plugin="shelltest", label="Section", icon="users"))
    nav.register(Contribution(id="st.child", plugin="shelltest", label="Enfant", parent_id="st.parent", path="/"))
    nav.register(Contribution(id="st.other", plugin="shelltest", label="Autre", path="/autre"))
    try:
        html = TestClient(make_app(monkeypatch)).get("/").text
        assert "<details" in html and "<summary" in html and "Section" in html
        assert re.search(r'<a href="/"[^>]*class="[^"]*menu-active[^"]*"', html), "la page courante doit être menu-active"
        assert re.search(r'<a href="/autre"[^>]*class="[^"]*"', html)
        assert not re.search(r'<a href="/autre"[^>]*class="[^"]*menu-active', html)
    finally:
        _cleanup()


def test_nav_active_state_does_not_leak_to_sibling_pages_sharing_a_slash_prefix(monkeypatch):
    """Repéré sur une capture d'écran réelle du shell (/app/demo/kanban) :
    "Démo" (path="/app/demo/") et "Kanban" (path="/app/demo/kanban")
    s'allumaient TOUS LES DEUX en même temps sur la page Kanban — un
    startswith() faisait matcher n'importe quelle page-fille avec toute
    page sœur dont le path se termine par "/", jamais un vrai ancêtre.
    Corrigé en égalité stricte (xweb/components/shell.xml::xweb.nav_items)."""
    nav.register(Contribution(id="st.index", plugin="shelltest", label="Démo", path="/plugins/shelltest/"))
    nav.register(Contribution(id="st.kanban", plugin="shelltest", label="Kanban", path="/plugins/shelltest/kanban"))

    async def fake_resolve(request):
        return None

    monkeypatch.setattr("xweb.context.resolve_user_or_anonymous", fake_resolve)
    registry = QwebRegistry()
    registry.register_source(PAGE)
    registry.register_dir(COMPONENTS_DIR)
    app = FastAPI()
    router = APIRouter()
    mount_xweb_page(router, FakePluginCtx(), registry, path="/plugins/shelltest/", template="test.page", view=lambda ctx: {"who": "x"}, app_name="Ma App")
    mount_xweb_page(router, FakePluginCtx(), registry, path="/plugins/shelltest/kanban", template="test.page", view=lambda ctx: {"who": "x"}, app_name="Ma App")
    app.include_router(router)
    try:
        html = TestClient(app).get("/plugins/shelltest/kanban").text
        assert re.search(r'<a href="/plugins/shelltest/kanban"[^>]*class="[^"]*menu-active[^"]*"', html), "Kanban doit être actif"
        assert not re.search(r'<a href="/plugins/shelltest/"[^>]*class="[^"]*menu-active', html), "Démo ne doit PAS s'allumer aussi sur la page Kanban"
    finally:
        _cleanup()


def test_nav_item_badge_renders_next_to_the_label(monkeypatch):
    """Contribution.badge (xweb/contrib.py) — même idée que la prop `badge`
    de xweb.menu, mais STATIQUE (posé une fois à nav.register(), pas un
    compteur par utilisateur — voir la docstring du champ)."""
    nav.register(Contribution(id="st.badged", plugin="shelltest", label="Boîte de réception", path="/inbox", badge="3"))
    nav.register(Contribution(id="st.plain", plugin="shelltest", label="Sans badge", path="/plain"))
    try:
        html = TestClient(make_app(monkeypatch)).get("/").text
        assert re.search(r'<a href="/inbox"[^>]*>.*?Boîte de réception.*?<span class="[^"]*badge-neutral[^"]*">3</span>', html, re.S)
        # aucun <span class="badge...> parasite sur l'item qui n'en a pas
        # ("badge" seul ne suffit pas comme négation : le label de test
        # lui-même contient ce mot — chercher la vraie classe CSS)
        plain_link = re.search(r'<a href="/plain"[^>]*>(.*?)</a>', html, re.S).group(1)
        assert 'class="badge' not in plain_link
    finally:
        _cleanup()


def test_empty_registries_render_placeholders_not_errors(monkeypatch):
    html = TestClient(make_app(monkeypatch)).get("/").text
    assert "Aucun plugin n&#39;a encore contribué de navigation." in html  # texte littéral, échappé par le compilateur
    assert "Aucune commande enregistrée." in html


# ---------------------------------------------------------------------
# Compte, CSRF, déconnexion
# ---------------------------------------------------------------------


def test_logout_form_carries_csrf_token_and_leaves_the_boost(monkeypatch):
    user = {"sub": "u1", "roles": [], "user": {"email": "ada@example.com", "name": "Ada"}}
    html = TestClient(make_app(monkeypatch, user=user)).get("/").text
    assert 'action="/app/account/logout"' in html
    assert 'name="csrf_token" value="csrf-secret-xyz"' in html
    assert re.search(r'<form method="post" action="/app/account/logout" hx-boost="false"', html)
    assert 'href="/app/account/security"' in html and 'href="/app/account/sessions"' in html


def test_anonymous_login_link_keeps_next_with_query_and_skips_boost(monkeypatch):
    html = TestClient(make_app(monkeypatch)).get("/?tab=2").text
    assert 'href="/app/account/login?next=/?tab=2" hx-boost="false"' in html


def test_page_title_from_view_wins_and_is_suffixed_with_app_name(monkeypatch):
    app = make_app(monkeypatch, view=lambda ctx: {"who": "x", "page_title": "Contacts"})
    html = TestClient(app).get("/").text
    assert "<title>Contacts · Ma App</title>" in html
    assert 'id="xweb-page-title"' in html and "Contacts · Ma App" in html


# ---------------------------------------------------------------------
# htmx — fragments, titres, redirections
# ---------------------------------------------------------------------


def test_hx_fragment_starts_with_a_title_for_htmx_to_pick_up(monkeypatch):
    app = make_app(monkeypatch, view=lambda ctx: {"who": "x", "page_title": "Contacts"})
    r = TestClient(app).get("/", headers={"HX-Request": "true"})
    assert r.text.startswith("<title>Contacts · Ma App</title>")
    assert "<html>" not in r.text and 'id="hello"' in r.text


def test_minimal_layout_answers_hx_redirect_instead_of_a_fragment(monkeypatch):
    """Une page hors shell (login) atteinte en boost ne doit jamais finir
    en fragment dans #xweb-content — HX-Redirect force la vraie navigation."""
    app = make_app(monkeypatch, layout=MINIMAL_LAYOUT)
    r = TestClient(app).get("/?next=/x", headers={"HX-Request": "true"})
    assert r.status_code == 200
    assert r.headers["HX-Redirect"] == "/?next=/x"
    assert r.text == ""


def test_minimal_layout_has_head_and_no_nav(monkeypatch):
    html = TestClient(make_app(monkeypatch, layout=MINIMAL_LAYOUT)).get("/").text
    assert "<html>" in html and 'href="/xweb-static/app.css"' in html
    assert 'id="xweb-sidebar"' not in html and 'id="command-palette"' not in html
    assert 'id="hello"' in html


def test_anonymous_on_protected_page_gets_hx_redirect_when_boosted(monkeypatch):
    def view(ctx):
        ctx.require_user()
        return {}

    app = make_app(monkeypatch, view=view)
    r = TestClient(app).get("/", headers={"HX-Request": "true"})
    assert r.status_code == 200
    assert r.headers["HX-Redirect"] == "/app/account/login?next=/"
    r2 = TestClient(app, follow_redirects=False).get("/")
    assert r2.status_code == 303 and r2.headers["location"] == "/app/account/login?next=/"


def test_403_is_rendered_inside_the_shell_with_the_error_page_component(monkeypatch):
    def view(ctx):
        ctx.require_role("crm.viewer")
        return {}

    user = {"sub": "u1", "roles": []}
    r = TestClient(make_app(monkeypatch, user=user, view=view)).get("/")
    assert r.status_code == 403
    assert "<html>" in r.text and 'id="xweb-sidebar"' in r.text
    assert "crm.viewer" in r.text and "Accès refusé" in r.text


def test_redirect_response_helper_and_login_url():
    from starlette.requests import Request

    def req(headers):
        return Request({"type": "http", "method": "GET", "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()], "path": "/", "query_string": b""})

    assert redirect_response(req({}), "/x").status_code == 303
    hx = redirect_response(req({"HX-Request": "true"}), "/x")
    assert hx.status_code == 200 and hx.headers["HX-Redirect"] == "/x"
    assert login_url("/login", "/a b?x=1&y=2") == "/login?next=/a%20b?x=1&y=2"
    assert login_url("/login", None) == "/login"


def test_theme_script_is_identical_in_both_layouts():
    """Même script anti-flash → même hash CSP (xweb/security.py) pour le
    shell et le layout minimal."""
    r = QwebRegistry()
    r.register_dir(COMPONENTS_DIR)
    ctx = {"content": "", "nav_tree": [], "ribbon": [], "commands": [], "status_left": [], "status_right": [],
           "app_name": "x", "page_title": "x", "user": None, "account": {}, "csrf_token": "", "login_url": "/l",
           "account_path": "/a", "logout_path": "/o", "current_path": "/"}
    a = re.search(r"<script>(.*?)</script>", r.render("xweb.shell", ctx), re.DOTALL).group(1)
    b = re.search(r"<script>(.*?)</script>", r.render("xweb.shell_minimal", ctx), re.DOTALL).group(1)
    assert a == b
