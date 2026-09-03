# Shell, nav et permissions

Chaque page montée via [`mount_xweb_page`](first-page.md) est enveloppée dans `xweb.shell` par défaut — sidebar de nav, topbar, palette Ctrl+K, barre de statut. Un plugin **contribue** à ces régions via quatre registres singletons (`xweb/contrib.py`), typiquement dans `on_load()`. Détail complet : [`shell.md`](../shell.md).

## Nav

```python
from xweb.contrib import Contribution, nav

nav.register(Contribution(
    id="guestbook.index", plugin="guestbook", label="Livre d'or",
    path="/plugins/guestbook/", icon="mail", order=50,
))
```

`id` doit être unique process-wide (`nav.register` lève si déjà pris). `order` (défaut `100`) trie les entrées — plus petit, plus haut. Une entrée avec `parent_id` pointant vers une autre devient un enfant repliable (`<details>`, zéro JS).

## Palette de commandes (Ctrl+K)

```python
from xweb.contrib import commands

commands.register(Contribution(
    id="guestbook.index", plugin="guestbook", label="Ouvrir le livre d'or",
    icon="mail", action_url="/plugins/guestbook/", order=50,
))
```

Même dataclass `Contribution`, registre séparé — une entrée de nav n'apparaît pas automatiquement dans la palette, il faut l'enregistrer aussi si voulu (les deux appels ci-dessus sont volontairement distincts, pas un raccourci qui ferait les deux à la fois).

## Restreindre à une permission ou aux connectés

```python
nav.register(Contribution(
    id="guestbook.admin", plugin="guestbook", label="Modération",
    path="/plugins/guestbook/admin", permission="guestbook:moderate",
))
```

`permission` accepte un rôle/permission réel (vérifié contre l'`AuthPayload` de l'utilisateur), **ou** la constante `AUTHENTICATED` (`xweb.contrib.AUTHENTICATED`) pour "visible dès qu'on est connecté, peu importe le rôle" :

```python
from xweb.contrib import AUTHENTICATED

nav.register(Contribution(id="guestbook.index", ..., permission=AUTHENTICATED))
```

!!! danger "L'affichage n'est pas la sécurité"
    `permission=` ne fait que masquer l'entrée dans le menu — la vraie protection reste `ctx.require_role(...)`/`ctx.require_user()` **dans la route elle-même**. Une entrée cachée dont la route n'a pas son propre contrôle reste atteignable par n'importe qui connaissant l'URL.

## Nettoyage au déchargement — rien à faire

Contrairement à un ancien système où un plugin devait se désinscrire lui-même, le nettoyage des quatre registres (nav/ribbon/commands/status_bar) au unload/reload d'un plugin est **centralisé** dans `ext.xweb` (`bind_hot_reload`, voir [Démarrage rapide](quickstart.md)) — un `on_load()` qui ne fait qu'enregistrer, sans `on_unload()` correspondant, est le cas normal.

## Badge statique — et sa vraie limite

```python
nav.register(Contribution(id="guestbook.index", ..., badge="Nouveau"))
```

`badge` est un champ **statique**, posé une fois à l'enregistrement — `NavRegistry` est un singleton partagé par tout le process, résolu une seule fois, pas par requête ni par utilisateur. Il ne peut **pas** afficher un compteur qui varie par visiteur (notifications non lues, par exemple) sans un mécanisme séparé côté client — `plugins/account/templates/_shared.xml::account.shell_notifications_badge` est un exemple réel qui résout ça via un patch `t-inherit` sur `xweb.shell` + un flux SSE, pas via `badge=`.
