"""Vraies requêtes HTTP via TestClient, pas des appels directs à
dispatch() — le rejeu du body (xweb/csrf.py docstring) ne se prouve que
sur un vrai cycle ASGI."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from xweb.csrf import CSRFMiddleware

TOKEN = "secret-token-123"


def make_app() -> FastAPI:
    app = FastAPI()

    @app.get("/plugins/crm/contacts")
    async def list_contacts():
        return {"items": []}

    @app.post("/plugins/crm/contacts")
    async def create_contact():
        return {"ok": True}

    @app.post("/webhooks/stripe")  # outside protected_paths — bearer/signature auth, not cookies
    async def webhook():
        return {"received": True}

    app.add_middleware(CSRFMiddleware, get_token=lambda: TOKEN, protected_paths=("/plugins/",))
    return app


def test_get_request_never_checked():
    client = TestClient(make_app())
    assert client.get("/plugins/crm/contacts").status_code == 200


def test_post_without_session_cookie_not_checked():
    """docs/csrf.py: pas de cookie de session => pas une mutation
    cookie-authentifiée, une route API bearer-token n'a jamais besoin de ça."""
    client = TestClient(make_app())
    assert client.post("/plugins/crm/contacts", data={}).status_code == 200


def test_post_with_session_cookie_and_correct_token_passes():
    client = TestClient(make_app())
    client.cookies.set("session", "abc")
    r = client.post("/plugins/crm/contacts", data={"csrf_token": TOKEN})
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_post_with_session_cookie_and_wrong_token_rejected():
    client = TestClient(make_app())
    client.cookies.set("session", "abc")
    r = client.post("/plugins/crm/contacts", data={"csrf_token": "wrong"})
    assert r.status_code == 403
    assert r.json()["error"] == "csrf_invalid"


def test_post_with_session_cookie_and_missing_token_rejected():
    client = TestClient(make_app())
    client.cookies.set("session", "abc")
    r = client.post("/plugins/crm/contacts", data={})
    assert r.status_code == 403


def test_path_outside_protected_prefix_never_checked_even_with_session_cookie():
    client = TestClient(make_app())
    client.cookies.set("session", "abc")
    r = client.post("/webhooks/stripe", data={})  # no csrf_token at all — would 403 if checked
    assert r.status_code == 200


# ---------------------------------------------------------------------
# Ajouts avec plugins/account : cookies de session configurables,
# en-tête X-CSRF-Token, requêtes Bearer jamais vérifiées.
# ---------------------------------------------------------------------


def make_app_cookies(session_cookies) -> FastAPI:
    app = FastAPI()

    @app.post("/app/account/password")
    async def change():
        return {"ok": True}

    app.add_middleware(
        CSRFMiddleware, get_token=lambda: TOKEN, protected_paths=("/app/",), session_cookies=session_cookies,
    )
    return app


def test_access_token_cookie_counts_as_a_session_when_configured():
    client = TestClient(make_app_cookies(("session", "access_token")))
    client.cookies.set("access_token", "jwt")
    assert client.post("/app/account/password", data={}).status_code == 403
    assert client.post("/app/account/password", data={"csrf_token": TOKEN}).status_code == 200


def test_access_token_cookie_ignored_with_default_session_cookies():
    """Sans le réglage, le cookie access_token seul n'est pas une session
    aux yeux du middleware — c'est exactement le trou que main.py referme."""
    client = TestClient(make_app_cookies(("session",)))
    client.cookies.set("access_token", "jwt")
    assert client.post("/app/account/password", data={}).status_code == 200


def test_header_token_accepted_for_json_bodies():
    client = TestClient(make_app_cookies(("access_token",)))
    client.cookies.set("access_token", "jwt")
    assert client.post("/app/account/password", json={"x": 1}).status_code == 403
    r = client.post("/app/account/password", json={"x": 1}, headers={"X-CSRF-Token": TOKEN})
    assert r.status_code == 200
    assert client.post("/app/account/password", json={"x": 1}, headers={"X-CSRF-Token": "wrong"}).status_code == 403


def test_bearer_requests_are_never_checked_even_with_a_cookie():
    client = TestClient(make_app_cookies(("access_token",)))
    client.cookies.set("access_token", "jwt")
    r = client.post("/app/account/password", json={}, headers={"Authorization": "Bearer abc"})
    assert r.status_code == 200


def test_rejected_hx_request_gets_hx_refresh_to_force_a_reload():
    """Le csrf_token est stable pour tout le process (docs/csrf.py) — un
    onglet resté ouvert par-dessus un redémarrage serveur en a un périmé.
    Sans HX-Refresh, htmx swappe le JSON d'erreur brut dans #xweb-content
    (son comportement par défaut sur toute réponse) — invisible/déroutant
    pour qui ne sait pas qu'il suffit de recharger la page."""
    client = TestClient(make_app_cookies(("access_token",)))
    client.cookies.set("access_token", "jwt")
    r = client.post("/app/account/password", data={}, headers={"HX-Request": "true"})
    assert r.status_code == 403
    assert r.headers["HX-Refresh"] == "true"


def test_non_hx_rejection_has_no_hx_refresh_header():
    """Une requête JSON pure (pas de navigateur/htmx derrière) n'a aucune
    raison de porter un en-tête que seul htmx interprète."""
    client = TestClient(make_app_cookies(("access_token",)))
    client.cookies.set("access_token", "jwt")
    r = client.post("/app/account/password", data={})
    assert r.status_code == 403
    assert "HX-Refresh" not in r.headers
