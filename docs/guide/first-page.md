# Votre première page

Exemple complet, de bout en bout : un mini livre d'or — une liste de messages en mémoire (comme `plugins/demo`'s tableau kanban, `_KANBAN_BOARD` : pas de base de données, l'objectif est de montrer le câblage, pas la persistance) et un formulaire pour en ajouter un, sans recharger la page.

## 1. Le plugin

```
plugins/guestbook/
├── plugin.yaml
├── src/
│   └── main.py
└── templates/
    ├── index.xml       # la page
    └── entries.xml     # le fragment htmx (liste seule)
```

```yaml
# plugins/guestbook/plugin.yaml
name: guestbook
version: "1.0.0"
execution_mode: trusted
entry_point: src/main.py
permissions:
  # fail-closed (CLAUDE.md) : sans cette liste, TOUTE route de ce plugin
  # renvoie {"status": "error", "code": "permission_denied"} en silence.
  - resource: "guestbook.entries"
    actions: ["*"]
    effect: "allow"
```

## 2. Les templates

```xml title="plugins/guestbook/templates/index.xml"
<template t-name="guestbook.index">
    <div class="flex flex-col gap-4 max-w-lg">
        <h1 class="text-2xl font-bold">Livre d'or</h1>

        <!-- xweb.form (xweb/components/form.xml) ne connaît que ses props
             déclarées (action/method/token/boost/…) — un hx-post posé sur
             le t-call lui-même ne serait JAMAIS rendu (aucune prop ne s'y
             attend). Pour un formulaire qui échange un FRAGMENT en htmx
             plutôt qu'une vraie redirection, un <form> nu + xweb.csrf est
             le bon niveau — xweb.form vise l'autre cas (login/logout,
             boost="false", voir sa propre docstring). -->
        <form hx-post="/plugins/guestbook/entries" hx-target="#entries" hx-swap="afterbegin"
              class="flex flex-col gap-4">
            <t t-call="xweb.csrf" t-att-token="csrf_token"/>
            <t t-call="xweb.field" label="Votre message" for_="message">
                <t t-call="xweb.input" name="message" id="message" t-att-required="True"/>
            </t>
            <t t-call="xweb.button" variant="primary" size="sm" type="submit" extra_class="">
                Envoyer
            </t>
        </form>

        <div id="entries" class="flex flex-col gap-2">
            <t t-call="guestbook.entries" t-att-entries="entries"/>
        </div>
    </div>
</template>
```

```xml title="plugins/guestbook/templates/entries.xml"
<!-- Le MÊME fragment sert deux fois : inclus par t-call dans la page
     initiale ci-dessus, ET renvoyé tel quel par la route POST plus bas —
     jamais deux templates qui dessinent la même chose (docs/plugins.md). -->
<template t-name="guestbook.entries">
    <t t-foreach="entries" t-as="e">
        <div class="card bg-base-100 border shadow-sm">
            <div class="card-body p-3 text-sm"><t t-esc="e"/></div>
        </div>
    </t>
    <t t-if="not entries">
        <t t-call="xweb.empty" icon="mail" title="Aucun message" message="Soyez le premier à signer."/>
    </t>
</template>
```

`t-esc` échappe toujours (`e` vient d'un formulaire, jamais `t-out` dessus — voir [Templates QWeb](templates.md#t-esc-vs-t-out)).

!!! warning "`t-call` isole son contexte — même en interne au même plugin"
    `<t t-call="guestbook.entries" t-att-entries="entries"/>` : le `t-att-entries="entries"` **est obligatoire**, pas cosmétique. Un `t-call` sans lui ne voit rien de la page appelante — repéré en écrivant cet exemple : `t-foreach="entries"` sur un nom absent du contexte ne plante pas (rend silencieusement rien), et `t-if="not entries"` sur ce même nom absent **ne s'affiche pas non plus** — `_eval` retombe sur `None` pour l'expression *entière* dès qu'un nom qu'elle contient est indéfini, pas sur l'inversion booléenne de "absent = faux". Concrètement : `not entries` sur un nom manquant vaut `None` (donc `t-if` ne s'affiche pas), pas `True`. Le même piège avec `entries` réellement présent mais valant `[]` fonctionne, lui, comme attendu — la distinction ne saute pas aux yeux à la lecture.

## 3. La route

```python title="plugins/guestbook/src/main.py"
from __future__ import annotations

from fastapi import APIRouter, Request
from xcore import TrustedBase

from xweb.context import XwebContext
from xweb.contrib import Contribution, nav
from xweb.mount import mount_xweb_page

_ENTRIES: list[str] = []


class Plugin(TrustedBase):
    async def on_load(self) -> None:
        nav.register(Contribution(
            id="guestbook.index", plugin="guestbook", label="Livre d'or",
            path="/plugins/guestbook/", icon="mail", order=50,
        ))

    def get_router(self) -> APIRouter:
        engine = self.get_service("ext.xweb").engine
        router = APIRouter()

        async def index_view(ctx: XwebContext) -> dict:
            return {"entries": _ENTRIES}

        mount_xweb_page(
            router, self.ctx, engine, path="/", template="guestbook.index",
            view=index_view, app_name="xweb",
        )

        @router.post("/entries")
        async def add_entry(request: Request):
            form = await request.form()
            message = str(form.get("message") or "").strip()
            if message:
                _ENTRIES.insert(0, message)
            # fragment htmx — jamais la page complète (CLAUDE.md "Plugin
            # structure") ; hx-swap="afterbegin" côté template insère ce
            # <div> AVANT les entrées déjà là.
            return engine.render("guestbook.entries", {"entries": _ENTRIES[:1]})

        return router

    async def handle(self, action: str, payload: dict) -> dict:
        return {"status": "error", "msg": "unknown action"}
```

## 4. Enregistrer le namespace de templates

```yaml
# integration.yaml
services:
  extensions:
    xweb:
      config:
        namespaces:
          guestbook: "plugins/guestbook/templates"
```

Redémarrez le serveur (les changements d'`integration.yaml` ne sont **jamais** repris par `--reload`, voir [Démarrage rapide](quickstart.md)) et ouvrez `/plugins/guestbook/` (ou `/app/guestbook/` si `app.plugin_prefix` a été changé — voir [`integration-xcore.md`](../integration-xcore.md)).

!!! note "Ce que fait `mount_xweb_page` pour vous"
    Résout l'utilisateur courant, injecte le contexte de base (`csrf_token`, `nav_tree`, `plugin_prefix`, locale…), enveloppe dans `xweb.shell` par défaut, et répond soit la page complète soit `<title>…</title>` + fragment selon l'en-tête `HX-Request` — un lien de nav cliqué (boosté) ne reçoit jamais le chrome persistant en double. Voir [`shell.md`](../shell.md).
