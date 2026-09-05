"""Corrections apportées suite à know/features/*.md (frottements réels
remontés depuis un autre projet vendorisant xweb, vérifiés contre CE
dépôt avant d'être corrigés) : xweb.marketing_layout (lien "Démo" codé en
dur), xweb.locale_switcher (libellés), xweb.card (slot_header), xweb.stat
(bordered)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from markupsafe import Markup

from xweb.engine.registry import QwebRegistry

COMPONENTS_DIR = Path(__file__).parent.parent / "xweb" / "components"


@pytest.fixture
def registry() -> QwebRegistry:
    r = QwebRegistry()
    r.register_dir(COMPONENTS_DIR)
    return r


BASE_CTX = {
    "app_name": "xweb", "page_title": "xweb", "user": None, "account": {},
    "locale": "fr", "locales": ["fr"], "content": "<p>corps</p>",
    "login_url": "/login", "request": None,
}


# ---------------------------------------------------------------------
# xweb.marketing_layout — demo_path (know/features/marketing-layout-hardcoded-links.md)
# ---------------------------------------------------------------------


def test_demo_link_absent_when_demo_path_not_given(registry):
    """Avant ce correctif : lien "Démo" codé en dur vers {{plugin_prefix}}/demo/,
    sans condition — un 404 visible dès qu'aucun plugin demo n'existe."""
    html = registry.render("xweb.marketing_layout", BASE_CTX)
    assert "Démo" not in html
    assert "/demo/" not in html


def test_demo_link_present_and_uses_demo_path_when_given(registry):
    html = registry.render("xweb.marketing_layout", {**BASE_CTX, "demo_path": "/plugins/crm/demo"})
    assert 'href="/plugins/crm/demo"' in html
    assert "Démo" in html


# ---------------------------------------------------------------------
# xweb.locale_switcher — labels (know/features/locale-switcher-display-labels.md)
# ---------------------------------------------------------------------


def test_locale_switcher_shows_raw_code_without_labels(registry):
    html = registry.render("xweb.locale_switcher", {"locale": "fr", "locales": ["fr", "en"], "request": _fake_request()})
    assert re.search(r">\s*fr\s*<", html.lower())


def test_locale_switcher_shows_display_label_when_given(registry):
    html = registry.render("xweb.locale_switcher", {
        "locale": "fr", "locales": ["fr", "en"], "request": _fake_request(),
        "labels": {"fr": "Français", "en": "English"},
    })
    assert "Français" in html
    assert "English" in html
    assert ">fr<" not in html.lower().replace("français", "")  # le code brut n'apparaît plus seul


def test_locale_switcher_unlisted_code_falls_back_to_raw_code(registry):
    """labels partiel — un code sans entrée retombe sur le code brut,
    jamais une KeyError."""
    html = registry.render("xweb.locale_switcher", {
        "locale": "fr", "locales": ["fr", "en"], "request": _fake_request(),
        "labels": {"fr": "Français"},  # "en" absent exprès
    })
    assert "Français" in html
    assert re.search(r">\s*en\s*<", html.lower())


def _fake_request():
    from starlette.requests import Request

    scope = {"type": "http", "method": "GET", "path": "/x", "query_string": b"", "headers": []}
    return Request(scope)


# ---------------------------------------------------------------------
# xweb.card — slot_header (know/features/composable-header-slot.md)
# ---------------------------------------------------------------------


def test_card_header_prop_still_works_unchanged(registry):
    # Markup(...), pas une str brute : t-out n'échappe QUE si la valeur
    # n'est pas déjà un Markup de confiance (docs/language.md#t-esc-vs-t-out)
    # — un str construit à la main n'a jamais eu vocation à passer brut ici.
    html = registry.render("xweb.card", {"title": "Titre", "header": Markup("<span>brut</span>"), "slot": "corps"})
    assert "<span>brut</span>" in html


def test_card_slot_header_composes_real_qweb_markup(registry):
    """Le vrai frottement corrigé : header="..." est une prop littérale
    (jamais un t-call imbriqué) — <t t-set-slot="header"> permet de
    composer un vrai xweb.icon + xweb.badge sans vue Python dédiée."""
    r = QwebRegistry()
    r.register_dir(COMPONENTS_DIR)
    r.register_source(
        '<template t-name="test.page">'
        '<t t-call="xweb.card" title="Statut">'
        '<t t-set-slot="header">'
        '<t t-call="xweb.badge" color="success">actif</t>'
        "</t>"
        "corps"
        "</t></template>"
    )
    html = r.render("test.page", {})
    assert "badge-success" in html
    assert "actif" in html


def test_card_slot_header_takes_priority_over_header_prop_if_both_given(registry):
    r = QwebRegistry()
    r.register_dir(COMPONENTS_DIR)
    r.register_source(
        '<template t-name="test.page">'
        '<t t-call="xweb.card" title="x" header="ancien">'
        '<t t-set-slot="header">nouveau</t>'
        "corps</t></template>"
    )
    html = r.render("test.page", {})
    assert "nouveau" in html
    assert "ancien" not in html


# ---------------------------------------------------------------------
# xweb.stat — bordered (know/features/stat-minimal-variant.md)
# ---------------------------------------------------------------------


def test_stat_bordered_by_default_unchanged(registry):
    html = registry.render("xweb.stat", {"title": "Total", "value": "42"})
    assert "stats bg-base-100 border" in html


def test_stat_bordered_false_skips_the_box(registry):
    html = registry.render("xweb.stat", {"title": "Total", "value": "42", "bordered": False})
    assert "stats bg-base-100 border" not in html
    assert "42" in html and "Total" in html
