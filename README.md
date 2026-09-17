# xweb + xdsl

Un moteur de rendu QWeb (XML + directives `t-*`, héritage non-destructif par
XPath) et un SDK de plugin pour **xcore** (`xcoreruntime` sur PyPI, importé
`xcore`) — plus `xdsl`, un DSL déclaratif façon QML qui compile vers ce même
XML QWeb, pour écrire des composants/pages sans toucher aux directives `t-*`
à la main.

```qml
component contacts_page {
    form { use: create_contact
        input { name: "name"; required: true }
        button { type: "submit" "Ajouter" }
    }
}
```

## Ce qu'il y a dans ce dépôt

- **`xweb/`** — le moteur QWeb (`xweb/engine/`) : parseur `lxml`, compilateur
  de directives `t-*`, héritage `t-inherit`/XPath (modes `extension` et
  `primary`). Plus le SDK plugin — `mount.py`, `contrib.py` (registres de
  navigation/ruban/commandes), `cookies.py`, `forms.py`, `csrf.py`,
  `i18n.py`, `pdf.py`, `email.py`. `xweb/components/` : ~50 composants
  DaisyUI (`xweb.button`, `xweb.table`, `xweb.popover`, `xweb.kanban`,
  `xweb.editable_table`…), catalogue documenté dans `docs/components.md`.
- **`xdsl/`** — le DSL déclaratif : `parser.py` (texte → AST), `compiler.py`
  (AST → XML QWeb), `validators.py` (règles de validation réutilisables
  côté serveur), `serialize.py`/`api.py` (round-trip `.xdsl.json`, format
  d'échange pour un futur éditeur no-code). Design complet et à jour dans
  [`docs/dsl-design.md`](docs/dsl-design.md).
- **`contacts_demo.dsl` + `contacts_demo_app.py`** — une démo CRUD complète
  et autonome (formulaire dans un popover, table qui se rafraîchit par
  événement htmx) qui sert de référence vivante pour le pattern
  `endpoint`/`use:` du DSL. Ne dépend d'aucun système de plugins.
- **`assets/` + `xweb/static/`** — Tailwind v4 + DaisyUI 5 ; `htmx.min.js`
  et `_hyperscript.min.js` vendorisés. Node est un outil de build
  uniquement, jamais une dépendance d'exécution — ce qui tourne en
  production est le CSS/JS déjà committé dans `xweb/static/`.

`plugins/`/`extensions/` sont vides à ce jour (pas de vraie app xcore
montée) — voir `XWEB_KNOWLEDGE.md` §2 pour l'état exact.

## Démarrer

```bash
uv sync                                        # dépendances Python
npm install && npm run build:css               # CSS compilé (obligatoire avant de rendre quoi que ce soit)

uv run pytest                                  # suite principale
uv run pytest xdsl/tests                       # tests xdsl (pas ramassés par la commande ci-dessus)

uv run uvicorn contacts_demo_app:app --reload  # voir le DSL tourner pour de vrai
# -> http://127.0.0.1:8000/
```

## Documentation

| Fichier | Pour qui / quoi |
|---|---|
| [`CLAUDE.md`](CLAUDE.md) | Guide d'architecture complet — à lire en premier pour comprendre le repo |
| [`docs/index.md`](docs/index.md) | Index de la spec complète (`docs/*.md`) — le *pourquoi* de chaque décision |
| [`docs/dsl-design.md`](docs/dsl-design.md) | Design + référence complète du DSL `xdsl` |
| [`AGENTS.md`](AGENTS.md) | Aide-mémoire compact — ce qu'on devinerait mal, trouvé en le cassant une fois |
| [`XWEB_KNOWLEDGE.md`](XWEB_KNOWLEDGE.md) | Référence exhaustive, vérifiée, pour un LLM qui valide du code touchant ce projet |

Pas de commande lint/format configurée dans ce dépôt — ne pas en inventer.
Tout commentaire/doc de ce dépôt est écrit en **français** — garder cette
convention en éditant un fichier existant.
