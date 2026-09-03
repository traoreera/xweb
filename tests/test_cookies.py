"""Vraies requêtes HTTP via TestClient (comme test_csrf.py) — les attributs
Set-Cookie (Secure/SameSite/__Host-) ne se prouvent que sur un vrai cycle
ASGI, jamais en inspectant les arguments passés à Response.set_cookie."""

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from xweb.cookies import (
    PendingState,
    clear_pending_state,
    clear_strict_cookie,
    read_pending_state,
    read_strict_cookie,
    set_pending_state,
    set_strict_cookie,
)


def make_app() -> FastAPI:
    app = FastAPI()

    @app.get("/set-root")
    async def set_root(request: Request):
        from starlette.responses import Response

        resp = Response()
        set_strict_cookie(resp, request, "session", "abc123", path="/", same_site="lax")
        return resp

    @app.get("/set-scoped")
    async def set_scoped(request: Request):
        from starlette.responses import Response

        resp = Response()
        set_strict_cookie(resp, request, "refresh", "r-1", path="/account", max_age=3600)
        return resp

    @app.get("/clear-root")
    async def clear_root(request: Request):
        from starlette.responses import Response

        resp = Response()
        clear_strict_cookie(resp, request, "session", path="/")
        return resp

    @app.get("/read-root")
    async def read_root(request: Request):
        return {"value": read_strict_cookie(request, "session", path="/")}

    # Sous /account/... : Path=/account du cookie ne serait sinon jamais
    # renvoyé par le jar du client vers des routes à la racine.
    @app.get("/account/set-pending")
    async def set_pending(request: Request):
        from starlette.responses import Response

        resp = Response()
        set_pending_state(resp, request, "pending", {"step": "mfa", "token": "t-1"}, path="/account", max_age=900)
        return resp

    @app.get("/account/read-pending")
    async def read_pending(request: Request):
        return {"data": read_pending_state(request, "pending", path="/account")}

    @app.get("/account/set-pending-signed")
    async def set_pending_signed(request: Request):
        from starlette.responses import Response

        resp = Response()
        set_pending_state(resp, request, "pending", {"tenant_id": "t-1"}, path="/account", max_age=900, secret="s3cr3t")
        return resp

    @app.get("/account/read-pending-signed")
    async def read_pending_signed(request: Request):
        return {"data": read_pending_state(request, "pending", path="/account", secret="s3cr3t")}

    @app.get("/account/clear-pending")
    async def clear_pending(request: Request):
        from starlette.responses import Response

        resp = Response()
        clear_pending_state(resp, request, "pending", path="/account")
        return resp

    return app


# ── set_strict_cookie — HTTP (dev local, jamais Secure) ─────────────────────


def test_http_cookie_has_httponly_but_never_secure_or_prefixed():
    client = TestClient(make_app())  # base_url http:// par défaut
    resp = client.get("/set-root")
    raw = resp.headers.get("set-cookie")
    assert "session=abc123" in raw  # jamais __Host-/__Secure- sans Secure
    assert "HttpOnly" in raw
    assert "Secure" not in raw
    assert "SameSite=lax" in raw
    assert "Path=/" in raw


def test_http_cookie_default_samesite_is_strict():
    app = FastAPI()

    @app.get("/set")
    async def set_(request: Request):
        from starlette.responses import Response

        resp = Response()
        set_strict_cookie(resp, request, "x", "1")  # same_site non précisé
        return resp

    client = TestClient(app)
    raw = client.get("/set").headers.get("set-cookie")
    assert "SameSite=strict" in raw


# ── set_strict_cookie — HTTPS (préfixe __Host-/__Secure-) ───────────────────


def test_https_root_cookie_gets_host_prefix_and_secure():
    client = TestClient(make_app(), base_url="https://testserver")
    raw = client.get("/set-root").headers.get("set-cookie")
    assert "__Host-session=abc123" in raw
    assert "Secure" in raw
    assert "HttpOnly" in raw


def test_https_scoped_path_cookie_gets_secure_prefix_not_host():
    """__Host- exige path=/ — un cookie à path restreint ne peut pas le
    porter (RFC 6265bis), __Secure- est le maximum atteignable ici."""
    client = TestClient(make_app(), base_url="https://testserver")
    raw = client.get("/set-scoped").headers.get("set-cookie")
    assert "__Secure-refresh=r-1" in raw
    assert "__Host-refresh" not in raw
    assert "Secure" in raw
    assert "Path=/account" in raw
    assert "Max-Age=3600" in raw


# ── clear_strict_cookie — doit cibler exactement le nom posé ────────────────


def test_clear_on_https_targets_the_prefixed_name():
    client = TestClient(make_app(), base_url="https://testserver")
    raw = client.get("/clear-root").headers.get("set-cookie")
    assert raw.startswith("__Host-session=")
    assert "Max-Age=0" in raw or "01 Jan 1970" in raw


# ── read_strict_cookie — aller-retour réel dans le jar du client ────────────


def test_read_round_trip_over_http():
    client = TestClient(make_app())
    client.get("/set-root")
    body = client.get("/read-root").json()
    assert body["value"] == "abc123"


def test_read_round_trip_over_https_with_prefix():
    client = TestClient(make_app(), base_url="https://testserver")
    client.get("/set-root")
    body = client.get("/read-root").json()
    assert body["value"] == "abc123"


def test_read_missing_cookie_is_none_not_an_error():
    client = TestClient(make_app())
    body = client.get("/read-root").json()
    assert body["value"] is None


# ── PendingState — codec seul ────────────────────────────────────────────────


def test_pending_state_round_trip_without_secret():
    codec = PendingState()
    encoded = codec.encode({"step": "mfa", "token": "abc"})
    assert codec.decode(encoded) == {"step": "mfa", "token": "abc"}


def test_pending_state_garbage_input_returns_none_never_raises():
    codec = PendingState()
    assert codec.decode("not-base64-json-!!!") is None
    assert codec.decode("") is None


def test_pending_state_signed_round_trip():
    codec = PendingState(secret="s3cr3t")
    encoded = codec.encode({"tenant_id": "t-1"})
    assert codec.decode(encoded) == {"tenant_id": "t-1"}


def test_pending_state_signed_rejects_tampered_payload():
    """Le porteur ne peut pas modifier un champ (ex. tenant_id) et se
    faire quand même relire — c'est tout l'intérêt de secret=."""
    codec = PendingState(secret="s3cr3t")
    encoded = codec.encode({"tenant_id": "t-1"})
    # Un attaquant change juste le payload JSON encodé, garde la signature.
    import base64
    import json

    padded = encoded + "=" * (-len(encoded) % 4)
    blob = base64.urlsafe_b64decode(padded)
    mac_part, _raw = blob.split(b".", 1)
    tampered_raw = json.dumps({"tenant_id": "OTHER-TENANT"}, separators=(",", ":")).encode()
    tampered_blob = mac_part + b"." + tampered_raw
    tampered_encoded = base64.urlsafe_b64encode(tampered_blob).decode("ascii").rstrip("=")

    assert codec.decode(tampered_encoded) is None


def test_pending_state_wrong_secret_rejected():
    encoded = PendingState(secret="s3cr3t").encode({"a": 1})
    assert PendingState(secret="wrong").decode(encoded) is None


# ── set_pending_state / read_pending_state — bout en bout via cookie ───────


def test_pending_state_end_to_end_over_https():
    client = TestClient(make_app(), base_url="https://testserver")
    raw = client.get("/account/set-pending").headers.get("set-cookie")
    assert "SameSite=strict" in raw  # jamais un paramètre, toujours strict
    assert "__Secure-pending" in raw  # path="/account" != "/"

    body = client.get("/account/read-pending").json()
    assert body["data"] == {"step": "mfa", "token": "t-1"}


def test_pending_state_signed_end_to_end():
    client = TestClient(make_app(), base_url="https://testserver")
    client.get("/account/set-pending-signed")
    body = client.get("/account/read-pending-signed").json()
    assert body["data"] == {"tenant_id": "t-1"}


def test_clear_pending_state_removes_it():
    client = TestClient(make_app(), base_url="https://testserver")
    client.get("/account/set-pending")
    assert client.get("/account/read-pending").json()["data"] is not None
    client.get("/account/clear-pending")
    assert client.get("/account/read-pending").json()["data"] is None
