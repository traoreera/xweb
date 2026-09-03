"""CSRF pour les routes xweb cookie-authentifiées (docs/spec-v1.md).

Porté depuis xui/csrf.py — ce module ne dépend d'aucun moteur de rendu,
seulement d'un `get_token: Callable[[], str]` fourni par l'appelant (le
token vit sur XwebExtension.csrf_token, un secret de process stable —
voir engine/integration/xcore.py).

Seules les pages en cookie-auth ont besoin de ça : le navigateur rejoue
le cookie automatiquement sur une requête cross-site, donc une route de
mutation doit exiger en plus une valeur que la page de l'attaquant ne
peut pas lire (same-origin only). Une requête portant `Authorization:
Bearer …` n'est PAS cookie-authentifiée (XAuthBackend lit le header en
premier, plugins/auth/src/backend.py) — elle n'est jamais vérifiée ici,
même si un cookie traîne à côté.

`session_cookies` : les cookies dont la présence signale une session
navigateur. xui ne connaissait que "session" ; avec plugins/auth +
plugins/account (docs/auth.md) la session est portée par `access_token`
— main.py passe les deux. Sans ce réglage le middleware était
construit mais ne vérifiait jamais rien en pratique sur ce squelette
(trouvé en reconstruisant le flux d'auth, pas repéré avant).

Le token est accepté soit en champ de formulaire `csrf_token` (composant
xweb.csrf), soit en en-tête `X-CSRF-Token` (htmx : `hx-headers`) — un
appel JSON cookie-authentifié sans l'en-tête est refusé, c'est voulu.

Rejeu du body : `BaseHTTPMiddleware.call_next()` relance l'app interne
avec le `receive()` ASGI d'origine, pas l'objet Request du middleware —
une fois `await request.form()` appelé ici, le flux est consommé et la
route verrait un formulaire vide. On capture les bytes bruts puis on
remplace `request._receive` par une closure qui les rejoue, avant
`call_next` — pattern standard pour lire le body dans un
BaseHTTPMiddleware sans le voler à la route.
"""

from __future__ import annotations

import hmac
from typing import Callable, Sequence

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
CSRF_FIELD = "csrf_token"
CSRF_HEADER = "X-CSRF-Token"
_FORM_CONTENT_TYPES = ("application/x-www-form-urlencoded", "multipart/form-data")


class CSRFMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app,
        get_token: Callable[[], str],
        protected_paths: Sequence[str],
        session_cookies: Sequence[str] = ("session",),
    ) -> None:
        super().__init__(app)
        self._get_token = get_token
        self._paths = tuple(protected_paths)
        self._cookies = tuple(session_cookies)

    def _is_cookie_authenticated(self, request: Request) -> bool:
        if request.headers.get("authorization", "").startswith("Bearer "):
            return False
        return any(name in request.cookies for name in self._cookies)

    async def dispatch(self, request: Request, call_next):
        if (
            request.method in MUTATING_METHODS
            and request.url.path.startswith(self._paths)
            and self._is_cookie_authenticated(request)
        ):
            token = request.headers.get(CSRF_HEADER)
            if not token:
                body = await request.body()

                async def _replay() -> dict:
                    return {"type": "http.request", "body": body, "more_body": False}

                request._receive = _replay

                content_type = request.headers.get("content-type", "")
                if content_type.startswith(_FORM_CONTENT_TYPES):
                    form = await request.form()
                    value = form.get(CSRF_FIELD)
                    token = value if isinstance(value, str) else None

            expected = self._get_token()
            if not token or not expected or not hmac.compare_digest(token, expected):
                headers = {}
                if request.headers.get("HX-Request") == "true":
                    # Cas réel, pas théorique : csrf_token est stable pour tout
                    # le process (secrets.token_urlsafe généré une fois à la
                    # construction de XwebExtension, docs/csrf.py) — un onglet
                    # resté ouvert par-dessus un redémarrage serveur (xcli
                    # manager start --reload en dev, ou tout redéploiement) a un
                    # jeton périmé. Sans ce header, htmx swappe ce JSON brut tel
                    # quel dans #xweb-content (son comportement par défaut sur
                    # N'IMPORTE QUELLE réponse, y compris une erreur) — l'action
                    # semble juste ne rien faire, ou afficher du JSON, sans qu'il
                    # soit jamais évident qu'il suffit de recharger la page.
                    # HX-Refresh force htmx à faire un vrai window.location.reload()
                    # à la place : la page suivante embarque le csrf_token à jour.
                    headers["HX-Refresh"] = "true"
                return JSONResponse({"error": "csrf_invalid"}, status_code=403, headers=headers)
        return await call_next(request)
