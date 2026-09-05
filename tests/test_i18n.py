"""i18n — xweb/i18n.py (Catalog, resolve_locale) et son câblage dans
xweb/mount.py (ctx["_"]/ctx["locale"], cookie xweb_locale). docs/i18n.md.
"""

from pathlib import Path

from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from xweb.engine.registry import QwebRegistry
from xweb.i18n import LOCALE_COOKIE, SOURCE_LOCALE, Catalog, resolve_locale
from xweb.mount import mount_xweb_page

COMPONENTS_DIR = Path(__file__).parent.parent / "xweb" / "components"


def make_request(path="/x", query="", headers=None, cookies=None):
    from starlette.requests import Request

    raw_headers = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    if cookies:
        raw_headers.append((b"cookie", "; ".join(f"{k}={v}" for k, v in cookies.items()).encode()))
    scope = {"type": "http", "method": "GET", "path": path, "query_string": query.encode(), "headers": raw_headers}
    return Request(scope)


# ---------------------------------------------------------------------
# Catalog — chargement, dégradation
# ---------------------------------------------------------------------


def test_catalog_without_locales_dir_only_knows_french():
    cat = Catalog(None, ["en"])
    assert cat.available == ["fr", "en"]
    assert cat.translator_for("en")("Bonjour") == "Bonjour"  # aucun fichier -> identité


def test_catalog_loads_a_real_json_file(tmp_path):
    (tmp_path / "en.json").write_text('{"Bonjour": "Hello", "Se connecter": "Log in"}', encoding="utf-8")
    cat = Catalog(tmp_path, ["en"])
    tr = cat.translator_for("en")
    assert tr("Bonjour") == "Hello"
    assert tr("Se connecter") == "Log in"
    assert tr("Pas encore traduit") == "Pas encore traduit"  # clé absente -> identité, jamais une KeyError


def test_catalog_missing_file_degrades_to_identity_not_an_exception(tmp_path):
    cat = Catalog(tmp_path, ["de"])  # de.json n'existe pas
    assert cat.translator_for("de")("Bonjour") == "Bonjour"


def test_catalog_invalid_json_degrades_to_identity_not_an_exception(tmp_path):
    (tmp_path / "en.json").write_text("{ceci n'est pas du json", encoding="utf-8")
    cat = Catalog(tmp_path, ["en"])
    assert cat.translator_for("en")("Bonjour") == "Bonjour"


def test_catalog_non_dict_json_degrades_to_identity(tmp_path):
    (tmp_path / "en.json").write_text('["une", "liste"]', encoding="utf-8")
    cat = Catalog(tmp_path, ["en"])
    assert cat.translator_for("en")("Bonjour") == "Bonjour"


def test_catalog_ignores_underscore_prefixed_keys_as_comments(tmp_path):
    """locales/en.json porte un "_comment" décrivant le fichier — convention
    JSON courante, jamais une vraie clé source française (qui ne commence
    jamais par "_")."""
    (tmp_path / "en.json").write_text('{"_comment": "note de fichier", "Bonjour": "Hello"}', encoding="utf-8")
    cat = Catalog(tmp_path, ["en"])
    tr = cat.translator_for("en")
    assert tr("Bonjour") == "Hello"
    assert tr("_comment") == "_comment"  # jamais traité comme une traduction


def test_catalog_source_locale_never_needs_a_file_even_if_listed():
    cat = Catalog(None, ["fr", "en"])  # "fr" listé par erreur, ignoré
    assert cat.available == ["fr", "en"]
    assert cat.translator_for("fr")("Bonjour") == "Bonjour"


def test_catalog_unknown_locale_returns_identity_translator():
    cat = Catalog(None, ["en"])
    assert cat.translator_for("de")("Bonjour") == "Bonjour"


# ---------------------------------------------------------------------
# resolve_locale — ordre de résolution
# ---------------------------------------------------------------------


def test_resolve_locale_defaults_to_source_locale_with_nothing_provided():
    cat = Catalog(None, ["en"])
    assert resolve_locale(make_request(), cat) == SOURCE_LOCALE


def test_resolve_locale_query_param_wins_over_everything():
    cat = Catalog(None, ["en"])
    req = make_request(query="lang=en", headers={"Accept-Language": "fr-FR"}, cookies={LOCALE_COOKIE: "fr"})
    assert resolve_locale(req, cat) == "en"


def test_resolve_locale_falls_back_to_cookie_without_query_param():
    cat = Catalog(None, ["en"])
    req = make_request(cookies={LOCALE_COOKIE: "en"})
    assert resolve_locale(req, cat) == "en"


def test_resolve_locale_falls_back_to_accept_language_without_cookie():
    cat = Catalog(None, ["en"])
    req = make_request(headers={"Accept-Language": "en-US,en;q=0.9,fr;q=0.8"})
    assert resolve_locale(req, cat) == "en"


def test_resolve_locale_ignores_a_locale_with_no_catalogue():
    """?lang=de mais aucun catalogue "de" chargé -> jamais un code fantôme,
    replie sur le français plutôt que d'afficher du texte non traduit."""
    cat = Catalog(None, ["en"])
    req = make_request(query="lang=de")
    assert resolve_locale(req, cat) == SOURCE_LOCALE


def test_resolve_locale_query_param_requesting_source_locale_is_honoured():
    cat = Catalog(None, ["en"])
    req = make_request(query="lang=fr", cookies={LOCALE_COOKIE: "en"})
    assert resolve_locale(req, cat) == "fr"


# ---------------------------------------------------------------------
# Câblage réel dans mount.py — via un vrai cycle ASGI (TestClient),
# même stratégie que tests/test_mount.py.
# ---------------------------------------------------------------------


class FakeExt:
    csrf_token = "tok"

    def __init__(self, catalog):
        self.i18n = catalog


class FakePluginCtx:
    name = "demo"
    tenant_id = None
    caller = None

    def __init__(self, catalog):
        self._catalog = catalog

    def get_service(self, name):
        return FakeExt(self._catalog) if name == "ext.xweb" else None


PAGE = """<template t-name="test.page"><h1 t-tr="1">Bonjour</h1></template>"""


def make_app(monkeypatch, tmp_path, *, user=None):
    (tmp_path / "en.json").write_text('{"Bonjour": "Hello"}', encoding="utf-8")
    catalog = Catalog(tmp_path, ["en"])

    async def fake_resolve(request):
        return user

    monkeypatch.setattr("xweb.context.resolve_user_or_anonymous", fake_resolve)
    registry = QwebRegistry()
    registry.register_source(PAGE)
    registry.register_dir(COMPONENTS_DIR)
    app = FastAPI()
    router = APIRouter()
    mount_xweb_page(router, FakePluginCtx(catalog), registry, path="/", template="test.page", view=lambda ctx: {})
    app.include_router(router)
    return app


def test_page_renders_in_french_by_default(monkeypatch, tmp_path):
    r = TestClient(make_app(monkeypatch, tmp_path)).get("/")
    assert "Bonjour" in r.text and "Hello" not in r.text


def test_lang_query_param_translates_the_page_and_sets_the_cookie(monkeypatch, tmp_path):
    client = TestClient(make_app(monkeypatch, tmp_path))
    r = client.get("/?lang=en")
    assert "Hello" in r.text and "Bonjour" not in r.text
    assert client.cookies.get(LOCALE_COOKIE) == "en"


def test_cookie_alone_keeps_translating_on_the_next_request(monkeypatch, tmp_path):
    client = TestClient(make_app(monkeypatch, tmp_path))
    client.get("/?lang=en")  # pose le cookie
    r = client.get("/")  # plus de ?lang= du tout
    assert "Hello" in r.text


def test_unknown_lang_query_param_does_not_set_a_cookie(monkeypatch, tmp_path):
    client = TestClient(make_app(monkeypatch, tmp_path))
    r = client.get("/?lang=de")
    assert "Bonjour" in r.text  # replie sur le français
    assert LOCALE_COOKIE not in client.cookies


# ---------------------------------------------------------------------
# source_locale configurable (know/features/configurable-source-locale.md)
# ---------------------------------------------------------------------


def test_source_locale_defaults_to_fr_unchanged():
    catalog = Catalog(None, [])
    assert catalog.source_locale == "fr" == SOURCE_LOCALE
    assert catalog.available == ["fr"]


def test_source_locale_can_be_configured_to_another_code():
    catalog = Catalog(None, ["fr"], source_locale="en")
    assert catalog.source_locale == "en"
    assert catalog.available[0] == "en"


def test_source_locale_needs_no_catalog_file_identity_translator(tmp_path):
    """Même garantie que pour "fr" par défaut : la locale source, quelle
    qu'elle soit, n'a jamais besoin de fichier — _() y est l'identité."""
    catalog = Catalog(str(tmp_path), [], source_locale="en")
    translator = catalog.translator_for("en")
    assert translator("Hello") == "Hello"


def test_source_locale_listed_in_locales_warns_and_is_still_excluded_from_loading(tmp_path, caplog):
    """Piège d'origine : locales=["fr", "en"] avec source_locale="fr"
    filtrait "fr" silencieusement (aucun fr.json jamais chargé, aucune
    indication). Toujours exclu du chargement — mais maintenant avec un
    avertissement explicite plutôt qu'un silence total."""
    import logging

    (tmp_path / "fr.json").write_text('{"Bonjour": "ne devrait jamais être lu"}', encoding="utf-8")
    with caplog.at_level(logging.WARNING, logger="xweb.i18n"):
        catalog = Catalog(str(tmp_path), ["fr", "en"], source_locale="fr")
    assert any("source_locale" in r.message and "fr" in r.message for r in caplog.records)
    assert "fr" not in catalog._tables  # jamais chargé, malgré le fichier présent


def test_resolve_locale_falls_back_to_the_catalogs_configured_source_locale():
    """Avant ce correctif, le repli final de resolve_locale lisait
    toujours la CONSTANTE de module SOURCE_LOCALE ("fr" en dur) — un
    projet à source_locale="en" serait quand même retombé sur "fr" ici,
    malgré une config explicite différente."""
    catalog = Catalog(None, [], source_locale="en")
    request = make_request()  # aucun ?lang=, aucun cookie, aucun Accept-Language
    assert resolve_locale(request, catalog) == "en"
