"""Email — xweb/email.py::render_email() et xweb.email_layout
(components/email.xml). docs/email.md, docs/spec-v1.md §5.

Comme xweb/pdf.py : ce module ne sait que produire du HTML, jamais
envoyer — le transport reste le contrat ext.email déjà établi
(extensions/email.py::ConsoleEmailExtension en dev, absent tant qu'aucun
plugin n'est reconstruit). L'exemple bout en bout qui vivait ici
(plugins/demo, POST /plugins/demo/email/send) a été retiré avec
plugins/ — à réécrire contre le prochain plugin qui consomme ext.email,
voir docs/plugins.md §5. Ce qui reste ci-dessous ne teste que xweb lui-même,
sans dépendance à un plugin.
"""

from __future__ import annotations

from pathlib import Path

import pytest

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
