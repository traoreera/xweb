"""Phase 5 (xweb Blueprint §7, docs/components.md) — les composants
migrés de xui vers des classes DaisyUI. Chaque test trace le comportement
réel du composant django-cotton-ui original qu'il doit préserver.
"""

from pathlib import Path

import pytest

from xweb.engine.registry import QwebRegistry

COMPONENTS_DIR = Path(__file__).parent.parent / "xweb" / "components"


@pytest.fixture
def registry() -> QwebRegistry:
    r = QwebRegistry()
    r.register_dir(COMPONENTS_DIR)
    return r


# ---------------------------------------------------------------------
# badge.xml
# ---------------------------------------------------------------------


def test_badge_defaults_render_span_with_soft_style(registry):
    html = registry.render("xweb.badge", {"slot": "Nouveau"})
    assert "<span" in html
    assert "badge badge-neutral badge-md badge-soft" in html
    assert "Nouveau" in html


def test_badge_solid_variant_drops_soft_class(registry):
    html = registry.render("xweb.badge", {"slot": "x", "variant": "solid", "color": "error"})
    assert "badge-soft" not in html
    assert "badge-error" in html


def test_badge_href_renders_anchor(registry):
    html = registry.render("xweb.badge", {"slot": "Voir", "href": "/x"})
    assert html.strip().startswith("<a ")
    assert 'href="/x"' in html


def test_badge_icons_are_not_escaped_trusted_markup(registry):
    """icon_leading/icon_trailing portent du SVG — docs/components.md,
    même convention que xui: props de confiance, pas du texte utilisateur."""
    from markupsafe import Markup

    html = registry.render("xweb.badge", {"slot": "x", "icon_leading": Markup("<svg>i</svg>")})
    assert "<svg>i</svg>" in html


# ---------------------------------------------------------------------
# spinner.xml
# ---------------------------------------------------------------------


def test_spinner_defaults(registry):
    html = registry.render("xweb.spinner", {})
    assert "loading loading-spinner loading-md text-accent" in html


def test_spinner_white_and_current_map_to_plain_utilities_not_daisyui_color(registry):
    assert "text-white" in registry.render("xweb.spinner", {"color": "white"})
    assert "text-current" in registry.render("xweb.spinner", {"color": "current"})


# ---------------------------------------------------------------------
# alert.xml
# ---------------------------------------------------------------------


def test_alert_variant_maps_directly_to_daisyui_no_remapping_needed(registry):
    for variant in ("info", "success", "warning", "error"):
        html = registry.render("xweb.alert", {"slot": "x", "variant": variant})
        assert f"alert alert-{variant}" in html
        assert 'role="alert"' in html


def test_alert_title_optional(registry):
    html = registry.render("xweb.alert", {"slot": "Message"})
    assert "font-semibold" not in html
    html2 = registry.render("xweb.alert", {"slot": "Message", "title": "Attention"})
    assert "Attention" in html2 and "font-semibold" in html2


def test_alert_dismiss_button_only_when_dismissible(registry):
    html = registry.render("xweb.alert", {"slot": "x"})
    assert "<button" not in html
    html2 = registry.render("xweb.alert", {"slot": "x", "dismissible": True})
    assert 'remove closest .alert' in html2  # vérifié en vrai contre _hyperscript.min.js, voir scripts/


# ---------------------------------------------------------------------
# label.xml
# ---------------------------------------------------------------------


def test_label_for_attribute_omitted_when_absent(registry):
    html = registry.render("xweb.label", {"slot": "Nom"})
    assert " for=" not in html


def test_label_for_attribute_present_when_given(registry):
    html = registry.render("xweb.label", {"slot": "Nom", "for_": "name-field"})
    assert 'for="name-field"' in html


def test_label_badge_calls_the_real_badge_component(registry):
    """label.xml fait t-call="xweb.badge" — preuve que la composition
    entre composants migrés marche, pas juste chacun isolément."""
    html = registry.render("xweb.label", {"slot": "Email", "for_": "email"})
    assert "badge" not in html
    html2 = registry.render("xweb.label", {"slot": "Email", "badge": "Bêta"})
    assert "badge badge-neutral badge-sm" in html2
    assert "Bêta" in html2


# ---------------------------------------------------------------------
# input.xml
# ---------------------------------------------------------------------


def test_input_basic_attributes(registry):
    html = registry.render("xweb.input", {"name": "email", "type": "email", "placeholder": "vous@exemple.com"})
    assert 'type="email"' in html
    assert 'name="email"' in html
    assert 'placeholder="vous@exemple.com"' in html
    assert "input input-bordered w-full input-md" in html


def test_input_addons_add_padding_classes(registry):
    from markupsafe import Markup

    html = registry.render("xweb.input", {"left_addon": Markup("@")})
    assert "pl-10" in html
    assert "pr-10" not in html


def test_input_disabled_and_readonly_are_boolean_attrs(registry):
    html = registry.render("xweb.input", {"disabled": True, "readonly": True})
    assert 'disabled="disabled"' in html
    assert 'readonly="readonly"' in html


# ---------------------------------------------------------------------
# checkbox.xml
# ---------------------------------------------------------------------


def test_checkbox_label_and_description(registry):
    html = registry.render("xweb.checkbox", {"label": "Recevoir la newsletter", "description": "Une fois par mois"})
    assert 'type="checkbox"' in html
    assert "class=\"checkbox mt-0.5\"" in html
    assert "Recevoir la newsletter" in html
    assert "Une fois par mois" in html


def test_checkbox_slot_takes_priority_over_label(registry):
    """docs xui original : {% if slot %}{{ slot }}{% elif label %} — même ordre de priorité porté."""
    html = registry.render("xweb.checkbox", {"slot": "Contenu libre", "label": "Ignoré"})
    assert "Contenu libre" in html
    assert "Ignoré" not in html


def test_checkbox_checked_and_disabled(registry):
    html = registry.render("xweb.checkbox", {"checked": True, "disabled": True})
    assert 'checked="checked"' in html
    assert 'disabled="disabled"' in html
    assert "cursor-not-allowed" in html


# ---------------------------------------------------------------------
# card.xml
# ---------------------------------------------------------------------


def test_card_without_title_subheading_header_skips_the_border_block(registry):
    """"border-b" seul matcherait par accident "border-base-200" — on
    cherche le vrai marqueur du bloc d'en-tête, pas une sous-chaîne."""
    html = registry.render("xweb.card", {"slot": "Contenu simple"})
    assert "px-6 py-4 border-b" not in html
    assert "Contenu simple" in html


def test_card_with_title_gets_the_header_block(registry):
    html = registry.render("xweb.card", {"slot": "x", "title": "Titre", "subheading": "Sous-titre"})
    assert "px-6 py-4 border-b" in html
    assert "card-title" in html and "Titre" in html
    assert "Sous-titre" in html


def test_card_outline_variant(registry):
    html = registry.render("xweb.card", {"slot": "x", "variant": "outline"})
    assert "card-border" in html
    assert "shadow-sm" not in html


def test_card_padding_none_removes_padding_class(registry):
    html = registry.render("xweb.card", {"slot": "x", "padding": "none"})
    assert "p-6" not in html


def test_card_composes_a_real_nested_button(registry):
    """La vraie preuve que la composition marche : une card dont le
    contenu est un t-call vers xweb.button, pas du texte."""
    r = QwebRegistry()
    r.register_dir(COMPONENTS_DIR)
    r.register_source(
        """<template t-name="test.page">
            <t t-call="xweb.card" title="Actions" extra_class="">
                <t t-call="xweb.button" variant="primary" size="md" extra_class="">Confirmer</t>
            </t>
        </template>"""
    )
    html = r.render("test.page", {})
    assert "&lt;button" not in html
    assert "<button" in html
    assert "Confirmer" in html
    assert "card-title" in html and "Actions" in html
