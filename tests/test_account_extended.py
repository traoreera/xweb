"""plugins/account — surfaces "étendues" devant l'API JSON de plugins/auth :
notifications, console admin plateforme, journal d'audit, et tenant étendu
(création / settings / suppression). Même principe que tests/
test_account_organization.py : fausse API plugins/auth branchée via
httpx.ASGITransport, de vraies requêtes HTTP internes.

Permissions (plugins/auth/src/services/seed.py + _scope.py, docs/auth.md) :
- notifications      : tout utilisateur connecté (get_current_user)
- admin plateforme   : user:list + admin:* portés par le rôle "admin" seedé
- audit              : audit:read (propriétaire de tenant ou admin)
- création tenant    : tout connecté (limite 3 membreships)
- settings (PUT)     : owner du tenant (scope tenant)
- suppression tenant : tenants:delete (admin plateforme uniquement)
"""

from __future__ import annotations

import importlib
import re
import sys
import types
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response
from fastapi.testclient import TestClient

from xweb.engine.registry import QwebRegistry

ROOT = Path(__file__).parent.parent
SRC = ROOT / "plugins" / "account" / "src"

OWNER_TOKEN = "tok-owner"
MEMBER_TOKEN = "tok-member"
ADMIN_TOKEN = "tok-admin"
TENANT = "t1"
USER_A = "u-a"
USER_B = "u-b"


def load_account_pkg():
    if "account_ext_src" not in sys.modules:
        pkg = types.ModuleType("account_ext_src")
        pkg.__path__ = [str(SRC)]
        sys.modules["account_ext_src"] = pkg
    return importlib.import_module("account_ext_src.routes"), importlib.import_module("account_ext_src.api")


def make_fake_auth(state: dict) -> FastAPI:
    app = FastAPI()
    P = "/app/auth"

    def bearer(request: Request) -> str:
        auth = request.headers.get("authorization", "")
        token = auth[7:] if auth.startswith("Bearer ") else ""
        if token not in (OWNER_TOKEN, MEMBER_TOKEN, ADMIN_TOKEN):
            raise HTTPException(401, "Token invalide ou expiré")
        return token

    def require_admin(request: Request) -> None:
        if bearer(request) != ADMIN_TOKEN:
            raise HTTPException(403, "Réservé à l'administration plateforme.")

    def require_owner(request: Request) -> None:
        if bearer(request) != OWNER_TOKEN:
            raise HTTPException(403, "Réservé au propriétaire du tenant.")

    # ── notifications ──────────────────────────────────────────────────────

    @app.get(f"{P}/notifications")
    async def list_notifications(request: Request):
        bearer(request)
        return {"items": [dict(n) for n in state["notifications"]]}

    @app.patch(f"{P}/notifications/{{notif_id}}/read")
    async def mark_read(notif_id: str, request: Request):
        bearer(request)
        for n in state["notifications"]:
            if n["id"] == notif_id:
                n["is_read"] = True
        return {"success": True}

    @app.patch(f"{P}/notifications/read-all")
    async def mark_all_read(request: Request):
        bearer(request)
        for n in state["notifications"]:
            n["is_read"] = True
        return {"success": True}

    @app.delete(f"{P}/notifications/{{notif_id}}", status_code=204)
    async def delete_notif(notif_id: str, request: Request):
        bearer(request)
        state["notifications"] = [n for n in state["notifications"] if n["id"] != notif_id]
        return Response(status_code=204)

    # ── admin plateforme ────────────────────────────────────────────────────

    @app.get(f"{P}/admin/users")
    async def list_users(request: Request):
        require_admin(request)
        return {"items": [dict(u) for u in state["users"].values()]}

    @app.patch(f"{P}/admin/users/{{user_id}}")
    async def set_user_active(user_id: str, request: Request):
        require_admin(request)
        body = await request.json()
        state["users"][user_id]["is_active"] = body.get("is_active", True)
        return state["users"][user_id]

    @app.delete(f"{P}/admin/users/{{user_id}}", status_code=204)
    async def delete_user(user_id: str, request: Request):
        require_admin(request)
        if user_id not in state["users"]:
            raise HTTPException(404, "Utilisateur introuvable")
        del state["users"][user_id]
        return Response(status_code=204)

    # ── audit ───────────────────────────────────────────────────────────────

    @app.get(f"{P}/audit/tenants/{{tenant_id}}")
    async def audit_tenant(tenant_id: str, request: Request):
        require_owner(request)
        return {"items": list(state["audit"])}

    # ── tenants : création / settings / suppression ─────────────────────────

    @app.get(f"{P}/tenants/")
    async def list_tenants(request: Request):
        bearer(request)
        return list(state["tenants"])

    @app.post(f"{P}/tenants/", status_code=201)
    async def create_tenant(request: Request):
        bearer(request)
        body = await request.json()
        t = {"id": "t9", "name": body["name"], "slug": body["slug"], "created_at": "2026-09-02T00:00:00+00:00", "is_owner": True, "license_state": "trial"}
        state["tenants"].append(t)
        return t

    @app.get(f"{P}/tenants/{{tenant_id}}/settings")
    async def get_settings(tenant_id: str, request: Request):
        bearer(request)
        return {"tenant_id": tenant_id, "settings": state["settings"]}

    @app.put(f"{P}/tenants/{{tenant_id}}/settings")
    async def put_settings(tenant_id: str, request: Request):
        require_owner(request)
        body = (await request.json()).get("settings") or {}
        state["settings"].update(body)
        return {"tenant_id": tenant_id, "settings": state["settings"]}

    @app.delete(f"{P}/tenants/{{tenant_id}}", status_code=204)
    async def delete_tenant(tenant_id: str, request: Request):
        require_admin(request)
        state["tenants"] = [t for t in state["tenants"] if t["id"] != tenant_id]
        return Response(status_code=204)

    # ── google (agenda/email — plugins/auth/src/routes/google.py) ───────────

    @app.get(f"{P}/google/status")
    async def google_status(request: Request):
        bearer(request)
        linked = state["google_linked"]
        return {"linked": linked, "email": "owner@example.com" if linked else None}

    @app.get(f"{P}/google/calendar/events")
    async def google_events(request: Request):
        bearer(request)
        if not state["google_linked"]:
            raise HTTPException(404, "google_not_linked")
        return {"events": list(state["google_events"])}

    @app.get(f"{P}/google/gmail/messages")
    async def google_messages(request: Request):
        bearer(request)
        if not state["google_linked"]:
            raise HTTPException(404, "google_not_linked")
        return {"messages": list(state["google_messages"])}

    @app.get(f"{P}/oauth/{{provider}}/authorize")
    async def oauth_authorize(provider: str, request: Request):
        # Mode liaison côté vrai plugins/auth (routes/oauth.py::authorize) :
        # DEUX conditions, pas une seule — link_user_id présent en query
        # string (sa valeur est ignorée par le vrai serveur, seule sa
        # présence compte) ET un Bearer valide. Un Bearer seul, sans le
        # paramètre, retombe silencieusement en connexion normale côté vrai
        # serveur (pas une erreur) — ce fake choisit de lever une erreur au
        # lieu de reproduire ce silence, pour attraper la régression
        # directement ici plutôt que plus loin dans un callback qui aurait
        # l'air de réussir avec le mauvais type de jeton.
        bearer(request)
        if not request.query_params.get("link_user_id"):
            raise HTTPException(400, "Provider Error")
        return {"auth_url": f"https://accounts.google.com/o/oauth2/v2/auth?provider={provider}", "provider": provider}

    return app


class FakePluginCtx:
    name = "account"
    tenant_id = None
    caller = None
    config = {}

    def get_service(self, name):
        return None


@pytest.fixture
def state():
    return {
        "notifications": [
            {"id": "n1", "title": "Bienvenue", "message": "Votre compte est actif.", "type": "SYSTEM", "link": None, "is_read": False, "created_at": "2026-09-01T09:00:00+00:00"},
            {"id": "n2", "title": "Rapport prêt", "message": "Le rapport mensuel est disponible.", "type": "INFO", "link": None, "is_read": True, "created_at": "2026-09-01T10:00:00+00:00"},
        ],
        "users": {
            "u-self": {"id": "u-self", "email": "admin@example.com", "is_active": True, "mfa_enabled": True, "created_at": "2026-01-01T00:00:00+00:00"},
            "u-a": {"id": "u-a", "email": "alpha@example.com", "is_active": True, "mfa_enabled": False, "created_at": "2026-02-01T00:00:00+00:00"},
            "u-b": {"id": "u-b", "email": "beta@example.com", "is_active": False, "mfa_enabled": False, "created_at": "2026-03-01T00:00:00+00:00"},
        },
        "tenants": [
            {"id": TENANT, "name": "Acme", "slug": "acme", "created_at": "2026-09-01T00:00:00+00:00", "is_owner": True, "license_state": "trial"},
        ],
        "settings": {"locale": "fr", "timezone": "Europe/Paris"},
        "google_linked": False,
        "google_events": [
            {"id": "e1", "summary": "Réunion équipe", "start": "2026-09-05T10:00:00+02:00", "all_day": False, "location": "Salle A", "html_link": "https://calendar.google.com/e1"},
        ],
        "google_messages": [
            {"id": "m1", "subject": "Bienvenue", "from": "welcome@example.com", "date": "Tue, 01 Sep 2026 09:00:00 +0000", "snippet": "Votre compte est prêt.", "unread": True},
        ],
        "audit": [
            {"id": "e1", "tenant_id": TENANT, "action": "user.login", "resource": "session", "resource_id": "s1", "user_id": "u-a", "ip_address": "10.0.0.1", "meta": "connexion ok", "created_at": "2026-09-01T11:00:00+00:00"},
        ],
    }


@pytest.fixture
def client(monkeypatch, state):
    routes, api = load_account_pkg()

    async def fake_resolve(request):
        token = request.cookies.get("access_token")
        if token == OWNER_TOKEN:
            return {"sub": "u-owner", "roles": ["owner"], "permissions": ["tenants:read", "audit:read", "tenants:write"], "user": {"email": "owner@example.com", "tenant_id": TENANT}}
        if token == MEMBER_TOKEN:
            return {"sub": "u-mem", "roles": [], "permissions": [], "user": {"email": "member@example.com", "tenant_id": TENANT}}
        if token == ADMIN_TOKEN:
            return {"sub": "u-self", "roles": ["admin"], "permissions": ["user:list", "admin:*", "tenants:delete", "audit:read", "tenants:read"], "user": {"email": "admin@example.com", "tenant_id": TENANT}}
        return None

    monkeypatch.setattr("xweb.context.resolve_user_or_anonymous", fake_resolve)
    fake_auth = make_fake_auth(state)
    registry = QwebRegistry()
    registry.register_dir(ROOT / "xweb" / "components")
    registry.register_dir(ROOT / "plugins" / "account" / "templates", source_plugin="account")

    def api_factory(request):
        return api.AuthApi("http://auth.internal", transport=httpx.ASGITransport(app=fake_auth))

    app = FastAPI()
    app.include_router(
        routes.build_router(FakePluginCtx(), registry, config={"app_name": "TestApp", "home_path": "/home"}, api_factory=api_factory),
        prefix="/app/account",
    )
    c = TestClient(app, follow_redirects=False)
    return c


def as_owner(client):
    client.cookies.set("access_token", OWNER_TOKEN)
    return client


def as_member(client):
    client.cookies.set("access_token", MEMBER_TOKEN)
    return client


def as_admin(client):
    client.cookies.set("access_token", ADMIN_TOKEN)
    return client


# ── notifications ────────────────────────────────────────────────────────────


def test_notifications_list(client, state):
    as_owner(client)
    r = client.get("/app/account/notifications")
    assert r.status_code == 200
    assert "Bienvenue" in r.text
    assert "Rapport prêt" in r.text
    assert "1" in r.text  # compteur non lus


def test_notification_mark_read(client, state):
    as_owner(client)
    r = client.post("/app/account/notifications/n1/read")
    assert r.status_code == 303 and "m=notification_read" in r.headers["location"]
    assert all(n["is_read"] for n in state["notifications"])


def test_notifications_read_all(client, state):
    as_owner(client)
    r = client.post("/app/account/notifications/read-all")
    assert r.status_code == 303 and "m=notifications_read_all" in r.headers["location"]
    assert all(n["is_read"] for n in state["notifications"])


def test_notification_delete(client, state):
    as_owner(client)
    r = client.post("/app/account/notifications/n1/delete")
    assert r.status_code == 303 and "m=notification_deleted" in r.headers["location"]
    ids = [n["id"] for n in state["notifications"]]
    assert "n1" not in ids


def test_notifications_requires_login(client):
    r = client.get("/app/account/notifications")
    assert r.status_code in (302, 303)


def test_notifications_page_wires_the_xpulse_sse_stream(client, state):
    # plugins/XPulses expose <préfixe plugin>/xpulse/stream, monté sur le même
    # process xcore — pas besoin d'un fake serveur ici, on vérifie juste que
    # la page câble bien un EventSource dessus (l'URL vient de
    # data-xpulse-stream-url, jamais un "/plugins/xpulse" codé en dur dans
    # le template — voir routes.py::notifications_ctx et xweb.paths.plugin_prefix()),
    # avec un id de cible stable pour l'insertion en direct
    # (xpulse-status/notif-list/notif-empty).
    as_owner(client)
    r = client.get("/app/account/notifications")
    assert r.status_code == 200
    assert 'data-xpulse-stream-url="/app/xpulse/stream?channels=notification"' in r.text
    assert 'document.currentScript.getAttribute("data-xpulse-stream-url")' in r.text
    assert 'id="xpulse-status"' in r.text


# ── badge de nav dynamique (non lues en direct, xweb.shell patché) ──────────


def test_shell_carries_the_live_notifications_badge_script_for_a_logged_in_user(client, state):
    # Cette suite construit son app directement depuis routes.build_router()
    # (jamais Plugin.on_load()), donc le NavRegistry — singleton process-
    # global — n'a jamais reçu la vraie contribution "account.notifications"
    # ici (elle vit dans plugins/account/src/main.py). On l'enregistre à la
    # main, exactement comme main.py le ferait, pour qu'un <a> réel porte
    # data-nav-id : sans ça, la seule occurrence de cette chaîne dans la
    # page serait celle DANS le script lui-même (le sélecteur CSS qu'il
    # construit), une assertion qui passerait toujours, même si le vrai
    # lien de nav ne le portait jamais — trouvé en écrivant ce test.
    from xweb.contrib import Contribution, nav

    nav.register(Contribution(id="account.notifications", plugin="account", label="Notifications", path="/app/account/notifications", icon="bell"))
    try:
        as_owner(client)
        r = client.get("/app/account/")
        assert r.status_code == 200
        assert re.search(r'<a href="/app/account/notifications"[^>]*data-nav-id="account\.notifications"', r.text)
        assert 'class="nav-live-badge badge badge-sm badge-primary" hidden="hidden"' in r.text
        assert 'data-badge-prefix="/app"' in r.text
        # Concaténation faite côté navigateur (prefix + "..."), pas de
        # "/app/..." précalculé côté serveur dans le script lui-même.
        assert '"/xpulse/stream?channels=notification"' in r.text
        assert '"/account/notifications/unread-count"' in r.text
    finally:
        nav.unregister_plugin("account")


def test_unread_count_endpoint_counts_only_unread(client, state):
    as_owner(client)
    r = client.get("/app/account/notifications/unread-count")
    assert r.status_code == 200
    assert r.json() == {"count": 1}  # state["notifications"] : 1 non lue, 1 lue (fixture)


def test_unread_count_endpoint_requires_login(client):
    r = client.get("/app/account/notifications/unread-count")
    assert r.status_code == 401
    assert r.json() == {"count": 0}


def test_unread_count_endpoint_degrades_to_zero_on_api_error(client, state, monkeypatch):
    as_owner(client)

    async def _boom(self, token):
        from account_ext_src.api import AuthApiError
        raise AuthApiError(503, "down")

    monkeypatch.setattr("account_ext_src.api.AuthApi.list_notifications", _boom)
    r = client.get("/app/account/notifications/unread-count")
    assert r.status_code == 200
    assert r.json() == {"count": 0}


def test_notifications_list_empty_does_not_crash(client, state):
    # Régression : notifications.xml testait `notifications[1:] or notifications[0]`
    # pour décider d'afficher "Tout marquer comme lu" — avec une liste vide,
    # notifications[1:] vaut [] (faux) donc l'expression retombait sur
    # notifications[0], un IndexError sur liste vide (500 au lieu d'une page
    # "Aucune notification"). Un simple `t-if="notifications"` suffit : une
    # liste est déjà vraie/fausse selon son contenu, pas besoin d'indexer.
    state["notifications"] = []
    as_owner(client)
    r = client.get("/app/account/notifications")
    assert r.status_code == 200
    assert "Aucune notification" in r.text
    assert "Tout marquer comme lu" not in r.text


# ── admin plateforme ─────────────────────────────────────────────────────────


def test_admin_list_users(client, state):
    as_admin(client)
    r = client.get("/app/account/admin")
    assert r.status_code == 200
    assert "alpha@example.com" in r.text and "beta@example.com" in r.text


def test_admin_user_toggle_activate(client, state):
    as_admin(client)
    r = client.post("/app/account/admin/users/u-b/toggle", data={"is_active": "true"})
    assert r.status_code == 303 and "m=user_activated" in r.headers["location"]
    assert state["users"]["u-b"]["is_active"] is True


def test_admin_user_toggle_deactivate(client, state):
    as_admin(client)
    r = client.post("/app/account/admin/users/u-a/toggle", data={"is_active": "false"})
    assert r.status_code == 303 and "m=user_deactivated" in r.headers["location"]
    assert state["users"]["u-a"]["is_active"] is False


def test_admin_cannot_toggle_own_account(client, state):
    as_admin(client)
    r = client.post("/app/account/admin/users/u-self/toggle", data={"is_active": "false"})
    assert r.status_code == 400 and "Impossible de désactiver" in r.text
    assert state["users"]["u-self"]["is_active"] is True


def test_admin_delete_user(client, state):
    as_admin(client)
    r = client.post("/app/account/admin/users/u-a/delete")
    assert r.status_code == 303 and "m=user_deleted" in r.headers["location"]
    assert "u-a" not in state["users"]


def test_admin_forbidden_for_non_admin(client):
    as_owner(client)
    r = client.get("/app/account/admin")
    assert r.status_code == 403


# ── audit ────────────────────────────────────────────────────────────────────


def test_audit_lists_entries(client, state):
    as_owner(client)
    r = client.get("/app/account/audit")
    assert r.status_code == 200
    assert "user.login" in r.text
    assert "alpha@example.com" in r.text or "u-a" in r.text


def test_audit_forbidden_without_permission(client):
    as_member(client)
    r = client.get("/app/account/audit")
    assert r.status_code == 403


# ── audit : export PDF (docs/pdf.md, xweb/pdf.py) ───────────────────────────


def test_audit_export_pdf_returns_a_real_pdf(client, state):
    as_owner(client)
    r = client.get("/app/account/audit/export.pdf")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert "attachment" in r.headers["content-disposition"]
    assert r.content.startswith(b"%PDF-")


def test_audit_export_pdf_forbidden_without_permission(client):
    as_member(client)
    r = client.get("/app/account/audit/export.pdf")
    assert r.status_code == 403


def test_audit_export_pdf_redirects_anonymous_to_login(client):
    r = client.get("/app/account/audit/export.pdf")
    assert r.status_code in (303, 307)
    assert "/login" in r.headers["location"]


# ── organisation étendue : création / settings / suppression ────────────────


def test_org_create(client, state):
    as_owner(client)
    r = client.post("/app/account/organization/create", data={"name": "Nouvelle Boîte", "slug": "nouvelle-boite"})
    assert r.status_code == 303 and "m=tenant_created" in r.headers["location"]
    assert any(t["name"] == "Nouvelle Boîte" for t in state["tenants"])


def test_org_create_missing_name(client, state):
    as_owner(client)
    n = len(state["tenants"])
    r = client.post("/app/account/organization/create", data={"name": "  "})
    assert r.status_code == 400 and "requis" in r.text
    assert len(state["tenants"]) == n


def test_org_settings_save(client, state):
    as_owner(client)
    r = client.post("/app/account/organization/settings", data={"tenant_id": TENANT, "setting_locale": "en", "setting_timezone": "Europe/Berlin"})
    assert r.status_code == 303 and "m=settings_saved" in r.headers["location"]
    assert state["settings"]["locale"] == "en"
    assert state["settings"]["timezone"] == "Europe/Berlin"


def test_org_delete_tenant(client, state):
    as_admin(client)
    r = client.post(f"/app/account/organization/{TENANT}/delete")
    assert r.status_code == 303 and "m=tenant_deleted" in r.headers["location"]
    assert all(t["id"] != TENANT for t in state["tenants"])


def test_org_delete_forbidden_for_non_admin(client, state):
    as_owner(client)
    r = client.post(f"/app/account/organization/{TENANT}/delete")
    assert r.status_code == 403
    assert any(t["id"] == TENANT for t in state["tenants"])


# ── agenda / email (Google, plugins/auth/src/routes/google.py) ───────────────


def test_agenda_shows_connect_cta_when_google_not_linked(client, state):
    as_owner(client)
    r = client.get("/app/account/agenda")
    assert r.status_code == 200
    assert "Connecter Google" in r.text
    assert "Réunion équipe" not in r.text


def test_agenda_lists_events_when_google_linked(client, state):
    state["google_linked"] = True
    as_owner(client)
    r = client.get("/app/account/agenda")
    assert r.status_code == 200
    assert "Réunion équipe" in r.text
    assert "Connecter Google" not in r.text


def test_email_shows_connect_cta_when_google_not_linked(client, state):
    as_owner(client)
    r = client.get("/app/account/email")
    assert r.status_code == 200
    assert "Connecter Google" in r.text
    assert "Bienvenue" not in r.text


def test_email_lists_messages_when_google_linked(client, state):
    state["google_linked"] = True
    as_owner(client)
    r = client.get("/app/account/email")
    assert r.status_code == 200
    assert "Bienvenue" in r.text
    assert "welcome@example.com" in r.text


def test_agenda_and_email_require_login(client):
    assert client.get("/app/account/agenda").status_code in (302, 303)
    assert client.get("/app/account/email").status_code in (302, 303)


def test_google_connect_redirects_to_the_provider_authorize_url(client, state):
    as_owner(client)
    r = client.get("/app/account/google/connect")
    assert r.status_code == 302
    assert r.headers["location"].startswith("https://accounts.google.com/")


def test_google_connect_requires_login(client):
    r = client.get("/app/account/google/connect")
    assert r.status_code in (302, 303)
    assert "/app/account/login" in r.headers["location"]


def test_oauth_link_callback_success_flashes_and_redirects_to_agenda(client):
    r = client.get("/app/account/oauth/link/callback", params={"success": "true", "provider": "google", "email": "a@b.com"})
    assert r.status_code == 303
    assert r.headers["location"] == "/app/account/agenda?m=google_linked"


def test_oauth_link_callback_without_success_flashes_failure_on_security(client):
    r = client.get("/app/account/oauth/link/callback")
    assert r.status_code == 303
    assert r.headers["location"] == "/app/account/security?m=google_link_failed"
