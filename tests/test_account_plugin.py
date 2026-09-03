"""plugins/account — le pont HTML vers plugins/auth (docs/auth.md), testé
contre une FAUSSE API d'auth qui reproduit les formes de réponse réelles
de plugins/auth (TokenResponse, flows.md §7 : MFA, multi-organisation,
onboarding) — branchée via httpx.ASGITransport, donc de vraies requêtes
HTTP internes, pas des mocks de méthodes.
"""

from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from fastapi.testclient import TestClient

from xweb.engine.registry import QwebRegistry

ROOT = Path(__file__).parent.parent
SRC = ROOT / "plugins" / "account" / "src"

VALID_TOKENS = {"tok-ok", "tok-ok2", "tok-new"}


def load_account_pkg():
    """plugins/account/src utilise des imports relatifs (comme xcore le
    charge : un package dont __path__ pointe sur src/, lifecycle.py)."""
    if "account_src" not in sys.modules:
        pkg = types.ModuleType("account_src")
        pkg.__path__ = [str(SRC)]
        sys.modules["account_src"] = pkg
    return importlib.import_module("account_src.routes"), importlib.import_module("account_src.api")


# ---------------------------------------------------------------------
# Fausse API plugins/auth — mêmes chemins, mêmes formes de réponse
# ---------------------------------------------------------------------


def make_fake_auth(state: dict) -> FastAPI:
    app = FastAPI()
    P = "/app/auth"

    def tokens(access="tok-ok", refresh="r-ok", **extra):
        return {"access_token": access, "refresh_token": refresh, "token_type": "bearer", "mfa_required": False, "tenants": None, **extra}

    def bearer(request: Request) -> str:
        auth = request.headers.get("authorization", "")
        token = auth[7:] if auth.startswith("Bearer ") else ""
        if token not in VALID_TOKENS:
            raise HTTPException(401, "Token invalide ou expiré")
        return token

    @app.post(f"{P}/login")
    async def login(request: Request):
        body = await request.json()
        state["last_forwarded_for"] = request.headers.get("x-forwarded-for")
        email, pw = body["email"], body["password"]
        if pw != "Secret1x":
            raise HTTPException(401, "Invalid credentials")
        if email == "ada@example.com":
            return tokens()
        if email == "mfa@example.com":
            return tokens(access="", refresh="", mfa_required=True, mfa_token="mfa-1")
        if email == "multi@example.com":
            return tokens(access="", refresh="r-multi", tenants=[
                {"id": "t1", "name": "Acme", "slug": "acme", "is_owner": True}, {"id": "t2", "name": "Beta", "slug": "beta"},
            ])
        if email == "new@example.com":
            return tokens(access="tok-new", refresh="r-new", onboarding_required=True, tenants=[])
        raise HTTPException(401, "Invalid credentials")

    @app.post(f"{P}/register", status_code=201)
    async def register(request: Request):
        body = await request.json()
        if body["email"] == "ada@example.com":
            raise HTTPException(400, "Email already registered")
        if len(body["password"]) < 8:
            raise HTTPException(400, "Password must be at least 8 characters long")
        state["registered"] = body["email"]
        return {"id": "u-new", "email": body["email"], "is_active": True, "mfa_enabled": False}

    @app.post(f"{P}/refresh")
    async def refresh(request: Request):
        body = await request.json()
        if body["refresh_token"] == "r-ok":
            return tokens(access="tok-ok2", refresh="r-ok2")
        raise HTTPException(401, "Invalid or expired refresh token")

    @app.post(f"{P}/logout", status_code=204)
    async def logout(request: Request):
        state["logged_out"] = (await request.json())["refresh_token"]
        return Response(status_code=204)

    @app.post(f"{P}/auth/verify-mfa")
    async def verify_mfa(request: Request):
        body = await request.json()
        if body["mfa_token"] == "mfa-1" and body["code"] == "123456":
            return tokens()
        raise HTTPException(401, "Code MFA invalide ou expiré")

    @app.post(f"{P}/select-tenant")
    async def select_tenant(request: Request):
        body = await request.json()
        if body["refresh_token"] == "r-multi" and body["tenant_id"] == "t1":
            return tokens(tenant_id="t1")
        raise HTTPException(400, "User is not a member of this tenant")

    @app.post(f"{P}/setup/create")
    async def setup_create(request: Request):
        body = await request.json()
        if body["refresh_token"] != "r-new":
            raise HTTPException(400, "Invalid or expired refresh token")
        state["created_tenant"] = (body["name"], body["slug"])
        return tokens(tenant_id="t-new", onboarding_required=False)

    @app.post(f"{P}/setup/join")
    async def setup_join(request: Request):
        body = await request.json()
        if body["invite_token"] == "INV":
            return tokens(tenant_id="t-join")
        raise HTTPException(400, "Code d'invitation invalide ou déjà utilisé")

    @app.post(f"{P}/password/forgot", status_code=202)
    async def forgot(request: Request):
        state["forgot"] = (await request.json())["email"]
        return {"detail": "ok"}

    @app.post(f"{P}/password/reset")
    async def reset(request: Request):
        body = await request.json()
        if body["token"] != "RST":
            raise HTTPException(400, "Token invalide ou expiré.")
        return {"detail": "ok"}

    @app.get(f"{P}/me")
    async def me(request: Request):
        bearer(request)
        return {"id": "u1", "email": "ada@example.com", "is_active": True, "mfa_enabled": state["mfa_enabled"], "has_password": True}

    @app.patch(f"{P}/account/email")
    async def change_email(request: Request):
        bearer(request)
        body = await request.json()
        if body["password"] != "Secret1x":
            raise HTTPException(400, "Mot de passe incorrect")
        state["email"] = body["new_email"]
        return {"email": body["new_email"]}

    @app.patch(f"{P}/account/password")
    async def change_password(request: Request):
        bearer(request)
        body = await request.json()
        if body["current_password"] != "Secret1x":
            raise HTTPException(400, "Mot de passe actuel incorrect")
        state["password_changed"] = True
        return {"ok": True}

    @app.get(f"{P}/auth/sessions")
    async def sessions(request: Request):
        bearer(request)
        return [
            {"id": "s1", "tenant_id": "t1", "ip_address": "10.0.0.1", "device_fingerprint": "Firefox", "last_seen": "2026-09-02T18:30:12.123456+00:00", "expires_at": "2026-09-09T18:30:12+00:00"},
            {"id": "s2", "tenant_id": "t1", "ip_address": None, "device_fingerprint": None, "last_seen": "2026-09-01T08:00:00", "expires_at": "2026-09-08T08:00:00"},
        ]

    @app.delete(f"{P}/auth/sessions/{{sid}}", status_code=204)
    async def revoke(request: Request, sid: str):
        bearer(request)
        if sid not in ("s1", "s2"):
            raise HTTPException(404, "Session not found")
        state.setdefault("revoked", []).append(sid)
        return Response(status_code=204)

    @app.delete(f"{P}/auth/sessions", status_code=204)
    async def revoke_all(request: Request):
        bearer(request)
        state["revoked_all"] = True
        return Response(status_code=204)

    @app.post(f"{P}/mfa/setup")
    async def mfa_setup(request: Request):
        bearer(request)
        return {"secret": "JBSWY3DPEHPK3PXP", "otpauth_url": "otpauth://totp/x", "qr_code": "iVBORw0KGgo=", "backup_codes": ["AAAA111111", "BBBB222222"]}

    @app.post(f"{P}/mfa/enable")
    async def mfa_enable(request: Request):
        bearer(request)
        if (await request.json())["code"] != "123456":
            raise HTTPException(400, "Invalid TOTP code")
        state["mfa_enabled"] = True
        return {"mfa_enabled": True}

    @app.delete(f"{P}/mfa/", status_code=204)
    async def mfa_disable(request: Request):
        bearer(request)
        if (await request.json())["code"] != "123456":
            raise HTTPException(400, "Code TOTP invalide ou expiré")
        state["mfa_enabled"] = False
        return Response(status_code=204)

    @app.post(f"{P}/invites/accept")
    async def accept_invite(request: Request):
        bearer(request)
        body = await request.json()
        if body["token"] != "INV":
            raise HTTPException(400, "Invite not found")
        state["invite_user"] = body["user_id"]
        return {"success": True, "tenant_id": "t9"}

    @app.get(f"{P}/oauth/providers")
    async def providers():
        return {"providers": ["github"]}

    @app.get(f"{P}/oauth/{{provider}}/authorize")
    async def authorize(provider: str, redirect: str | None = None):
        if provider != "github":
            raise HTTPException(400, "Provider Error")
        state["oauth_redirect"] = redirect
        return {"auth_url": f"https://github.example/authorize?redirect={redirect}", "provider": provider}

    return app


# ---------------------------------------------------------------------
# Le pont, monté comme xcore le ferait (/app/account + ext.xweb)
# ---------------------------------------------------------------------


class FakeExt:
    csrf_token = "csrf-test-token"


class FakePluginCtx:
    name = "account"
    tenant_id = None
    caller = None
    config = {}

    def get_service(self, name):
        return FakeExt() if name == "ext.xweb" else None


@pytest.fixture
def state():
    return {"mfa_enabled": False}


@pytest.fixture
def client(monkeypatch, state):
    routes, api = load_account_pkg()

    def _payload_for(token: str | None) -> dict | None:
        if token in VALID_TOKENS:
            return {"sub": "u1", "roles": ["user"], "permissions": [], "user": {"email": "ada@example.com", "tenant_id": "t1"}}
        return None

    async def fake_resolve(request):
        # Même contrat que le vrai xcore.kernel.api.rbac::_resolve_user :
        # request.state.user (posé par SilentRefreshRoute après un
        # rafraîchissement silencieux, routes.py) prime sur le cookie —
        # sinon un test ne verrait jamais l'utilisateur rafraîchi tant
        # qu'aucun cookie access_token à jour n'est réellement présent.
        cached = getattr(request.state, "user", None)
        if cached is not None:
            return cached
        return _payload_for(request.cookies.get("access_token"))

    monkeypatch.setattr("xweb.context.resolve_user_or_anonymous", fake_resolve)

    class FakeAuthBackend:
        """routes.py::SilentRefreshRoute appelle get_auth_backend().decode_token()
        directement (pas resolve_user_or_anonymous) pour décoder un
        access_token frais après un rafraîchissement silencieux — même
        mapping token->payload que fake_resolve ci-dessus, pour rester
        cohérent."""

        async def decode_token(self, token: str) -> dict | None:
            return _payload_for(token)

    # Patché sur le NOM importé dans routes.py (account_src.routes.get_auth_backend),
    # pas sur xcore.kernel.api.auth — monkeypatch doit viser où le nom est
    # utilisé, pas sa source (déjà lié au moment de l'import du module).
    monkeypatch.setattr("account_src.routes.get_auth_backend", lambda: FakeAuthBackend())

    fake_auth = make_fake_auth(state)
    registry = QwebRegistry()
    registry.register_dir(ROOT / "xweb" / "components")
    registry.register_dir(ROOT / "plugins" / "account" / "templates", source_plugin="account")

    def api_factory(request):
        return api.AuthApi("http://auth.internal", transport=httpx.ASGITransport(app=fake_auth), client_ip="203.0.113.7")

    app = FastAPI()
    app.include_router(
        routes.build_router(FakePluginCtx(), registry, config={"app_name": "TestApp", "home_path": "/home"}, api_factory=api_factory),
        prefix="/app/account",
    )
    return TestClient(app, follow_redirects=False)


def set_cookies(r):
    return r.headers.get_list("set-cookie")


def login(client, email="ada@example.com", password="Secret1x", next_path=None):
    data = {"email": email, "password": password}
    if next_path:
        data["next"] = next_path
    return client.post("/app/account/login", data=data)


# ── connexion ────────────────────────────────────────────────────────────


def test_login_page_has_csrf_next_providers_and_no_shell(client):
    r = client.get("/app/account/login?next=/app/demo/")
    assert r.status_code == 200
    assert "<html>" in r.text and 'href="/xweb-static/app.css"' in r.text  # layout minimal : CSS chargé
    assert 'id="xweb-sidebar"' not in r.text
    assert 'name="csrf_token" value="csrf-test-token"' in r.text
    assert 'name="next" value="/app/demo/"' in r.text
    assert 'href="/app/account/oauth/github"' in r.text and "Continuer avec Github" in r.text
    # github a désormais son propre logo (fill_paths, xweb/components/icon.xml)
    # au lieu du "globe" générique partagé par tous les providers.
    assert 'fill="currentColor"' in r.text
    assert 'hx-boost="false"' in r.text
    assert "<title>Connexion · TestApp</title>" in r.text


def test_login_success_sets_cookies_and_redirects_to_next(client, state):
    r = login(client, next_path="/app/demo/?x=1")
    assert r.status_code == 303 and r.headers["location"] == "/app/demo/?x=1"
    cookies = set_cookies(r)
    assert any(c.startswith("access_token=tok-ok;") and "HttpOnly" in c and "Path=/;" in c for c in cookies)
    assert any(c.startswith("refresh_token=r-ok;") and "Path=/app/account" in c for c in cookies)
    assert state["last_forwarded_for"] == "203.0.113.7"  # rate limit côté auth par vrai visiteur


def test_login_failure_keeps_email_and_answers_401(client):
    r = login(client, password="nope")
    assert r.status_code == 401
    assert "Email ou mot de passe incorrect." in r.text
    assert 'value="ada@example.com"' in r.text


def test_login_rejects_open_redirect_in_next(client):
    for bad in ("//evil.example", "https://evil.example/x", "javascript:alert(1)"):
        r = login(client, next_path=bad)
        assert r.headers["location"] == "/home", bad


def test_logged_in_user_is_sent_away_from_login(client):
    client.cookies.set("access_token", "tok-ok")
    r = client.get("/app/account/login?next=/x")
    assert r.status_code == 303 and r.headers["location"] == "/x"


def test_silent_refresh_from_refresh_cookie(client):
    client.cookies.set("refresh_token", "r-ok", path="/app/account")
    r = client.get("/app/account/login?next=/after")
    assert r.status_code == 303 and r.headers["location"] == "/after"
    assert any(c.startswith("access_token=tok-ok2;") for c in set_cookies(r))
    assert any(c.startswith("refresh_token=r-ok2;") for c in set_cookies(r))


def test_dead_refresh_cookie_is_cleared_and_form_shown(client):
    client.cookies.set("refresh_token", "r-dead", path="/app/account")
    r = client.get("/app/account/login")
    assert r.status_code == 200 and 'name="email"' in r.text
    assert any(c.startswith("refresh_token=") and ("Max-Age=0" in c or "max-age=0" in c) for c in set_cookies(r))


# ── MFA / organisations / onboarding ─────────────────────────────────────


def test_mfa_flow(client):
    r = login(client, email="mfa@example.com", next_path="/dest")
    assert r.status_code == 303 and r.headers["location"] == "/app/account/mfa"
    assert any(c.startswith("xweb_auth_pending=") for c in set_cookies(r))
    assert not any(c.startswith("access_token=") for c in set_cookies(r))

    page = client.get("/app/account/mfa")
    assert page.status_code == 200 and 'name="code"' in page.text

    bad = client.post("/app/account/mfa", data={"code": "000000"})
    assert bad.status_code == 401 and "Code MFA invalide" in bad.text

    ok = client.post("/app/account/mfa", data={"code": "123 456"})
    assert ok.status_code == 303 and ok.headers["location"] == "/dest"
    assert any(c.startswith("access_token=tok-ok;") for c in set_cookies(ok))
    assert any(c.startswith("xweb_auth_pending=") and ("Max-Age=0" in c or "max-age=0" in c) for c in set_cookies(ok))


def test_mfa_page_without_pending_state_goes_back_to_login(client):
    r = client.get("/app/account/mfa")
    assert r.status_code == 303 and r.headers["location"] == "/app/account/login?m=flow_expired"


def test_multi_tenant_flow(client):
    r = login(client, email="multi@example.com")
    assert r.headers["location"] == "/app/account/tenant"
    page = client.get("/app/account/tenant")
    assert "Acme" in page.text and "Beta" in page.text and 'value="t1"' in page.text and "propriétaire" in page.text

    wrong = client.post("/app/account/tenant", data={"tenant_id": "t-unknown"})
    assert wrong.status_code == 400 and "Choisissez une organisation" in wrong.text

    ok = client.post("/app/account/tenant", data={"tenant_id": "t1"})
    assert ok.status_code == 303 and ok.headers["location"] == "/home"
    assert any(c.startswith("access_token=tok-ok;") for c in set_cookies(ok))


def test_onboarding_create_and_join(client, state):
    r = login(client, email="new@example.com")
    assert r.headers["location"] == "/app/account/onboarding"
    assert any(c.startswith("access_token=tok-new;") for c in set_cookies(r))  # token valide, sans organisation

    page = client.get("/app/account/onboarding?invite=INV")
    assert page.status_code == 200 and "Bienvenue" in page.text and 'value="INV"' in page.text

    created = client.post("/app/account/onboarding/create", data={"name": "Ma Boîte SAS", "slug": ""})
    assert created.status_code == 303 and created.headers["location"] == "/home"
    assert state["created_tenant"] == ("Ma Boîte SAS", "ma-bo-te-sas")

    # rejoindre par invitation, même état d'attente
    login(client, email="new@example.com")
    bad = client.post("/app/account/onboarding/join", data={"invite": "NOPE"})
    assert bad.status_code == 400 and "invitation invalide" in bad.text
    ok = client.post("/app/account/onboarding/join", data={"invite": "INV"})
    assert ok.status_code == 303 and ok.headers["location"] == "/home"


# ── inscription, mot de passe oublié, réinitialisation ───────────────────


def test_register_validations_and_success(client, state):
    r = client.get("/app/account/register")
    assert r.status_code == 200 and "Au moins 8 caractères" in r.text
    mismatch = client.post("/app/account/register", data={"email": "x@example.com", "password": "Secret1x", "password_confirm": "other"})
    assert mismatch.status_code == 400 and "ne correspondent pas" in mismatch.text
    exists = client.post("/app/account/register", data={"email": "ada@example.com", "password": "Secret1x", "password_confirm": "Secret1x"})
    assert exists.status_code == 400 and "existe déjà" in exists.text
    weak = client.post("/app/account/register", data={"email": "new@example.com", "password": "short", "password_confirm": "short"})
    assert weak.status_code == 400 and "au moins 8 caractères" in weak.text
    ok = client.post("/app/account/register", data={"email": "new@example.com", "password": "Secret1x", "password_confirm": "Secret1x"})
    assert state["registered"] == "new@example.com"
    assert ok.status_code == 303 and ok.headers["location"] == "/app/account/onboarding"  # auto-login → onboarding


def test_forgot_never_reveals_whether_email_exists(client, state):
    assert 'name="email"' in client.get("/app/account/forgot").text
    r = client.post("/app/account/forgot", data={"email": "whoever@example.com"})
    assert r.status_code == 200 and "Si cet email existe" in r.text
    assert state["forgot"] == "whoever@example.com"


def test_reset_flow(client):
    assert "Jeton manque" not in client.get("/app/account/reset?token=RST").text
    missing = client.get("/app/account/reset")
    assert missing.status_code == 400 and "jeton manque" in missing.text
    bad = client.post("/app/account/reset", data={"token": "WRONG", "password": "Secret1x", "password_confirm": "Secret1x"})
    assert bad.status_code == 400 and "Token invalide ou expiré." in bad.text
    ok = client.post("/app/account/reset", data={"token": "RST", "password": "Secret1x", "password_confirm": "Secret1x"})
    assert ok.status_code == 303 and ok.headers["location"] == "/app/account/login?m=password_reset"
    assert "Mot de passe réinitialisé" in client.get("/app/account/login?m=password_reset").text


# ── déconnexion ──────────────────────────────────────────────────────────


def test_logout_revokes_session_and_clears_cookies(client, state):
    client.cookies.set("access_token", "tok-ok")
    client.cookies.set("refresh_token", "r-ok", path="/app/account")
    confirm = client.get("/app/account/logout")
    assert confirm.status_code == 200 and 'action="/app/account/logout"' in confirm.text
    r = client.post("/app/account/logout")
    assert r.status_code == 303 and r.headers["location"] == "/app/account/login?m=logged_out"
    assert state["logged_out"] == "r-ok"
    cleared = [c for c in set_cookies(r) if "Max-Age=0" in c or "max-age=0" in c]
    assert any(c.startswith("access_token=") for c in cleared) and any(c.startswith("refresh_token=") for c in cleared)


def test_logout_via_htmx_uses_hx_redirect(client):
    client.cookies.set("access_token", "tok-ok")
    r = client.post("/app/account/logout", headers={"HX-Request": "true"})
    assert r.status_code == 200 and r.headers["HX-Redirect"] == "/app/account/login?m=logged_out"


# ── pages authentifiées ──────────────────────────────────────────────────


def test_profile_requires_login_and_renders_in_shell(client):
    anon = client.get("/app/account/")
    assert anon.status_code == 303 and anon.headers["location"] == "/app/account/login?next=/app/account/"
    client.cookies.set("access_token", "tok-ok")
    r = client.get("/app/account/")
    assert r.status_code == 200
    assert 'id="xweb-sidebar"' in r.text  # dans le shell
    assert "ada@example.com" in r.text and 'action="/app/account/email"' in r.text and 'action="/app/account/password"' in r.text
    assert 'class="tab gap-2 tab-active"' in r.text  # onglet Profil actif
    assert 'name="otp_code"' not in r.text  # MFA désactivée : pas de champ code


def test_change_email(client, state):
    client.cookies.set("access_token", "tok-ok")
    bad = client.post("/app/account/email", data={"new_email": "new@example.com", "password": "wrong"})
    assert bad.status_code == 400 and "Mot de passe incorrect" in bad.text and 'id="xweb-sidebar"' in bad.text
    ok = client.post("/app/account/email", data={"new_email": "new@example.com", "password": "Secret1x"})
    assert ok.status_code == 303 and ok.headers["location"] == "/app/account/?m=email_changed"
    assert state["email"] == "new@example.com"
    assert "Adresse email mise à jour." in client.get("/app/account/?m=email_changed").text


def test_change_email_survives_a_mid_form_access_token_expiry_via_silent_refresh(client, state):
    """Le vrai gap que SilentRefreshRoute ferme (routes.py) : avant ce
    correctif, un access_token expiré au moment d'un POST redirigeait vers
    /login, perdant les données du formulaire en cours de soumission —
    l'utilisateur devait tout ressaisir. Ici : aucun access_token du tout
    (simule l'expiration), mais un refresh_token valide -> la mutation
    aboutit quand même DANS LA MÊME requête, sans redirection ni perte de
    saisie, et les nouveaux cookies sont posés pour la suite de la session."""
    client.cookies.set("refresh_token", "r-ok", path="/app/account")
    r = client.post("/app/account/email", data={"new_email": "new2@example.com", "password": "Secret1x"})
    assert r.status_code == 303 and r.headers["location"] == "/app/account/?m=email_changed"
    assert state["email"] == "new2@example.com"  # la mutation a bien eu lieu, pas juste un redirect vide
    assert any(c.startswith("access_token=tok-ok2;") for c in set_cookies(r))
    assert any(c.startswith("refresh_token=r-ok2;") for c in set_cookies(r))


def test_change_password_closes_the_session(client, state):
    client.cookies.set("access_token", "tok-ok")
    mismatch = client.post("/app/account/password", data={"current_password": "Secret1x", "new_password": "Newpass1x", "new_password_confirm": "other"})
    assert mismatch.status_code == 400 and "ne correspondent pas" in mismatch.text
    r = client.post("/app/account/password", data={"current_password": "Secret1x", "new_password": "Newpass1x", "new_password_confirm": "Newpass1x"}, headers={"HX-Request": "true"})
    assert r.status_code == 200 and r.headers["HX-Redirect"] == "/app/account/login?m=password_changed"
    assert state["password_changed"] is True
    assert any(c.startswith("access_token=") and ("Max-Age=0" in c or "max-age=0" in c) for c in set_cookies(r))


def test_accept_invite_from_profile(client, state):
    client.cookies.set("access_token", "tok-ok")
    r = client.post("/app/account/invite", data={"invite": "INV"})
    assert r.status_code == 303 and r.headers["location"] == "/app/account/?m=invite_accepted"
    assert state["invite_user"] == "u1"


def test_security_mfa_setup_enable_disable(client, state):
    client.cookies.set("access_token", "tok-ok")
    page = client.get("/app/account/security")
    assert page.status_code == 200 and 'action="/app/account/security/mfa/setup"' in page.text

    setup = client.post("/app/account/security/mfa/setup")
    assert setup.status_code == 200 and "JBSWY3DPEHPK3PXP" in setup.text and "AAAA111111" in setup.text
    assert 'alt="QR code TOTP"' in setup.text and "data:image/png;base64," in setup.text
    assert 'action="/app/account/security/mfa/enable"' in setup.text

    bad = client.post("/app/account/security/mfa/enable", data={"code": "111111"})
    assert bad.status_code == 400 and "Code invalide." in bad.text
    ok = client.post("/app/account/security/mfa/enable", data={"code": "123456"})
    assert ok.status_code == 303 and ok.headers["location"] == "/app/account/security?m=mfa_enabled"
    assert state["mfa_enabled"] is True

    enabled = client.get("/app/account/security?m=mfa_enabled")
    assert "Activée sur ce compte." in enabled.text and 'action="/app/account/security/mfa/disable"' in enabled.text
    assert "deux facteurs activée" in enabled.text
    assert 'name="otp_code"' in client.get("/app/account/").text  # le profil demande maintenant le code

    off = client.post("/app/account/security/mfa/disable", data={"code": "123456"})
    assert off.status_code == 303 and off.headers["location"] == "/app/account/security?m=mfa_disabled"
    assert state["mfa_enabled"] is False


def test_sessions_list_revoke_one_and_all(client, state):
    client.cookies.set("access_token", "tok-ok")
    page = client.get("/app/account/sessions")
    assert page.status_code == 200
    assert "Firefox" in page.text and "10.0.0.1" in page.text and "2026-09-02 18:30" in page.text
    assert 'action="/app/account/sessions/s1/revoke"' in page.text and 'action="/app/account/sessions/s2/revoke"' in page.text

    r = client.post("/app/account/sessions/s1/revoke")
    assert r.status_code == 303 and r.headers["location"] == "/app/account/sessions?m=session_revoked"
    assert state["revoked"] == ["s1"]

    missing = client.post("/app/account/sessions/nope/revoke")
    assert missing.status_code == 404 and "Session introuvable." in missing.text

    all_ = client.post("/app/account/sessions/revoke-all")
    assert all_.status_code == 303 and all_.headers["location"] == "/app/account/login?m=logged_out_all"
    assert state["revoked_all"] is True
    assert any(c.startswith("access_token=") and ("Max-Age=0" in c or "max-age=0" in c) for c in set_cookies(all_))


def test_authenticated_posts_without_user_go_to_login(client):
    r = client.post("/app/account/password", data={})
    assert r.status_code == 303 and r.headers["location"].startswith("/app/account/login?m=login_required")


# ── OAuth ────────────────────────────────────────────────────────────────


def test_oauth_start_and_callback(client, state):
    r = client.get("/app/account/oauth/github")
    assert r.status_code == 302 and r.headers["location"].startswith("https://github.example/authorize")
    assert state["oauth_redirect"] == "http://testserver/app/account/oauth/callback"

    unknown = client.get("/app/account/oauth/nope")
    assert unknown.status_code == 400 and "Fournisseur externe indisponible" in unknown.text

    cb = client.get("/app/account/oauth/callback?access_token=tok-ok&refresh_token=r-ok&user_id=u1")
    assert cb.status_code == 303 and cb.headers["location"] == "/home"
    assert any(c.startswith("access_token=tok-ok;") for c in set_cookies(cb))

    mfa = client.get("/app/account/oauth/callback?access_token=&refresh_token=&mfa_required=true&mfa_token=mfa-1")
    assert mfa.headers["location"] == "/app/account/mfa"

    failed = client.get("/app/account/oauth/callback?error=oauth_callback_failed")
    assert failed.status_code == 400 and "fournisseur externe a échoué" in failed.text


def test_oauth_callback_onboarding_required_needs_a_real_access_token(client, state):
    # Régression : plugins/auth/src/services/oauth.py (branche "aucun
    # tenant" de handle_callback) renvoyait access_token="" pour un login
    # OAuth sans organisation — finish_login() (routes.py) vérifie `if not
    # access: erreur` AVANT de regarder onboarding_required (son propre
    # docstring documente cet ordre : onboarding suppose un access_token
    # DÉJÀ valide, juste sans tenant — exactement ce que le flow mot de
    # passe fait déjà, authentication.py::login()). Testé pour de vrai :
    # "Réponse inattendue du service d'authentification." (502) au lieu de
    # l'écran d'onboarding.
    empty_token = client.get("/app/account/oauth/callback?access_token=&refresh_token=r-ok&user_id=u1&onboarding=true")
    assert empty_token.status_code == 502
    assert "Réponse inattendue" in empty_token.text

    ok = client.get("/app/account/oauth/callback?access_token=tok-onboard&refresh_token=r-onboard&user_id=u1&onboarding=true")
    assert ok.status_code == 303 and ok.headers["location"] == "/app/account/onboarding"
    assert any(c.startswith("access_token=tok-onboard;") for c in set_cookies(ok))


# ── helpers purs ─────────────────────────────────────────────────────────


def test_helpers_safe_next_slugify_messages():
    routes, api = load_account_pkg()
    assert routes.safe_next("/ok?x=1", "/d") == "/ok?x=1"
    assert routes.safe_next("//evil", "/d") == "/d"
    assert routes.safe_next("http://evil", "/d") == "/d"
    assert routes.safe_next("/bad\r\nheader", "/d") == "/d"
    assert routes.safe_next(None, "/d") == "/d"
    assert routes.slugify("Ma Boîte  SAS ") == "ma-bo-te-sas"
    assert routes.with_message("/p", "logged_out", next="/x") == "/p?m=logged_out&next=%2Fx"
    assert api._FR["Invalid credentials"] == "Email ou mot de passe incorrect."
