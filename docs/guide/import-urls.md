# URLs d'importation DSL xdsl

## Import absolu depuis le package `xweb`

```qml
import { button, input, form, toast, card, modal } from "xweb"
```

- Résout vers : `xweb.button`, `xweb.input`, `xweb.form`, etc.
- Disponible dans tous les projets (package cœur)
- Voir `docs/guide/dsl-user.md` §"Import absolu" pour la liste complète

## Import relatif depuis le plugin courant

```qml
import { nav } from "./"
import { auth } from "../auth"
import { card } from "../../other_plugin"
```

- Le `package_id` vient de `plugin.yaml` du plugin
- `./` → `plugins/<nom>/templates/` du plugin courant
- `../auth` → `plugins/auth/templates/`
- Utilisé pour composer ses propres composants sur ceux du cœur

## Exemple complet d'import

```qml
@include "xweb.shell"

import { button, form, input, toast } from "xweb"
import { nav } from "./"

data user_form {
    name: string @required @min_length(2)
    email: string @required @email
}
```

## Mapping DSL → QWeb pour les imports

| DSL                              | QWeb generated           |
|----------------------------------|--------------------------|
| `import { button } from "xweb"`  | `<t t-call="xweb.button"/>` |
| `import { nav } from "./"`       | `<t t-call="current_plugin.nav"/>` |
| `import { helper } from "../auth"` | `<t t-call="auth.helper"/>` |

## Notes importantes

1. Les imports doivent apparaître **avant** le premier `component` dans le fichier
2. Les imports répétés sans noms uniques sont tolérés mais peuvent ombreger précédentes définitions
3. Un composant ne peut pas s'importer lui-même (cyclique non supportée)
4. Après compilation, les imports sont remplacés par les références `t-call` complets