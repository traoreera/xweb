# xweb — Spécification technique v1

*Décision actée : `ext.template_engine` (microframe) n'est pas conservé en parallèle de `ext.xweb`. Le basculement est unique, après validation complète de la checklist de parité ([`migration-guide.md`](migration-guide.md)) — pas de bascule progressive plugin par plugin en production.*

---

## 0. Principes fondateurs

1. **xweb est un SDK de plugin, jamais du kernel.** Rien dans `xcore/kernel/` ne doit connaître xweb. Le kernel expose des contrats génériques (router, auth, permissions, events) ; xweb les consomme comme n'importe quel framework externe le ferait.
2. **Le serveur est la seule source de vérité pour la sécurité.** Aucune décision d'affichage côté client (rôle, permission, tenant) ne remplace jamais la vérification serveur. `t-if` peut cacher un bouton dans le HTML rendu ; ça ne protège jamais la route derrière.
3. **Un seul système d'auth, deux façades.** `AuthBackend` / `RBACChecker` / `get_current_user` du kernel servent à la fois les routes API pures et les pages xweb. Pas de logique RBAC dupliquée dans `UIContext`.
4. **Compatible par construction avec tout frontend externe.** Un plugin `mode: spa` (React/Vue/Svelte) doit fonctionner sans importer un seul module `xweb`.
5. **Chaque appel réseau est explicite, tracé, passe par le pipeline de sécurité complet.** htmx ne dispense d'aucun maillon (`PermissionMiddleware`, `RateLimitMiddleware`, `CSRFMiddleware`) — une requête `hx-post` est une requête HTTP comme une autre pour le kernel.
6. **Un seul moteur de templates, jamais deux en production.** xweb ne parle jamais Jinja2 en interne. Le basculement depuis microframe/xui est un événement unique après parité prouvée, pas une cohabitation permanente — voir principe 1 de *xweb Blueprint* §0.
7. **L'extension d'un template est toujours non-destructive.** Un plugin qui veut modifier une page ou un composant qu'il ne possède pas écrit un `t-inherit`, jamais une copie du fichier original. C'est la raison d'être de xweb — voir [`inheritance.md`](inheritance.md).

---

## 1. Architecture globale

```
Browser
   │  HTTP (form POST / hx-get / hx-post) — 1 requête = 1 action
   ▼
FastAPI app (xcore)
   │
   ├── Router système (kernel/api/router.py)
   ├── Router par plugin (get_router())
   │        │
   │        ├── mode=xweb  → pages server-rendues (QwebRegistry)
   │        ├── mode=spa   → StaticFiles + fallback index.html
   │        └── mode=hybrid → mix, routes déclarées explicitement
   │
   └── PluginSupervisor.call() → pipeline middlewares → plugin.handle()
```

Aucune couche de transport entre le navigateur et `PluginSupervisor.call()`. Une interaction htmx (`hx-post="/plugins/crm_app/contacts"`) est un `POST` ordinaire vers une route déclarée par le plugin — jamais un dispatcher générique par-dessus.

---

## 2. Packaging — structure d'un plugin avec UI xweb

```
plugins/<name>/
├── plugin.yaml
├── src/
│   └── main.py              # Plugin(TrustedBase), get_router(), enregistrement des contributions (shell.md)
└── templates/
    ├── *.xml                 # si mode=xweb
    └── components/           # composants xweb propres au plugin, exportables (packages.py)
```

### 2.1 Extension du manifeste

```yaml
# plugin.yaml
ui:
  mode: xweb              # xweb | spa | hybrid | none
  mount_path: null        # override du /plugins/<name>/ par défaut
  package_id: null        # ex. com.xcore.crm — requis si ce plugin exporte des composants
  exports: []              # noms de templates t-name exportés sous ce package_id
  packages: []              # package_id externes dont ce plugin dépend
  contributes:              # voir shell.md — nav/ribbon/commands/status_bar
    nav: true
    ribbon: false
    commands: true
```

---

## 3. Kernel — ajouts nécessaires

| Ajout | Nature | Généralise |
|---|---|---|
| `ContributionRegistry` + 4 registres typés | nouveau module | `NavRegistry` de xui, seul à exister aujourd'hui |
| `QwebRegistry` | nouveau module | `ComponentRegistry` de microframe (flat, sans héritage) |
| `PatchResolver` (XPath) | nouveau module | rien d'équivalent aujourd'hui |
| `CSRFMiddleware` | porté depuis `xui/csrf.py` | inchangé sur le fond |
| Validation anti-collision `mount_path` | porté depuis xui | inchangé |
| `unregister_plugin()` sur chaque `ContributionRegistry` | porté/généralisé | `NavRegistry.unregister_plugin()` |

**Hook de nettoyage — résolu et implémenté.** `PluginSupervisor.unload()` émet `plugin.{name}.unloaded` sur l'event bus après `_loader.unload()` (`xcore/kernel/runtime/supervisor.py:323-327`) ; `EventBus.subscribe()` accepte les wildcards via `fnmatch` (`xcore/kernel/events/bus.py`). Le nom du plugin vient d'`event.name` (payload de l'event toujours vide, `Event.data == {}` — vérifié dans `EventBus.emit()`).

**Correction par rapport à une version précédente de ce document** — `ext.xweb` ne peut PAS s'abonner lui-même dans son propre `init()` : `ExtensionLoader._load()` instancie une extension avec seulement `config`, jamais le `KernelContext`/`EventBus` (`xcore/services/extensions/loader.py`, vérifié en essayant, pas supposé). Le vrai point de câblage est **après `xcore.boot(app)`, côté app** — même endroit que `bind_engine()` pour microframe :

```python
# xweb/engine/integration/xcore.py::bind_hot_reload — appelé depuis main.py
await xcore.boot(app)
bind_hot_reload(xcore, xcore.services.get("ext.xweb"))
```

`bind_hot_reload()` nettoie `QwebRegistry` (templates de base **et** patches d'un plugin déchargé — `QwebRegistry.unregister_plugin()`, trouvé manquant en implémentant ceci : seuls les patches traçaient leur `source_plugin`, pas les templates de base) et les 4 `ContributionRegistry`. Testé contre le vrai `EventBus` xcore installé (`test_bind_hot_reload_cleans_up_on_real_xcore_event_bus`), pas un mock.

Centralisé dans `ext.xweb`, pas délégué à chaque auteur de plugin — contrairement à ce que `xui/nav.py` demandait jusqu'ici (« chaque plugin doit le faire lui-même dans son `on_unload()` »).

Aucun autre changement kernel requis — le reste (moteur, composants, rendu) vit entièrement dans `xweb/`.

---

## 4. `XwebContext` — contexte injecté à chaque page

```python
# xweb/context.py
@dataclass
class XwebContext:
    plugin_ctx: PluginContext
    request: Request
    user: AuthPayload | None

    def get_service(self, name: str) -> Any: ...
    def require_role(self, *roles: str) -> None: ...   # lève XwebPermissionDenied, jamais un 200 avec du HTML vide
```

Même contrat que `UIContext` dans xui — renommé pour cohérence de nommage, comportement inchangé.

---

## 5. Hors scope v1

Explicitement non traité par cette spécification au départ — voir *xweb Blueprint* §9 pour le détail. **Les quatre points ci-dessous sont maintenant tous implémentés** (barrés, liens vers leur doc) ; conservé pour l'historique plutôt que supprimé — même politique que le reste de ce corpus (docs/index.md : "là où une décision reste ouverte, c'est noté explicitement", et symétriquement, une fois refermée, ça se voit aussi). `t-inherit-mode="primary"` (duplication complète, `xweb/engine/inherit.py`) n'était même pas listé ici — jamais formellement "hors scope v1", juste non implémenté jusqu'à ce qu'un besoin réel le justifie (CLAUDE.md) — désormais fait aussi, voir [`inheritance.md#primary`](inheritance.md#primary).

- ~~i18n / traduction des templates~~ — implémenté, voir [`i18n.md`](i18n.md) (`t-tr`, `_()`, `xweb.i18n.Catalog`).
- ~~Génération PDF via le même moteur~~ — implémenté, voir [`pdf.md`](pdf.md) (`xweb/pdf.py::render_pdf()`).
- ~~Génération email via le même moteur~~ — implémenté, voir [`email.md`](email.md) (`xweb/email.py::render_email()`, `xweb.email_layout`). Ne remplace pas le système Jinja2 déjà en production dans `plugins/auth` (plugin séparé, auto-contenu) — comble la capacité pour tout le reste (`plugins/demo` en fait la preuve concrète).
- ~~Contexte multi-tenant intégré au rendu~~ — implémenté : `xweb/mount.py::_base_render_context()` relaie `request.state.tenant_id` (posé par le vrai `xcore.kernel.tenancy.middleware.TenantMiddleware`, câblé au niveau module dans `main.py`) dans `ctx["tenant_id"]`, disponible dans tout template sans qu'une vue ait à le refaire à la main. `xweb` ne fait que relayer la décision déjà prise par xcore, jamais ne la fabrique lui-même — `None` seulement si ce middleware n'a jamais tourné. Testé dans `tests/test_mount.py`.
