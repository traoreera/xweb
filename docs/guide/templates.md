# Templates QWeb

Antisèche des directives `t-*`, chacune avec un exemple minimal vérifié contre le moteur réel (`xweb/engine/compiler.py`). Pour le détail et les décisions derrière chaque choix, voir [`language.md`](../language.md) (onglet *Référence*) — cette page est volontairement courte.

## `t-esc` vs `t-out`

`t-esc` échappe toujours ; `t-out` n'échappe **que** si la valeur n'est pas déjà un `Markup` de confiance (sortie d'un autre `t-call`/`render()`, jamais une chaîne construite à la main). Défaut : `t-esc`, systématiquement, pour tout ce qui vient d'un formulaire, d'une API ou d'un autre plugin.

```xml
<p><t t-esc="comment.body"/></p>          <!-- toujours -->
<div><t t-out="trusted_widget_html"/></div>  <!-- seulement si ça vient d'un rendu xweb -->
```

## `t-if` / `t-elif` / `t-else`

```xml
<t t-if="user">
    <span>Connecté</span>
</t>
<t t-elif="anonymous_allowed">
    <span>Invité</span>
</t>
<t t-else="1">
    <a href="/login">Se connecter</a>
</t>
```

`t-else="1"` — la valeur n'a pas de sens, seule la présence de l'attribut compte (convention du moteur, pas une expression évaluée).

## `t-foreach` / `t-as`

```xml
<t t-foreach="items" t-as="item">
    <li><t t-esc="item['label']"/></li>
</t>
```

Pas de `t-foreach="range(...)"` — `range` n'est pas dans les builtins autorisés (`eval(expr, {"__builtins__": {}}, ctx)`) ; construisez la liste côté Python et passez-la déjà prête.

## `t-att-*` / `t-attf-*`

```xml
<!-- t-att-* : la valeur est une EXPRESSION Python -->
<a t-att-href="account_path + 'security'">Sécurité</a>

<!-- t-attf-* : interpolation {{...}} dans une chaîne littérale -->
<a t-attf-href="{{account_path}}security">Sécurité</a>
```

Les deux échappent toujours (jamais de `Markup` possible sur un attribut, contrairement à `t-out`). `hx-*` et `_` (`_hyperscript`) sont des attributs **normaux** — `t-att-hx-post="url"` ou juste `hx-post="/plugins/x/y"` en dur, les deux marchent, le compilateur ne les traite jamais spécialement.

## `t-call` + props + `slot`

```xml
<t t-call="xweb.card" title="Statut" extra_class="">
    <p>Contenu passé en slot.</p>
</t>
```

**Contexte isolé** — la cible ne voit *que* les props explicitement données, jamais le reste du contexte de l'appelant :

```xml
<!-- account_path n'existe PAS dans account.tabs sans ce t-att- -->
<t t-call="account.tabs" tab="security" t-att-account_path="account_path"/>
```

Prop littérale (`title="Statut"`) → chaîne fixe, jamais évaluée. Prop calculée (`t-att-title="page_title"`) → expression Python. Les deux formes coexistent sur un même appel.

## `t-set` / `t-value`

```xml
<t t-set="badge" t-default="'neutral'"/>          <!-- prop avec défaut -->
<t t-set="total" t-value="len(items) if items else 0"/>  <!-- calcul intermédiaire -->
```

`t-default` définit une variable seulement si elle n'existe pas déjà dans le contexte (pattern "prop avec défaut" pour un composant) ; `t-value` l'écrase toujours.

## Filtres `| nom[:args]`

```xml
<t t-esc="price | money"/>                 <!-- 1234.5 -> "1 234,50 €" -->
<t t-esc="created_at | date"/>             <!-- ISO -> "2026-09-03 14:30" -->
<t t-esc="names | join:', '"/>             <!-- ["a","b"] -> "a, b" -->
<t t-esc="maybe_missing | default:'—'"/>   <!-- valeur absente/vide -> "—" -->
```

Set fermé, volontairement — voir `xweb/engine/filters.py` pour la liste complète et [`language.md#filtres`](../language.md#filtres-de-valeur-nomargs) pour le détail de chacun. Un nom de filtre inconnu n'est **jamais** traité comme un filtre : `a | b` avec `b` absent de la liste reste l'opérateur Python `|` (OR bit à bit) normal.

## `t-tr` — traduction du texte statique

```xml
<h1 t-tr="1">Organisation</h1>
```

Uniquement pour un texte **littéral** du gabarit — une valeur composée passe par `_()` :

```xml
<t t-esc="_('Bonjour ' + name)"/>
```

`_`/`locale`/`locales` vivent dans le contexte de base (`xweb/mount.py`) — un composant générique ne les appelle jamais lui-même, l'appelant traduit avant de passer la prop (voir [`i18n.md`](../i18n.md)).

## `t-inherit` — étendre un template sans le forker

```xml
<template t-name="mon_plugin.button_badge" t-inherit="xweb.button" t-inherit-mode="extension">
    <xpath expr="//button" position="inside">
        <span class="badge badge-accent">Nouveau</span>
    </xpath>
</template>
```

`position` : `before` / `after` / `inside` / `replace` / `attributes`. `t-inherit-mode="extension"` (défaut) patche l'arbre **partagé** de la cible — tout appelant de `xweb.button` voit le patch. `t-inherit-mode="primary"` duplique l'arbre déjà résolu de la cible sous le `t-name` du patch — une copie figée, pas un lien vivant. Détail complet, résolution de conflits entre deux patches sur le même nœud, chaînage : [`inheritance.md`](../inheritance.md).

## Ce qu'il n'y a *pas*

- **Aucun builtin** dans une expression — `len()`, `sorted()`, `str()` lèvent `NameError`, silencieusement récupéré comme une valeur `None` (falsy). Précalculez côté Python et passez la valeur déjà prête, ou utilisez un filtre (`| length`, `| join:...`).
- **Un nom absent du contexte** rend `None`, jamais une exception — sauf s'il fait partie d'une expression plus large qui, elle, plante pour une autre raison (`TemplateError`, remonté tel quel). Voir l'encart sur `not <nom absent>` dans [`language.md`](../language.md#t-if-t-elif-t-else).
