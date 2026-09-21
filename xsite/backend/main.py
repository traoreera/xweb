"""xsite/backend/main.py — le site xweb+xdsl, boot xcore RÉEL.

Usage :
    uv run uvicorn xsite.backend.main:app --reload
    puis ouvrir http://127.0.0.1:8000/

Différence avec contacts_demo_app.py / docs_site_app.py (racine du dépôt,
sessions précédentes) : ceux-là instanciaient leur propre QwebRegistry() nu,
sans xcore. Ici, xweb est déclaré `services.extensions.xweb` dans
xsite/integration.yaml et chargé par un vrai `Xcore().boot()` — c'est
`xcore.services.get("ext.xweb").engine` qui sert toutes les pages, exactement
comme dans un déploiement xcore réel (docs/integration-xcore.md).

Aucun plugin n'est nécessaire pour ce site (xsite/plugins/ reste vide) : ses
pages sont montées directement sur `app`, comme la landing page d'un vrai
projet xcore (CLAUDE.md — "Aucun plugin ne peut jamais servir la racine /").
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from xcore import Xcore

from xweb.engine.integration.xcore import bind_hot_reload
from xweb.mount import mount_builtin_assets

from . import routes

ROOT = Path(__file__).resolve().parent.parent.parent
SITE_ROOT = ROOT / "xsite"

xcore = Xcore(config_path=str(SITE_ROOT / "integration.yaml"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    await xcore.boot(app)
    ext = xcore.services.get("ext.xweb")
    bind_hot_reload(xcore, ext)
    routes.mount(app, ext.engine)
    yield
    await xcore.shutdown()


app = FastAPI(title="xweb + xdsl — le site", lifespan=lifespan)
xcore.setup(app)

# /xweb-static/* — app.css, htmx.min.js, _hyperscript.min.js, live_channel.js,
# storage.js, validators.js : le socle vendorisé du SDK, identique pour
# n'importe quel projet qui installe xweb (docs/theming.md#build).
mount_builtin_assets(app)

# /site-static/* — le peu de CSS/JS propre à CE site (xsite/static/), injecté
# dans le <head> par xsite/templates/shell_patch.dsl (un patch t-inherit sur
# xweb.shell_head, jamais une édition du composant vendorisé).
app.mount("/site-static", StaticFiles(directory=str(SITE_ROOT / "static")), name="site-static")
