# Héritage — `t-inherit` et XPath

> **Implémenté** — `xweb/engine/inherit.py` + `xweb/engine/registry.py`, 24 tests dans `tests/test_inherit.py`, tous verts. Ce document décrit ce qui existe réellement, pas seulement ce qui est prévu.

C'est la raison d'être de xweb (*spec-v1.md* principe 7) : un plugin étend un template qu'il ne possède pas, sans le forker.

## Syntaxe

```xml
<template t-name="crm_app.button_badge" t-inherit="xweb.button" t-inherit-mode="extension">
    <xpath expr="//button" position="inside">
        <span class="badge badge-accent">CRM</span>
    </xpath>
</template>
```

- `t-inherit` — `t-name` du template ciblé.
- `t-inherit-mode="extension"` (défaut) — le template original reste la base ; ce document ne fait qu'y appliquer des patchs XPath, en place, partagés par tout appelant.
- `t-inherit-mode="primary"` — duplication complète, voir [primary](#primary) plus bas.
- `<xpath expr="…" position="…">` — un ou plusieurs, appliqués dans l'ordre du document.

## `position`

| Valeur | Effet |
|---|---|
| `before` | insère le contenu du `<xpath>` juste avant le nœud ciblé |
| `after` | insère juste après |
| `inside` | insère comme dernier enfant du nœud ciblé |
| `replace` | remplace le nœud ciblé entièrement |
| `attributes` | ajoute/modifie des attributs du nœud ciblé (enfants `<attribute name="…">valeur</attribute>`) |

```xml
<xpath expr="//button" position="attributes">
    <attribute name="data-crm">1</attribute>
</xpath>
```

## Résolution — priorité et ordre

Plusieurs extensions peuvent cibler le même `t-inherit`. Résolution triée par `priority` (entier, défaut `0`, plus petit = appliqué en premier) puis par ordre d'enregistrement à priorité égale — jamais par ordre d'import implicite.

```python
PatchRegistry.register(
    t_name="crm_app.button_badge",
    inherit="xweb.button",
    priority=10,
    source_plugin="crm_app",
)
```

Le nombre d'appels à `PatchRegistry.register` (ou l'équivalent déclaré en XML via `t-inherit`, selon ce qui sera choisi en Phase 2 — voir *xweb Blueprint* §7) n'est pas limité : cinq plugins peuvent tous étendre `xweb.button`, chacun sans savoir que les autres existent.

## Conflits

Deux extensions qui ciblent le **même** `expr` avec `position="replace"` sont en conflit réel (l'une écrase forcément le travail de l'autre). Comportement par défaut :

> Un warning est loggé, nommant les deux plugins en conflit ; l'extension de plus haute priorité (valeur la plus basse) s'applique, l'autre est ignorée pour ce nœud précis.

Comportement par défaut implémenté et testé (`test_conflict_on_replace_keeps_lowest_priority_and_warns`, `test_non_conflicting_ops_on_same_patch_still_apply_when_one_loses` — perdre un conflit ne supprime que l'op en cause, pas tout le patch qui la porte).

**Tranché : jamais d'exception, même pas en mode debug.** `xweb.button` (ou tout composant partagé) peut être utilisé par n'importe quelle page de l'appli — lever une exception sur un conflit le concernant ferait planter (500) toutes les pages qui l'utilisent, à cause d'un désaccord entre deux plugins qui n'ont peut-être aucun rapport avec la page qu'un visiteur essaie de charger. Disproportionné. Le compromis retenu à la place : **résolution anticipée au boot** (`QwebRegistry.check_all()`, appelé depuis `XwebExtension.init()`) — les conflits sortent dans le log de démarrage, pas seulement quand une page les déclenche par hasard des heures plus tard. Testé (`test_check_all_surfaces_conflicts_without_any_render_call`, `test_init_surfaces_xpath_conflicts_in_boot_log`).

Deux extensions sur le même nœud avec `position="inside"` ou `"attributes"` (non contradictoires — l'une ajoute, l'autre aussi) ne sont **pas** un conflit : les deux s'appliquent, dans l'ordre de priorité.

## primary

`t-inherit-mode="extension"` patch la cible **en place** : tout le monde qui appelle `xweb.button` voit la version patchée, y compris ceux qui n'ont jamais entendu parler de l'extension. `t-inherit-mode="primary"` fait l'inverse — il **duplique** la cible sous le **propre `t-name` du patch**, et seul ce nouveau nom porte le changement :

```xml
<template t-name="crm_app.custom_button" t-inherit="xweb.button" t-inherit-mode="primary">
    <xpath expr="//button" position="inside">
        <span class="badge badge-accent">CRM</span>
    </xpath>
</template>
```

Après ça : `xweb.button` rend exactement comme avant — inchangé, jamais touché. `crm_app.custom_button` est un **tout nouveau template**, indépendant, appelable via `t-call="crm_app.custom_button"` comme n'importe quel autre. Les deux coexistent ; rien ne force à choisir entre patcher en place ou dupliquer, un plugin peut faire l'un pour un composant et l'autre pour un autre.

**Une copie figée, pas un lien vivant.** La duplication se fait la première fois que `crm_app.custom_button` est demandé (paresseux, comme le reste de la résolution) : elle copie l'arbre **déjà résolu** de la cible (patches `extension` déjà appliqués sur elle compris), puis applique ses propres `<xpath>` par-dessus. Si `xweb.button` change *après coup* (rechargement d'un plugin qui le patche autrement) sans que `crm_app.custom_button` soit lui-même ré-enregistré, la copie ne suit pas — c'est le sens même de "dupliquer", pas "encore un patch".

**Composable avec `extension`** : une fois qu'un template `primary` a été résolu une première fois, il n'est plus distingué d'un vrai template de base — un patch `extension` ordinaire peut le cibler à son tour (`t-inherit="crm_app.custom_button" t-inherit-mode="extension"`), et se comporte exactement comme s'il ciblait n'importe quel autre composant. Un `primary` peut aussi cibler un autre `primary` (chaîne A → B → C), chaque maillon restant indépendant des suivants.

**Cible introuvable** → `TemplateError` explicite au moment de la résolution — jamais un template silencieusement absent. `QwebRegistry.check_all()` (appelé au boot par `XwebExtension.init()`, comme pour les conflits `extension`) résout tous les `primary` en attente dès le démarrage, pas seulement à la première page qui les rend — même philosophie que les conflits `replace` : une cible cassée doit apparaître dans le log de boot, pas des heures plus tard sur la page d'un visiteur qui n'a rien à voir avec le plugin fautif.

Testé dans `tests/test_inherit.py` : duplication sans toucher la cible, appelable via `t-call`, chaîne à plusieurs niveaux, composition avec `extension`, erreur claire sur cible manquante, copie pure sans `<xpath>`, nettoyage au unload de plugin (résolu ou non), résolution anticipée au boot.

## xpatch — copie-modification par rendu (`<t t-copy>`)

**Implémenté** — `xweb/engine/compiler.py::_render_copy`, les tests dans `tests/test_compiler.py` (branches `t-copy`) et `xdsl/tests/test_compiler.py` (`TestInlineCopy`, `TestInlineCopyEndToEnd`).

`extension` patche en place, `primary` duplique au niveau *template* — les deux sont **globaux** : ils s'enregistrent dans le registre, se résolvent au boot et s'appliquent à **tous** les appelants, ce qui peut déclencher des conflits entre plugins (`check_all()`). `t-copy` est la troisième manière, **par rendu et scoped à un fragment** : elle prend une *snapshot* de l'arbre **déjà résolu** de la cible (patches `extension`/`primary` compris), applique ses propres `<xpath>` **sur la copie seulement**, rend la copie, et **ne laisse aucune trace** — la source n'est jamais modifiée, rien n'est enregistré globalement, et deux pages peuvent donc composer un même template partagé différemment sans jamais se rejoindre dans un conflit.

```xml
<template t-name="expeditions.page_head">
    <head>
        <t t-copy="xweb.shell_head">
            <xpath expr="//link[@rel='stylesheet']" position="after">
                <link rel="stylesheet" href="/expeditions/site.css"/>
            </xpath>
        </t>
    </head>
</template>
```

- **Cible** : `t-copy="<t-name>"` — se résout via `QwebRegistry.get()`, **arbre résolu** (toute patch `extension`/`primary` déjà enregistrée sur la cible est dans la snapshot).
- **Ops** : enfants `<xpath expr="…" position="…">…</xpath>`, mêmes expressions et **mêmes positions** que `t-inherit` (voir [le tableau](#position)) — le vocabulaire est partagé : `xweb/engine/inherit.py::parse_xpath_ops` sert aux deux (`extract_patch` et `_render_copy`). Tout enfant **non-`<xpath>`** est une `TemplateError` — jamais du contenu silencieusement perdu.
- **Props** : comme `t-call` — `t-att-*`/attributs bruts passent (résolvés côté appelant, isolés dans la copie), **pas de slot** : l'endroit d'insertion est déjà décrit par les `position` des `<xpath>`, un contenu nominal n'aurait aucun sens.
- **Cible inconnue** → `TemplateError` au rendu.

### Sucre xdsl : `copy:` + `xpatch`

```dsl
component expeditions.page_head {
    head {
        copy: "xweb.shell_head"
        xpatch { expr: "//link[@rel='stylesheet']"; position: "after"
            link { rel: "stylesheet"; href: "/expeditions/site.css" }
        }
    }
}
```

Compile en `<head t-copy="xweb.shell_head"><xpath expr="…" position="after">…</xpath></head>`. `copy:` est un **nom de template littéral** entre guillemets (jamais une expression — la cible est résolue par nom brut dans le registre, comme `patch`/`use`). Les blocs `xpatch { expr: …; position: …; … }` sont les seuls enfants admis (CompileError sinon), les positions incluent `attributes` (enfants `link { disabled: "true" }` → `<attribute …/>`), et un élément void ne peut pas porter de `copy:` (pas de corps pour les ops — CompileError explicite).

## Ce qui n'est délibérément pas fait

- Pas de résolution XPath dynamique par requête — l'arbre fusionné est calculé une fois par changement de `PatchRegistry.version`, puis compilé et mis en cache (voir *xweb Blueprint* §5, diagramme des trois temps).
- Pas d'héritage multi-niveaux testé au-delà de deux niveaux (un patch qui étend un patch) — probablement supporté par construction puisque la résolution est juste un tri par priorité sur une liste de patchs ciblant le même `t-name` de base, mais pas explicitement vérifié tant qu'un test ne l'a pas prouvé.
