"""Cookies de session — pose stricte par défaut, dérogation explicite si besoin.

Généralise `plugins/account/src/cookies.py` (le pont HTML d'auth, disparu
avec `plugins/`) dans le SDK xweb : tout futur plugin de session/auth
reparte sur cette base plutôt que de re-régler `HttpOnly`/`Secure`/
`SameSite`/`path=` un par un, avec le risque d'en oublier un en cours de
route. Voir `docs/plugins.md#5-consommer-lapi-json-dun-autre-plugin` pour
le contrat plus large (IP forwardée, erreurs traduites…) dans lequel ce
module ne couvre que la partie cookies.

Posture : `HttpOnly` toujours vrai — aucun paramètre pour le désactiver,
un cookie lisible en JS n'a pas sa place dans ce module. `Secure` suit le
schéma réel de la requête (jamais forcé à True inconditionnellement : un
déploiement de dev en `http://localhost` — cas documenté et supporté,
voir CLAUDE.md, note OAuth — doit pouvoir poser des cookies quand même,
sinon le navigateur les jette silencieusement, sans la moindre erreur
visible). `SameSite` et le préfixe `__Host-`/`__Secure-` se choisissent
par rôle de cookie, jamais un seul réglage générique pour tout :

- Cookie de session lu par d'autres plugins (ex. jeton d'accès) : `path="/"`,
  `same_site="lax"` — DOIT survivre une navigation externe de haut niveau
  (lien cliqué depuis un email, un signet) sinon l'utilisateur perd sa
  session à chaque clic entrant. `SameSite=Strict` ici casserait un usage
  légitime, pas juste un vecteur d'attaque.
- Secret propre à UN plugin (ex. jeton de rafraîchissement), jamais
  renvoyé ailleurs : `path=` restreint au plugin, `same_site="strict"` —
  n'a jamais besoin de survivre une navigation externe, seulement des
  soumissions same-site internes au plugin.
- État intermédiaire multi-étapes (ex. défi MFA, sélection d'organisation) :
  même posture que le secret propre à un plugin — voir `PendingState`
  plus bas.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import dataclass
from typing import Any, Literal

from starlette.requests import Request
from starlette.responses import Response

SameSite = Literal["strict", "lax"]


def is_https(request: Request) -> bool:
    """Secure suit le schéma réel de la requête — voir la docstring du
    module pour pourquoi ce n'est délibérément pas forcé à True."""
    return request.url.scheme == "https"


def _prefixed_name(name: str, *, path: str, secure: bool) -> str:
    """`__Host-`/`__Secure-` (RFC 6265bis) : des garanties FORCÉES par le
    navigateur lui-même — pas juste des attributs qu'un bug pourrait un
    jour oublier de poser. `__Host-` (exige `path=/`, interdit `Domain`)
    est strictement plus fort que `__Secure-` (n'importe quel `path`) —
    utilisé automatiquement quand `path="/"` le permet.

    Ne s'applique QUE si `secure=True` : un navigateur REFUSE d'enregistrer
    un cookie `__Host-*`/`__Secure-*` posé sans `Secure` — ce n'est pas un
    cookie moins protégé, c'est un cookie qui ne sera jamais posé du tout.
    En dev `http://localhost`, préfixer inconditionnellement casserait la
    connexion entière (personne ne resterait connecté) au lieu de juste la
    rendre moins stricte — d'où la dépendance à `secure`, jamais un
    préfixe en dur dans un appelant."""
    if not secure:
        return name
    return f"__Host-{name}" if path == "/" else f"__Secure-{name}"


def set_strict_cookie(
    response: Response,
    request: Request,
    name: str,
    value: str,
    *,
    path: str = "/",
    same_site: SameSite = "strict",
    max_age: int | None = None,
) -> None:
    """Pose un cookie avec la posture la plus stricte possible pour son
    `path`/`same_site` — `HttpOnly` et le préfixe `__Host-`/`__Secure-`
    (si `Secure`) ne sont pas des paramètres, ils s'appliquent toujours.

    `same_site="strict"` par défaut — un appelant qui a besoin de "lax"
    (cookie qui doit survivre une navigation externe de haut niveau, voir
    docstring du module) le demande explicitement, jamais l'inverse : le
    défaut d'un module de sécurité doit être le plus restrictif, pas le
    plus pratique.
    """
    secure = is_https(request)
    response.set_cookie(
        _prefixed_name(name, path=path, secure=secure),
        value,
        httponly=True,
        secure=secure,
        samesite=same_site,
        path=path,
        max_age=max_age,
    )


def clear_strict_cookie(response: Response, request: Request, name: str, *, path: str = "/") -> None:
    """Supprime un cookie posé par `set_strict_cookie` — le nom effectif
    (préfixé ou non) doit correspondre exactement à celui posé, calculé de
    la même façon (`is_https(request)` au moment de l'appel), sinon le
    navigateur ignore silencieusement la suppression (nom inconnu)."""
    response.delete_cookie(_prefixed_name(name, path=path, secure=is_https(request)), path=path)


def read_strict_cookie(request: Request, name: str, *, path: str = "/") -> str | None:
    """Relit un cookie posé par `set_strict_cookie`. Essaie d'abord le nom
    attendu pour le schéma de CETTE requête (cas normal — écriture et
    lecture sur le même déploiement, donc le même schéma), puis retombe
    sur le nom non préfixé (bascule http/https en cours de vie d'un
    déploiement, ou dev local ponctuellement testé sans TLS) plutôt que de
    traiter l'utilisateur comme anonyme sans raison."""
    secure = is_https(request)
    expected = _prefixed_name(name, path=path, secure=secure)
    if expected in request.cookies:
        return request.cookies.get(expected)
    return request.cookies.get(name)


# ── État intermédiaire multi-étapes (défi MFA, sélection d'organisation…) ──


@dataclass(frozen=True)
class PendingState:
    """Codec JSON base64url pour un état intermédiaire porté en cookie —
    généralise `xweb_auth_pending` (plugins/account, disparu). Signature
    HMAC optionnelle : `secret=None` (défaut) reproduit le raisonnement
    d'origine — un payload qui ne contient que des secrets déjà opaques et
    vérifiés server-side à la relecture (un `mfa_token`, un refresh token
    en attente) n'a rien à gagner d'une signature, son porteur ne peut de
    toute façon rien forger de valide en le modifiant. `secret=<clé>`
    active HMAC-SHA256 — À FOURNIR dès que le payload porte un champ
    identifiant non opaque que le serveur utilise SANS le revalider à la
    relecture (ex. un tenant_id agi tel quel plutôt que re-vérifié contre
    les memberships de l'utilisateur) : sans signature, son porteur peut
    le modifier lui-même avant de le renvoyer.
    """

    secret: str | None = None

    def _sign(self, raw: bytes) -> bytes:
        if not self.secret:
            return raw
        mac = hmac.new(self.secret.encode("utf-8"), raw, hashlib.sha256).digest()
        return base64.urlsafe_b64encode(mac).rstrip(b"=") + b"." + raw

    def _unsign(self, blob: bytes) -> bytes | None:
        if not self.secret:
            return blob
        try:
            mac_part, raw = blob.split(b".", 1)
        except ValueError:
            return None
        expected = base64.urlsafe_b64encode(
            hmac.new(self.secret.encode("utf-8"), raw, hashlib.sha256).digest()
        ).rstrip(b"=")
        if not hmac.compare_digest(mac_part, expected):
            return None
        return raw

    def encode(self, data: dict[str, Any]) -> str:
        raw = json.dumps(data, separators=(",", ":")).encode("utf-8")
        signed = self._sign(raw)
        return base64.urlsafe_b64encode(signed).decode("ascii").rstrip("=")

    def decode(self, raw_cookie: str) -> dict[str, Any] | None:
        try:
            padded = raw_cookie + "=" * (-len(raw_cookie) % 4)
            blob = base64.urlsafe_b64decode(padded.encode("ascii"))
        except (ValueError, UnicodeDecodeError):
            return None
        unsigned = self._unsign(blob)
        if unsigned is None:
            return None
        try:
            data = json.loads(unsigned.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return None
        return data if isinstance(data, dict) else None


def set_pending_state(
    response: Response,
    request: Request,
    name: str,
    data: dict[str, Any],
    *,
    path: str,
    max_age: int,
    secret: str | None = None,
) -> None:
    """Pose un état intermédiaire — toujours `same_site="strict"` (jamais
    un paramètre : ce cookie ne doit jamais survivre une navigation
    externe, le flux qui le lit reste same-site du début à la fin)."""
    encoded = PendingState(secret=secret).encode(data)
    set_strict_cookie(response, request, name, encoded, path=path, same_site="strict", max_age=max_age)


def read_pending_state(request: Request, name: str, *, path: str = "/", secret: str | None = None) -> dict[str, Any] | None:
    raw = read_strict_cookie(request, name, path=path)
    if not raw:
        return None
    return PendingState(secret=secret).decode(raw)


def clear_pending_state(response: Response, request: Request, name: str, *, path: str) -> None:
    clear_strict_cookie(response, request, name, path=path)
