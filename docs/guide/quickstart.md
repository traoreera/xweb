# Démarrage rapide

## Lancer ce dépôt tel quel

```bash
# dépendances Python (xweb + plugins/auth ont chacun leur venv, voir
# CLAUDE.md "Python dependency layout" — root suffit pour tout faire tourner)
uv sync

# CSS compilé — refaire après toute modification de classes DaisyUI dans
# xweb/components/**/*.xml ou plugins/**/*.xml
export PATH="$HOME/.nvm/versions/node/v24.19.0/bin:$PATH"   # si node/npm absents du PATH
npm install
npm run build:css

# suite de tests complète
uv run pytest

# serveur réel
uv run xcli manager start
```

Une fois lancé, `http://localhost:8000/` sert la landing page, et `http://localhost:8000/app/demo/` (le préfixe `/app` vient de `app.plugin_prefix` dans [`integration.yaml`](../../integration.yaml) — voir [`integration-xcore.md`](../integration-xcore.md), ce n'est **jamais** `/plugins/` en dur) le catalogue de démo qui exerce la plupart des composants.

!!! warning "Le rechargement à chaud ne voit que les `.py`"
    `xcli manager start --reload` ne surveille que les fichiers Python. Une modification d'un `.xml` (template) ou d'`integration.yaml` n'est prise en compte qu'après avoir touché un `.py` quelconque (ou redémarré) — un piège rencontré plusieurs fois pendant le développement de ce dépôt.

## Ajouter xweb à un nouveau projet xcore

xweb est un SDK au niveau plugin, pas un plugin lui-même — il s'enregistre comme une **extension xcore** :

```yaml
# integration.yaml
services:
  extensions:
    xweb:
      module: xweb.engine.integration.xcore:XwebExtension
      config:
        namespaces:
          # <espace de noms> : <dossier de templates> — un plugin qui a ses
          # propres pages xweb doit apparaître ici. xweb/components/ est
          # chargé tout seul, jamais à lister.
          mon_plugin: "plugins/mon_plugin/templates"
```

```python
# main.py
from xcore import Xcore
from xweb.engine.integration.xcore import bind_hot_reload

xcore = Xcore()

async def lifespan(app):
    await xcore.boot(app)
    # après boot(), jamais dans lifespan() lui-même pour le reste — voir
    # CLAUDE.md "Middleware ordering" pour la raison exacte (extensions ne
    # reçoivent que `config`, jamais l'EventBus, au moment de leur init()).
    bind_hot_reload(xcore, xcore.services.get("ext.xweb"))
    yield
```

`bind_hot_reload` est ce qui nettoie `QwebRegistry` (templates + patches `t-inherit`) et les quatre registres de contribution (`nav`/`ribbon`/`commands`/`status_bar`) quand un plugin est déchargé — sans lui, un rechargement de plugin laisserait ses anciennes pages/contributions fantômes derrière lui.

Voir [`integration-xcore.md`](../integration-xcore.md) pour le contrat complet (permissions, cache, i18n).
