"""Phase 3 — même contrat que xui/context.py, vérifié sans xcore installé
(precedent réel : xui/tests/test_sans_xcore.py fait exactement ça)."""

from types import ModuleType
from typing import Any

import pytest

from xweb.context import XwebContext, XwebPermissionDenied, XwebRedirect


def fake_plugin_ctx(*, caller=None) -> Any:
    """Duck-typing, aucun PluginContext xcore requis — même fixture shape
    que req_ctx() dans xui/tests/test_sans_xcore.py."""

    class Ctx(ModuleType):
        pass

    ctx = Ctx("ctx")
    ctx.name = "demo"
    ctx.tenant_id = None
    ctx.caller = caller
    ctx.get_service = lambda name: f"service:{name}"
    return ctx


class FakeRequest:
    pass


def test_has_role_false_for_anonymous():
    ctx = XwebContext(plugin_ctx=fake_plugin_ctx(), request=FakeRequest(), user=None)
    assert ctx.has_role("crm.viewer") is False


def test_require_role_raises_for_anonymous():
    ctx = XwebContext(plugin_ctx=fake_plugin_ctx(), request=FakeRequest(), user=None)
    with pytest.raises(XwebPermissionDenied) as exc:
        ctx.require_role("crm.viewer")
    assert exc.value.required_roles == ("crm.viewer",)


def test_has_role_true_when_user_has_it_via_roles():
    user = {"roles": ["crm.viewer"], "permissions": []}
    ctx = XwebContext(plugin_ctx=fake_plugin_ctx(), request=FakeRequest(), user=user)
    assert ctx.has_role("crm.viewer") is True
    assert ctx.has_role("crm.editor") is False


def test_has_role_true_via_permissions_not_just_roles():
    user = {"roles": [], "permissions": ["crm.editor"]}
    ctx = XwebContext(plugin_ctx=fake_plugin_ctx(), request=FakeRequest(), user=user)
    assert ctx.has_role("crm.editor") is True


def test_require_role_accepts_any_of_several():
    user = {"roles": ["crm.viewer"], "permissions": []}
    ctx = XwebContext(plugin_ctx=fake_plugin_ctx(), request=FakeRequest(), user=user)
    ctx.require_role("crm.editor", "crm.viewer")  # doesn't raise — union match


def test_get_service_delegates_to_plugin_ctx():
    ctx = XwebContext(plugin_ctx=fake_plugin_ctx(), request=FakeRequest(), user=None)
    assert ctx.get_service("cache") == "service:cache"


def test_redirect_returns_xwebredirect():
    ctx = XwebContext(plugin_ctx=fake_plugin_ctx(), request=FakeRequest(), user=None)
    r = ctx.redirect("/plugins/crm/contacts")
    assert isinstance(r, XwebRedirect)
    assert r.path == "/plugins/crm/contacts"
    assert r.code == 303


async def test_call_plugin_raises_without_caller():
    ctx = XwebContext(plugin_ctx=fake_plugin_ctx(caller=None), request=FakeRequest(), user=None)
    with pytest.raises(RuntimeError, match="caller"):
        await ctx.call_plugin("crm_app", "list_contacts")


async def test_call_plugin_delegates_to_plugin_ctx_caller():
    calls = []

    async def fake_caller(plugin, action, payload, *, caller, tenant_id):
        calls.append((plugin, action, payload, caller, tenant_id))
        return {"ok": True}

    ctx = XwebContext(plugin_ctx=fake_plugin_ctx(caller=fake_caller), request=FakeRequest(), user=None)
    result = await ctx.call_plugin("crm_app", "list_contacts", {"q": "ada"})
    assert result == {"ok": True}
    assert calls == [("crm_app", "list_contacts", {"q": "ada"}, "demo", None)]
