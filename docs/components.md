# Composants — catalogue et état de migration

Liste reprise du catalogue réel de `xui/components/` (50 fichiers Jinja2/cotton portés depuis django-cotton-ui). **Migration terminée** — les 50 sont faits, sous leur propre nom `xweb.*` DaisyUI ; quelques-uns ont changé de nom en route (voir "Écarts de nommage" plus bas). Ce tableau reste le suivi historique de la Phase 5 de *xweb Blueprint* §7, remis à jour après un vrai audit fichier-par-fichier de `xweb/components/` (39 fichiers du catalogue original + les ajouts listés en bas de page) — la version précédente de ce document était restée figée à l'état "8 faits sur 26" pendant tout le reste de la migration, jamais recochée au fur et à mesure.

## Conteneurs & structure

| Composant | Origine (`xui/components/`) | Statut |
|---|---|---|
| `card` | `card.html` | **fait** — `xweb/components/card.xml`, 5 tests, compose un `xweb.button` réel |
| `field` | `field.html` | **fait** — `xweb/components/field.xml` |
| `description` | `description.html` | **fait** — `xweb/components/description.xml` |
| `error` | `error.html` | **fait** — `xweb/components/error.xml` (message d'erreur de champ) |
| `label` | `label.html` | **fait** — `xweb/components/label.xml`, 3 tests, compose un `xweb.badge` réel |

## Boutons & actions

| Composant | Origine | Statut |
|---|---|---|
| `button` | `button.html` | **fait** — `xweb/components/button.xml`, `tests/test_compiler.py` (7 tests) |
| `badge` | `badge.html` | **fait** — `xweb/components/badge.xml`, 4 tests |
| `spinner` | `spinner.html` | **fait** — `xweb/components/spinner.xml`, 2 tests |
| `progress` | `progress.html` | **fait** — `xweb/components/progress.xml` |

## Formulaire

| Composant | Origine | Statut |
|---|---|---|
| `form` | `form.html` | **fait** — `xweb/components/form.xml` (pose le CSRF automatiquement, voir `xweb.csrf`) |
| `input` | `input.html` | **fait** — `xweb/components/input.xml`, 3 tests |
| `textarea` | `textarea.html` | **fait** — `xweb/components/textarea.xml` |
| `checkbox` | `checkbox.html` | **fait** — `xweb/components/checkbox.xml`, 3 tests |
| `radio` | `radio.html` | **fait** — `xweb/components/radio.xml` |
| `switch` | `switch.html` | **fait, renommé `xweb.toggle`** — `xweb/components/toggle.xml` (nom DaisyUI natif) |
| `range` | `range.html` | **fait** — `xweb/components/range.xml` |
| `select`, `select_native`, `select_option` | `select*.html` | **fait, fusionnés en un seul composant** — `xweb/components/select.xml` (props `options`, pas trois composants séparés) |
| `combobox` | `combobox.html` | **fait** — `xweb/components/combobox.xml`. Filtrage `_hyperscript` (même idiome que `organization_roles.xml`), sélection via attribut `data-value` (jamais interpolé en dur dans le script — piège d'injection évité, voir la docstring du fichier). Vérifié dans `scripts/verify-hyperscript.mjs`, `tests/test_components_extra.py` |
| `datepicker`, `calendar` | `datepicker.html`, `calendar.html` | **fait** — `xweb/components/calendar.xml` + `datepicker.xml`, `xweb/calendar.py::month_grid()` (la grille est calculée côté Python — aucun builtin date dans les expressions QWeb). `xweb.calendar` envoie `calendar:select(iso:…)`, `xweb.datepicker` l'écoute — découplés, vérifiés ensemble dans `scripts/verify-hyperscript.mjs` |

## Avatar & identité

| Composant | Origine | Statut |
|---|---|---|
| `avatar`, `avatar_group` | `avatar*.html` | **fait** — `xweb/components/avatar.xml` + `avatar_group.xml` |
| `breadcrumbs`, `breadcrumb_item` | `breadcrumb*.html` | **fait, fusionnés** — `xweb/components/breadcrumbs.xml` (prop `items`, pas un `breadcrumb_item` séparé) |

## Disclosure — accordéon, tabs, collapse

| Composant | Origine | Statut |
|---|---|---|
| `accordion`, `accordion_item` | `accordion*.html` | **fait** — `xweb/components/accordion.xml`. Plusieurs `<details>` groupés par l'attribut `name` natif (exclusivité mutuelle sans JS, support navigateurs Baseline 2023) |
| `collapse` | `collapse.html` | **fait** — `xweb/components/collapse.xml`. `<details>`/`<summary>` natif + classes DaisyUI, zéro JS |
| `tabs`, `tab` | `tabs.html`, `tab.html` | **fait, fusionnés** — `xweb/components/tabs.xml` (prop `items`) |
| `table` | `table.html` | **fait** — `xweb/components/table.xml` |

## Overlays — dropdown, menu, dialog, popover

| Composant | Origine | Statut |
|---|---|---|
| `dropdown`, `dropdown_group`, `dropdown_item`, `dropdown_separator` | `dropdown*.html` | **fait, fusionnés** — `xweb/components/dropdown.xml` (`<li><a>` dans le slot, pas de sous-composants séparés) |
| `menu`, `menu_content`, `menu_group`, `menu_item`, `menu_search`, `menu_trigger` | `menu*.html` | **fait, fusionnés** — `xweb/components/menu.xml` (prop `items`) — base de la sidebar/palette, voir `shell.md` |
| `dialog`, `dialog_title`, `dialog_description` | `dialog*.html` | **fait, renommé `xweb.modal`** — `xweb/components/modal.xml` + `xweb.modal_trigger` séparé (même split déclencheur/contenu repris pour `xweb.drawer`/`drawer_toggle`). `<dialog>` natif comme prévu |
| `drawer` | `drawer.html` | **fait** — `xweb/components/drawer.xml` + `xweb.drawer_toggle`. Checkbox-driven (classe DaisyUI `drawer`), zéro JS |
| `popover`, `tooltip` | `popover.html`, `tooltip.html` | **fait** — `tooltip.xml` (survol simple, déjà fait) + `xweb/components/popover.xml` (contenu riche déclenché par clic, `_hyperscript`, ferme sur clic extérieur/Escape). Piège réel trouvé en écrivant popover : sans `then halt the event` sur le déclencheur, le clic d'ouverture est vu comme "elsewhere" par le panneau et le referme aussitôt — vérifié dans `scripts/verify-hyperscript.mjs` |
| `toast` | `toast.html` | **fait** — `xweb/components/toast.xml` |

## Système & natifs xweb

| Composant | Origine | Statut |
|---|---|---|
| `alert` | `alert.html` | **fait** — `xweb/components/alert.xml`, 3 tests. Bouton de fermeture en `_hyperscript` (`remove closest .alert`, pas de `x-show` Alpine), vérifié en vrai dans `scripts/verify-hyperscript.mjs` |
| `mode_toggle`, `mode_toggle_head` | `mode_toggle*.html` | **fait, renommé** — `xweb.theme_toggle` (`xweb/components/layout.xml`), voir `theming.md` |
| `theme` | `theme.html` | remplacé par le mécanisme `data-theme` (`theming.md`), pas de migration directe |
| `alpine` | `alpine.html` | supprimé — plus de runtime Alpine à charger |
| `xui.html`, `xuiscript.html`, `xuiboost.html` | — | résolu implicitement par le choix technique lui-même (`index.md`, pile technique) : htmx + `_hyperscript` remplacent ces trois fichiers, aucun composant `xweb.*` dédié n'était nécessaire |
| `icon` | — (n'existait pas dans `xui/components/`) | **fait** — `xweb/components/icon.xml`. SVG inline (Heroicons v2 outline), aucune police d'icônes à charger (CSP `default-src 'self'`) |

## Écarts de nommage avec le catalogue xui d'origine

Pour qui cherche un composant par son ancien nom xui et ne le trouve pas sous ce nom dans `xweb/components/` :

| Nom xui | Nom xweb |
|---|---|
| `switch` | `xweb.toggle` |
| `dialog` | `xweb.modal` (+ `xweb.modal_trigger`) |
| `mode_toggle` | `xweb.theme_toggle` |
| `select` / `select_native` / `select_option` | `xweb.select` (un seul composant, prop `options`) |
| `breadcrumbs` / `breadcrumb_item` | `xweb.breadcrumbs` (un seul composant, prop `items`) |
| `tabs` / `tab` | `xweb.tabs` (un seul composant, prop `items`) |
| `dropdown` / `dropdown_group` / `dropdown_item` / `dropdown_separator` | `xweb.dropdown` (slot `<li><a>`) |
| `menu` / `menu_content` / `menu_group` / `menu_item` / `menu_search` / `menu_trigger` | `xweb.menu` (un seul composant, prop `items`) |
| `accordion` / `accordion_item` | `xweb.accordion` (un seul composant, prop `items`) |

## Au-delà du catalogue xui

Composants ajoutés après coup, sans équivalent dans `xui/components/` d'origine — ne comptent pas dans les "50" ci-dessus.

| Composant | Statut |
|---|---|
| `kanban` | **fait** — `xweb/components/kanban.xml`. Glisser-déposer natif HTML5 (`draggable`, `_hyperscript` : `dragstart`/`dragover`/`drop`), pas de librairie externe (SortableJS irait à l'encontre du choix "aucun bundle JS", CLAUDE.md). Piège réel trouvé en l'écrivant : `move X to end of Y` ne parse pas avec la version vendorisée de `_hyperscript` (`move` seul n'accepte pas `to end of`) — `put X at end of Y` est l'équivalent qui marche et déplace vraiment le nœud (pas un clone). Mécanique vérifiée dans `scripts/verify-hyperscript.mjs`, exemple concret avec vraie persistance serveur dans `plugins/demo` (`/plugins/demo/kanban`, `tests/test_kanban.py`). |

## Conventions de migration

- **Feuilles avant composites** — un composant qui ne fait pas de `t-call` vers un autre composant se migre avant ceux qui en dépendent (*xweb Blueprint* Phase 5).
- **Classes DaisyUI d'abord, `t-attf-class` ensuite** — ne pas recréer les dictionnaires `variants`/`outlined_variants`/`size_classes` que `button.html` portait à la main dans xui ; DaisyUI les fournit déjà (voir `language.md`).
- **`t-esc` par défaut** — un composant qui reçoit du texte utilisateur (`label`, `title`) l'échappe toujours ; seul un `slot` qui contient du HTML de confiance (rendu par un autre composant xweb) justifie `t-out`.
- **Zéro JS quand le natif suffit** — `<details>`/`<summary>` (`collapse`, `accordion`), `<dialog>` (`modal`), une checkbox cachée (`drawer`) : préférer le mécanisme HTML natif à `_hyperscript` chaque fois qu'il existe, `_hyperscript` seulement pour ce que le natif ne couvre pas (glisser-déposer, filtrage local, ouverture/fermeture avec logique conditionnelle comme `popover`).
