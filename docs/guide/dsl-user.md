# DSL xdsl — Guide d'utilisation

Le DSL xdsl (syntaxe style QML) est un sucre syntaxique qui compile en XML QWeb standard. Il vise à réduire la verbosité des templates QWeb tout en gardant la pleine puissance du moteur.

## Installation

```bash
# Dépendances Python
uv sync

# CSS compilé — refaire après toute modification de classes
export PATH="$HOME/.nvm/versions/node/v24.19.0/bin:$PATH"
npm install
npm run build:css
```

## Compilation de base

```python
from xdsl.api import compile_dsl

source = """
@include "xweb.shell"
import { button, form, input } from "xweb"

data contact_form {
    name: string @required @min_length(2)
    email: string @required @email
}

endpoint create_contact {
    method: POST
    url: "/api/contacts"
    send: contact_form
    receive {
        type: json
        target: "#contact-table"
        event: "contacts:changed"
    }
    onsuccess { toast { variant: "success" "Contact créé !" } }
}
"""

xml = compile_dsl(source)
print(xml)
```

Résultat XML généré (extraits) :
```xml
<template t-name="create_contact">
    <t t-call="xweb.form" hx-post="/api/contacts" hx-swap="none" _="...">
        ...
    </t>
</template>
<script>...channel bootstrap...</script>
```

## Structure du fichier `.dsl`

Un fichier DSL se compose de plusieurs sections, dans cet ordre :

### 1. Layout et imports

```qml
@include "xweb.shell"

import { button, input, form } from "xweb"
import { nav } from "./"
```

- `@include "layout_name"` — insère un layout (généralement `xweb.shell`)
- `import { ... } from "xweb"` — importe des composants du cœur
- `import { ... } from "./"` — importe des composants du même plugin (chemin relatif)

### 2. Schémas de données (`data`)

```qml
data contact_form {
    name: string @required @min_length(2)
    email: string @required @email
}
```

Déclare un schéma de validation réutilisable. Les décorateurs `@` viennent de `xdsl/validators.py`. Utilisé par `endpoint.send` et les channels `validate:`.

### 3. Endpoints (`endpoint`)

```qml
endpoint create_contact {
    method: POST
    url: "/api/contacts"
    send: contact_form
    receive {
        type: json
        target: "#contact-table"
        event: "contacts:changed"
    }
    onsuccess { toast { variant: "success" "Contact créé !" } }
    onerror { toast { variant: "error" "Erreur." } }
}
```

- `method` : GET, POST, PUT, DELETE
- `url` : URL de l'API
- `send` : référence au schéma `data` envoyé
- `receive` : documentation de la réponse JSON
- `onsuccess` / `onerror` : blocs hyperscript pré-compilés, révélés par htmx `afterRequest`

### 4. Channels (`channel`)

```qml
channel contacts_feed {
    url: "/sse/contacts"
    transport: "sse"
    channels: ["contacts"]
    onmessage {
        refresh: "#contact-table"
        dispatch: true
        bind: { "#count": "count" }
    }
}
```

- `url` : URL SSE ou WS
- `transport` : "auto" | "sse" | "ws"
- `onmessage.refresh` : sélecteur CSS à rafraîchir via `htmx.trigger()`
- `onmessage.dispatch` : diffuse un `CustomEvent DOM` sur `document`
- `onmessage.bind` : écriture en `textContent` sur des sélecteurs

### 5. Composants (`component`)

```qml
component user_page {
    div {
        use_channel: contacts_feed
        class: ["max-w-2xl", "mx-auto", "py-6"]
        h1 { class: ["text-2xl", "font-bold"] "Users" }
        form { use: create_contact
            input { name: "placeholder: "Nom"; required: true }
            button { type: "submit" "Envoyer" }
        }
    }
}
```

- `use_channel: name` — instancie le bootstrap du channel
- `use: name` — référence un endpoint, ajoute `hx-*/_` attributs
- `class: [...]` / `style: { ... }` — classes Tailwind / CSS inline
- `_ : on click ...` / `_ { ... }` — hyperscript client

### 6. Hyperscript

```qml
button {
    _ : on click
        add .pulse
        wait 300ms
        remove .pulse
    "Action rapide"
}
```

- `_ : on click ligne` — script sur une seule ligne (capturé jusqu'au `\n`)
- `_ { ... }` — script sur plusieurs lignes (bloc, gestion de `{ }` profondeurs)
- `${ expr }` — interpolation serveur, convertie en `{{ expr }}` par le compilateur
- Les mots-clés hyperscript (`on`, `click`, `wait`, `if`, `js(...)`) restent du texte brut

### 7. Contrôle de flux

```qml
if (admin) {
    button { variant: "success" "Admin" }
} elif (role == "editor") {
    button { variant: "secondary" "Éditeur" }
} else {
    button { variant "ghost" "Utilisateur" }
}

for member in team {
    card { title: member.name }
}
```

- `if` / `elif` / `else` — fratries `t-if`/`t-elif`/`t-else`
- `for x in list` — boucle `t-foreach`/`t-as`

### 8. Props et affectation

```qml
component card {
    admin = true
    current_user ?= "Alice"
    score = "42 points"
}
```

- `name = value` — affectation simple (`t-value`)
- `name ?= value` — affectation par défaut (`t-default`, ne remplace pas si déjà défini)
- Utilisés comme props locales au composant

## Import URLs

Le DSL supporte deux types d'imports :

### Import absolu (depuis le package `xweb`)

```qml
import { button, form, input, toast } from "xweb"
```

Résout en `xweb.button`, `xweb.form`, etc. Ces composants sont toujours disponibles car xweb est le package cœur.

### Import relatif (depuis le plugin courant)

```qml
import { nav } from "./"
import { card } from "../auth"
```

Le `package_id` défini dans `plugin.yaml` sert de racine. Le chemin `./` réfère au dossier `templates/` du plugin courant.

## Astuces et limites

1. **Ternaires** : `cond ? a : b` est supporté au niveau racine d'expression, mais pas à l'intérieur de parenthèses ni d'imbrication directe. Utilisez `a if c else b` à la place.

2. **Listes d'objets inline** : `options: [{"label": ...}]` casse à la virgule. Déclarez d'abord `opts = [...]` puis `options: opts`.

3. **Membres de dict** : `member["role"]` fonctionne, mais `member.role` sur un dict lève `AttributeError`. Utilisez la syntaxe de crochet.

4. **Hyperscript `<` / `>`** : Les symboles `<` et `>` sont des opérateurs de comparaison, pas des mots anglais. `less than`/`greater than` ne parsèent pas.

5. **Interpolation `${...}`** : Convertie en `{{...}}` par le compilateur. Sans conversion, QWeb laisserait `${...}` littéral.

6. **Attribut `_` double** : Un élément ne peut avoir qu'un seul attribut `_`. Utilisez `_ { ... }` pour les scripts multi-lignes ou `_ : on click ...` pour le mode ligne.

7. **Guillemets dans les attributs** : Dans les attributs XML, préférez `hx-vals="js:{column: '{{expr}}'}"` (double-quoted XML, single-quoted JS) plutôt que `t-attf-hx-vals='{"column": "{{expr}}"}'` qui cause une erreur de parse XML.