# DSL xweb — Design en cours de conception

> **Statut** : Phase de conception, pas encore implémenté. Ce document capture les décisions de design prises jusqu'à présent.

Un DSL (Domain Specific Language) déclaratif, inspiré de QML, qui génère du XML standard pour lxml. Le moteur QWeb reste inchangé — le DSL est un sucre syntaxique pur, 100% de parité avec les directives `t-*` existantes.

## Pourquoi un DSL

Le QWeb actuel (XML + directives `t-*`) est puissant mais verbeux pour un débutant. Trois technologies doivent être maîtrisées simultanément :
1. XML + directives QWeb (`t-if`, `t-foreach`, `t-call`, `t-att-*`, etc.)
2. Tailwind CSS (noms de classes utilities)
3. DaisyUI (composants et variantes)

Le DSL réduit la barrière d'entrée tout en gardant la pleine puissance de QWeb en dessous.

## Architecture

```
.dsl (syntaxe QML-like)
   ↓  parser Python
.xml (QWeb standard — directives t-* intactes)
   ↓  lxml + QwebRegistry
HTML rendu
```

Le DSL ne touche pas au moteur. Il écrit du XML que lxml sait déjà parser. Intégration prévue dans `QwebRegistry.register_source()` — intercepte les fichiers `.dsl`, les convertit avant enregistrement.

## Syntaxe du composant

```qml
component auth.login_form {
    // props du composant
    props: { email: ""; password: "" }

    // CSS scoped au composant
    style: "
        .login-card { background: var(--base-200); padding: 2rem; border-radius: 1rem; }
        .login-btn { width: 100%; margin-top: 1rem; }
    "

    // import de composants externes
    import { input, button, form } from "xweb"

    // corps du composant
    Form { class: "login-card"
        input { label: "Email"; type: "email"; bind: email }
        input { label: "Mot de passe"; type: "password"; bind: password }
        button { label: "Connexion"; variant: "primary"; class: "login-btn" }
    }
}
```

**Génère :**

```xml
<template t-name="auth.login_form">
    <style>
        .login-card { background: var(--base-200); padding: 2rem; border-radius: 1rem; }
        .login-btn { width: 100%; margin-top: 1rem; }
    </style>
    <div class="login-card">
        <t t-call="xweb.form">
            <t t-call="xweb.input" t-att-label="'Email'" t-att-type="'email'"/>
            <t t-call="xweb.input" t-att-label="'Mot de passe'" t-att-type="'password'"/>
            <t t-call="xweb.button" t-att-label="'Connexion'" t-att-variant="'primary'" t-att-class="'login-btn'"/>
        </t>
    </div>
</template>
```

## Imports

Le DSL utilise une syntaxe d'import inspirée d'ES6/Python pour référencer les composants.

### Import absolu (composants externes)

```qml
import { button, input, form } from "xweb"
import { icon } from "xweb"
```

**Génère :** référence `xweb.button`, `xweb.input`, etc. dans les `t-call`.

### Import relatif (même plugin)

```qml
import { nav } from "./"
import { helper } from "../auth"
import { card } from "../xweb"
```

Le `package_id` du plugin (déclaré dans `plugin.yaml`) sert de racine pour les chemins relatifs.

**Mapping :**

| DSL | QWeb |
|-----|------|
| `import { button } from "xweb"` | `<t t-call="xweb.button"/>` |
| `import { nav } from "./"` | `<t t-call="current_plugin.nav"/>` |
| `import { helper } from "../auth"` | `<t t-call="auth.helper"/>` |

## Hyperscript

Le DSL supporte le code hyperscript brut via la syntaxe `_`. Le lexer
intercepte `_ :` / `_ {` avant toute tokenisation — les mots-clés
hyperscript (on, click, wait, if…) restent du texte brut, jamais tokenisés
comme du DSL. L'attribut `_` évolue selon le contenu :

| Contenu du script | XML généré |
| --- | --- |
| sans `${...}` | `_="..."` — statique, passe tel quel |
| avec `${...}` | `t-attf-_="... {{expr}} ..."` — interpolation **serveur** |

### Syntaxe en ligne (une seule instruction)

```qml
button {
    label: "Fermer"
    _ : on click log "Post ${post.id} aimé !"
}
```

Le script est capturé jusqu'à la fin de la ligne ou l'accolade fermante
de l'élément (`}` sur la même ligne). Un groupe `${...}` est consommé
**entier** (accolades éventuellement imbriquées) — son `}` de fermeture
n'est jamais confondu avec l'accolade de fin d'élément.

### Syntaxe en bloc (multi-lignes)

```qml
div {
    class: "alert"
    _ {
        on load
            wait 2s
            transition opacity to 0
        on click remove me
        js(me) return {a: 1, b: 2} end
    }
}
```

Les accolades internes (`{ }` dans un `js()`) sont gérées par compteur
de profondeur — le bloc s'arrête uniquement quand la profondeur retombe
à zéro. Les **nouvelles lignes internes sont préservées** : hyperscript
sépare ses déclarations par des sauts de ligne (deux handlers `on ...`
deviennent le corps du premier si on les écrase par des espaces), et
`xweb/components/shell.xml:252` utilise déjà de vrais `_="..."` multilignes.

### Interpolation serveur — `${...}`

Le DSL utilise `${ expr }` pour injecter une valeur du contexte QWeb
dans le script (l'équivalent de la syntaxe des props). Le compilateur
convertit :

```
_ : on click put ${user.name} into me
      ↓
t-attf-_="on click put {{user.name}} into me"
      ↓ (render QWeb, contexte {user: ...})
_="on click put Bob into me"
```

- Le moteur n'interpelle que `{{ }}` (`_eval_formatted`). La conversion
  `${}` → `{{}}` est faite par le compilateur (`_to_qweb_interp`), avec
  comptage de profondeur : `${JSON.stringify({a: 1})}` reste un groupe.
  Sans cette conversion, QWeb laisserait `${...}` littéral.
- Même contrat que les props interpolées (`class:` → `t-attf-extra_class`)
  — qui en profitent aussi : le chemin `t-attf-*` n'avait jamais converti
  `${}` en `{{}}` auparavant.
- Sur un `t-call`, `t-attf-_` devient la prop `_` de la cible
  (`xweb/engine/compiler.py:_render_call`) ; sur un élément brut, un
  attribut `_` rendu (`_render_attrs`).
- L'expression est du **Python du contexte** (comme toute prop) — pas une
  variable hyperscript, pas un littéral client. Une interpolation qui ne
  trouve pas la valeur rend une chaîne vide (convention `_eval`).

### Rôle du compilateur en l'absence d'interpolation

`_build_component_props` émet `_="value"` (statique) et `_build_html_attrs`
fait de même pour les éléments HTML bruts. Les caractères `<`, `>`, `&`
sont échappés automatiquement par `_esc()` — dans le DSL, écrivez du code
hyperscript brut (pas `&lt;`/`&gt;`), c'est le compilateur qui échappe.

### Limites

- `"` et `'` dans le script sont échappées (`&quot;`/`&apos;`).
- Le mode bloc (`_ { ... }`) échoue si des accolades non équilibrées
  apparaissent (inhabituel hors de `js()`).
- Un `${...}` non fermé dans un script n'est pas une erreur : il reste
  littéral (mais le moteur QWeb verrait `{{` et tenterait de l'évaluer
  au render — une `${` orpheline est un bug, pas une feature).
- L'interpolation hyperscript **côté client** n'existe plus : un
  `` `/api/items/${id}` `` est désormais une interpolation serveur.
  Pour une valeur calculée côté navigateur, passez-la en attribut
  (`data-...`) lu ensuite via `me`.

## Layout

Chaque composant d'un fichier est un fragment (`<template t-name=...>`),
jamais une page complète. La directive au niveau fichier `@include` déclare
dans quel layout envelopper ces fragments au montage — même contrat que
`mount.py::render_xweb_template` (le fragment rendu devient la prop `content`
du layout, jamais un slot).

```qml
@include "xweb.shell"
```

**Génère :** marqueur en tête de l'XML compilé, consommé par le pipeline de
montage (`scripts/dsl2html.py`, `render_xweb_template(layout=...)`) :

```xml
<!-- layout: xweb.shell -->
<template t-name="auth.login">…</template>
```

- Directive **fichier** (hors composant, comme `import`) — l'XML des
  composants reste un fragment pur, réutilisable sans layout.
- La valeur est un nom de template QWeb (`xweb.shell`, `xweb.shell_minimal`…).
- Absente → comportement actuel (fragments nus).

## Structures de contrôle

### Condition

```qml
if (is_authenticated) {
    button { label: "Déconnexion" }
} else {
    button { label: "Connexion" }
}
```

**Génère :**

```xml
<t t-if="is_authenticated">
    <t t-call="xweb.button" t-att-label="'Déconnexion'"/>
</t>
<t t-else="1">
    <t t-call="xweb.button" t-att-label="'Connexion'"/>
</t>
```

### Boucle

```qml
for item in items {
    div { class: "row"
        span { item.name }
        span { item.email }
    }
}
```

**Génère :**

```xml
<t t-foreach="items" t-as="item">
    <div class="row">
        <span><t t-esc="item.name"/></span>
        <span><t t-esc="item.email"/></span>
    </div>
</t>
```

### Variables

```qml
x = expr                    // t-set avec valeur
x ?= expr                   // t-default (seulement si absent)
title = "Bonjour"           // valeur littérale
count = items.length        // expression Python
```

**Génère :**

```xml
<t t-set="x" t-value="expr"/>
<t t-set="x" t-default="expr"/>
<t t-set="x" t-value="'Bonjour'"/>
<t t-set="x" t-value="items.length"/>
```

### Filtres

Le set fermé de filtres QWeb (`xweb/engine/filters.py`, `docs/language.md#filtres`
— `money`, `upper`, `truncate`, `default`, etc.) est utilisable dans une
expression DSL comme en QWeb natif, `expr | nom[:arg]` :

```qml
span { item.price | money }
badge { label: title | truncate:5 }
badge { label: title | upper | truncate:5 }
```

**Génère :**

```xml
<span><t t-esc="item.price | money"/></span>
<t t-call="xweb.badge" t-att-label="title | truncate: 5"/>
<t t-call="xweb.badge" t-att-label="title | upper | truncate: 5"/>
```

**Limite (expression nue, hors `${...}`)** : un seul argument par filtre.
Le `:` qui suit un nom de filtre n'interrompt pas l'expression (il
introduit son argument), mais une virgule de premier niveau après cet
argument en interrompt toujours la lecture (`_read_expression`,
`xdsl/parser.py`) — elle sert par ailleurs de séparateur d'item dans
`class: [...]`/`style: {...}` et ne peut pas être désambiguïsée sans
contexte. Un filtre multi-arguments (`join:', ',name`) lève donc une
`ParseError` franche s'il est écrit nu ; à l'intérieur d'un `${...}`, en
revanche, tout passe en texte brut sans cette ambiguïté (voir Hyperscript
ci-dessus) — `"${names | join:', ',name}"` fonctionne.

## Héritage et patching (t-inherit)

### Extension (défaut)

Le patch modifie l'arbre partagé du composant cible — tout appelant voit le patch.

```qml
patch xweb.form {
    xpath "//button" {
        inside: span { "CGU" }
    }
}
```

**Génère :**

```xml
<template t-inherit="xweb.form" t-inherit-mode="extension">
    <xpath expr="//button" position="inside"><span>CGU</span></xpath>
</template>
```

### Primary

Copie complète du composant cible, personnalisée par des blocs `xpath` —
**uniquement** des blocs `xpath`, exactement comme `patch`. Le moteur QWeb
(`xweb/engine/inherit.py::extract_patch`) ne lit que les enfants `<xpath>`
d'un `<template t-inherit-mode="primary">` ; un corps littéral (`div { ...
}` directement dans le `copy`) n'a **aucun effet** — silencieusement, sans
erreur (bug réel trouvé en enregistrant une vraie copie pour la première
fois ; `copy.CopyDef`, xdsl/parser.py, refuse maintenant ce corps au parse
plutôt que de compiler quelque chose de mort).

```qml
copy xweb.form as auth.login_form {
    xpath "//button" { attributes: a { data-variant: "enterprise" } }
}
```

**Génère :**

```xml
<template t-name="auth.login_form" t-inherit="xweb.form" t-inherit-mode="primary">
    <xpath expr="//button" position="attributes">
        <attribute name="data-variant">enterprise</attribute>
    </xpath>
</template>
```

Une fois enregistrée, une copie est un template comme un autre — `patch
auth.login_form { ... }` la cible ensuite par son nom, sans distinction
avec un template de base (`xdsl/tests/test_compiler.py::TestCopyEndToEnd`).

### Positions XPath

| DSL | QWeb |
|-----|------|
| `xpath "//button" { inside: ... }` | `<xpath expr="//button" position="inside">` |
| `xpath "//button" { replace: ... }` | `<xpath expr="//button" position="replace">` |
| `xpath "//button" { before: ... }` | `<xpath expr="//button" position="before">` |
| `xpath "//button" { after: ... }` | `<xpath expr="//button" position="after">` |
| `xpath "//input" { attributes: a { disabled: "true" } }` | `<xpath expr="//input" position="attributes"><attribute name="disabled">true</attribute></xpath>` |

`attributes:` attend un élément dont les attributs deviennent ceux posés
(`a { clé: valeur; ... }`, une seule balise `<a>` par convention, jamais
utilisée pour autre chose ici) — chacun devient un `<attribute name="clé">
valeur</attribute>`, la seule forme que `extract_patch()` sait lire. Un
autre exemple `xpath "//input" { attributes: { disabled: "true" } }`
(dict littéral) a déjà circulé dans une version antérieure de ce document
— **jamais implémenté**, ne pas s'y fier.

### Priorité

Plusieurs patches sur la même cible se résolvent par priorité (entier, défaut 0, le plus bas d'abord), puis ordre d'enregistrement.

```qml
patch xweb.form priority: 10 {
    xpath "//button" {
        inside: span { "Premium" }
    }
}
```

## Attributs htmx

Les attributs htmx suivent la même logique que les props — le parser détecte automatiquement le type de valeur.

### Valeurs statiques

```qml
button {
    label: "OK"
    hx-post: "/login"
    hx-target: "#form"
    hx-swap: "outerHTML"
}
```

**Génère :** `hx-post="/login"` (attribut statique).

### Valeurs dynamiques (variables)

```qml
button {
    label: "OK"
    hx-post: url
    hx-target: "#form"
}
```

**Génère :** `t-att-hx-post="url"` (expression Python).

### Expressions JS (hx-vals)

```qml
button {
    label: "OK"
    hx-post: "/save"
    hx-vals: "js:{id: ${selected_id}}"
}
```

**Génère :** `t-attf-hx-vals="js:{id: ${selected_id}}""` (interpolation).

### Règle du parser

| Syntaxe DSL | Type détecté | Génère |
|-------------|--------------|--------|
| `hx-post: "/url"` | Littéral (guillemets) | `hx-post="/url"` |
| `hx-post: url` | Variable seule | `t-att-hx-post="url"` |
| `hx-vals: "js:{x: ${y}}""` | String avec `${}` | `t-attf-hx-vals="js:{x: ${y}}""` |

### Hyperscript

Les attributs `_="..."` passent tels quels, même comportement que QWeb :

```qml
button {
    _="on click toggle .hidden"
    hx-post: "/toggle"
}
```

## Props et styling

### Props DaisyUI exposées directement

Chaque composant xweb expose ses props de styling (variant, size, etc.) comme des propriétés DSL.

```qml
button {
    label: "Connexion"
    variant: "primary"
    size: "lg"
    outline: true
    disabled: false
}
```

**Génère :**

```xml
<t t-call="xweb.button"
   t-att-label="'Connexion'"
   t-att-variant="'primary'"
   t-att-size="'lg'"
   t-att-outline="true"
   t-att-disabled="false"/>
```

### Utilities Tailwind (class)

La propriété `class` supporte deux formes : une chaîne classique ou une liste structurée.

**Forme chaîne** (comportement existant, avec interpolation `${...}`) :

```qml
button {
    label: "OK"
    variant: "primary"
    class: "flex gap-2 px-4 shadow-lg"
}
```

**Forme liste** — jetons de classes, statiques ou dynamiques :

```qml
div {
    class: ["flex", "items-center", live_class, "${size}-gap"]
}
```

Se compose de :

- Chaînes littérales → `items-center`
- Expressions non entre guillemets → `live_class`
- `${expr}` dans une chaîne → interpolation serveur

**Génère :**

```xml
<!-- tout statique → texte brut -->
<div class="flex items-center"/>

<!-- mixte → t-attf-class avec {{expr}} -->
<div t-attf-class="flex items-center {{live_class}} {{size}}-gap"/>
```

> **Sur un t-call** (`component xweb.button { ... }`), `class` cible `extra_class`
> (convention xweb — `class` est un mot-clé réservé Python) :
> ```xml
> <t t-call="xweb.button" t-attf-extra_class="btn {{active}}"/>
> ```

### Style inline (style: {...})

Le style d'un élément peut être un dictionnaire de propriétés CSS. Les clés sont des identifiants ou des chaînes (pour les noms kebab-case comme `"background-color"`).

```qml
div {
    style: {
        color: "red"
        padding: "2rem"
        "font-size": "${scale}em"
    }
}
```

**Génère :**

```xml
<!-- tout statique → attribut style brut -->
<div style="color: red; padding: 2rem; font-size: 1.5em;"/>

<!-- dynamique → t-att-style avec concat Python -->
<div t-att-style="'color: ' + 'red' + '; ' + 'padding: ' + '2rem' + '; ' + 'font-size: ' + (scale) + 'em' + ';'"/>
```

> **Clés kebab-case** : le lexer ignore `-` isolé, il faut les mettre entre guillemets (`"background-color": "..."`).

### CSS natif (style)

Le bloc `style:` au niveau composant (string) génère un `<style>` dans le template — CSS classique avec sélecteurs, scoped au composant.

```qml
component auth.login_form {
    style: "
        .login-card { background: var(--base-200); padding: 2rem; }
        .login-btn { width: 100%; margin-top: 1rem; }
    "

    div { class: "login-card"
        input { label: "Email" }
        button { label: "Connexion"; class: "login-btn" }
    }
}
```

### Règle de styling

| Besoin | Syntaxe DSL | Génère |
|--------|-------------|--------|
| Prop DaisyUI | `variant: "primary"` | `t-att-variant="'primary'"` |
| Utilities Tailwind | `class: "flex gap-2"` | `t-attf-class="flex gap-2"` |
| Utilities (liste) | `class: ["flex", expr]` | `t-attf-class="flex {{expr}}"` |
| Style inline (statique) | `style: { color: "red" }` | `style="color: red;"` |
| Style inline (dynamique) | `style: { color: expr }` | `t-att-style="'color: ' + (expr) + ';'"` |
| CSS scoped (composant) | `style: ".x { color: red }"` | `<style>.x { color: red }</style>` |

## Texte et traduction

### Texte simple

Le texte entre accolades est automatiquement échappé (`t-esc`) :

```qml
span { "Bonjour le monde" }
div { title }  // variable, échappée
```

### Texte brut (raw)

Préfixe `raw` pour injecter du HTML de confiance :

```qml
div { raw slot }
```

### Traduction

Préfixe `tr` pour le texte statique, `tr()` pour les expressions :

```qml
h1 { tr "Organisation" }
p { tr "Bienvenue, ${name}" }
```

**Génère :**

```xml
<h1 t-tr="1">Organisation</h1>
<p><t t-out="tr('Bienvenue, ' + name)"/></p>
```

## Slots

Le contenu passé dans un composant est disponible via `slot` :

```qml
// définition du composant
component xweb.card {
    div { class: "card-body"
        slot
    }
}

// utilisation
xweb.card {
    h2 { "Titre" }
    p { "Contenu de la carte" }
}
```

Un composant défini dans le **même fichier** peut être appelé par son
`t-name` complet (dotted) — `xweb.card { }` ci-dessus compile en
`<t t-call="xweb.card"/>` sans import préalable. Résolution d'un tag :
**scope d'import d'abord**, puis t-name local, puis élément HTML brut.

```qml
// imbrication : composant conteneur appelant un fragment défini plus haut
component auth.login { div { "Login" } }
component auth {
    auth.login { }
}
```

**Génère :** `<template t-name="auth">` contenant
`<t t-call="auth.login"/>`.

**Génère :**

```xml
<!-- définition -->
<template t-name="xweb.card">
    <div class="card-body">
        <t t-out="slot"/>
    </div>
</template>

<!-- utilisation -->
<t t-call="xweb.card">
    <t t-set="slot">
        <h2>Titre</h2>
        <p>Contenu de la carte</p>
    </t>
</t>
```

## Props d'un composant

### Définition

```qml
component auth.login_form {
    props: { email: ""; password: ""; remember: false }

    form {
        input { label: "Email"; bind: email }
        input { label: "Mot de passe"; type: "password"; bind: password }
        checkbox { label: "Se souvenir de moi"; bind: remember }
        button { label: "Connexion" }
    }
}
```

### Appel avec props

```qml
auth.login_form { email: user.email; password: user.password }
```

**Génère :**

```xml
<t t-call="auth.login_form" t-att-email="user.email" t-att-password="user.password"/>
```

### Props avec défaut

Les props avec une valeur par défaut utilisent `t-default` — la valeur n'est utilisée que si la prop n'est pas passée par l'appelant.

```qml
props: { variant: "primary"; size: "md" }
```

## Scope des variables

Le DSL respecte exactement les règles de portée de QWeb :

1. **Portée locale** — une variable définie dans un bloc `{ }` n'existe que dans ce bloc
2. **Contexte isolé de `t-call`** — un composant ne voit que les props qui lui sont passées, jamais le contexte de l'appelant
3. **Forwarding explicite** — pour passer une variable à un sous-composant, il faut la forwarder en prop

```qml
component parent {
    props: { title: "Titre" }

    // title est disponible ici
    h1 { title }

    // mais PAS ici — l'appel isole le contexte
    child_component { }  // title n'existe pas dans child

    // il faut forwarder explicitement
    child_component { title: title }
}
```

## Mapping complet DSL → QWeb

| DSL | QWeb |
|-----|------|
| `component x.y { }` | `<template t-name="x.y">` |
| `import { a, b } from "xweb"` | — (déclare les noms disponibles) |
| `@include "xweb.shell"` | `<!-- layout: xweb.shell -->` (au montage, chaque fragment devient `content` du shell) |
| `_ : on click ...` | `_="on click ..."` (attribut statique brut, passe tel quel) |
| `a { }` | `<t t-call="xweb.a"/>` |
| `xweb.card { }` (composant local) | `<t t-call="xweb.card"/>` (résolu par t-name local) |
| `if (expr) { }` | `<t t-if="expr">` |
| `elif (expr) { }` | `<t t-elif="expr">` |
| `else { }` | `<t t-else="1">` |
| `for x in list { }` | `<t t-foreach="list" t-as="x">` |
| `x = expr` | `<t t-set="x" t-value="expr"/>` |
| `x ?= expr` | `<t t-set="x" t-default="expr"/>` |
| `expr | filtre[:arg]` | `expr | filtre[:arg]` (passthrough, `xweb/engine/filters.py`) |
| `<texte>` | `<t t-esc="..."/>` (auto) |
| `raw expr` | `<t t-out="expr"/>` |
| `tr "texte"` | `<t t-tr="1">texte</t>` |
| `patch x.y { }` | `<t t-inherit="x.y" t-inherit-mode="extension">` |
| `copy x.y as z { }` | `<t t-inherit="x.y" t-inherit-mode="primary" t-name="z">` |
| `xpath "//x" { inside: ... }` | `<xpath expr="//x" position="inside">` |
| `priority: N` | `priority="N"` sur `<template>` |
| `props: { x: default }` | `<t t-set="x" t-default="default"/>` |
| `style: "..."` | `<style>...</style>` |
| `class: "..."` | `t-attf-class="..."` |
| `hx-post: url` | `t-att-hx-post="url"` |
| `hx-post: "/url"` | `hx-post="/url"` |
| `_="on click ..."` | `_="on click ..."` (passthrough) |
| `slot` | `<t t-out="slot"/>` |

## Cas d'usage complets

### Login page

```qml
component auth.login_page {
    style: "
        .login-container { max-width: 400px; margin: 4rem auto; }
        .login-card { background: var(--base-200); border-radius: 1rem; padding: 2rem; }
    "

    import { input, button, form, card } from "xweb"

    div { class: "login-container"
        card { class: "login-card"
            h1 { tr "Connexion" }
            form { hx-post: "/login"; hx-target: "#error"; hx-swap: "innerHTML"
                input { label: "Email"; type: "email"; name: "email"; required: true }
                input { label: "Mot de passe"; type: "password"; name: "password"; required: true }
                div { id: "error"; class: "text-error" }
                button { label: "Se connecter"; variant: "primary"; class: "w-full" }
            }
        }
    }
}
```

### Liste avec CRUD

```qml
component crm.contacts_list {
    style: "
        .contacts-header { display: flex; justify-content: space-between; align-items: center; }
        .contact-row { display: flex; padding: 0.75rem; border-bottom: 1px solid var(--base-300); }
    "

    import { button, input, badge } from "xweb"

    div {
        div { class: "contacts-header"
            h2 { "Contacts" }
            button { label: "Ajouter"; variant: "primary"; hx-get: "/contacts/new"; hx-target: "#modal" }
        }

        for contact in contacts {
            div { class: "contact-row"
                span { contact.name }
                badge { label: contact.role; variant: contact.role == "admin" ? "primary" : "ghost" }
                button { label: "Modifier"; hx-get: "/contacts/${contact.id}/edit"; hx-target: "#modal" }
                button { label: "Supprimer"; variant: "error"; hx-delete: "/contacts/${contact.id}"; hx-confirm: "Supprimer ce contact ?" }
            }
        }
    }
}
```

## Requêtes réseau déclaratives (`data`/`endpoint`/`use:`)

Décrire une requête HTTP en un seul endroit — méthode/URL, données envoyées,
validation des données **reçues**, et ce qui se passe pendant/après — plutôt
que d'assembler `hx-post`/`hx-target`/`hx-vals`/hyperscript à la main à
chaque formulaire. **Implémenté** : `xdsl/parser.py` (grammaire),
`xdsl/compiler.py` (expansion), `xdsl/validators.py` (règles), testé dans
`xdsl/tests/test_compiler.py::TestDataSchema/TestExtractSchemas/TestUseEndpoint`
et `scripts/verify-hyperscript.mjs` (bout en bout, vrai moteur).

### Décision d'architecture : pas de rendu JSON côté client

QWeb (`xweb/engine/`) est un moteur **server-only** — rien dans ce repo ne
sait interpréter un composant xweb en JavaScript. Une conception où le
serveur répondrait en JSON et où le DSL re-rendrait un composant (`table`,
`card`…) dans le navigateur à partir de ce JSON demanderait de réécrire une
deuxième fois le moteur de rendu, en JS — hors de portée de ce DSL. La
requête reste donc pilotée par **htmx**, comme le reste du projet
(docs/spec-v1.md, principe "un seul moteur de template") :

- `onloading`/`onsuccess`/`onerror` : du contenu DSL **statique**,
  précompilé une seule fois côté serveur (pas de liaison aux champs de la
  réponse JSON — un `toast { "Contact créé !" }` fixe, jamais
  `toast { "Bonjour ${response.name}" }`).
- Pour un vrai rendu dynamique du résultat (`receive.target`), l'endpoint
  diffuse, au succès, un **CustomEvent DOM** sur l'élément cible
  (`document.querySelector(target).dispatchEvent(new CustomEvent(event))`,
  `event` par défaut `{nom}:done`) — c'est à l'élément CIBLE de
  s'auto-rafraîchir depuis le serveur avec un vrai
  `hx-trigger="{event} from:body"` (même idiome que `calendar:select` ->
  `xweb.datepicker`, ou xpulse). Le "rendu" reste donc un aller-retour
  serveur normal, jamais du JSON interprété en JS.

La **validation de la réponse** (`receive.schema`) est aussi un aller-retour :
c'est le HYPerscript généré qui vérifie la forme JSON arrivée, jamais un
re-rendu. voir la section `endpoint` plus bas.

### Schéma `data` — validation, décorateurs

```qml
data contact_form {
    name: string @required @min_length(3)
    email: string @required @email
    role: string @in(["admin", "editor"])
    phone: string
}
```

Chaque `@décorateur[(args)]` est une règle de `xdsl/validators.py::BUILTIN_VALIDATORS`
(`required`, `min_length`, `max_length`, `min`, `max`, `email`, `pattern`,
`in`) — un champ sans `@required` est optionnel (`Required` est une règle
comme une autre, pas un cas spécial). `data` n'émet **aucun XML** : c'est un
schéma réutilisable, consommé de deux façons —

1. **Côté serveur, chemin canonique — un vrai modèle Pydantic** via
   `xdsl.api.extract_models()`. Depuis la décision « pas d'ORM → Pydantic
   comme source de vérité » (tous les schémas servent à la fois la
   validation et, plus tard, le rendu de champ façon `t-field` d'Odoo), le
   bloc `data` compile vers un `BaseModel` construit par
   `xdsl/pydantic_bridge.py::build_model()`, où chaque `@décorateur` est
   attaché comme `AfterValidator` réutilisant la **même classe** Validator
   que l'ancien chemin (jamais de contraintes Pydantic natives ré-implantées :
   pydantic ancrerait `pattern` en full-match quand le moteur fait du
   préfixe, `ge` refuserait les non-nombres quand `MinValue` passe au
   travers). Le `value_type` devient une vraie annotation **appliquée**
   (l'ancien `validate_dict` ne typait jamais), `@required` rend le champ
   requis au modèle, `extra="ignore"` pour les champs inconnus du payload.

   ```python
   from xdsl.api import extract_models, validate_model

   models = extract_models(open("contacts.dsl").read())
   errors = validate_model(models["contact_form"], request_json)
   # {} si valide, sinon {"name": ["Minimum 3 caractères"], ...}
   # drop-in de validate_dict : mêmes règles, mêmes messages français
   # (les messages de plusieurs règles d'un champ sont agrégés en une
   # entrée). Ou construction objet typée, prête à persister :
   contact = models["contact_form"].model_validate(request_json)
   ```

   Une route HTML (via `xweb/forms.py::parse_form`) peut aussi recevoir
   directement le modèle : `parse_form(form, models["contact_form"])` —
   parse_form n'exige qu'un `BaseModel`, le pont fournit exactement ça.
   Le chemin historique `xdsl.api.extract_schemas()` + `validate_dict()`
   reste disponible (nécessaire aux vecteurs du miroir JS `validators.js`),
   mais toute nouvelle validation doit passer par `extract_models`.

2. Par `endpoint.send: contact_form` (documentation de la forme envoyée —
   ne génère pas encore d'attributs HTML5 natifs sur les `<input>`, voir
   Limites plus bas) et par `endpoint.receive.schema` (validation de la
   RÉPONSE, voir la section `endpoint`). Un `channel { validate: contact_form }`
   exporte aussi `window.XWEB_SCHEMAS_JSON[nom]` — le **JSON Schema** de
   `model_json_schema()` du même modèle (aux côtés des listes de règles de
   `XWEB_SCHEMAS`), réservé au futur rendu de champ et à tout consommateur
   JSON Schema.

**Composition et listes typées** : un champ peut être une RÉFÉRENCE à un
autre `data` ou une liste typée —

```qml
data address {
    street: string @required
    city:   string @required
}

data contact {
    name:    string @required
    address: address            // objet imbriqué (référence)
    phones:  list[phone]        // liste d'objets (réf + décorateurs)
    tags:    list[string]       // liste de primitifs
}
```

`list[item]` accepte un primitif (`string`, `int`…) ou une référence ;
`xdsl/parser.py::split_value_type()` est la classification unique partagée
par tous les étages (`("primitive", t)` / `("ref", nom)` / `("list", item)`).
Côté serveur, `extract_models` construit la **map complète** de modèles
imbriqués (`_ModelBuilder` récursif, `xdsl/pydantic_bridge.py`) et rejette
les références circulaires au build (« Référence circulaire entre schémas »,
jamais un RecursionError de validation). Les erreurs remontent au chemin
doté serveur (`address.city`, `phones.0.number`) et au chemin crochets
client (`phones[0].number`) — même descente, deux conventions d'index.
Côté client, `validators.js` descend dans les mêmes `ref`/`list` (voir
`endpoint` ci-dessous). Un type composé est un `ValueError` explicite sur le
chemin plat legacy `extract_schemas`/`validate_dict` — le chemin canonique,
composés inclus, est `extract_models`/`validate_model`/`validate_model_list`.

### `endpoint` — la requête elle-même

```qml
endpoint save_contact {
    method: POST
    url: "/api/contacts"
    send: contact_form
    headers: { "Content-Type": "application/json" }
    auth: cookie

    receive {
        type: json
        schema: contact_form
        target: "#contact-table"
        event: "save_contact:done"        // optionnel, défaut "{nom}:done"
    }

    onloading { p { "Envoi..." } }
    onsuccess { toast { "Contact créé !" } }
    onerror { toast { "Erreur" } }
}
```

`endpoint` n'émet rien non plus par lui-même — c'est une déclaration
réutilisable, consommée par la prop `use: nom` sur n'importe quel élément
(brut ou composant xweb importé) :

```qml
form { use: save_contact
    input { name: "name"; required: true }
    button { type: "submit" "Envoyer" }
}
```

**Génère** (résumé — voir `Compiler._endpoint_attrs`/`_endpoint_hyperscript`
pour le détail exact) :

```xml
<form hx-post="/api/contacts" hx-headers='{"Content-Type": "application/json"}'
      hx-indicator="#save_contact-1-indicator" hx-swap="none"
      _="on htmx:afterRequest
         js(event)
           let ok = event.detail.successful;
           document.querySelector('#save_contact-1-onsuccess').hidden = !ok;
           if (ok) { var t = document.querySelector('#contact-table'); if (t) t.dispatchEvent(new CustomEvent('save_contact:done')); }
         end">
    <t t-call="xweb.csrf" t-att-token="csrf_token"/>
    <input name="name" required="required"/>
    <button type="submit">Envoyer</button>
</form>
<div id="save_contact-1-indicator" class="htmx-indicator"><p>Envoi...</p></div>
<div id="save_contact-1-onsuccess" hidden="hidden"><t t-call="xweb.toast">...</t></div>
<div id="save_contact-1-onerror" hidden="hidden"><t t-call="xweb.toast">...</t></div>
```

- `hx-indicator` cible une `class="htmx-indicator"` — convention **native**
  htmx (`xweb/static/htmx.min.js` injecte lui-même le CSS d'opacité), aucune
  règle à ajouter dans ce projet.
- Le suffixe numérique (`save_contact-1-...`) est propre à CHAQUE usage de
  `use: save_contact` dans un fichier — deux éléments peuvent réutiliser le
  même endpoint sans collision d'id (`Compiler._use_counter`).
- `method: POST`/`PUT`/`PATCH`/`DELETE` sur un `form` **brut** injecte
  automatiquement `<t t-call="xweb.csrf" t-att-token="csrf_token"/>` comme
  premier enfant. Sur un `t-call="xweb.form"`, le jeton est plutôt transmis
  via sa propre prop `token` (xweb.form pose déjà son propre champ
  `csrf_token` en interne, `xweb/components/form.xml`) — jamais les deux à
  la fois. `xweb.button`/`xweb.form` doivent déclarer `hx_headers`/
  `hx_indicator` (en plus des `hx_get`/`hx_post`/… déjà là) pour que `use:`
  s'applique correctement sur leurs t-call — déjà fait pour ces deux-là ;
  un composant tiers qui veut supporter `use:` doit faire pareil.
- Un `use: nom_inconnu` lève une `xdsl.compiler.CompileError` à la
  compilation — jamais un élément inerte silencieux (même posture que le
  raccourci `<xweb:...>`, `docs/language.md`). Idem pour `receive.schema:
  nom_inconnu` (une validation morte qui laisserait tout passer serait pire
  que pas de validation du tout).

### Validation de la réponse (`receive { schema, list }`)

Contrairement à v1 (où `receive.schema` ne documentait que la forme
attendue), le schema est maintenant **câblé** : le hyperscript généré valide
la réponse JSON au succès HTTP —

```qml
endpoint list_contacts {
    method: GET
    url: "/api/contacts"
    receive {
        type: json
        schema: contact
        target: "#rows"          // re-rendu via hx-trigger depuis le serveur
        event: "contacts:loaded"
        list: true               // la réponse est un TABLEAU d'objets
    }
    onsuccess { p { "Contacts chargés" } }
    onerror { p { "Erreur de chargement" } }
}
```

Au succès HTTP, le hyperscript appelle
`window.XwebValidate("contact", JSON.parse(responseText), { list: true })`
(exporté par `xweb/static/validators.js`, le miroir JS du moteur Python) —
une réponse **invalide** passe par le chemin **onerror** (jamais onsuccess ni
l'event de refresh) ; un corps non-JSON est invalide, jamais une exception.
C'est de l'**UX** (afficher l'erreur au client, préserver un tableau
semi-à-jour) : la source de vérité reste le serveur
(`xdsl.api.validate_response(models, "contact", payload, as_list=True)`).
Le scaffolding exporte le descripteur dans `window.XWEB_SCHEMAS` + la
**fermeture transitive** des `ref`/`list[ref]` composés (`_schema_closure`,
partagée avec le bootstrap d'un `channel { validate: }` composé).
`receive.list: true` ✔ sa validation passe par `validate_model_list`
(`{"__root__": ["Doit être une liste valide."]}` si ce n'est pas un tableau)
et, côté JS, par `XwebValidate(..., { list: true })` (`__root__` idem).

**Piège lxml → forme `js(event)` imposée** : le script est écrit multi-ligne
pour la lisibilité du XML compilé, mais lxml normalise les `\n` d'attributs
en **espaces** au round-trip `QwebRegistry` — le hyperscript reçoit
TOUJOURS la forme aplatie, et la structure `if/else/end` d'hyperscript ne
survit pas à cet aplatissement (`Unexpected Token : else`, vérifié au vrai
`_hyperscript.min.js`). Tout le routing de `_endpoint_hyperscript` est donc
**un seul bloc `js(...) end`** (JS verbatim, `;`-séparé) : try/catch du
`JSON.parse`, `XwebValidate`, bascule `hidden`, dispatch conditionnel —
jamais un if hyperscript. `npm run verify:endpoint-dsl` prouve cette forme
RÉELLE (aplatie par un vrai rendu QwebRegistry) contre le vrai
htmx/_hyperscript/validators.js en jsdom. Un endpoint sans onsuccess/onerror/
`receive.target` n'émet aucun `_` (rien à révéler ni diffuser).

### Limites connues (v1)

- **Pas d'attributs HTML5 natifs auto-générés** depuis `data`/`@décorateurs`
  sur les `<input>` d'un formulaire — `required`/`type="email"`/etc.
  restent à écrire à la main sur chaque champ (comme dans l'exemple
  ci-dessus). `data` sert aujourd'hui la validation **serveur**
  (`extract_schemas`/`extract_models`) et **client de la réponse**
  (`receive { schema }`), pas encore le HTML généré — le modèle Pydantic est
  en place et `model_json_schema()` est déjà exporté
  (`window.XWEB_SCHEMAS_JSON`) : l'étage rendu de champ façon `t-field`
  partira de là.
- La validation client de la réponse (`receive { schema }`) est de l'**UX**
  uniquement — le serveur reste la source de vérité (`validate_response`).
  Un client malveillant peut toujours envoyer/ignorer n'importe quoi ;
  une route qui applique ONLY le hyperscript généré (sans route Python de
  validation) ne valide rien.
- **Un seul argument par filtre/décorateur en interpolation nue** — même
  limite que le chaînage de filtres QWeb (voir section Filtres) : sans
  rapport direct avec `data`, mais la même prudence s'applique aux
  décorateurs à arguments.

## Channels temps réel déclaratifs (`channel`/`use_channel:`)

Sucre déclaratif au-dessus de `xweb/static/live_channel.js` (SSE/WS unifiés,
reconnexion avec backoff + timeout de connexion) — décrire un flux temps
réel une fois, puis l'attacher à un élément avec `use_channel:`, plutôt que
d'écrire le `<script>` de bootstrap à la main sur chaque page. **Implémenté** :
`xdsl/parser.py` (`ChannelDef`/`ChannelOnMessage`), `xdsl/compiler.py`
(`Compiler._write_channel_bootstrap`), testé dans
`xdsl/tests/test_parser.py::TestParserChannel`,
`xdsl/tests/test_compiler.py::TestChannel/TestChannelEndToEnd`,
`xdsl/tests/test_serialize.py::test_channel_roundtrip`, et bout-en-bout
(vrai DOM, vrai JS généré, vrai `validators.js`) par
`npm run verify:channel-dsl`.

```qml
data contact_form {
    count: int @min(0)
}

channel contacts_feed {
    url: "/stream"                 // requis — passé tel quel à XwebLiveChannel
    channels: ["chat", "notif"]    // optionnel — filtre les events SSE/l'enveloppe {channel,...} en WS
    transport: "sse"               // "sse" | "ws" | "auto" (défaut) — voir live_channel.js
    connect_timeout_ms: 5000       // optionnel — force une reconnexion si rien ne répond
    validate: "contact_form"       // optionnel — référence un schéma `data` déclaré dans CE fichier
    persist: "last_contact"        // optionnel — écrit chaque message dans xweb/static/storage.js
    onmessage {
        bind: { "#counter": "count" }        // écrit data["count"] en textContent de #counter
        refresh: "#contacts-table"           // déclenche un hx-trigger sur cet élément
        dispatch: true                       // diffuse un CustomEvent DOM réel sur document
        event: "contacts:changed"            // optionnel — nom PARTAGÉ par refresh/dispatch, défaut "{nom du channel}:message"
    }
}

component contacts_page {
    div { use_channel: contacts_feed
        span { id: "counter"  "0" }
        div { id: "contacts-table"  ... }
    }
}
```

**Génère** (résumé — voir `Compiler._write_channel_bootstrap` pour le détail
exact), un `<script>` juste après l'élément porteur de `use_channel:` :

```html
<script>
(function () {
  window.XWEB_SCHEMAS = window.XWEB_SCHEMAS || {};
  window.XWEB_SCHEMAS["contact_form"] = {"count": [["min", [0]]]};
  var _xwebChannelOpts = {"url": "/stream", "channels": ["chat", "notif"], "transport": "sse", "connectTimeoutMs": 5000};
  _xwebChannelOpts.onMessage = function (channel, data) {
    if (window.XwebValidate && !window.XwebValidate("contact_form", data).valid) return;
    (function () { var el = document.querySelector("#counter"); if (el && data) el.textContent = data["count"]; })();
    (function () { var t = document.querySelector("#contacts-table"); if (t && window.htmx) window.htmx.trigger(t, "contacts:changed", data); })();
    document.dispatchEvent(new CustomEvent("contacts:changed", { detail: { channel: channel, data: data } }));
    if (window.XwebStorage) window.XwebStorage.set("last_contact", data);
  };
  if (window.XwebLiveChannel) { new window.XwebLiveChannel(_xwebChannelOpts); }
  else { console.error('[xdsl] XwebLiveChannel introuvable — xweb/static/live_channel.js doit être chargé par la page'); }
})();
</script>
```

- **La page doit charger `xweb/static/live_channel.js`** (et `storage.js`
  si `persist:` est posé, et `validators.js` si `validate:` est posé) —
  jamais injecté automatiquement par le DSL, même contrat que
  `htmx.min.js`/`_hyperscript.min.js` (docs/theming.md). Sans
  `live_channel.js` chargé, le bootstrap échoue proprement
  (`console.error`, jamais une exception qui casse le reste de la page).
- **`bind:`** écrit toujours en `textContent`, jamais `innerHTML` — pas de
  surface XSS depuis une donnée temps réel non fiable (même garde-fou que
  `xweb.notifications`/`live_channel.js` §Sécurité).
- **`refresh:`** ne rend JAMAIS le JSON reçu directement dans le DOM — même
  décision d'architecture que `endpoint`/`receive` plus haut (pas de moteur
  QWeb côté client) : `refresh:` se contente de déclencher un
  `htmx.trigger()` sur la cible, qui doit avoir son propre
  `hx-get`/`hx-trigger="{event} from:body"` pour aller rechercher le HTML
  à jour côté serveur.
- **`use_channel: nom_inconnu`** lève une `xdsl.compiler.CompileError` à la
  compilation (`Compiler._resolve_use_channel`) — même posture que
  `use: nom_inconnu` pour `endpoint`.
- **`validate: "schema_inconnu"`** lève aussi une `CompileError` (compile-time,
  jamais un `window.XWEB_SCHEMAS["schema_inconnu"]` silencieusement absent
  découvert seulement au premier message reçu en prod).

### `dispatch: true` — la porte de sortie vers du hyperscript/JS arbitraire

`onmessage {}` reste une grammaire **fermée** (`bind`/`refresh`/`event`/
`dispatch`, rien d'autre — une clé inconnue lève `ParseError`) : impossible
d'y écrire du JS ou du hyperscript brut. Mais `bind:`/`refresh:` ne
couvrent pas tout — une classe CSS temporaire, une animation, une
manipulation de DOM plus riche que "un champ en textContent". Plutôt
qu'ouvrir `onmessage {}` à du code arbitraire, `dispatch: true` diffuse un
vrai `CustomEvent` DOM sur `document` à chaque message (après le garde-fou
`validate:` s'il est posé, comme `bind:`/`refresh:`/`persist:`) :

```js
document.dispatchEvent(new CustomEvent(EVENT_NAME, { detail: { channel: channel, data: data } }));
```

`EVENT_NAME` est le même `event:` (ou son défaut `"{nom du channel}:message"`)
que `refresh:` utilise pour son `htmx.trigger()` — un seul champ pour les
deux mécanismes. N'importe quel élément de la page récupère alors le
message via du **hyperscript ordinaire**, déjà supporté partout ailleurs
dans le DSL (attribut `_`, aucune syntaxe nouvelle) :

```qml
span {
    id: "contacts-count"
    class: ["badge", "badge-neutral"]
    _ {
        on contacts:changed from document
            add .badge-primary
            wait 400ms
            remove .badge-primary
    }
    "0"
}
```

`event.detail.channel` permet de discriminer si plusieurs sous-channels
(SSE nommés, ou l'enveloppe WS `{channel, data}`) arrivent sur le même
`channel {}` — `dispatch: true` diffuse pour **chaque** message reçu sur
l'instance, sans filtrer par sous-channel (même portée que `bind:`).
Fonctionne identiquement quel que soit `transport:` (`sse`/`ws`/`auto`) —
`onMessage` est le même code généré des deux côtés, vérifié bout-en-bout
sur les deux transports (vrai `_hyperscript.min.js`, vrai serveur SSE+WS
de test) par `npm run verify:channel-dispatch`.

### Validation côté client (`validate:` + `xweb/static/validators.js`)

`validate: "nom"` référence un schéma `data` déclaré dans le **même
fichier** — le compilateur exporte alors ce schéma tel quel en JSON dans
`window.XWEB_SCHEMAS["nom"]`, colocalisé dans le `<script>` du bootstrap
(garanti disponible avant que `onMessage` ne puisse jamais s'exécuter,
même fonction synchrone). `xweb/static/validators.js` est un port JS du
même ensemble **fermé** de règles que `xdsl/validators.py`
(`required`/`min_length`/`max_length`/`min`/`max`/`email`/`pattern`/`in`,
mêmes messages français) — parité vérifiée mécaniquement, pas juste
"relue", par `npm run verify:validators` (exécute les DEUX moteurs sur les
mêmes vecteurs de test et compare les résultats).

**Ceci reste de l'UX, jamais de la sécurité** — comme rappelé dans
`xweb/static/validators.js` lui-même : un client hostile ignore
trivialement cette validation. La seule validation qui compte pour la
sécurité reste `xdsl.validators.validate_dict()` côté serveur, sur tout ce
qui arrive par `endpoint`/`receive` (section précédente). `validate:` sur
un `channel` sert uniquement à éviter d'appliquer un `bind:`/`refresh:`/
`persist:` sur une donnée malformée reçue en live (ex. un bug transitoire
côté émetteur du flux), pas à se défendre contre un attaquant.

### Limites connues (v1)

- Un seul `data` schema par `validate:`, résolu par nom dans le même
  fichier — pas de schéma partagé entre plusieurs fichiers `.dsl` compilés
  séparément (chacun a son propre `window.XWEB_SCHEMAS`, fusionnés en
  runtime seulement s'ils finissent sur la même page).
- `bind:` ne fait qu'un `textContent` simple sur un seul champ — pas de
  formatage/interpolation (`"${count} contacts"`), pas de binding sur un
  attribut (seulement le texte d'un élément).
- Pas de "unsubscribe" déclaratif — le channel vit tant que l'élément
  porteur de `use_channel:` reste dans le DOM (comportement de
  `XwebLiveChannel`, pas spécifique au DSL).

## Prochaines étapes

Les étapes 1 (parser), 2 (intégration registry) et 4 (validation round-trip,
`xdsl/tests/`) sont **faites** ; l'étape 3 (cas réels) est partielle :

1. ~~**Parser Python** — une classe qui lit le DSL et produit du XML~~ — fait (`xdsl/parser.py`, `xdsl/compiler.py`)
2. ~~**Intégration QwebRegistry** — intercepter les fichiers `.dsl` avant enregistrement~~ — fait (`xweb/engine/registry.py` : `register_source` détecte le DSL par extension `.dsl` OU par contenu — pas de `<` en tête — et `register_dir` scanne `*.dsl` comme `*.xml` ; le paquet `xdsl` est embarqué dans le wheel, `pyproject.toml`). Erreur claire (TemplateSyntaxError) si un `.dsl` arrive sans xdsl installé.
3. **Test sur des cas réels** — en cours : `catalogue.dsl` (tous les composants xweb) est le fixture vivant ; y ajouter login/CRUD/kanban end-to-end.
4. ~~**Validation** — chaque sortie DSL doit être identique à l'XML QWeb équivalent~~ — fait (`xdsl/tests/test_compiler.py`, `test_serialize.py`).

Bonus consommé depuis l'écriture de ce doc : comparaisons `< > <= >= != ==` et
ternaires `cond ? a : b` normalisés en Python (`a if (cond) else b`) — voir
AGENTS.md pour leurs limites exactes (niveau racine uniquement, pas de `if`
inline, `?=` intact).
