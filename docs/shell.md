# Le shell — layout persistant et registres de contribution

> **Implémenté** — `xweb/contrib.py`, `xweb/components/shell.xml`, câblé dans `xweb/mount.py` (chaque page est enveloppée par défaut, `use_shell=False` pour y échapper) et vérifié en vrai sur le squelette (`~/devs/xcore-integration`) : la nav affiche réellement l'entrée enregistrée par `plugins/demo/src/main.py::on_load()`. 13 tests (`test_contrib.py` + ajouts `test_mount.py`), plus `test_bind_hot_reload_cleans_up_on_real_xcore_event_bus` contre le vrai `EventBus` xcore installé.

## Widget de compte — bas du sidebar

`shell.xml` affiche, sous la nav, l'identité de l'utilisateur connecté (avatar-placeholder DaisyUI avec initiale + nom/email/`sub`) — basé sur le vrai contrat `AuthPayload` de xcore (`xcore/kernel/api/auth.py`), pas deviné : seul `sub` est garanti, `user` (le profil détaillé) est un dict optionnel de forme libre côté backend d'auth. Le widget dégrade sur `sub` si `user` est absent, ne plante jamais. **Rien ici en anonyme** — un lien "Se connecter" y vivait aussi jusqu'ici, en double avec celui de la topbar (`btn-primary`, en haut à droite) ; repéré comme redondant sur une capture d'écran réelle et retiré, pas juste caché (`tests/test_mount.py::test_anonymous_sees_login_link_not_account_widget` verrouille qu'il n'y en a plus qu'un seul dans toute la page). `account_path`/`login_path` configurables via `mount_xweb_page(..., account_path=..., login_path=...)`, propagés dans le contexte du shell. 5 tests contre le vrai `xweb/components/shell.xml`, pas un fixture minimal.

## Sidebar repliable (desktop) — `xweb.sidebar_toggle`

`#xweb-sidebar` peut se replier en rail d'icônes sur desktop (`lg+` — sur mobile c'est déjà un tiroir superposé, replier n'a pas de sens). Même mécanique que le thème (`xweb.theme_toggle`, `docs/theming.md`) : un attribut `data-sidebar` (`"expanded"`/`"collapsed"`) sur `<html>`, persisté en `localStorage`, relu par le **même** script anti-flash de `xweb.shell_head` (`xweb/components/layout.xml`) avant le tout premier rendu — sinon un flash de sidebar dépliée précéderait le repli, le temps que `_hyperscript` s'exécute.

Un seul `<script>` inline porte les deux préoccupations (thème + sidebar) plutôt que d'en ajouter un second : `XWEB_THEME_SCRIPT_HASH` (`xweb/security.py`) est le hash CSP de ce script exact, un de plus à maintenir sinon. Modifier ce script exige de régénérer ce hash — `test_security.py::test_theme_script_hash_matches_the_real_rendered_shell` casse sinon et donne la nouvelle valeur exacte dans son message d'échec.

`.sidebar-label` marque chaque texte à masquer en mode replié (titre de la sidebar, libellés de nav, badges, nom/email du widget de compte) — `[data-sidebar="collapsed"] .sidebar-label { display: none }` dans `assets/app.css`. `#xweb-sidebar` (id) l'emporte sur `.w-60` (classe Tailwind) par spécificité CSS normale, jamais besoin de `!important`. Bouton dans la topbar (`xweb.sidebar_toggle`, à côté du hamburger mobile), `hidden lg:inline-flex` — inutile de le montrer là où il n'a aucun effet. Pas de tooltips au survol des icônes en mode replié pour l'instant — laissé de côté, pas oublié.

## Navigation sans rechargement — `hx-boost`

Un `<a href>` classique dans la nav déclenche une vraie navigation navigateur (le `<head>`/scripts/nav entière se recharge) même si seul `#xweb-content` change. `shell.xml` pose `hx-boost="true" hx-target="#xweb-content"` sur `<body>` — htmx intercepte les clics sur les liens/formulaires descendants, envoie `HX-Request: true`, et `render_xweb_template` (xweb/mount.py) répond avec **juste** le contenu, jamais le shell, quand cet en-tête est présent. Un accès direct (F5, lien copié-collé, sans l'en-tête) reçoit toujours la page complète.

**Vérifié par un vrai clic dans jsdom, pas juste par le code source** — `scripts/verify-demo-page.mjs` pose un marqueur JS avant de cliquer sur le lien de nav réel ; s'il survit au clic, c'est qu'aucun vrai rechargement n'a eu lieu (un rechargement détruirait le contexte JS entier). Deux nouvelles limites de jsdom trouvées et patchées **dans le script de test seulement** en vérifiant : `CSS.escape()` (absent de jsdom, htmx s'en sert en phase de "settle") et `Element.scrollIntoView()` (jsdom n'a aucune mise en page — no-op correct, pas un contournement).

**Piège réel trouvé sur une capture d'écran, pas en lisant le code** : `hx-boost`/`hx-target="#xweb-content"` ne remplace QUE le contenu — la sidebar (`#xweb-sidebar`) n'est **jamais** renvoyée dans une réponse boostée (confirmé : `curl -H "HX-Request: true" .../components` ne contient aucun `id="xweb-sidebar"`). Sans rien de plus, `.menu-active` reste donc figé sur la page du dernier chargement **complet** — naviguer de "Démo" vers "Composants" via la sidebar laissait "Démo" allumé indéfiniment, les deux en même temps si la page suivante partageait aussi un préfixe d'URL (voir le piège `startswith()` juste en dessous). Corrigé côté client, jamais par un aller-retour serveur de plus : `#xweb-sidebar` porte son propre `_hyperscript` qui, après **chaque** règlement htmx (`htmx:afterSettle`, boosté ou non — l'événement bulle jusqu'à `body`), recalcule `.menu-active` sur chacun de ses liens en comparant leur `href` à `location.pathname` (déjà à jour : htmx gère l'historique du navigateur pour une navigation boostée). Vérifié à trois niveaux : mécanique pure en jsdom (plusieurs navigations d'affilée, `scripts/verify-hyperscript.mjs`), et un vrai clic sur le vrai lien contre le vrai serveur (`scripts/verify-demo-page.mjs`).

**Deuxième piège, dans le même repérage** : le highlight de la nav (`xweb.nav_items`, `xweb/components/shell.xml`) testait `current_path == node['path'] or current_path.startswith(node['path'])` — pensé pour garder un parent actif sur ses sous-pages, mais **aucun** `path` réellement enregistré (`nav.register(...)` dans `plugins/*/src/main.py`) n'est un vrai ancêtre d'un autre — ce sont tous des feuilles. Résultat : "Démo" (`/plugins/demo/`) s'allumait aussi sur "Kanban" (`/plugins/demo/kanban`), puisque ce dernier commence bien par le premier. Corrigé en égalité stricte — voir `tests/test_shell.py::test_nav_active_state_does_not_leak_to_sibling_pages_sharing_a_slash_prefix`.

xweb ne demande pas à chaque plugin de dessiner une page complète et isolée. Un layout persistant (`templates/shell.xml`) fournit quatre régions fixes ; les plugins y contribuent des éléments au chargement, à la manière des plugins Obsidian (`addRibbonIcon`, `addCommand`, `registerView`).

## Les quatre régions

```
┌──────┬─────────────┬──────────────────────────────────┐
│      │             │                                    │
│ribbon│   sidebar    │        contenu — vue active        │
│      │  (NavRegistry)│        du plugin (t-out="content") │
│      │             │                                    │
├──────┴─────────────┴──────────────────────────────────┤
│                    status bar                            │
└──────────────────────────────────────────────────────────┘
```

Plus une **palette de commandes** (`CommandRegistry`), en overlay, jamais une région fixe — ouverte à la demande, pas affichée en permanence.

## `ContributionRegistry` — la forme commune

Généralisation de `NavRegistry` (`xui/nav.py`), seul registre de ce type qui existe aujourd'hui.

```python
# xweb/contrib.py
@dataclass
class Contribution:
    id: str
    plugin: str
    order: int = 100
    permission: str | None = None

class ContributionRegistry:
    def register(self, item: Contribution) -> None: ...
    def unregister_plugin(self, plugin: str) -> None: ...   # appelé au hot-reload
    def list(self, user_roles: set[str] | None = None) -> list[Contribution]: ...

class NavRegistry(ContributionRegistry):
    """Seule différence avec la base : tree() au lieu de list(), pour la hiérarchie
    parent_id/children déjà présente dans xui/nav.py."""

class RibbonRegistry(ContributionRegistry): ...
class CommandRegistry(ContributionRegistry): ...
class StatusBarRegistry(ContributionRegistry): ...
```

Chaque registre est un singleton de module (même choix que `xui.nav.registry` aujourd'hui — voir `spec-v1.md` §3, aucun slot kernel dédié tant qu'une vraie extension n'est montée en amont).

### `permission=AUTHENTICATED` — visible dès qu'on est connecté

Repéré sur une capture d'écran réelle du shell : la section "Compte" (et ses sous-pages Mon compte/Sécurité/Sessions, `plugins/account/src/main.py`) s'affichait même pour un visiteur anonyme, alors que cliquer dessus ne fait jamais que rebondir vers `/login` — aucune de ces `Contribution` n'avait de `permission=`, donc rien ne les filtrait.

`AUTHENTICATED` (`xweb/contrib.py`) est une pseudo-permission — jamais un vrai nom de rôle qu'un plugin utiliserait lui-même — que `xweb/mount.py::_base_render_context()` injecte dans `user_roles` pour **tout** utilisateur connecté, peu importe ses rôles réels :

```python
user_roles = (set(user.get("roles", [])) | set(user.get("permissions", [])) | {AUTHENTICATED}) if user else set()
```

Poser `permission=AUTHENTICATED` sur une `Contribution` la cache donc pour un anonyme sans avoir besoin d'un champ à part — le même mécanisme de filtrage que `"audit:read"`/`"tenants:read"` (`ContributionRegistry.list()`), pas un système parallèle. Testé dans `tests/test_contrib.py` et `tests/test_mount.py` (injection réelle par `_base_render_context()`).

### `badge` — un indicateur à côté du label

`Contribution.badge: str | None` (`xweb/contrib.py`) ajoute un petit badge DaisyUI (`badge badge-sm badge-neutral`) à côté du label dans `xweb.nav_items` — même idée que la prop `badge` de `xweb.menu` (démo : `plugins/demo/templates/components.xml`).

**Statique, pas un compteur par utilisateur.** Posé une seule fois à `nav.register(...)` — `NavRegistry` est un singleton de module partagé par **toute** requête/utilisateur, jamais reconstruit par visiteur. S'en servir pour une valeur qui dépend du visiteur (des notifications non lues, par exemple) montrerait à tout le monde la valeur du dernier utilisateur qui l'aurait mise à jour, pas la sienne — ça exigerait un vrai mécanisme de résolution par requête, qui n'existe pas ici. Bon pour un tag fixe ("Bêta", une version…) — exemple concret : `demo.kanban` (`plugins/demo/src/main.py`) porte `badge="Nouveau"`.

## Un plugin contribue

```python
# plugins/crm_app/src/main.py, appelé au chargement du plugin
from xweb.contrib import RibbonRegistry, CommandRegistry, Contribution

RibbonRegistry.register(Contribution(id="crm_app.ribbon", plugin="crm_app", order=20))
CommandRegistry.register(Contribution(id="crm_app.new_contact", plugin="crm_app", order=10))
```

Et dans `plugin.yaml`, pour que le shell sache que ce plugin a des contributions à charger avant de rendre la première page :

```yaml
ui:
  contributes:
    nav: true
    ribbon: true
    commands: true
    status_bar: false
```

## `shell.xml` — composition, pas redéfinition

DaisyUI fournit déjà `drawer`, `menu`, `dropdown` — le shell les compose plutôt que de styler chaque région à la main.

```xml
<template t-name="xweb.shell">
<div class="drawer lg:drawer-open">
    <input id="shell-drawer" type="checkbox" class="drawer-toggle"/>
    <div class="drawer-content flex flex-col">
        <t t-call="xweb.status_bar"/>
        <main class="flex-1"><t t-out="content"/></main>
    </div>
    <div class="drawer-side">
        <ul class="menu bg-base-200 min-h-full w-64">
            <t t-foreach="nav_tree" t-as="node">
                <li><a t-att-href="node.path" t-esc="node.label"/></li>
            </t>
        </ul>
    </div>
</div>
</template>
```

Une page de plugin ne redéfinit jamais ce fichier — elle fournit juste le contenu de `content` en étant montée dedans (`mount.py`, voir *spec-v1.md* §4).

## Palette de commandes

Rendue côté serveur au chargement du shell (liste complète depuis `CommandRegistry.list()`), filtrée côté client — `_hyperscript` suffit pour une poignée de plugins (voir *xweb Blueprint* §2, question ouverte sur le passage à un filtrage serveur si le nombre de commandes grandit).

```xml
<div id="command-palette" class="modal" _="on keydown[key=='k' and ctrlKey] from window toggle .modal-open on me">
    <div class="modal-box">
        <input type="text" class="input input-bordered w-full"
               _="on input show <li/> in #cmd-list when its textContent.toLowerCase() contains my value.toLowerCase()"/>
        <ul id="cmd-list" class="menu">
            <t t-foreach="commands" t-as="cmd">
                <li t-att-hx-post="cmd.action_url"><a t-esc="cmd.label"/></li>
            </t>
        </ul>
    </div>
</div>
```

**Vérifié** — les deux extraits `_hyperscript` ci-dessus (raccourci clavier et filtrage) tournent tels quels contre le vrai `_hyperscript.min.js` (`scripts/verify-hyperscript.mjs`, `npm run verify:hyperscript`). Contrairement à l'exemple de `theming.md`, ceux-là étaient corrects du premier coup.
