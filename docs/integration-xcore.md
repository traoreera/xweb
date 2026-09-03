# Intégration xcore

> **Implémenté** — `xweb/engine/integration/xcore.py` (`XwebExtension`), `xweb/context.py`, `csrf.py`, `forms.py`, `mount.py`, `packages.py`, `security.py`, `urls.py`. 46 tests (`test_context.py`, `test_csrf.py`, `test_forms.py`, `test_mount.py`, `test_packages.py`, `test_security.py`, `test_urls.py`, `test_xcore_extension.py`), tous verts. Le contrat `BaseService` a été vérifié contre le vrai code source de xcore (`xcore/services/base.py`, `xcore/services/extensions/loader.py`, `xcore/services/container.py`), pas supposé.

xweb s'intègre à xcore comme une véritable **extension** (`BaseService`), pas comme un plugin — un service de rendu, pas une unité métier. Même position architecturale que `microframe` aujourd'hui.

## Sécurité — câblée dans `main.py`, pas juste construite

`CSRFMiddleware` et `SecurityHeadersMiddleware` existaient depuis Phase 3 (12 tests) mais n'avaient **jamais été ajoutés à l'app réelle** — trouvé en faisant le point sur ce qui restait. Le squelette n'avait aucune protection active. Corrigé, vérifié en direct sur le serveur qui tourne (en-têtes CSP présents, requête avec cookie de session + mauvais token rejetée en 403, sans cookie acceptée normalement).

**Trouvé au même moment** : `xcore.setup(app)` — qui enregistre `TraceContextMiddleware`/`TenantMiddleware` — n'avait jamais été appelé non plus, alors que `docs/integration-xcore.md` documentait déjà ce piège (middleware à poser avant que l'app serve, jamais dans `lifespan()`) sans que le code du squelette le respecte lui-même.

```python
# main.py — tout avant que l'app serve, jamais dans lifespan()
xcore.setup(app)
mount_builtin_assets(app)
app.add_middleware(SecurityHeadersMiddleware, report_only=True, exclude_paths=("/xweb-static",))
app.add_middleware(
    CSRFMiddleware,
    get_token=lambda: xcore.services.get("ext.xweb").csrf_token,  # callable — voir xweb/csrf.py
    protected_paths=("/plugins/",),
)
```

Le token vit sur `XwebExtension.csrf_token` (`secrets.token_urlsafe(32)`, généré une fois à la construction, stable sur tout le process — pas régénéré par requête, ce qui invaliderait un formulaire déjà affiché).

## Exigence de déploiement — `plugin_prefix`

Tous les exemples de ce corpus (`plugins.md`, `spec-v1.md`, `mount.py`) supposent des routes sous `/plugins/<nom>/...` (pluriel). Ce n'est **pas** le défaut réel de xcore — `app.plugin_prefix` vaut `/plugin` (singulier) par défaut (`xcore/configurations/sections.py:93`, vérifié contre le paquet installé, pas supposé). xweb ne cherche pas à imposer sa convention au kernel : tout projet qui l'utilise doit positionner explicitement dans `integration.yaml` —

```yaml
app:
  plugin_prefix: "/plugins"
```

Vérifié en conditions réelles sur le squelette (`~/devs/xcore-integration`), pas en théorie.

## Déclaration de l'extension

```yaml
# xcore.yaml — état final, après le basculement de *xweb Blueprint* §6
services:
  extensions:
    xweb:
      module: xweb.engine.integration.xcore:XwebExtension
      config:
        directory: templates          # shell.xml et layouts partagés
        namespaces:                   # un dossier de templates par plugin
          billing: plugins/billing/templates
          crm_app: plugins/crm_app/templates
        enable_cache: true
        cache_ttl: 300
# plus de bloc template_engine — microframe n'est plus une dépendance de xcore.yaml
```

Avant le basculement (pendant la Phase 6 de *xweb Blueprint* §7), ce bloc `xweb` n'existe qu'en environnement de dev/staging — jamais dans le `xcore.yaml` de production tant que la checklist de parité (`migration-guide.md`) n'est pas cochée en entier.

## Plusieurs plugins, un seul `shell.xml`

`directory` est le chemin de recherche partagé (`shell.xml`, voir `shell.md`). `namespaces` associe un préfixe à un dossier par plugin : `crm_app/contacts.xml` charge `plugins/crm_app/templates/contacts.xml` sans collision avec un autre plugin qui aurait aussi un `contacts.xml`. Chaque template de page fait `t-call="xweb.shell"` en s'y insérant via la région `content` — pas d'équivalent `{% extends %}`, l'inclusion QWeb est toujours explicite (`language.md#t-call`).

### Composants : partagés, jamais namespacés

`QwebRegistry` est un registre unique, process-global, indépendant des `namespaces` de pages ci-dessus — deux plugins qui déclarent chacun un `t-name="card"` non qualifié entrent en collision. D'où la convention de nommage qualifié (`language.md#t-name`) : `xweb.card` pour le cœur, `crm_app.contact_card` pour un composant propre à un plugin. Les composants vraiment partagés vivent dans `xweb/components/`, résolus sans risque de collision par tout plugin qui en fait `t-call`.

## Câblage de l'application

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from xcore import Xcore
from xweb.engine.integration.xcore import bind_engine, register_action_routes, mount_static

xcore = Xcore(config_path="xcore.yaml")
engine = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global engine
    await xcore.boot(app)
    engine = xcore.services.get("ext.xweb").engine
    bind_engine(xcore, engine)
    register_action_routes(app, xcore, engine, prefix="/_/a")
    mount_static(app, static_dir="static", url_prefix="/static")
    yield
    await xcore.shutdown()

app = FastAPI(lifespan=lifespan)
xcore.setup(app)   # middlewares AVANT que l'app serve — Starlette refuse d'en ajouter après
```

Même piège que documenté pour microframe : les extensions xcore sont initialisées **avant** que le Plugin Supervisor existe (services → registry → plugins). Le câblage htmx (`register_action_routes`) se fait donc séparément, après `await xcore.boot(app)`.

## Permissions (fail-closed)

xcore refuse tout appel de plugin par défaut — un `plugin.yaml` avec `permissions: []` bloque silencieusement tous ses appels (`{"status": "error", "code": "permission_denied"}`, jamais une exception qui remonterait bruyamment). Un plugin qui expose des routes htmx appelées depuis ses propres pages doit autoriser explicitement :

```yaml
# plugins/crm_app/plugin.yaml
permissions:
  - resource: "*"
    actions: ["execute"]
    effect: allow
```

## Cache

Le `CacheService` de xcore est async par nature. Le pont vers `QwebRegistry` reprend le même principe que `XCoreCacheBackend` dans microframe : pas de gymnastique `asyncio.run()` pour se faire passer pour un backend sync — un petit helper `_maybe_await` attend le résultat si c'est awaitable, le laisse passer sinon. La clé de cache inclut `PatchRegistry.version` (`inheritance.md`), pas seulement le nom de template et le contexte — sinon un nouveau `t-inherit` enregistré à chaud ne serait jamais reflété dans le rendu.

## Accès depuis un plugin

```python
from xcore.kernel.api.contract import TrustedBase

class MyPlugin(TrustedBase):
    async def handle(self, action: str, payload: dict) -> dict:
        engine = self.get_service("ext.xweb").engine
        html = await engine.render("crm_app.contacts_list", payload)
        return {"html": html}
```
