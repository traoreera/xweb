"""plugins/auth/src/utils/deeplink.py::is_allowed_redirect_target — le seul
garde-fou entre `?redirect=<n'importe quoi>` côté client et une redirection
finale d'OAuth callback qui porte un access_token/refresh_token fraîchement
émis (open-redirect avec exfiltration de jeton si mal gardé). Import direct
du module (aucune dépendance externe, pas besoin d'un fake plugins/auth
complet comme test_account_extended.py) — même mécanique de chargement
dynamique que load_account_pkg() ailleurs dans ce dossier.
"""

from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path

ROOT = Path(__file__).parent.parent
SRC = ROOT / "plugins" / "auth" / "src"


def load_deeplink():
    if "auth_ext_src" not in sys.modules:
        pkg = types.ModuleType("auth_ext_src")
        pkg.__path__ = [str(SRC)]
        sys.modules["auth_ext_src"] = pkg
        utils_pkg = types.ModuleType("auth_ext_src.utils")
        utils_pkg.__path__ = [str(SRC / "utils")]
        sys.modules["auth_ext_src.utils"] = utils_pkg
    return importlib.import_module("auth_ext_src.utils.deeplink")


def test_desktop_scheme_always_allowed_even_with_no_web_origins():
    dl = load_deeplink()
    assert dl.is_allowed_redirect_target("erp://oauth-callback", frozenset())


def test_https_origin_allowed_only_when_listed():
    dl = load_deeplink()
    origins = frozenset({"https://app.example.com"})
    assert dl.is_allowed_redirect_target("https://app.example.com/callback", origins)
    assert not dl.is_allowed_redirect_target("https://evil.com/callback", origins)


def test_https_rejected_when_web_origins_empty():
    dl = load_deeplink()
    assert not dl.is_allowed_redirect_target("https://app.example.com/callback", frozenset())


def test_plain_http_rejected_for_a_non_loopback_host():
    # Le coeur de la protection anti open-redirect : http en clair vers un
    # hôte arbitraire reste refusé même s'il apparaît dans web_origins par
    # erreur — seule la boucle locale bénéficie de l'exception http.
    dl = load_deeplink()
    origins = frozenset({"http://app.example.com"})
    assert not dl.is_allowed_redirect_target("http://app.example.com/callback", origins)


def test_loopback_http_allowed_when_explicitly_listed():
    # Régression : plugins/account (login via Google/GitHub, plus le flow de
    # liaison agenda/email) construit son redirect_uri depuis
    # request.base_url — http://localhost:8000 en dev local tant qu'il n'y a
    # pas de TLS. Avant ce correctif, TOUTE tentative de connexion OAuth
    # échouait avec "Provider Error" en local, même avec un provider
    # pleinement configuré (client_id/secret réels) — le blocage se
    # produisait avant même d'atteindre Google/GitHub.
    dl = load_deeplink()
    origins = frozenset({"http://localhost:8000"})
    assert dl.is_allowed_redirect_target("http://localhost:8000/app/account/oauth/callback", origins)
    assert dl.is_allowed_redirect_target("http://127.0.0.1:8000/app/account/oauth/callback", frozenset({"http://127.0.0.1:8000"}))


def test_loopback_http_still_rejected_when_not_listed():
    # La boucle locale n'est pas inconditionnelle comme erp:// — un
    # déploiement qui n'a jamais déclaré OAUTH_WEB_REDIRECT_ORIGINS reste
    # protégé par défaut, même en http+localhost.
    dl = load_deeplink()
    assert not dl.is_allowed_redirect_target("http://localhost:8000/callback", frozenset())


def test_malformed_target_rejected():
    dl = load_deeplink()
    assert not dl.is_allowed_redirect_target("not a url###", frozenset({"https://app.example.com"}))
