# xdsl — extension VS Code

Coloration syntaxique, icône de fichier et auto-complétion pour `.dsl`
([`xdsl/`](../xdsl/) — voir [`docs/dsl-design.md`](../docs/dsl-design.md)
pour le langage lui-même). Extension locale, non publiée sur le
Marketplace — `publisher: xcore-integration` dans [package.json](package.json)
est un nom de convenance, pas une identité vérifiée.

## Ce que ça fait

- **Grammaire TextMate** ([syntaxes/xdsl.tmLanguage.json](syntaxes/xdsl.tmLanguage.json)) — mots-clés (`component`/`data`/`endpoint`/`channel`/`patch`/`copy`/...), décorateurs `@required`/`@min_length(3)`/... (le décorateur est signalé `invalid` s'il n'est pas dans l'ensemble fermé `xdsl/validators.py::BUILTIN_VALIDATORS` — une vraie faute que le compilateur rejettera aussi), chaînes avec interpolation `${...}`, blocs hyperscript `_ : ...`/`_ { ... }` (avec un sous-ensemble de mots-clés hyperscript reconnus), commentaires `//`/`/* */`, noms de balises/composants, attributs/champs.
- **Icône de fichier** ([icons/](icons/), light+dark) — via `contributes.languages[].icon`. C'est un **fallback** : elle ne s'affiche que si le thème d'icônes actif de l'utilisateur n'a pas déjà sa propre icône pour `.dsl` (comportement documenté de VS Code — un thème qui connaît déjà `.dsl` d'une autre extension garde la sienne).
- **Auto-complétion** ([src/completions.js](src/completions.js) + [src/extension.js](src/extension.js)) — contextuelle : les clés proposées dépendent du bloc englobant (dans `channel { }` → `url`/`channels`/`transport`/.../`onmessage` ; dans `onmessage { }` → seulement `bind`/`refresh`/`dispatch`/`event`, jamais les clés d'un `endpoint` ; après `@` → les 8 décorateurs de `BUILTIN_VALIDATORS`, rien d'autre). La détection de contexte est une heuristique de comptage d'accolades en remontant depuis le curseur (`findEnclosingBlockHeader`) — pas un vrai parseur xdsl, volontairement : dupliquer `xdsl/parser.py` ici coûterait plus cher à maintenir en double que le gain marginal côté éditeur.
- **Catalogue réel des composants xweb.*** ([src/components-catalog.json](src/components-catalog.json), généré par [scripts/generate_components_catalog.py](scripts/generate_components_catalog.py) depuis `../xweb/components/*.xml`) — les 93 composants (`popover`, `table`, `button`, `form`, ...) sont proposés comme complétion de balise (forme courte ET qualifiée `xweb.nom`), et une fois À L'INTÉRIEUR de l'un d'eux, ce sont ses **vraies** props déclarées (extraites de son `<t t-set="prop" t-default="...">`) qui sont proposées — jamais une liste générique. Distinction volontaire et non-cosmétique : un composant expose ses props htmx en `hx_get`/`hx_post` (underscore, ce sont des kwargs Python), une balise HTML brute utilise `hx-get`/`hx-post` (tiret, un vrai attribut HTML) — les deux formes ne sont JAMAIS mélangées. Regénérer après tout changement dans `xweb/components/` : `npm run generate:catalog`.
- **Snippets** ([snippets/xdsl.code-snippets](snippets/xdsl.code-snippets)) — squelettes complets (`channel`, `endpoint` avec `receive`/`onsuccess`/`onerror`, `data`, `copy ... as ...`, `patch`, blocs `onmessage`/hyperscript...).

## Utiliser en développement (sans publier)

Depuis VS Code, ouvrir ce dossier `design/` puis appuyer sur **F5**
(*Run Extension*) — ça lance une fenêtre "Extension Development Host" avec
l'extension chargée. Ouvrir un `.dsl` du dépôt (ex. `../contacts_demo.dsl`)
dedans pour voir la coloration/complétion en action.

Alternative sans lancer VS Code : `npm run verify:grammar` /
`npm run verify:completions` (voir plus bas) prouvent que la grammaire et
la complétion fonctionnent réellement, sans ouvrir l'éditeur.

## Empaqueter en `.vsix` (installation locale)

```bash
npm install -g @vscode/vsce   # une fois
cd design
vsce package                  # écrit xdsl-language-0.1.0.vsix
code --install-extension xdsl-language-0.1.0.vsix
```

## Vérification — pas juste "ça a l'air bon à la lecture"

```bash
npm install
npm run verify:grammar        # tokenise pour de VRAI via vscode-textmate + vscode-oniguruma
                               # (le même moteur qu'utilise VS Code en interne, pas une regex JS
                               # approximative) — contre du .dsl réel du dépôt (../contacts_demo.dsl)
npm run verify:completions    # logique de complétion pure (src/completions.js), aucune dépendance
                               # à `vscode` — exécutable en Node pur, sans Extension Development Host
```

Les deux scripts sont volontairement écrits pour prouver le comportement
réel plutôt que de survoler le JSON : `verify:grammar` a trouvé deux bugs
réels en construisant cette extension (l'espace avant `{` héritait le
scope de balise ; `onmessage {` — un ouvreur de bloc, pas un `clé: valeur`
— était mal classé dans un test), et `verify:completions` en a trouvé un
troisième (un `\s+` générique dans l'heuristique de contexte franchissait
un saut de ligne et collait deux tokens sans rapport, `"POST"` +
`"receive"`, à cause d'un `method: POST\n    receive {` réel).

Le catalogue de composants a son propre script de génération, séparé des
deux vérifications ci-dessus (il ÉCRIT `src/components-catalog.json`
plutôt que de le lire) :

```bash
npm run generate:catalog   # (re)génère src/components-catalog.json depuis ../xweb/components/*.xml
```

À relancer chaque fois qu'un composant `xweb/components/*.xml` change ses
props — sinon la complétion propose un catalogue périmé (jamais faux vis-
à-vis du fichier généré, juste en retard sur le vrai code).

## Limites connues (v1)

- La complétion contextuelle est une heuristique, pas un vrai parseur —
  du texte syntaxiquement invalide en cours de frappe peut donner un
  contexte approximatif (jamais une erreur, au pire une liste un peu trop
  large).
- Pas de diagnostics (soulignement d'erreur) ni de "go to definition" —
  ça demanderait un vrai serveur de langage (LSP) branché sur
  `xdsl/parser.py`/`xdsl/compiler.py` via un pont Python↔Node ou une
  réécriture du parseur ; hors scope de cette v1.
- L'icône de fichier n'est qu'un fallback (voir plus haut).
- Non publiée sur le Marketplace — un `vsce publish` demanderait un vrai
  compte éditeur et un nom d'extension disponible.
