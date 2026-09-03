"""plugins/auth/src/services/oauth.py::OAuthService.handle_callback —
régression sur OAuthCallbackFailed (trouvé en testant pour de vrai un
conflit "compte déjà lié à un autre utilisateur" en local : le callback
retombait sur un popup navigateur "ouvrir avec xdg-open" — le deep-link
desktop erp:// — plutôt qu'un message d'erreur lisible côté web, alors que
le `redirect` fourni par plugins/account était pourtant valide et déjà
connu au moment de l'échec).

Import direct du module de service (comme tests/test_oauth_deeplink.py
pour deeplink.py, étendu ici : services/oauth.py importe plusieurs paquets
frères via des imports relatifs — models/providers/repositories/utils —
tous enregistrés ci-dessous pour que ces `from ..xxx import yyy` résolvent).
"""

from __future__ import annotations

import importlib
import json
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
SRC = ROOT / "plugins" / "auth" / "src"


def load_oauth_service():
    if "auth_ext_src" in sys.modules:
        return importlib.import_module("auth_ext_src.services.oauth")

    pkg = types.ModuleType("auth_ext_src")
    pkg.__path__ = [str(SRC)]
    sys.modules["auth_ext_src"] = pkg

    for sub in ("models", "providers", "repositories", "services", "utils"):
        sub_pkg = types.ModuleType(f"auth_ext_src.{sub}")
        sub_pkg.__path__ = [str(SRC / sub)]
        sys.modules[f"auth_ext_src.{sub}"] = sub_pkg

    return importlib.import_module("auth_ext_src.services.oauth")


class FakeCache:
    """get/set/delete minimal — handle_callback ne lit/n'écrit rien d'autre
    sur le cache que le state OAuth avant de déléguer à _handle_callback_body."""

    def __init__(self, state_data: dict | None) -> None:
        self._value = json.dumps(state_data) if state_data is not None else None
        self.deleted = False

    async def get(self, key: str):
        return self._value

    async def delete(self, key: str):
        self.deleted = True


@pytest.fixture
def oauth_mod():
    return load_oauth_service()


@pytest.mark.asyncio
async def test_state_not_found_raises_plain_value_error_not_wrapped(oauth_mod):
    # Rien à récupérer : le state lui-même est introuvable/expiré — erp://
    # reste le seul repli possible, jamais un OAuthCallbackFailed (aucun
    # redirect n'a jamais été connu, cf. le commentaire de handle_callback).
    svc = oauth_mod.OAuthService(session=None, token_service=None, cache=FakeCache(None), providers={})
    with pytest.raises(ValueError) as exc_info:
        await svc.handle_callback("google", "code", "bad-state")
    assert not isinstance(exc_info.value, oauth_mod.OAuthCallbackFailed)


@pytest.mark.asyncio
async def test_failure_after_state_resolved_wraps_with_the_real_redirect(oauth_mod, monkeypatch):
    # Coeur de la régression : une fois state_data chargé (redirect connu),
    # toute exception du corps de la fonction doit ressortir en
    # OAuthCallbackFailed portant CE redirect — jamais un ValueError nu que
    # routes/oauth.py::callback() ne pourrait pas distinguer d'un state
    # introuvable, et qui retombait donc sur erp:// à tort.
    state_data = {
        "provider": "google", "tenant_id": None,
        "redirect": "http://localhost:8000/app/account/oauth/link/callback",
        "link_user_id": "u-admin", "app_state": "nonce-123",
    }
    svc = oauth_mod.OAuthService(session=None, token_service=None, cache=FakeCache(state_data), providers={})

    async def _boom(self, provider_name, code, data, ip_address=None):
        raise ValueError("Ce compte google est déjà lié à un autre utilisateur.")

    monkeypatch.setattr(oauth_mod.OAuthService, "_handle_callback_body", _boom)

    with pytest.raises(oauth_mod.OAuthCallbackFailed) as exc_info:
        await svc.handle_callback("google", "code", "good-state")
    assert exc_info.value.redirect == "http://localhost:8000/app/account/oauth/link/callback"
    assert exc_info.value.app_state == "nonce-123"
    assert "déjà lié" in str(exc_info.value)


@pytest.mark.asyncio
async def test_failure_with_no_redirect_in_state_carries_none(oauth_mod, monkeypatch):
    # Client desktop (aucun `redirect` fourni à /authorize) : exc.redirect
    # est None, routes/oauth.py::callback() retombe alors sur erp:// — pas
    # une régression, le comportement voulu pour ce cas précis.
    state_data = {"provider": "google", "tenant_id": None, "redirect": None, "link_user_id": None, "app_state": None}
    svc = oauth_mod.OAuthService(session=None, token_service=None, cache=FakeCache(state_data), providers={})

    async def _boom(self, provider_name, code, data, ip_address=None):
        raise ValueError("boom")

    monkeypatch.setattr(oauth_mod.OAuthService, "_handle_callback_body", _boom)

    with pytest.raises(oauth_mod.OAuthCallbackFailed) as exc_info:
        await svc.handle_callback("google", "code", "good-state")
    assert exc_info.value.redirect is None


@pytest.mark.asyncio
async def test_success_passes_through_unchanged(oauth_mod, monkeypatch):
    state_data = {"provider": "google", "tenant_id": None, "redirect": "http://localhost:8000/x", "link_user_id": None, "app_state": None}
    svc = oauth_mod.OAuthService(session=None, token_service=None, cache=FakeCache(state_data), providers={})

    async def _ok(self, provider_name, code, data, ip_address=None):
        return {"is_link": True, "provider": provider_name}

    monkeypatch.setattr(oauth_mod.OAuthService, "_handle_callback_body", _ok)

    result = await svc.handle_callback("google", "code", "good-state")
    assert result == {"is_link": True, "provider": "google"}
