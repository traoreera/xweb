"""La landing page ("/", templates/landing.xml) — montée depuis main.py
(aucun plugin ne peut servir "/" lui-même, voir integration.yaml). Reproduit
le même montage que main.py (QwebRegistry + mount_xweb_page,
layout="xweb.marketing_layout") pour rester testable sans booter xcore.
"""

from pathlib import Path

from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from xweb.engine.registry import QwebRegistry
from xweb.mount import mount_xweb_page

ROOT = Path(__file__).parent.parent


class FakePluginCtx:
    name = "site"
    tenant_id = None
    caller = None

    def get_service(self, name):
        return None


def make_app(monkeypatch, *, user=None):
    async def fake_resolve(request):
        return user

    monkeypatch.setattr("xweb.context.resolve_user_or_anonymous", fake_resolve)
    registry = QwebRegistry()
    registry.register_dir(ROOT / "xweb" / "components")
    registry.register_dir(ROOT / "templates", source_plugin="site")
    app = FastAPI()
    router = APIRouter()
    mount_xweb_page(
        router, FakePluginCtx(), registry, path="/", template="site.landing", view=lambda ctx: {},
        app_name="xweb", page_title="xweb", layout="xweb.marketing_layout", use_shell=False,
    )
    app.include_router(router)
    return app


def test_anonymous_sees_login_cta_not_account(monkeypatch):
    html = TestClient(make_app(monkeypatch)).get("/").text
    assert "<html>" in html and 'href="/xweb-static/app.css"' in html
    assert 'id="xweb-sidebar"' not in html  # marketing_layout, pas le chrome interne de l'appli
    assert 'href="/app/account/login?next=/"' in html
    assert "Aller à la démo" not in html
    assert "Mon compte" not in html


def test_authenticated_sees_dashboard_cta_and_name(monkeypatch):
    user = {"sub": "u1", "roles": [], "user": {"name": "Ada Lovelace", "email": "ada@example.com"}}
    html = TestClient(make_app(monkeypatch, user=user)).get("/").text
    assert "Aller à la démo" in html and "Mon compte" in html
    assert "Ada Lovelace" in html
    assert 'href="/app/account/login' not in html


def test_boosted_navigation_to_the_landing_page_forces_a_real_navigation(monkeypatch):
    """marketing_layout != DEFAULT_LAYOUT (xweb.shell) — un clic hx-boost
    depuis l'intérieur de l'appli vers "/" ne doit jamais atterrir comme
    fragment dans #xweb-content, toujours une vraie navigation (même
    mécanisme que le login, xweb/mount.py)."""
    r = TestClient(make_app(monkeypatch)).get("/?x=1", headers={"HX-Request": "true"})
    assert r.status_code == 200
    assert r.headers["HX-Redirect"] == "/?x=1"
    assert r.text == ""


def test_cta_link_to_the_demo_plugin_is_present(monkeypatch):
    html = TestClient(make_app(monkeypatch)).get("/").text
    assert html.count('href="/app/demo/"') >= 2  # nav du bandeau + au moins un CTA
