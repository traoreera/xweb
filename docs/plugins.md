# Intégrer xweb dans un plugin

!!! info "Voir aussi"
    Cette page reste la référence architecturale — pour un exemple complet, copiable, vérifié contre le moteur réel, voir [Votre première page](guide/first-page.md) dans le Guide.

## Structure

```
plugins/<name>/
├── plugin.yaml
├── src/
│   └── main.py
└── templates/
    ├── *.xml
    └── components/
```

## 1. Déclarer une page

```python
# plugins/crm_app/src/main.py
from fastapi import APIRouter
from xcore import TrustedBase

from xweb.context import XwebContext
from xweb.mount import mount_xweb_page


class Plugin(TrustedBase):
    def get_router(self) -> APIRouter:
        # résolu ici, pas en on_load() — même prudence que plugins/demo :
        # ext.xweb doit déjà être initialisé.
        engine = self.get_service("ext.xweb").engine
        router = APIRouter()

        async def contacts_view(ctx: XwebContext) -> dict:
            ctx.require_role("crm.viewer")   # lève XwebLoginRequired/XwebPermissionDenied
            return {"contacts": await list_contacts()}

        mount_xweb_page(
            router, self.ctx, engine, path="/contacts",
            template="crm_app.contacts_list", view=contacts_view, app_name="MonApp",
        )
        return router

    async def handle(self, action: str, payload: dict) -> dict:
        return {"status": "error", "msg": "unknown action"}
```

`mount_xweb_page` résout l'utilisateur, injecte le contexte de base (`csrf_token`, `nav_tree`, `plugin_prefix`, locale…), enveloppe la réponse dans `xweb.shell` par défaut, et répond page complète ou fragment (`<title>` + contenu) selon l'en-tête `HX-Request` d'une navigation boostée. `view` reçoit un `XwebContext` (`ctx.user`, `ctx.require_role(...)`, `ctx.require_user()`) et renvoie soit un `dict` de contexte de rendu, soit une `XwebRedirect` (`ctx.redirect("/ailleurs")`).

## 2. Mutation = route htmx explicite

Jamais de dispatcher générique. Chaque bouton qui mute quelque chose pointe vers une route déclarée par le plugin, sur le même routeur.

```xml
<!-- plugins/crm_app/templates/contacts_list.xml -->
<button hx-post="/plugins/crm_app/contacts" hx-target="#contacts" hx-swap="afterbegin"
        class="btn btn-primary">Ajouter</button>
<div id="contacts">
    <t t-foreach="contacts" t-as="c"><t t-call="crm_app.contact_row" t-att-contact="c"/></t>
</div>
```

```python
@router.post("/contacts")
async def create_contact(request: Request):
    user = await current_user(request)   # ou via XwebContext selon comment la route est câblée
    ...
    contact = await create(form_data)
    # fragment htmx, pas la page entière — le MÊME template sert le rendu
    # initial (via t-call ci-dessus) ET la mise à jour htmx.
    return HTMLResponse(engine.render("crm_app.contact_row", {"contact": contact}))
```

La route htmx retourne un **fragment**, jamais la page complète — `hx-swap` l'insère à l'endroit ciblé. Voir [Votre première page](guide/first-page.md) pour un exemple GET+POST complet, testé.

## 3. Contribuer au shell

```python
from xweb.contrib import Contribution, nav, commands

nav.register(Contribution(id="crm.contacts", plugin="crm_app", label="Contacts", path="/plugins/crm_app/contacts", permission="crm.viewer"))
commands.register(Contribution(id="crm.new_contact", plugin="crm_app", label="Nouveau contact", action_url="/plugins/crm_app/contacts", order=10))
```

À faire dans `on_load()` du plugin. Le nettoyage au unload/reload, lui, est centralisé dans `ext.xweb` (abonnement à `plugin.*.unloaded` sur l'event bus xcore via `bind_hot_reload`, voir [Démarrage rapide](guide/quickstart.md)) — un plugin n'a rien à faire lui-même pour ça. Détail des quatre registres (nav/ribbon/commands/status_bar), permissions d'affichage, badges : [Shell, nav et permissions](guide/shell-and-nav.md).

## 4. Étendre un plugin tiers

```xml
<!-- plugins/analytics_widget/templates/dashboard_patch.xml -->
<template t-name="analytics_widget.dashboard_widget" t-inherit="dashboard.index" t-inherit-mode="extension">
    <xpath expr="//div[@id='kpis']" position="after">
        <t t-call="analytics_widget.chart_card"/>
    </xpath>
</template>
```

Aucune coordination requise avec l'auteur de `dashboard` — voir [`inheritance.md`](inheritance.md) pour la résolution de priorité si plusieurs plugins patchent le même nœud.

## 5. Consommer l'API JSON d'un autre plugin

Contrat suivi par `plugins/account` en face de `plugins/auth` ([`plugins/account/src/api.py`](../plugins/account/src/api.py)) — la référence si un futur plugin doit faire la même chose en face d'un backend JSON-only. `plugins/auth`/`plugins/account` ont servi à valider que xweb tient la route en conditions réelles ; ce qui suit généralise le motif qui en est ressorti, pas un cas particulier à eux.

### Un seul client, un seul endroit qui connaît le format

```python
class MonApi:
    def __init__(self, base_url: str, *, prefix: str | None = None, client_ip: str | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.prefix = prefix or f"{plugin_prefix()}/mon_backend"
        self.client_ip = client_ip

    async def _call(self, method: str, path: str, *, json=None, token=None) -> dict:
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        if self.client_ip:
            headers["X-Forwarded-For"] = self.client_ip
        async with httpx.AsyncClient(base_url=self.base_url) as client:
            resp = await client.request(method, f"{self.prefix}{path}", json=json, headers=headers)
        if resp.status_code >= 400:
            raise MonApiError(resp.status_code, _extract_detail(resp))
        return resp.json()
```

`routes.py` appelle `api.login(...)`/`api.sessions(...)`, jamais `httpx` ni une URL en dur — une méthode par appel, comme `AuthApi`.

### Base URL et préfixe, jamais codés en dur

`base_url=str(request.base_url)` (le port réel n'est connu qu'à la requête) et `prefix=f"{plugin_prefix()}/<backend>"` (jamais `"/plugins/<backend>"` littéral) — voir [`xweb.paths.plugin_prefix()`](../CLAUDE.md). Un changement de préfixe de déploiement casserait ce client silencieusement sinon.

### Forwarder l'IP réelle du visiteur

```python
headers["X-Forwarded-For"] = self.client_ip  # request.client.host, pas l'IP du pont
```

Le backend rate-limite par IP (`plugins/auth/src/utils/rate_limit.py`) — sans ce header, chaque tentative de brute-force arrive avec l'IP du plugin qui relaie, jamais celle du visiteur, et le rate-limit protège tout le monde... contre un seul attaquant à la fois. À ne forwarder que si le backend fait explicitement confiance à `127.0.0.1` comme proxy (`utils/http.py`) — sinon n'importe quel visiteur usurpe l'IP qu'il veut via ce header.

### Cookies : un propriétaire par cookie, `path=` jamais large par défaut

| Cookie | `path=` | Qui le lit |
|---|---|---|
| jeton de session (`access_token`) | `/` | tous les plugins, via le backend d'auth du kernel |
| secret propre au pont (`refresh_token`) | `{plugin_prefix()}/<ce_plugin>` | ce plugin seul, jamais envoyé ailleurs |

Modèle : [`plugins/account/src/cookies.py`](../plugins/account/src/cookies.py). Un cookie posé sans `path=` explicite hérite de `/` — donc un secret que seul le pont doit relire (un refresh token, un état de connexion en plusieurs étapes) a besoin d'un `path=` restreint posé **explicitement**, sinon il part sur toutes les requêtes du navigateur vers n'importe quel autre plugin. Le réflexe par défaut n'est pas sûr ici.

### Garde-fous à la frontière, pas dispersés dans les routes

- **CSRF** : toute route mutative de ce plugin (pas du backend JSON lui-même) est protégée automatiquement dès qu'elle est montée sous `plugin_prefix()` et que la requête porte un cookie de session — `CSRFMiddleware` est câblé une fois pour tous les plugins dans `main.py`, rien à reconfigurer par plugin. Ce qui reste à charge : que chaque formulaire/appel htmx porte le jeton (`csrf_token` du contexte de rendu, injecté automatiquement par `mount_xweb_page`) — l'oublier fait échouer silencieusement toute mutation en 403, jamais une erreur explicite au démarrage.
- **Permissions** : `ctx.require_role(...)`/`ctx.require_user()` **avant** d'appeler le backend, jamais après — un appel qui échoue en 403 côté backend ne défait pas une action déjà déclenchée côté client.
- **Erreurs traduites une seule fois, à la frontière** : le client (`MonApiError`) porte `status_code`/`detail` bruts ; la traduction (dictionnaire `_FR`-style, si le backend répond en anglais et le projet en français) se fait dans le client, jamais recopiée dans chaque route qui l'appelle — voir `plugins/account/src/api.py::_FR`.

## RBAC unifié

```python
ctx.require_role("crm.editor")   # lève XwebPermissionDenied — jamais un 200 avec du HTML vide
```

Même `AuthPayload` que les routes API pures du kernel — pas de second système de rôles propre à xweb.

## Mode SPA — zéro dépendance xweb

```yaml
# plugin.yaml
ui:
  mode: spa
  dist_dir: ui/dist
```

Un plugin `mode: spa` n'importe jamais `xweb` — StaticFiles + fallback `index.html`. Aucun plugin de ce dépôt n'utilise ce mode aujourd'hui (`plugins/auth` est JSON pur sans templates du tout, `plugins/account`/`plugins/demo` sont `mode: xweb` par la présence de `templates/`) — section décrivant le contrat du manifeste xcore, pas un exemple vérifié ici.

## Checklist sécurité

- Toute route mutative (`hx-post`/`hx-put`/`hx-delete`) passe par `require_role`/vérification d'utilisateur avant d'agir, jamais après avoir déjà écrit en base.
- Aucun `t-out` sur une donnée qui vient directement d'un `t-att-*`/formulaire sans passer par un composant de confiance — `t-esc` par défaut, systématiquement.
- `permissions:` dans `plugin.yaml` déclaré explicitement pour toute route appelée en htmx ([`integration-xcore.md`](integration-xcore.md#permissions-fail-closed)) — sinon bloqué silencieusement par défaut (fail-closed, jamais une exception qui alerterait).
- Un plugin qui consomme l'API JSON d'un autre plugin suit le contrat de la [section 5](#5-consommer-lapi-json-dun-autre-plugin) : client unique, IP réelle forwardée, `path=` de cookie explicite et restreint pour tout secret propre au pont, permissions vérifiées avant l'appel, erreurs traduites une seule fois à la frontière.
