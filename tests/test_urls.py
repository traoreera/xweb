"""_names est un dict process-wide dans xweb/urls.py (même choix que
xui/urls.py) — chaque test utilise un nom de route unique pour ne pas
entrer en collision avec les autres tests du même run."""

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from xweb.engine.registry import QwebRegistry
from xweb.urls import PageRoute, mount_xweb_pages, path, reverse

TEMPLATE = '<template t-name="test.urlpage"><p>ok</p></template>'


class FakePluginCtx:
    name = "demo"
    tenant_id = None
    caller = None

    def get_service(self, name):
        return None


def test_path_builds_a_pageroute():
    route = path("/x", lambda ctx: {}, template="test.urlpage", name="test.x")
    assert isinstance(route, PageRoute)
    assert route.path == "/x"
    assert route.name == "test.x"


def test_mount_xweb_pages_mounts_each_route(monkeypatch):
    async def fake_resolve(request):
        return None

    monkeypatch.setattr("xweb.context.resolve_user_or_anonymous", fake_resolve)

    registry = QwebRegistry()
    registry.register_source(TEMPLATE)
    registry.register_source('<template t-name="xweb.shell"><body><t t-out="content"/></body></template>')

    urlpatterns = [path("/one", lambda ctx: {}, template="test.urlpage", name="test.mount_one")]
    app = FastAPI()
    router = APIRouter()
    mount_xweb_pages(router, FakePluginCtx(), registry, urlpatterns)
    app.include_router(router)

    assert TestClient(app).get("/one").status_code == 200


def test_reverse_resolves_a_named_route(monkeypatch):
    async def fake_resolve(request):
        return None

    monkeypatch.setattr("xweb.context.resolve_user_or_anonymous", fake_resolve)

    registry = QwebRegistry()
    registry.register_source(TEMPLATE)
    router = APIRouter()
    mount_xweb_pages(
        router, FakePluginCtx(), registry,
        [path("/two", lambda ctx: {}, template="test.urlpage", name="test.reverse_two")],
    )
    assert reverse("test.reverse_two") == "/two"


def test_reverse_unknown_name_raises():
    with pytest.raises(KeyError, match="aucune route nommée"):
        reverse("test.does_not_exist_xyz")


def test_duplicate_name_different_path_raises(monkeypatch):
    async def fake_resolve(request):
        return None

    monkeypatch.setattr("xweb.context.resolve_user_or_anonymous", fake_resolve)

    registry = QwebRegistry()
    registry.register_source(TEMPLATE)
    router = APIRouter()
    mount_xweb_pages(
        router, FakePluginCtx(), registry,
        [path("/dup1", lambda ctx: {}, template="test.urlpage", name="test.dup")],
    )
    with pytest.raises(ValueError, match="déjà utilisé"):
        mount_xweb_pages(
            router, FakePluginCtx(), registry,
            [path("/dup2", lambda ctx: {}, template="test.urlpage", name="test.dup")],
        )
