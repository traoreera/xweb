"""PDF — xweb/pdf.py::render_pdf() et le layout xweb.pdf_document
(xweb/components/pdf.xml). docs/pdf.md.

weasyprint est une vraie dépendance installée (`uv add weasyprint`,
pyproject.toml) — ces tests appellent le paquet réel, jamais un mock, pour
vérifier qu'un vrai PDF sort du moteur (même politique que
npm run verify:hyperscript/verify:demo : vérifier pour de vrai).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from xweb.engine.registry import QwebRegistry
from xweb.pdf import PdfUnavailable, render_pdf

COMPONENTS_DIR = Path(__file__).parent.parent / "xweb" / "components"

CONTENT_TEMPLATE = """<template t-name="test.pdf_content">
    <p>Bonjour <t t-esc="name"/></p>
</template>"""

RAW_DOCUMENT_TEMPLATE = """<template t-name="test.pdf_raw">
<html><head><meta charset="utf-8"/><title>Brut</title></head>
<body><p>Document déjà complet, sans layout.</p></body></html>
</template>"""


@pytest.fixture
def registry():
    r = QwebRegistry()
    r.register_dir(COMPONENTS_DIR)
    r.register_source(CONTENT_TEMPLATE)
    r.register_source(RAW_DOCUMENT_TEMPLATE)
    return r


def test_render_pdf_produces_real_pdf_bytes(registry):
    pdf = render_pdf(registry, "test.pdf_content", {"page_title": "Test", "app_name": "xweb", "generated_at": "2026-09-02 12:00", "name": "Alice"})
    assert isinstance(pdf, bytes)
    assert pdf.startswith(b"%PDF-")


def test_render_pdf_wraps_content_in_the_pdf_layout_by_default(registry):
    """test.pdf_content lui-même ne référence jamais page_title — un PDF
    qui varie avec page_title prouve donc que le layout par défaut
    (xweb.pdf_document, qui affiche page_title dans son en-tête) a bien
    été appliqué autour du contenu. Comparaison directe du texte impossible
    : les flux PDF sont compressés (FlateDecode), pas une simple recherche
    de sous-chaîne."""
    ctx = {"app_name": "xweb", "generated_at": "2026-09-02 12:00", "name": "Alice"}
    pdf_a = render_pdf(registry, "test.pdf_content", {**ctx, "page_title": "Rapport Un"})
    pdf_b = render_pdf(registry, "test.pdf_content", {**ctx, "page_title": "Rapport Deux"})
    assert pdf_a != pdf_b


def test_render_pdf_with_layout_none_uses_template_as_a_complete_document(registry):
    pdf = render_pdf(registry, "test.pdf_raw", {}, layout=None)
    assert pdf.startswith(b"%PDF-")


def test_render_pdf_raises_pdf_unavailable_when_weasyprint_is_missing(registry, monkeypatch):
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "weasyprint":
            raise ImportError("no weasyprint")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    with pytest.raises(PdfUnavailable):
        render_pdf(registry, "test.pdf_content", {"page_title": "T", "app_name": "xweb", "generated_at": "x", "name": "Alice"})


def test_pdf_document_shows_empty_state_placeholder_verbatim():
    """xweb.pdf_document se contente d'injecter t-out="content" — le
    contenu (ex. account.audit_pdf sur liste vide) porte son propre texte
    d'état vide, pas le layout lui-même."""
    r = QwebRegistry()
    r.register_dir(COMPONENTS_DIR)
    html = r.render("xweb.pdf_document", {"page_title": "X", "app_name": "xweb", "generated_at": "2026-09-02", "content": "<p class=\"pdf-empty\">Rien.</p>"})
    assert "Rien." in html
    assert "pdf-empty" in html
