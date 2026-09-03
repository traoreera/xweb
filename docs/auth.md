# Auth — `plugins/auth`, câblé et vérifié en vrai

> **Implémenté** — `plugins/auth` (fourni par l'utilisateur, plugin `trusted`
> enterprise complet : multi-tenant, RBAC, audit log, invitations, MFA TOTP,
> OAuth) est câblé comme vrai `AuthBackend` de xcore, à la place de
> l'`AnonymousAuthBackend` temporaire. `plugins/login` (nouveau, minimal)
> fournit le pont HTML qui manquait — `plugins/auth` est une API JSON pure,
> sans page de login. Vérifié par un vrai cycle navigateur complet, jar de
> cookies curl : formulaire → `POST /plugins/login/` → `/plugins/auth/login`
> en interne → JWT RS256 → cookie `access_token` → widget de compte du shell
> (`docs/shell.md`) affichant le vrai utilisateur DB — pas une simulation.

## Ce qu'il a fallu ajouter

`plugins/auth/src/main.py::on_load()` exige, sans filet, trois choses que le
squelette xweb ne fournissait pas :

```python
db = self.get_service("db")              # AsyncSQLAdapter — kernel, pas ext.*
cache = self.get_service("cache")         # CacheService — kernel, pas ext.*
email_ext = self.get_service("ext.email") # extension custom — n'existe pas dans xcore
```

(`ext.google` est protégé par un `try/except` dans le plugin — vraiment
optionnel. `db`/`cache`/`ext.email` ne le sont pas.)

### `db` / `cache` — services kernel, pas des extensions

Contrairement à `ext.xweb`, "db" et "cache" ne passent pas par
`services.extensions` — `xcore/services/container.py:46-51` (lu en vrai) :
`DatabaseServiceProvider` n'enregistre **rien** sous la clé `"db"` si
`services.databases` est vide, quelle que soit la config `cache`. `cache`,
lui, est gratuit — `CacheConfig()` par défaut (`backend: "memory"`) est
toujours instanciée donc toujours enregistrée, section `services.cache:`
explicite ou pas.

```yaml
# integration.yaml
services:
  databases:
    default:
      type: "sqlite+aio"                       # → AsyncSQLAdapter (xcore/services/database/manager.py)
      url: "sqlite+aiosqlite:///./xweb.db"
```

`type: "sqlite"` seul (sans `+aio`) route vers l'adaptateur **synchrone**
(`SQLAdapter`) — le plugin appelle `db.engine.begin()`/`db.session()` en
async, donc c'est `sqlite+aio` qui est exigé ici, pas juste `sqlite`.
`aiosqlite` doit être installé (`uv add aiosqlite` côté racine — le plugin
a son propre `pyproject.toml`/`uv.lock` séparé, mais un plugin `trusted`
s'exécute in-process dans le même interpréteur que `main.py` : ses imports
doivent être satisfaits par **le venv racine**, pas par son lockfile à lui).

### `ext.email` — n'existe pas dans xcore, écrit pour ce squelette

Recherché dans tout `xcore` installé : aucune extension email intégrée.
`plugins/auth/src/services/email/base.py` documente le contrat attendu :

```python
async def send(self, to: str, subject: str, body: str, is_html: bool = True) -> bool
def       queue(self, to: str, subject: str, body: str, is_html: bool = True) -> bool
```

`plugins/auth/.env` n'a aucun credential SMTP réel (`XAUTH_SMTP_USER`/
`PASSWORD` vides). Plutôt qu'exiger un vrai serveur SMTP pour faire booter
le squelette, `extensions/email.py::ConsoleEmailExtension` logue les emails
(inscription, reset mdp, invitations) au lieu de les envoyer — suffisant
pour vérifier le flux. **À remplacer par un vrai transport SMTP avant toute
mise en production.**

```yaml
services:
  extensions:
    email:
      module: extensions.email:ConsoleEmailExtension
      config: {}
```

### Clés JWT RS256

`plugins/auth/src/services/token.py::TokenService.__init__` fait
`Path(private_key_path).read_text()` — un chemin plat, sans génération
automatique. `.env` pointe vers `conf/private.pem`/`conf/public.pem`
("relatifs à la racine du projet" — donc `~/devs/xcore-integration/conf/`,
pas `plugins/auth/conf/`). Générées une fois avec `cryptography` :

```python
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
# → conf/private.pem (PKCS8, chmod 600) + conf/public.pem (SubjectPublicKeyInfo)
```

### Dépendances Python manquantes dans le venv racine

Le `pyproject.toml` du plugin ne déclare que `pydantic[email]` et
`python-jose` — très incomplet. Le vrai besoin, trouvé en grep-ant tous les
`import`/`from` de `plugins/auth/src` (imports lazy, à l'intérieur des
fonctions, donc invisibles tant qu'on ne lit pas le code — `passlib`/
`geoip2` en particulier ne cassent qu'à l'usage, pas au chargement) :
`cryptography`, `python-jose`, `passlib`, `argon2-cffi`, `bcrypt`, `pyotp`,
`qrcode`. Ajoutées côté racine (`uv add ...`) — `geoip2` reste non installé,
volontairement : lazy-importé dans `middleware/geoip.py`, jamais appelé par
le flux login/register/me testé ici.

### `main.py` — retrait de `AnonymousAuthBackend`

`plugins/auth/src/main.py::on_load()` appelle lui-même
`register_auth_backend(XAuthBackend(...))`. Garder l'`AnonymousAuthBackend`
posé plus tôt dans `main.py` n'aurait plus fait qu'attendre l'ordre de
chargement des plugins par hasard — silencieusement dangereux si `auth`
échoue à charger un jour (on se retrouverait anonyme partout au lieu d'un
503 "auth backend non disponible" explicite). Supprimé, pas juste
neutralisé.

## Vérifié en vrai — pas en test unitaire

```bash
# 1. login réel contre le vrai admin seedé (plugin.yaml → seed:)
curl -X POST http://127.0.0.1:8000/plugins/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"contact@xcorehub.dev","password":"Hunters123@"}'
# → {"access_token": "eyJhbGci...", "refresh_token": "...", ...}

# 2. le JWT en cookie access_token sur la page demo (docs/shell.md) —
#    XAuthBackend.extract_token (cookie), decode_token (JWT + JTI blacklist
#    cache + rôles/permissions RBAC réels en DB) tournent pour de vrai
curl http://127.0.0.1:8000/plugins/demo/ --cookie "access_token=$ACCESS"
# → widget de compte : avatar "C", "contact@xcorehub.dev", plus "Se connecter"

# anonyme (pas de cookie) → toujours "Se connecter", jamais planté
curl http://127.0.0.1:8000/plugins/demo/
```

Les deux cas (anonyme via `test_anonymous_sees_login_link_not_account_widget`,
authentifié via `test_authenticated_falls_back_to_sub_without_nested_user_dict`
— `tests/test_mount.py`) avaient déjà été écrits contre le contrat
`AuthPayload` réel avant que ce vrai backend n'existe ; ce vrai backend
produit exactement la forme `{"sub":..., "roles":[...], "permissions":[...],
"user": {"email":..., "tenant_id":...}}` anticipée — aucun changement de
`shell.xml` n'a été nécessaire.

134 tests toujours verts après câblage (`uv run pytest`).

## Deux vrais bugs trouvés dans `plugins/auth`

1. **`migrations/env.py:2`** — `from alembics import context` (faute de
   frappe, module inexistant). Corrigé en `from alembic import context`.
2. **`migrations/env.py:3`** — `from app.auth.src.models import Base` :
   chemin absolu d'un layout différent (`app/auth/...`) qui ne correspond à
   rien ici (`plugins/auth/...`) — `No module named 'app'` une fois (1)
   corrigé. **Non corrigé** — la bonne résolution dépend du layout de
   déploiement visé (celui-ci, ou un autre), pas devinée à l'aveugle.

Ni l'un ni l'autre n'empêche le plugin de fonctionner aujourd'hui : le
`_initialize_tables()` du plugin appelle d'abord `Base.metadata.create_all`
(qui a réellement créé les tables — confirmé dans les logs) *avant*
d'essayer les migrations Alembic, et l'échec de ces dernières est avalé
(`except Exception: logger.warning(...)`, jamais fatal). Ça mordra au
premier vrai changement de schéma en prod, où `create_all` ne suffit plus.

## `plugins/login` — le pont HTML, construit et vérifié en vrai

`plugins/auth` est une **API JSON pure** — 13 routers, tous
`POST`/`GET`/`PATCH` JSON (`/login`, `/register`, `/me`, `/account/email`,
`/mfa`, `/oauth`, …), aucun template, aucune route qui rend du HTML. Le
widget de compte du shell (`docs/shell.md`) a besoin d'un `login_path`
cliquable au sens navigateur (GET qui rend un formulaire, POST classique
qui le traite) — ce que `/plugins/auth/login` n'est pas (POST JSON
uniquement). Les indices dans le plugin lui-même (`OAUTH_WEB_REDIRECT_ORIGINS`,
deep-link `erp://` dans `utils/deeplink.py`) suggèrent qu'il a été pensé
pour un client externe (app desktop/SPA séparée), pas pour un `<a href>`
de navigateur.

`plugins/login` (nouveau, minimal) comble cet écart **sans réimplémenter
aucune logique d'auth** : il appelle `POST /plugins/auth/login` en HTTP
interne — via `request.base_url`, jamais d'URL en dur, le port réel n'est
connu qu'à la requête — exactement comme le ferait un client externe, puis
traduit sa réponse JSON `{access_token, refresh_token}` en cookie
`access_token` (`HttpOnly`, `SameSite=Lax`, `Secure` si HTTPS) — le seul
format que `XAuthBackend.extract_token` (chemin cookie) sait lire.

```
plugins/login/
  plugin.yaml              # trusted, comme demo
  src/main.py               # GET / (mount_xweb_page, use_shell=False)
                             # POST / (appelle /plugins/auth/login, pose le cookie, 303)
  templates/login.xml       # formulaire DaisyUI, xweb.alert pour les erreurs
```

`plugins/demo/src/main.py` pointe maintenant `login_path="/plugins/login/"`
au lieu du défaut `/login`.

~~Pas de refresh token géré~~ — implémenté depuis : `SilentRefreshRoute`
(`plugins/account/src/routes.py`) rafraîchit silencieusement un
access_token expiré, pour TOUTE route de ce plugin (GET comme POST), avant
même que la route ne s'exécute — voir la docstring de la classe pour le
détail (pourquoi un `route_class` plutôt qu'un vrai middleware ASGI : un
plugin ne peut pas en ajouter un lui-même). Testé dans
`tests/test_account_plugin.py` (rafraîchissement réussi, refresh_token mort
nettoyé, et le cas qui comptait vraiment : un POST — pas seulement un GET —
dont l'access_token vient d'expirer aboutit quand même, sans perdre les
données du formulaire).

### Vérifié en vrai — flux navigateur complet, jar de cookies curl

```bash
# 1. GET le formulaire, anonyme
curl -c jar.txt http://127.0.0.1:8000/plugins/login/
# → formulaire email/mot de passe rendu, PAS enveloppé dans le shell (use_shell=False)

# 2. POST les vrais identifiants seedés
curl -b jar.txt -c jar.txt -i -X POST http://127.0.0.1:8000/plugins/login/ \
  --data-urlencode "email=contact@xcorehub.dev" \
  --data-urlencode "password=Hunters123@" \
  --data-urlencode "next=/plugins/demo/"
# → 303 See Other, Location: /plugins/demo/
#   Set-Cookie: access_token=eyJhbGci...; HttpOnly; Path=/; SameSite=lax

# 3. GET la page demo avec CE jar — comme un vrai navigateur, aucun header manuel
curl -b jar.txt http://127.0.0.1:8000/plugins/demo/
# → widget de compte : avatar "C", "contact@xcorehub.dev", plus "Se connecter"

# 4. mauvais mot de passe → réaffiche le formulaire avec une erreur, ne plante jamais
curl -i -X POST http://127.0.0.1:8000/plugins/login/ \
  --data-urlencode "email=contact@xcorehub.dev" --data-urlencode "password=faux"
# → 401, .alert-error "Email ou mot de passe incorrect"
```

134 tests toujours verts après ajout de `plugins/login`.

### Bug trouvé en le construisant

`TrustedBase` exige `handle()` en méthode abstraite (pas documenté nulle
part avant de heurter `TypeError: Can't instantiate abstract class Plugin
without an implementation for abstract method 'handle'` au boot) — chaque
plugin trusted doit l'implémenter, même un stub, exactement comme
`plugins/demo` le fait déjà. `plugins/login` suit le même stub minimal.
