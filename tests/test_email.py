"""Email — xweb/email.py::render_email() et xweb.email_layout
(components/email.xml). docs/email.md, docs/spec-v1.md §5.

Comme xweb/pdf.py : ce module ne sait que produire du HTML, jamais
envoyer — le transport reste le contrat ext.email déjà établi
(extensions/email.py::ConsoleEmailExtension en dev). Exemple concret bout
en bout, avec un vrai ConsoleEmailExtension (pas mocké) : plugins/demo
(POST /plugins/demo/email/send).
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from xweb.email import render_email
from xweb.engine.registry import QwebRegistry

ROOT = Path(__file__).parent.parent
COMPONENTS_DIR = ROOT / "xweb" / "components"


@pytest.fixture
def registry() -> QwebRegistry:
    r = QwebRegistry()
    r.register_dir(COMPONENTS_DIR)
    return r


CONTENT_TEMPLATE = """<template t-name="test.email_content">
    <p>Bonjour <t t-esc="name"/></p>
</template>"""

RAW_DOCUMENT_TEMPLATE = """<template t-name="test.email_raw">
<html><head><meta charset="utf-8"/><title>Brut</title></head>
<body><p>Document déjà complet, sans layout.</p></body></html>
</template>"""


# ---------------------------------------------------------------------
# render_email() — en isolation
# ---------------------------------------------------------------------


def test_render_email_wraps_content_in_the_email_layout_by_default(registry):
    registry.register_source(CONTENT_TEMPLATE)
    html = render_email(registry, "test.email_content", {"page_title": "Test", "app_name": "xweb", "name": "Ada"})
    assert "Bonjour Ada" in html
    assert "<table" in html  # layout table-based, pas flexbox/grid


def test_render_email_never_pulls_in_app_css_or_daisyui_classes(registry):
    """xweb.email_layout doit rester indépendant d'app.css (docs/email.md)
    — la plupart des clients mail suppriment <style>/Flexbox/Grid, un
    style="..." inline est le seul dénominateur commun fiable."""
    registry.register_source(CONTENT_TEMPLATE)
    html = render_email(registry, "test.email_content", {"page_title": "Test", "app_name": "xweb", "name": "Ada"})
    assert "app.css" not in html
    assert "<link" not in html
    assert 'class="btn' not in html  # aucune classe DaisyUI dans le layout lui-même


def test_render_email_with_layout_none_uses_template_as_a_complete_document(registry):
    registry.register_source(RAW_DOCUMENT_TEMPLATE)
    html = render_email(registry, "test.email_raw", {}, layout=None)
    assert html.strip().startswith("<html>")
    assert "Document déjà complet" in html


def test_render_email_layout_differs_by_page_title_proving_the_wrap_happened(registry):
    registry.register_source(CONTENT_TEMPLATE)
    ctx = {"app_name": "xweb", "name": "Ada"}
    a = render_email(registry, "test.email_content", {**ctx, "page_title": "Un"})
    b = render_email(registry, "test.email_content", {**ctx, "page_title": "Deux"})
    assert a != b
    assert "Un" in a and "Deux" not in a
    assert "Deux" in b and "Un" not in b


def test_email_button_renders_a_table_based_link_not_a_button_element(registry):
    """Un <button> HTML n'est pas fiable en email — xweb.email_button
    rend un <a> stylé en bouton (docs/email.md)."""
    html = registry.render("xweb.email_button", {"href": "https://example.com/x", "slot": "Continuer"})
    assert "<a " in html and 'href="https://example.com/x"' in html
    assert "<button" not in html
    assert "Continuer" in html


# ---------------------------------------------------------------------
# plugins/demo — exemple concret bout en bout (docs/email.md)
# ---------------------------------------------------------------------


def load_demo_pkg():
    src = ROOT / "plugins" / "demo" / "src"
    if "demo_email_test_src" not in sys.modules:
        pkg = types.ModuleType("demo_email_test_src")
        pkg.__path__ = [str(src)]
        sys.modules["demo_email_test_src"] = pkg
    return __import__("demo_email_test_src.main", fromlist=["main"])


def load_console_email_extension():
    if "demo_email_ext_module" not in sys.modules:
        import importlib.util

        spec = importlib.util.spec_from_file_location("demo_email_ext_module", ROOT / "extensions" / "email.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules["demo_email_ext_module"] = module
        spec.loader.exec_module(module)
    return sys.modules["demo_email_ext_module"].ConsoleEmailExtension


@pytest.fixture
def demo_client(monkeypatch):
    async def fake_resolve(request):
        return None

    monkeypatch.setattr("xweb.context.resolve_user_or_anonymous", fake_resolve)

    main_mod = load_demo_pkg()
    ConsoleEmailExtension = load_console_email_extension()
    email_ext = ConsoleEmailExtension()

    registry = QwebRegistry()
    registry.register_dir(COMPONENTS_DIR)
    registry.register_dir(ROOT / "plugins" / "demo" / "templates", source_plugin="demo")

    class Ctx:
        def get_service(self, name):
            if name == "ext.xweb":
                return types.SimpleNamespace(engine=registry)
            if name == "ext.email":
                return email_ext
            return None

    plugin = main_mod.Plugin()
    plugin.ctx = Ctx()
    router = plugin.get_router()

    app = FastAPI()
    app.include_router(router, prefix="/plugins/demo")
    return TestClient(app), email_ext


def test_demo_email_send_renders_via_qweb_and_reaches_ext_email_for_real(demo_client):
    """Le point central : un vrai ConsoleEmailExtension (pas mocké) reçoit
    un vrai HTML produit par le moteur QWeb — pas un texte brut, pas un
    <button> échappé, un vrai document email."""
    client, email_ext = demo_client
    r = client.post("/plugins/demo/email/send")
    assert r.status_code == 200
    assert "envoyé à ada@example.com" in r.text

    assert len(email_ext.sent) == 1
    sent = email_ext.sent[0]
    assert sent["to"] == "ada@example.com"
    assert sent["is_html"] is True
    assert "<table" in sent["body"]
    assert "Bonjour Ada" in sent["body"]
    assert "Ouvrir la démo" in sent["body"]  # xweb.email_button, appelé depuis demo.welcome_email


def test_demo_email_send_degrades_gracefully_without_ext_email(monkeypatch):
    async def fake_resolve(request):
        return None

    monkeypatch.setattr("xweb.context.resolve_user_or_anonymous", fake_resolve)

    main_mod = load_demo_pkg()
    registry = QwebRegistry()
    registry.register_dir(COMPONENTS_DIR)
    registry.register_dir(ROOT / "plugins" / "demo" / "templates", source_plugin="demo")

    class Ctx:
        def get_service(self, name):
            return types.SimpleNamespace(engine=registry) if name == "ext.xweb" else None

    plugin = main_mod.Plugin()
    plugin.ctx = Ctx()
    router = plugin.get_router()
    app = FastAPI()
    app.include_router(router, prefix="/plugins/demo")
    r = TestClient(app).post("/plugins/demo/email/send")
    assert r.status_code == 200  # jamais un 500 — juste le message "indisponible"
    assert "pas disponible" in r.text  # apostrophe échappée (&#39;) dans le HTML rendu
