# Parler à un plugin JSON pur

`plugins/auth` est une API JSON pure (aucun template, aucun cookie) ; `plugins/account` est le pont HTML complet devant — connexion, MFA, organisations, sessions. Si votre plugin XML/HTML doit un jour s'appuyer sur un autre plugin qui n'expose que du JSON (interne ou tiers), reprenez ce même schéma plutôt que d'inventer autre chose — c'est le seul pattern déjà éprouvé dans ce dépôt pour ce cas précis.

## Le principe : un seul client, jamais d'URL en dur ailleurs

```python
# plugins/account/src/api.py — extrait réel
class AuthApi:
    def __init__(self, base_url: str, *, prefix: str | None = None, ...) -> None:
        self.base_url = base_url.rstrip("/")
        self.prefix = prefix if prefix is not None else f"{plugin_prefix()}/auth"
        ...

    async def _call(self, method: str, path: str, *, json=None, token=None, params=None) -> dict:
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        async with httpx.AsyncClient(base_url=self.base_url, timeout=self._timeout) as client:
            resp = await client.request(method, f"{self.prefix}{path}", json=json, params=params, headers=headers)
        if resp.status_code >= 400:
            raise AuthApiError(resp.status_code, _extract_detail(resp))
        return resp.json()

    async def me(self, token: str) -> dict:
        return await self._call("GET", "/me", token=token)
```

`routes.py` (le reste du plugin) n'appelle **jamais** `httpx` directement, ni ne construit une URL vers l'autre plugin à la main — une seule méthode par appel JSON, toutes dans `AuthApi`. Un changement de forme côté `plugins/auth` (un champ renommé, une route déplacée) se corrige à un seul endroit.

## Pourquoi `plugin_prefix()`, pas `"/plugins/auth"` en dur

`self.prefix` dérive de [`xweb.paths.plugin_prefix()`](../integration-xcore.md) plutôt qu'un littéral — `app.plugin_prefix` dans `integration.yaml` est un vrai réglage de déploiement (`/app`, `/plugins`, autre chose), et le plugin cible est monté dessous exactement comme le vôtre. Un préfixe codé en dur casse silencieusement dès que ce réglage change — pas une erreur au démarrage, juste des appels qui atterrissent en 404.

## Traduire l'erreur, jamais la laisser fuiter telle quelle

```python
_FR = {
    "Invalid credentials": "Email ou mot de passe incorrect.",
    "Account is inactive": "Ce compte est désactivé.",
}

class AuthApiError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
```

```python
try:
    data = await api_for(request).me(token_of(request) or "")
except AuthApiError as exc:
    return page(request, None, "account.login", login_ctx(request, error=exc.detail), status=_error_status(exc))
```

Le message anglais brut de l'API (souvent un détail d'implémentation) ne remonte jamais tel quel à l'écran — traduit via un dictionnaire fermé, avec un repli sur le texte original si la clé n'y est pas (jamais une `KeyError`).

## Cookies, pas de session côté serveur

`plugins/account` traduit chaque réponse JSON de `plugins/auth` en cookies `HttpOnly` (`access_token`, `refresh_token`) — il ne réimplémente **aucune** logique d'auth, seulement la traduction JSON ⇄ HTML/cookies. Le détail complet (refresh silencieux, portée des cookies, `?m=<clé>` pour les messages flash) : [`auth.md`](../auth.md).

## Étape intermédiaire ? Un cookie court-terme, pas une session serveur

Un flow en plusieurs étapes (MFA, choix d'organisation) garde son état dans un cookie `HttpOnly` chiffré côté client entre deux requêtes (`xweb_auth_pending`, `plugins/account/src/cookies.py`) — jamais une session stockée côté serveur pour un pont HTML qui, par ailleurs, n'a pas de base de données à lui.
