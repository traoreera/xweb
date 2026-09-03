"""plugins/account — la section "Organisation" (gestion du tenant, des
membres, des invitations, et RBAC délégué au propriétaire du tenant :
plugins/auth/src/routes/{tenants,rbac,invites}.py, docs/auth.md). Même
principe que tests/test_account_plugin.py : fausse API plugins/auth
branchée via httpx.ASGITransport, de vraies requêtes HTTP internes.
"""

from __future__ import annotations

import importlib
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
TENANT = "t1"

ROLE_SUPPORT = "role-support"
PERM_SUBMISSIONS_LIST = {"id": "p1", "name": "submissions:list", "description": "Lister les soumissions", "group": "Soumissions", "tenant_grantable": True}
PERM_USER_READ = {"id": "p2", "name": "user:read", "description": "Lire un utilisateur", "group": "Utilisateurs", "tenant_grantable": True}


def load_account_pkg():
    if "account_org_src" not in sys.modules:
        pkg = types.ModuleType("account_org_src")
        pkg.__path__ = [str(SRC)]
        sys.modules["account_org_src"] = pkg
    return importlib.import_module("account_org_src.routes"), importlib.import_module("account_org_src.api")


def make_fake_auth(state: dict) -> FastAPI:
    app = FastAPI()
    P = "/app/auth"

    def bearer(request: Request) -> str:
        auth = request.headers.get("authorization", "")
        token = auth[7:] if auth.startswith("Bearer ") else ""
        if token not in (OWNER_TOKEN, MEMBER_TOKEN):
            raise HTTPException(401, "Token invalide ou expiré")
        return token

    def require_owner(request: Request) -> None:
        if bearer(request) != OWNER_TOKEN:
            raise HTTPException(403, "Réservé au propriétaire du tenant.")

    # ── tenants ──────────────────────────────────────────────────────────────

    @app.get(f"{P}/tenants/")
    async def list_tenants(request: Request):
        bearer(request)
        return [{"id": TENANT, "name": state["tenant_name"], "slug": "acme", "created_at": "2026-09-01T00:00:00+00:00", "is_owner": True, "license_state": "trial"}]

    @app.patch(f"{P}/tenants/{{tenant_id}}")
    async def rename_tenant(tenant_id: str, request: Request):
        require_owner(request)
        body = await request.json()
        if body.get("name"):
            state["tenant_name"] = body["name"]
        return {"id": tenant_id, "name": state["tenant_name"], "slug": "acme", "created_at": "2026-09-01T00:00:00+00:00", "is_owner": True}

    @app.delete(f"{P}/tenants/{{tenant_id}}/members/{{user_id}}", status_code=204)
    async def remove_member(tenant_id: str, user_id: str, request: Request):
        require_owner(request)
        if user_id not in state["members"]:
            raise HTTPException(404, "Membre introuvable dans ce tenant")
        del state["members"][user_id]
        return Response(status_code=204)

    # ── invites ──────────────────────────────────────────────────────────────

    @app.get(f"{P}/invites/{{tenant_id}}")
    async def list_invites(tenant_id: str, request: Request):
        require_owner(request)
        return list(state["invites"].values())

    @app.post(f"{P}/invites/", status_code=201)
    async def create_invite(request: Request):
        require_owner(request)
        body = await request.json()
        inv_id = f"inv-{len(state['invites']) + 1}"
        state["invites"][inv_id] = {
            "id": inv_id, "tenant_id": body["tenant_id"], "tenant_name": state["tenant_name"], "email": body["email"],
            "token": "tok-inv", "role_id": body.get("role_id"), "expires_at": "2026-09-05T12:00:00+00:00",
            "used_at": None, "is_active": True, "invited_by": "u-owner",
        }
        return state["invites"][inv_id]

    @app.delete(f"{P}/invites/{{invite_id}}", status_code=204)
    async def revoke_invite(invite_id: str, request: Request):
        require_owner(request)
        state["invites"].pop(invite_id, None)
        return Response(status_code=204)

    # ── rbac : rôles de tenant ───────────────────────────────────────────────

    @app.get(f"{P}/rbac/tenants/{{tenant_id}}/grantable")
    async def grantable(tenant_id: str, request: Request):
        require_owner(request)
        return [PERM_SUBMISSIONS_LIST, PERM_USER_READ]

    @app.get(f"{P}/rbac/tenants/{{tenant_id}}/roles")
    async def list_roles(tenant_id: str, request: Request):
        require_owner(request)
        return list(state["roles"].values())

    @app.post(f"{P}/rbac/tenants/{{tenant_id}}/roles", status_code=201)
    async def create_role(tenant_id: str, request: Request):
        require_owner(request)
        body = await request.json()
        rid = f"role-{len(state['roles']) + 1}"
        by_name = {PERM_SUBMISSIONS_LIST["name"]: PERM_SUBMISSIONS_LIST, PERM_USER_READ["name"]: PERM_USER_READ}
        perms = [by_name[n] for n in body.get("permissions", []) if n in by_name]
        state["roles"][rid] = {"id": rid, "name": body["name"], "tenant_id": tenant_id, "description": body.get("description"), "permissions": perms}
        return state["roles"][rid]

    @app.delete(f"{P}/rbac/tenants/{{tenant_id}}/roles/{{role_id}}")
    async def delete_role(tenant_id: str, role_id: str, request: Request):
        require_owner(request)
        if role_id not in state["roles"]:
            raise HTTPException(400, "Rôle introuvable")
        del state["roles"][role_id]
        for uid, m in state["members"].items():
            m["role_ids"] = [r for r in m["role_ids"] if r != role_id]
        return {"success": True, "role_id": role_id}

    @app.post(f"{P}/rbac/tenants/{{tenant_id}}/roles/{{role_id}}/permissions")
    async def add_role_perm(tenant_id: str, role_id: str, request: Request):
        require_owner(request)
        body = await request.json()
        by_name = {PERM_SUBMISSIONS_LIST["name"]: PERM_SUBMISSIONS_LIST, PERM_USER_READ["name"]: PERM_USER_READ}
        perm = by_name.get(body["permission_name"])
        if perm is None:
            raise HTTPException(400, "Permission inconnue, inactive ou non délégable")
        role = state["roles"][role_id]
        if perm not in role["permissions"]:
            role["permissions"].append(perm)
        return role

    @app.delete(f"{P}/rbac/tenants/{{tenant_id}}/roles/{{role_id}}/permissions/{{permission_name}}")
    async def remove_role_perm(tenant_id: str, role_id: str, permission_name: str, request: Request):
        require_owner(request)
        role = state["roles"][role_id]
        role["permissions"] = [p for p in role["permissions"] if p["name"] != permission_name]
        return role

    # ── rbac : membres ───────────────────────────────────────────────────────

    @app.get(f"{P}/rbac/tenants/{{tenant_id}}/members")
    async def list_members(tenant_id: str, request: Request):
        require_owner(request)
        return [
            {"user_id": uid, "email": m["email"], "primary_role_id": None, "role_ids": m["role_ids"], "is_owner": m["is_owner"]}
            for uid, m in state["members"].items()
        ]

    @app.get(f"{P}/rbac/tenants/{{tenant_id}}/members/{{user_id}}/roles")
    async def member_roles(tenant_id: str, user_id: str, request: Request):
        require_owner(request)
        return state["members"][user_id]["role_ids"]

    @app.post(f"{P}/rbac/tenants/{{tenant_id}}/members/{{user_id}}/roles")
    async def add_member_role(tenant_id: str, user_id: str, request: Request):
        require_owner(request)
        body = await request.json()
        role_id = body["role_id"]
        if role_id not in state["roles"]:
            raise HTTPException(400, "Rôle introuvable")
        roles = state["members"][user_id]["role_ids"]
        if role_id not in roles:
            roles.append(role_id)
        return {"success": True}

    @app.delete(f"{P}/rbac/tenants/{{tenant_id}}/members/{{user_id}}/roles/{{role_id}}")
    async def remove_member_role(tenant_id: str, user_id: str, role_id: str, request: Request):
        require_owner(request)
        m = state["members"][user_id]
        m["role_ids"] = [r for r in m["role_ids"] if r != role_id]
        return {"success": True}

    @app.get(f"{P}/rbac/tenants/{{tenant_id}}/members/{{user_id}}/permissions")
    async def member_effective(tenant_id: str, user_id: str, request: Request):
        require_owner(request)
        m = state["members"][user_id]
        names = set(m.get("direct_permissions", []))
        for rid in m["role_ids"]:
            role = state["roles"].get(rid)
            if role:
                names.update(p["name"] for p in role["permissions"])
        return sorted(names)

    @app.post(f"{P}/rbac/tenants/{{tenant_id}}/members/{{user_id}}/permissions")
    async def grant_member_perm(tenant_id: str, user_id: str, request: Request):
        require_owner(request)
        body = await request.json()
        m = state["members"][user_id]
        m.setdefault("direct_permissions", [])
        if body["permission_name"] not in m["direct_permissions"]:
            m["direct_permissions"].append(body["permission_name"])
        return {"success": True, "permission": body["permission_name"]}

    @app.delete(f"{P}/rbac/tenants/{{tenant_id}}/members/{{user_id}}/permissions/{{permission_name}}")
    async def revoke_member_perm(tenant_id: str, user_id: str, permission_name: str, request: Request):
        require_owner(request)
        m = state["members"][user_id]
        removed = permission_name in m.get("direct_permissions", [])
        m["direct_permissions"] = [p for p in m.get("direct_permissions", []) if p != permission_name]
        return {"success": removed, "permission": permission_name}

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
        "tenant_name": "Acme",
        "members": {
            "u-owner": {"email": "owner@example.com", "role_ids": [], "is_owner": True, "direct_permissions": []},
            "u-bob": {"email": "bob@example.com", "role_ids": [], "is_owner": False, "direct_permissions": []},
        },
        "invites": {}, "roles": {},
    }


@pytest.fixture
def client(monkeypatch, state):
    routes, api = load_account_pkg()

    async def fake_resolve(request):
        token = request.cookies.get("access_token")
        if token == OWNER_TOKEN:
            return {"sub": "u-owner", "roles": [], "permissions": ["tenants:read", "tenants:write", "rbac:read", "rbac:write", "invites:read", "invites:write"], "user": {"email": "owner@example.com", "tenant_id": TENANT}}
        if token == MEMBER_TOKEN:
            return {"sub": "u-bob", "roles": [], "permissions": [], "user": {"email": "bob@example.com", "tenant_id": TENANT}}
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


# ── vue d'ensemble ───────────────────────────────────────────────────────────


def test_overview_shows_tenant_and_members(client):
    as_owner(client)
    r = client.get("/app/account/organization")
    assert r.status_code == 200
    assert "Acme" in r.text
    assert "owner@example.com" in r.text and "bob@example.com" in r.text
    assert "Propriétaire" in r.text
    assert 'action="/app/account/organization/rename"' in r.text  # owner : formulaire de renommage visible


def test_member_does_not_see_owner_only_actions(client):
    as_member(client)
    r = client.get("/app/account/organization")
    assert r.status_code == 200
    # is_owner=False côté page (my_membership.is_owner) -> pas de formulaire de renommage/invitation
    assert 'action="/app/account/organization/rename"' not in r.text
    assert 'action="/app/account/organization/invite"' not in r.text


def test_rename_tenant(client, state):
    as_owner(client)
    r = client.post("/app/account/organization/rename", data={"tenant_id": TENANT, "name": "Acme Corp"})
    assert r.status_code == 303 and "m=org_renamed" in r.headers["location"]
    assert state["tenant_name"] == "Acme Corp"
    assert "Acme Corp" in client.get("/app/account/organization").text


def test_rename_empty_name_rejected(client, state):
    as_owner(client)
    r = client.post("/app/account/organization/rename", data={"tenant_id": TENANT, "name": "  "})
    assert r.status_code == 400 and "Le nom ne peut pas être vide" in r.text
    assert state["tenant_name"] == "Acme"


def test_remove_member(client, state):
    as_owner(client)
    r = client.post("/app/account/organization/members/u-bob/remove", data={"tenant_id": TENANT})
    assert r.status_code == 303 and "m=member_removed" in r.headers["location"]
    assert "u-bob" not in state["members"]


# ── invitations ──────────────────────────────────────────────────────────────


def test_create_and_list_and_revoke_invite(client, state):
    as_owner(client)
    r = client.post("/app/account/organization/invite", data={"tenant_id": TENANT, "email": "new@example.com"})
    assert r.status_code == 303 and "m=invite_sent" in r.headers["location"]
    assert len(state["invites"]) == 1

    page = client.get("/app/account/organization")
    assert "new@example.com" in page.text
    assert "Rôle par défaut" in page.text  # pas de role_id -> pas de nom résolu

    invite_id = next(iter(state["invites"]))
    revoke = client.post(f"/app/account/organization/invites/{invite_id}/revoke", data={"tenant_id": TENANT})
    assert revoke.status_code == 303 and "m=invite_revoked" in revoke.headers["location"]
    assert not state["invites"]


def test_invite_requires_email(client):
    as_owner(client)
    r = client.post("/app/account/organization/invite", data={"tenant_id": TENANT, "email": ""})
    assert r.status_code == 400 and "Adresse email requise" in r.text


# ── rôles de tenant ──────────────────────────────────────────────────────────


def test_create_role_with_permissions_and_list(client, state):
    as_owner(client)
    r = client.post(
        "/app/account/organization/roles",
        data={"tenant_id": TENANT, "name": "Support", "description": "Équipe support", "permissions": ["submissions:list", "user:read"]},
    )
    assert r.status_code == 303 and "m=role_created" in r.headers["location"]
    assert len(state["roles"]) == 1
    role_id = next(iter(state["roles"]))
    assert {p["name"] for p in state["roles"][role_id]["permissions"]} == {"submissions:list", "user:read"}

    listing = client.get("/app/account/organization/roles")
    assert "Support" in listing.text and "2 perm." in listing.text


def test_create_role_permission_list_has_search_and_collapsible_grouped_counts(client):
    """La liste de permissions n'est pas une simple liste plate — un
    déploiement réel peut avoir bien plus que les deux permissions de ce
    test (plugins/auth/src/services/seed.py en a 15 "tenant_grantable" de
    base, chaque plugin peut en ajouter). Filtre + groupes repliables avec
    compteur, vérifiés ici sans dépendre du volume réel."""
    as_owner(client)
    page = client.get("/app/account/organization/roles")
    assert 'id="role-create-perms"' in page.text
    assert '_="on input show &lt;.perm-row/&gt; in #role-create-perms when' in page.text
    assert "<details open=\"open\">" in page.text
    # deux groupes distincts (Soumissions, Utilisateurs) avec 1 permission chacun
    assert "Soumissions (1)" in page.text
    assert "Utilisateurs (1)" in page.text
    assert "perm-row" in page.text  # marqueur ciblé par le filtre, posé sur chaque case à cocher


def test_create_role_requires_name(client):
    as_owner(client)
    r = client.post("/app/account/organization/roles", data={"tenant_id": TENANT, "name": "  "})
    assert r.status_code == 400 and "Le nom du rôle est requis" in r.text


def test_role_detail_grant_and_revoke_permission(client, state):
    as_owner(client)
    client.post("/app/account/organization/roles", data={"tenant_id": TENANT, "name": "Support"})
    role_id = next(iter(state["roles"]))

    detail = client.get(f"/app/account/organization/roles/{role_id}")
    assert detail.status_code == 200 and "Support" in detail.text
    assert 'action="/app/account/organization/roles/{}/permissions/grant"'.format(role_id) in detail.text

    grant = client.post(f"/app/account/organization/roles/{role_id}/permissions/grant", data={"tenant_id": TENANT, "permission_name": "submissions:list"})
    assert grant.status_code == 303 and "m=role_updated" in grant.headers["location"]
    assert state["roles"][role_id]["permissions"][0]["name"] == "submissions:list"

    after_grant = client.get(f"/app/account/organization/roles/{role_id}")
    assert 'permissions/revoke' in after_grant.text  # devenu "Retirer" pour cette permission

    revoke = client.post(f"/app/account/organization/roles/{role_id}/permissions/revoke", data={"tenant_id": TENANT, "permission_name": "submissions:list"})
    assert revoke.status_code == 303
    assert state["roles"][role_id]["permissions"] == []


def test_role_detail_permission_list_has_search_and_grouped_rows(client, state):
    as_owner(client)
    client.post("/app/account/organization/roles", data={"tenant_id": TENANT, "name": "Support"})
    role_id = next(iter(state["roles"]))
    detail = client.get(f"/app/account/organization/roles/{role_id}")
    assert 'id="role-perms"' in detail.text
    assert '_="on input show &lt;.perm-row/&gt; in #role-perms when' in detail.text
    assert "Soumissions (1)" in detail.text and "Utilisateurs (1)" in detail.text
    assert 'class="perm-row' in detail.text


def test_delete_role(client, state):
    as_owner(client)
    client.post("/app/account/organization/roles", data={"tenant_id": TENANT, "name": "Éphémère"})
    role_id = next(iter(state["roles"]))
    r = client.post(f"/app/account/organization/roles/{role_id}/delete", data={"tenant_id": TENANT})
    assert r.status_code == 303 and "m=role_deleted" in r.headers["location"]
    assert role_id not in state["roles"]


def test_role_detail_unknown_role_shows_api_error(client):
    as_owner(client)
    r = client.get("/app/account/organization/roles/does-not-exist")
    assert r.status_code == 200  # pas d'exception, page rendue avec l'erreur
    assert "Rôle introuvable" in r.text or "introuvable" in r.text.lower()


# ── membre : rôles multiples + permissions directes ──────────────────────────


def test_member_detail_add_and_remove_role(client, state):
    as_owner(client)
    client.post("/app/account/organization/roles", data={"tenant_id": TENANT, "name": "Support"})
    role_id = next(iter(state["roles"]))

    detail = client.get("/app/account/organization/members/u-bob")
    assert detail.status_code == 200 and "bob@example.com" in detail.text
    assert "Aucun rôle assigné" in detail.text

    grant = client.post("/app/account/organization/members/u-bob/roles/grant", data={"tenant_id": TENANT, "role_id": role_id})
    assert grant.status_code == 303 and "m=member_role_updated" in grant.headers["location"]
    assert role_id in state["members"]["u-bob"]["role_ids"]

    after = client.get("/app/account/organization/members/u-bob")
    assert "Support" in after.text and "Aucun rôle assigné" not in after.text

    revoke = client.post("/app/account/organization/members/u-bob/roles/revoke", data={"tenant_id": TENANT, "role_id": role_id})
    assert revoke.status_code == 303
    assert role_id not in state["members"]["u-bob"]["role_ids"]


def test_member_detail_grant_and_revoke_direct_permission(client, state):
    as_owner(client)
    grant = client.post("/app/account/organization/members/u-bob/permissions/grant", data={"tenant_id": TENANT, "permission_name": "user:read"})
    assert grant.status_code == 303 and "m=member_permission_updated" in grant.headers["location"]
    assert "user:read" in state["members"]["u-bob"]["direct_permissions"]

    detail = client.get("/app/account/organization/members/u-bob")
    assert "user:read" in detail.text  # apparaît en "Permissions directes" ET "Permissions effectives"

    revoke = client.post("/app/account/organization/members/u-bob/permissions/revoke", data={"tenant_id": TENANT, "permission_name": "user:read"})
    assert revoke.status_code == 303
    assert "user:read" not in state["members"]["u-bob"]["direct_permissions"]


def test_member_detail_distinguishes_role_permissions_from_direct(client, state):
    """direct_permissions affichées = effectives - celles couvertes par un
    rôle (calculé côté routes.py, docs/auth.md) — une permission déjà
    apportée par un rôle ne doit pas réapparaître comme "directe"."""
    as_owner(client)
    client.post("/app/account/organization/roles", data={"tenant_id": TENANT, "name": "Support", "permissions": ["submissions:list"]})
    role_id = next(iter(state["roles"]))
    client.post("/app/account/organization/members/u-bob/roles/grant", data={"tenant_id": TENANT, "role_id": role_id})
    client.post("/app/account/organization/members/u-bob/permissions/grant", data={"tenant_id": TENANT, "permission_name": "submissions:list"})

    detail = client.get("/app/account/organization/members/u-bob")
    # la permission vient du rôle -> ne doit apparaître qu'une fois, dans
    # "Permissions effectives" — jamais une seconde fois dans "Permissions
    # directes" avec son propre bouton Retirer redondant (routes.py calcule
    # direct_permissions = effectives - celles couvertes par un rôle).
    assert detail.text.count("submissions:list") == 1
    assert "Aucune permission directe." in detail.text
    assert "Support" in detail.text  # le rôle qui apporte cette permission est bien listé


def test_owner_cannot_be_removed_via_ui_shows_no_remove_button(client):
    as_owner(client)
    detail = client.get("/app/account/organization/members/u-owner")
    assert detail.status_code == 200
    assert "Retirer de l'organisation" not in detail.text


# ── accès non autorisé ────────────────────────────────────────────────────────


def test_member_gets_api_error_when_reaching_owner_only_pages(client):
    """Le membre simple n'a pas les permissions "tenants:read" côté API
    fake (miroir du gate réel côté plugins/auth) — la page ne plante jamais,
    elle affiche l'erreur retournée par l'API."""
    as_member(client)
    r = client.get("/app/account/organization")
    assert r.status_code in (200, 403)
    assert "Réservé au propriétaire" in r.text or "403" in r.text


def test_anonymous_redirected_to_login(client):
    r = client.get("/app/account/organization")
    assert r.status_code == 303
    assert r.headers["location"].startswith("/app/account/login")


def test_organization_nav_and_commands_registered_when_permission_granted():
    """docs/shell.md — la contribution 'Organisation' n'apparaît dans la nav
    que pour un utilisateur qui porte la permission tenants:read."""
    from xweb.contrib import Contribution, NavRegistry

    r = NavRegistry()
    r.register(Contribution(id="account.org", plugin="account", label="Organisation", permission="tenants:read"))
    assert [c.id for c in r.list({"user"})] == []
    assert [c.id for c in r.list({"tenants:read"})] == ["account.org"]
