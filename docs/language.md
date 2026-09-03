# Le langage — référence des directives

Templates xweb = XML valide + attributs `t-*`. Un fichier `.xml` sans directive est un template QWeb valide qui affiche du HTML statique.

## `t-name`

Nom qualifié du template — clé du registre (`QwebRegistry`), cible d'un `t-call` ou d'un `t-inherit`.

```xml
<template t-name="xweb.button">…</template>
```

**Convention actée** : `<package_id>.<nom>`, calquée sur le `module.template` d'Odoo — `xweb.button` pour un composant du cœur, `crm_app.contacts_list` pour une page de plugin. Le `package_id` vient du `plugin.yaml` du plugin propriétaire (`spec-v1.md` §2.1). Validée en pratique sur 3 phases de code réel (`xweb.button`, `demo.index`, `crm_app.button_badge`...) sans la moindre friction — plus une question ouverte.

## `t-if` / `t-elif` / `t-else`

Branchement conditionnel sur un nœud — le nœud entier disparaît si la condition est fausse, contrairement à un `t-esc` qui ne contrôle qu'un texte.

```xml
<t t-if="href">
    <a t-att-href="href"><t t-esc="slot"/></a>
</t>
<t t-else="1">
    <button><t t-esc="slot"/></button>
</t>
```

**Piège réel avec un nom absent du contexte, pas juste falsy** (trouvé en écrivant `docs/guide/first-page.md`) : `_eval` (`engine/compiler.py`) attrape `NameError` sur toute l'expression et retombe sur `None` — jamais sur une négation booléenne de "absent = faux". Donc `t-if="entries"` sur un `entries` absent du contexte se comporte comme attendu (ne s'affiche pas), mais `t-if="not entries"` sur ce même nom absent **ne s'affiche pas non plus** — `not entries` vaut `None`, pas `True`, parce que l'échec sur le nom `entries` invalide l'expression entière avant que `not` s'applique. Ça ne se voit qu'à l'usage : le même test avec `entries` réellement présent dans le contexte mais valant `[]` fonctionne, lui, normalement (`not []` vaut bien `True`, aucun nom indéfini). Un `t-call` (isole son contexte, voir plus bas) qui oublie de repasser une prop attendue par la cible tombe régulièrement dans ce cas précis.

## `t-foreach` + `t-as`

Répète le nœud porteur une fois par élément de l'itérable. `t-as` nomme la variable de boucle ; `<var>_index`, `<var>_size`, `<var>_first`, `<var>_last` sont disponibles automatiquement (convention QWeb standard).

```xml
<li t-foreach="items" t-as="item">
    <span t-esc="item.label"/>
    <span t-if="item_last">— dernier</span>
</li>
```

## `t-esc` / `t-out`

- `t-esc="expr"` — sortie texte, toujours échappée HTML. Défaut pour tout contenu utilisateur.
- `t-out="expr"` — sortie brute si la valeur est un `Markup` déjà sûr (ex. un composant qui retourne du HTML de confiance), échappée sinon.

Ne jamais utiliser `t-out` sur une valeur qui vient directement d'un input utilisateur non passé par un composant de confiance.

## `t-att-*` / `t-attf-*`

- `t-att-nom="expr"` — attribut dont la valeur entière est une expression.
- `t-attf-nom="texte {{expr}} texte"` — attribut formaté, expressions interpolées dans une chaîne littérale.

```xml
<a t-att-href="url" t-attf-class="btn btn-{{variant}} {{extra_class}}">…</a>
```

## `t-call`

Inclusion d'un autre template par son `t-name`. Remplace `{% component %}`/`<component.x>` de microframe — un seul mécanisme d'inclusion, pas une syntaxe séparée pour les « composants ».

```xml
<t t-call="xweb.card">
    <t t-set="title">Contacts récents</t>
    <t t-call="xweb.button" variant="primary">Nouveau</t>
</t>
```

## `t-set` / `t-value`

Variable locale au template, portée au sous-arbre qui suit.

```xml
<t t-set="size_class" t-value="'btn-sm' if compact else 'btn-md'"/>
```

## Filtres de valeur `| nom[:args]`

Les expressions supportent un **set fermé** de filtres de formatage, chaînés par `|` (syntaxe QWeb/Odoo) :

```xml
<t t-esc="price | money"/>                    <!-- 1234.5 -> 1 234,50 € -->
<t t-esc="created_at | since"/>               <!-- durée relative -->
<t t-esc="items | length"/>                   <!-- len() — le builtin est absent -->
<t t-esc="names | join:','"/>                 <!-- itérable -> "a,b,c" -->
<t t-esc="meta | truncate:80"/>               <!-- troncature propre -->
```

**C'est un set FERMÉ, délibérément :** aucun plugin ne peut déclarer ni surcharger un filtre (`xweb/engine/filters.py`). Rien d'exécutable ne vient d'un plugin dans le moteur de rendu — sur cette surface, le champ d'attaque est nul. Les filtres sont de pures transformations de valeur, sans état, sans accès au contexte requête, et ne produisent **jamais** de `Markup` : le résultat passe toujours par `escape()` au point d'usage (`t-esc`), la frontière de sécurité reste intacte.

Filtres disponibles (liste exhaustive) :

| Filtre | Rôle | Exemple |
|---|---|---|
| `since` | durée relative | `created_at | since` → `il y a 3 h` |
| `date` / `datetime` | compaction date/heure | `created_at | date` → `2026-09-01 09:00` |
| `time` | heure seule | `created_at | time` → `09:00` |
| `money` | montant français | `1234.5 | money` → `1 234,50 €` |
| `number` | nombre français | `1234.56 | number` → `1 234,56` |
| `percent` | pourcentage | `0.125 | percent` → `12,5 %` |
| `upper` / `lower` / `title` / `capitalize` | casse | `s | upper` |
| `truncate[:n]` | troncature (`…`, défaut 80) | `s | truncate:120` |
| `slug` | slug ASCII | `"Ça va ?" | slug` → `ca-va` |
| `length` / `count` | `len()` (builtin absent) | `items | length` |
| `first` / `last` | premier / dernier élément | `items | first` |
| `join[:sep]` | joint un itérable | `names | join:','` |
| `default[:fallback]` | repli si vide (None/""/[]/{}/0) | `x | default:'N/A'` |
| `default_if_empty[:fallback]` | repli si None/"" uniquement | `x | default_if_empty:'—'` |
| `yesno` | `Oui`/`Non`/`—` | `flag | yesno` |
| `urlencode` | encodage URL | `q | urlencode` |

**Compatibilité :** un `|` suivi d'un nom **inconnu** de filtre n'est pas découpé — l'expression passe par `eval()` normal (ex. `a | b` reste un OU binaire Python, pas un crash). Un filtre absent (`missing | money`) ou en erreur renvoie `None`/la valeur brute, jamais une exception de rendu.

## Attributs qui ne sont pas des directives — htmx et `_hyperscript`

`hx-*` (htmx) et `_` (`_hyperscript`) traversent le compilateur sans interprétation — ce sont des attributs HTML ordinaires du point de vue de xweb, seul le navigateur les interprète. Aucun échappement requis : les deux sont XML-safe par construction (lettres/tirets pour `hx-*`, un simple underscore pour `_`). Voir [`shell.md`](shell.md) et *xweb Blueprint* §2 pour le détail de ce choix face à Alpine.js.

```xml
<button hx-post="/plugins/crm_app/contacts" hx-target="#list" hx-swap="beforeend"
        class="btn btn-primary">Ajouter</button>
```

**Point de vigilance** — préférer `hx-on="click: …"` (événement dans la valeur) à `hx-on:click="…"` (événement dans le nom, réintroduit un `:` qui déclenche la résolution d'espace de noms XML). Voir *xweb Blueprint* §2.
