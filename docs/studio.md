# Studio — éditeur visuel de templates QWeb

Statut : **spec v2 ; la Component Metadata Layer (§2) et les métadonnées du
Layout Manager (§10) sont écrites, tout le reste n'est pas implémenté**.
Ce document fixe l'architecture avant tout code ; la seule dette technique
qu'il fallait lever en premier était la
[Component Metadata Layer](#2-component-metadata-layer--prérequis-non-négociable)
(§2) — sans elle, aucun `Inspector` n'est possible. Fait :

- [`studio/xweb/components/`](../studio/xweb/components/) — 88 fichiers, un par
  `t-name` réel sous `xweb/components/`, et son
  [README](../studio/xweb/components/README.md) pour le schéma exact —
  légèrement étendu par rapport à l'exemple ci-dessous
  (`category`/`palette`/`context_contract`).
- [`studio/xweb/layouts/`](../studio/xweb/layouts/) — 6 fichiers, un par option
  réelle du Layout Manager (`xweb.shell`/`xweb.shell_minimal`/
  `xweb.marketing_layout`/`none`/`xweb.pdf_document`/`xweb.email_layout`),
  et son [README](../studio/xweb/layouts/README.md) pour le schéma — référence
  `studio/xweb/components/` pour les props/context de chaque layout plutôt que
  de les dupliquer.
- [`studio/xweb/directives/`](../studio/xweb/directives/) — 14 fichiers, un par
  directive `t-*` (+ `<xpath>`, `| filtres`) réellement reconnue par
  `xweb/engine/compiler.py`/`inherit.py`/`filters.py` — le pendant "langage
  de template" de `studio/xweb/components/` (quels composants) et
  `studio/xweb/layouts/` (quel layout). Son
  [README](../studio/xweb/directives/README.md) documente l'ordre de précédence
  et une découverte qui justifie le dossier : une directive `t-*` mal
  orthographiée est **silencieusement ignorée** par le compilateur (jamais
  une erreur), exactement la même classe de piège que la whitelist `hx-*`
  du §4 — c'est donc au compilateur de sortie du Studio de la détecter.
- [`studio/xweb/assets/`](../studio/xweb/assets/) — 4 fichiers
  (`htmx.meta.yaml`/`css.meta.yaml`/`scripts.meta.yaml`/`themes.meta.yaml`),
  ce que le HTMX Editor (§4), le Theme Editor (§5) et l'Export chargent ou
  valident en dehors des composants/layouts eux-mêmes — la whitelist
  `hx-*` complète, le rôle réel d'`app.css`/`xweb.css` et son safelist, les
  scripts chargés par `xweb.shell_head`, et le format exact des blocs
  `[data-theme=x]`. Son [README](../studio/xweb/assets/README.md) détaille le
  schéma, calqué sur celui de `studio/xweb/components/`/`studio/xweb/directives/`.

Le Studio est un **UI builder pur** : il ne produit que du XML QWeb, des
classes Tailwind/DaisyUI et des attributs `hx-*`. Aucune surface
d'exécution — pas de code Python généré, pas de plugin scaffoldé, pas de
permission à déclarer. Il touche uniquement la couche présentation
(`xweb/engine/`), jamais le kernel (`xcore.kernel`) : pas de
`PermissionEngine`, pas d'`ASTScanner`, pas de signature de plugin, pas de
`PluginSupervisor`, pas de tenancy, pas de workflow compilé. C'est la
frontière qui rend le reste de cette spec tenable — une v1 antérieure qui
générait aussi le côté serveur (plugin Python, permissions, `execution_mode`)
a été abandonnée précisément parce qu'elle rouvrait toute la surface
sécurité du kernel pour un gain qui ne concerne que la présentation.

## 1. Ce que le canvas manipule réellement

Le moteur réel (`xweb/engine/parser.py`, `compiler.py`) ne connaît aucune
balise namespacée façon `<xweb:card>`/`<xweb:input>`. Il n'y a que deux
mécanismes :

- `<template t-name="...">` — déclaration d'un composant/page ;
- `t-call="xweb.card"` — invocation d'un composant déjà enregistré dans
  `QwebRegistry`, props en attributs plats, contenu enfant capturé comme
  `slot`.

Un login généré par le Studio ressemble donc à ceci, pas à un DOM abstrait
sérialisé après coup :

```xml
<template t-name="auth.login_page">
    <t t-call="xweb.card" extra_class="max-w-md mx-auto">
        <img src="/xweb-static/logo.svg" class="h-8 mb-4"/>
        <form method="post" action="/auth/login" hx-post="/auth/login"
              hx-target="#login-result" hx-swap="innerHTML">
            <t t-call="xweb.csrf" t-att-token="csrf_token"/>
            <t t-call="xweb.input" name="email" type="email" placeholder="Email"/>
            <t t-call="xweb.input" name="password" type="password" placeholder="Mot de passe"/>
            <t t-call="xweb.button" variant="primary" type="submit">Se connecter</t>
        </form>
        <div id="login-result"/>
    </t>
</template>
```

**Conséquence architecturale directe** : le canvas manipule *directement*
un arbre de `t-call`, où chaque nœud *est* un appel à un composant déjà
enregistré dans `QwebRegistry`. Le renderer du canvas et le compilateur de
sortie doivent être **le même code** — jamais deux représentations
(une IR interne + un sérialiseur QWeb) qui doivent rester synchronisées.

## 2. Component Metadata Layer — prérequis non négociable

Les composants réels (`xweb.button`, `xweb.card`, `xweb.input`…) déclarent
leurs props uniquement par convention interne (`<t t-set="variant"
t-default="'primary'"/>`), sans schéma exposé nulle part. Le Studio ne
peut pas construire un panneau de propriétés (`Component Inspector`) en
lisant le XML brut — sans métadonnées séparées, l'Inspector ne pourrait
proposer que « tape un attribut, tape une valeur » en texte libre, ce qui
revient à écrire du XML à la main avec un habillage graphique, pas un
vrai éditeur visuel.

```yaml
# studio/xweb/components/xweb.button.meta.yaml — un fichier par t-name, pas par
# fichier .xml source (plusieurs t-name peuvent partager un même fichier,
# ex. xweb.csrf + xweb.form dans form.xml — voir studio/xweb/components/README.md)
component: xweb.button
category: action
palette: true
props:
  variant: {type: enum, values: [primary, secondary, accent, neutral, info, success, warning, error], default: primary}
  size:    {type: enum, values: [xs, sm, md, lg, xl], default: md}
  href:    {type: string, optional: true}
  disabled: {type: bool, default: false}
slot: {accepts: text_or_inline, required: true}
```

**Fait** : chaque `t-name` réellement déclaré sous `xweb/components/*.xml`
(87 au total — pas ~45, ce chiffre de `docs/components.md` compte les
fichiers, pas les `t-name` qu'ils déclarent) a reçu son `.meta.yaml` dans
[`studio/xweb/components/`](../studio/xweb/components/) ; `category`/`palette` sont
des extensions à ce schéma, documentées dans le
[README](../studio/xweb/components/README.md) du dossier — `palette: false`
marque un `t-name` qui existe dans `QwebRegistry` (donc doit avoir ses
métadonnées) mais qu'un designer ne doit jamais glisser seul sur le canvas
(sous-template interne, ou layout entier couvert par le Layout Manager, §8
ci-dessous). Valeurs `enum` vérifiées contre le safelist Tailwind réel
(`xweb/static/xweb.css`), pas devinées — voir le README pour le détail.

## 3. CSRF — injection automatique, non désactivable silencieusement

`CSRFMiddleware` ([`xweb/csrf.py`](../xweb/csrf.py)) exige un champ
`csrf_token` en POST pour toute session cookie-authentifiée. `xweb.form`
l'injecte automatiquement ([`xweb/components/form.xml`](../xweb/components/form.xml)),
mais un designer qui compose un `<form>` à la main dans le canvas (comme
dans l'exemple du §1) peut très bien oublier `t-call="xweb.csrf"` — et
l'erreur ne se voit qu'au runtime, en 403 silencieux, jamais à l'édition.

**Règle imposée au compilateur de sortie** : tout `<form>` (natif ou
`t-call="xweb.form"`) avec `method="post"` généré par le Studio reçoit
automatiquement `<t t-call="xweb.csrf" t-att-token="csrf_token"/>` —
non désactivable sans confirmation explicite (« je gère le CSRF
autrement »), jamais un oubli silencieux.

## 4. HTMX Editor — whitelist fermée, pas de texte libre

Le compilateur (`_render_attrs`, [`xweb/engine/compiler.py`](../xweb/engine/compiler.py))
ne valide **aucun** nom d'attribut `hx-*` — tout passe tel quel, y compris
une faute de frappe (`hx-tagret` au lieu de `hx-target`) qui ne provoquera
jamais d'erreur, juste un comportement silencieusement cassé en prod.

Le HTMX Editor du Studio maintient donc sa propre liste fermée d'attributs
valides et refuse toute clé hors de cette liste — c'est le seul endroit où
l'erreur peut être détectée avant l'export, puisque le runtime ne la
détectera jamais :

```
hx-get, hx-post, hx-put, hx-delete, hx-target, hx-swap, hx-trigger,
hx-vals, hx-headers, hx-confirm, hx-indicator, hx-boost, hx-select,
hx-push-url
```

## 5. Theme Editor — contraint par DaisyUI + la CSP

### a) Le thème, ce sont des variables OKLCH DaisyUI, pas du CSS libre

`app.css` définit chaque thème comme un bloc
`[data-theme=nom] { --color-primary: oklch(...); --color-base-100: oklch(...); ... }`.
Le Theme Editor doit générer **exactement ce format de bloc** — sinon les
composants existants (`btn-primary`, `badge-neutral`…) qui référencent ces
variables ne captent jamais les nouvelles couleurs.

### b) v1 : un seul thème custom fixe, pas de toggle multi-thèmes

`xweb.theme_toggle` ([`xweb/components/layout.xml:81`](../xweb/components/layout.xml))
et le script anti-flash de `xweb.shell_head` ne connaissent que
`'light'`/`'dark'` (`localStorage.getItem('theme') || 'light'`). Ajouter un
troisième thème custom depuis le Studio impose de trancher : soit fixer
`data-theme` en dur sans toggle utilisateur, soit régénérer une variante de
`theme_toggle` qui cycle sur N thèmes.

**Décision v1** : un seul thème custom fixe par projet, pas de toggle
multi-thèmes — le cycle « light/dark natif » reste intouché. Un vrai
sélecteur multi-thèmes est hors scope v1.

### c) Pas de `<style>` inline — toujours un fichier `.css` externe

La CSP ([`xweb/security.py`](../xweb/security.py), `style-src-elem 'self'`)
bloque tout bloc `<style>` embarqué dans une page — seul
`style-src-attr 'unsafe-inline'` est permis (attributs `style="..."`
inline). Le Theme Editor doit donc **toujours** produire un fichier `.css`
externe, jamais un `<style>` injecté dans la page.

### d) Piège pour toute future feature JS custom

Si le Studio veut un jour injecter le moindre `<script>` inline
supplémentaire, la CSP (`script-src 'self' 'unsafe-eval' '<hash exact>'`,
`XWEB_THEME_SCRIPT_HASH`) le bloquera net. Contrainte dure à documenter :
**tout JS custom généré par le Studio doit être un fichier externe**,
jamais inline, sauf à régénérer le hash à chaque changement (pas praticable
pour du contenu généré dynamiquement).

## 6. Live Preview — un avantage caché de l'architecture xweb

`Compiler.render()` est **synchrone, pur Python, sans I/O**
([`xweb/engine/registry.py`](../xweb/engine/registry.py)). Pas besoin de
booter FastAPI/xcore pour prévisualiser en direct dans le Studio :

```python
preview_registry = QwebRegistry()
preview_registry.register_source(canvas_xml_en_cours_d_edition, source_plugin="studio-preview")
html = preview_registry.render("studio.preview_page", ctx_de_demo)
```

Le canvas offre donc un rendu WYSIWYG **exact** — même moteur qu'en prod,
pas une approximation React/Vue du rendu QWeb — en ré-exécutant ce
pipeline à chaque modification, sans serveur applicatif complet. Alimenté
par les mêmes fixtures que le [Context Contract](#7-context-contract--sans-génération-de-backend)
(§7).

## 7. Context Contract — sans génération de backend

Un `t-esc="user.email"` ou un `t-foreach="items"` dans le template généré
référence des variables que **seul le développeur** injecte depuis sa
`PageView` Python. Sans déclaration minimale, le canvas ne peut ni valider
ces expressions, ni proposer d'autocomplétion, ni faire tourner la preview
avec des données réalistes.

Chaque page déclare donc un petit contrat de contexte, indépendant de
toute API :

```yaml
# .studio/pages/customers_list.context.yaml
page: customers.list_page
context:
  items: {type: list_of, fields: {email: str, status: str}}
  user:  {type: auth_payload, optional: true}
fixtures:                      # données factices pour la preview
  items:
    - {email: "a@x.com", status: "active"}
    - {email: "b@x.com", status: "inactive"}
```

Ce n'est pas de la génération de backend — juste une déclaration de forme
de données, saisie à la main par le développeur, qui sert le canvas et la
preview et rien d'autre. Le binding `t-foreach="items"` reste écrit par le
développeur dans le code Python de sa `PageView` ; le Studio ne fait que
savoir *afficher* une preview cohérente. Ces fichiers vivent sous
`.studio/pages/` — un dossier de config d'outillage, distinct du dossier
de templates réel (§8) où atterrit le XML généré.

## 8. Emplacement des fichiers générés

`XwebExtension.init()` scanne des dossiers déclarés par plugin
(`namespaces: {nom: chemin}` dans `integration.yaml`,
[`integration.yaml:39`](../integration.yaml)) plus `xweb/components/`
embarqué dans le paquet. Le Studio doit donc écrire ses `.xml` **dans un
dossier de templates déjà déclaré** — jamais dans un répertoire
`.studio/output/` séparé qu'il faudrait ensuite copier à la main.

**Décision v1, spécifique à l'état actuel de ce dépôt** : `plugins/`
n'existe pas ici (dépôt réduit à `xweb` + une landing page de démo — voir
[CLAUDE.md](../CLAUDE.md)) ; `integration.yaml` ne déclare aujourd'hui
qu'un seul namespace réellement valide, `site: "templates"` (racine du
projet, monté directement par `main.py`, hors `PluginSupervisor` — voir
CLAUDE.md#url-prefix). La v1 du Studio écrit donc sous ce namespace :

```
templates/
├── customers_list.xml       # généré par le Studio
└── customers_list.meta.yaml # source_plugin, hash de contenu (détecte l'édition manuelle)

static/
└── theme.css                 # généré par le Theme Editor (§5), monté sur le
                               # router "site" via mount_plugin_static() — même
                               # mécanisme qu'un vrai plugin, appliqué au router
                               # non préfixé de la landing page (main.py)
```

Dès qu'un vrai plugin apparaît dans ce dépôt (ou dans un déploiement qui a
gardé `plugins/`), la même logique s'applique à
`plugins/<plugin_choisi>/templates/` et
`plugins/<plugin_choisi>/static/theme.css` : le Studio demande au premier
lancement « quel plugin hôte, quel dossier de templates » et lit
`integration.yaml` pour vérifier que ce dossier est bien déclaré dans
`namespaces`, plutôt que de le deviner. Le choix « site » ci-dessus n'est
qu'un cas particulier de cette règle générale (un seul namespace candidat
aujourd'hui), pas une exception.

## 9. Conflits de templates — toujours d'actualité même sans backend

`QwebRegistry._resolve()` loggue un warning (non bloquant) en cas de
collision `t-inherit position="replace"` entre deux `source_plugin`
différents ([`xweb/engine/registry.py`](../xweb/engine/registry.py),
voir aussi [inheritance.md](inheritance.md)). Le Studio doit :

- taguer tout ce qu'il génère avec un `source_plugin` distinct
  (`studio:<hôte>`, ex. `studio:site`) pour que ce warning au boot
  distingue clairement « généré visuellement » de « modifié à la main » ;
- détecter une divergence (hash du fichier `.xml` différent de celui
  enregistré au dernier export) au ré-import et proposer une fusion plutôt
  qu'écraser silencieusement une édition manuelle.

## Modules — vue d'ensemble

```
XWeb Studio (UI builder pur)
│
├── Component Metadata Layer          ← prérequis, §2 — écrit, studio/xweb/components/
│   └── *.meta.yaml (props, slots, types)
│
├── Component Palette                 ← lit la Metadata Layer, pas le XML brut
│
├── Directive Rules                    ← métadonnées écrites, studio/xweb/directives/
│   └── set fermé de directives t-* valides — même piège "silencieux si
│       mal orthographié" que le HTMX Editor ci-dessous, côté langage
│
├── Visual Canvas
│   └── manipule un arbre de t-call réel, pas une IR séparée (§1)
│
├── Component Inspector
│   ├── props (typées via metadata)
│   ├── classes Tailwind (dont sm:/lg: — pas de moteur responsive séparé)
│   └── slot content (récursif, imbrication de t-call)
│
├── HTMX Editor
│   └── whitelist fermée d'attributs hx-* (§4), validée au build
│
├── Layout Manager                    ← métadonnées écrites, studio/xweb/layouts/
│   └── mappe directement sur shell=True/False + layout=xweb.shell|xweb.shell_minimal|None
│
├── Theme Editor
│   ├── génère un bloc [data-theme=x] au format DaisyUI (§5a)
│   ├── sort toujours en .css externe (jamais inline, contrainte CSP §5c)
│   └── v1 : un thème custom fixe, pas de toggle multi-thèmes (§5b)
│
├── Context Contract (§7)
│   └── déclaration de forme de données + fixtures, sans génération de backend
│
├── Live Preview (§6)
│   └── QwebRegistry embarqué, synchrone, mêmes composants qu'en prod
│
├── CSRF Guard (§3)
│   └── injection automatique et non désactivable sur tout <form method=post>
│
└── Export
    ├── écrit dans le dossier de templates du namespace hôte (jamais un dossier
    │   séparé, §8 — "site"/templates en v1 dans ce dépôt)
    ├── écrit static/theme.css sur le router du même hôte
    ├── tague source_plugin="studio:<hôte>" (§9)
    └── détecte la divergence par hash au ré-import
```

## Hors scope v1

Aucune génération côté serveur : pas de plugin Python scaffoldé, pas de
`PermissionEngine`/`ASTScanner`/signature de plugin, pas de
`PluginSupervisor`, pas de tenancy, pas de workflow compilé en code —
`execution_mode`, `enforce_ipc`, rate limit et `actor` restent des
préoccupations du kernel que le Studio ne touche jamais. Un sélecteur
multi-thèmes (au-delà du cycle natif light/dark) est également hors scope
v1 (§5b).

## Voir aussi

- [components.md](components.md) — catalogue des ~45 composants `xweb.*`
  qui doivent chacun recevoir un `.meta.yaml` (§2).
- [inheritance.md](inheritance.md) — mécanique de conflit `t-inherit`
  réutilisée telle quelle par la détection du §9.
- [language.md](language.md) — référence complète des directives `t-*`
  que le canvas manipule (§1).
- [theming.md](theming.md) — format réel des blocs de thème DaisyUI que le
  Theme Editor doit reproduire (§5a).
