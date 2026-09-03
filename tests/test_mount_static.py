"""mount_builtin_assets() n'avait jamais été testé avec de vrais fichiers —
xweb/static/ était vide jusqu'au vendoring d'htmx/_hyperscript."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from xweb.mount import mount_builtin_assets


def test_htmx_is_actually_served():
    app = FastAPI()
    mount_builtin_assets(app)
    r = TestClient(app).get("/xweb-static/htmx.min.js")
    assert r.status_code == 200
    assert "htmx" in r.text[:50]


def test_hyperscript_is_actually_served():
    app = FastAPI()
    mount_builtin_assets(app)
    r = TestClient(app).get("/xweb-static/_hyperscript.min.js")
    assert r.status_code == 200


def test_custom_prefix_is_honoured():
    app = FastAPI()
    mount_builtin_assets(app, url_prefix="/assets")
    r = TestClient(app).get("/assets/htmx.min.js")
    assert r.status_code == 200


def test_assets_force_revalidation_not_blind_caching():
    """Un navigateur qui fait confiance à un Last-Modified ancien peut
    réutiliser un app.css périmé sans même revalider — vécu en vrai après
    un npm run build:css. Cache-Control: no-cache force une requête
    conditionnelle à chaque chargement (304 si inchangé, jamais une
    réutilisation aveugle du cache)."""
    app = FastAPI()
    mount_builtin_assets(app)
    r = TestClient(app).get("/xweb-static/app.css")
    assert r.headers["cache-control"] == "no-cache"


def test_etag_still_enables_a_cheap_304_on_unchanged_content():
    app = FastAPI()
    mount_builtin_assets(app)
    client = TestClient(app)
    first = client.get("/xweb-static/app.css")
    etag = first.headers["etag"]
    second = client.get("/xweb-static/app.css", headers={"If-None-Match": etag})
    assert second.status_code == 304
