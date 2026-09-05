"""Composants ajoutés pour compléter le catalogue DaisyUI, suite de
test_components_v3.py — swap, join, radial_progress, countdown, fieldset,
list, carousel, mockup, chat_bubble, popup.
"""

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


# ── xweb.swap ────────────────────────────────────────────────────────────


def test_swap_renders_both_states_and_a_hidden_checkbox(registry):
    html = registry.render("xweb.swap", {"slot_on": Markup("ON"), "slot_off": Markup("OFF")})
    assert "swap-on" in html and "ON" in html
    assert "swap-off" in html and "OFF" in html
    assert 'type="checkbox"' in html


def test_swap_checked_reflects_initial_state(registry):
    html = registry.render("xweb.swap", {"slot_on": Markup("x"), "slot_off": Markup("y"), "checked": True})
    assert 'checked="checked"' in html
    html2 = registry.render("xweb.swap", {"slot_on": Markup("x"), "slot_off": Markup("y")})
    assert 'checked="checked"' not in html2


def test_swap_flip_default_true_can_be_disabled(registry):
    html = registry.render("xweb.swap", {"slot_on": Markup("x"), "slot_off": Markup("y"), "flip": False})
    assert "swap-flip" not in html


# ── xweb.join ────────────────────────────────────────────────────────────


def test_join_wraps_slot_content_as_is(registry):
    html = registry.render("xweb.join", {"slot": Markup('<button class="btn join-item">A</button>')})
    assert 'class="join' in html
    assert "join-item" in html


def test_join_vertical_flag(registry):
    html = registry.render("xweb.join", {"slot": Markup("x"), "vertical": True})
    assert "join-vertical" in html


# ── xweb.radial_progress ─────────────────────────────────────────────────


def test_radial_progress_sets_value_and_size_via_style(registry):
    html = registry.render("xweb.radial_progress", {"value": 70, "size": "8rem"})
    assert "--value:70" in html
    assert "--size:8rem" in html


def test_radial_progress_default_slot_is_the_percentage(registry):
    html = registry.render("xweb.radial_progress", {"value": 42})
    assert "42%" in html


def test_radial_progress_custom_slot_overrides_percentage(registry):
    html = registry.render("xweb.radial_progress", {"value": 42, "slot": Markup("<b>ok</b>")})
    assert "<b>ok</b>" in html
    assert "42%" not in html


def test_radial_progress_thickness_omitted_when_not_given(registry):
    html = registry.render("xweb.radial_progress", {"value": 10})
    assert "--thickness" not in html


# ── xweb.countdown ───────────────────────────────────────────────────────


def test_countdown_sets_the_value_custom_property(registry):
    html = registry.render("xweb.countdown", {"value": 42})
    assert "--value:42;" in html


def test_countdown_label_is_optional(registry):
    html = registry.render("xweb.countdown", {"value": 5, "label": "jours"})
    assert "jours" in html
    html2 = registry.render("xweb.countdown", {"value": 5})
    assert "opacity-60" not in html2  # le <span> de label n'apparaît pas du tout


# ── xweb.fieldset ────────────────────────────────────────────────────────


def test_fieldset_renders_legend_slot_and_help(registry):
    html = registry.render("xweb.fieldset", {"legend": "Profil", "help": "Aide", "slot": Markup("<input/>")})
    assert "<legend" in html and "Profil" in html
    assert "<input/>" in html
    assert "fieldset-label" in html and "Aide" in html


def test_fieldset_legend_and_help_are_optional(registry):
    html = registry.render("xweb.fieldset", {"slot": Markup("<input/>")})
    assert "<legend" not in html
    assert "fieldset-label" not in html


# ── xweb.list ────────────────────────────────────────────────────────────


def test_list_renders_title_subtitle_icon(registry):
    html = registry.render("xweb.list", {"items": [{"title": "Ada", "subtitle": "Admin", "icon": "user"}]})
    assert "Ada" in html and "Admin" in html
    assert "list-row" in html


def test_list_subtitle_and_icon_are_optional(registry):
    html = registry.render("xweb.list", {"items": [{"title": "Sans rien"}]})
    assert "Sans rien" in html
    assert html.count("list-row") == 1


def test_list_value_is_escaped(registry):
    html = registry.render("xweb.list", {"items": [{"title": "<script>x</script>"}]})
    assert "<script>x</script>" not in html
    assert "&lt;script&gt;" in html


# ── xweb.carousel ────────────────────────────────────────────────────────


def test_carousel_renders_one_item_per_entry(registry):
    """class="carousel-item ne pas confondre avec l'id "...-item-N" qui
    contient aussi la sous-chaîne "carousel-item" (défaut id="xweb-
    carousel") — d'où le comptage sur la classe précisément, pas le mot."""
    html = registry.render("xweb.carousel", {"items": [{"src": "/a.jpg"}, {"src": "/b.jpg"}]})
    assert html.count('class="carousel-item') == 2
    assert '/a.jpg' in html and '/b.jpg' in html


def test_carousel_nav_wraps_around_with_modulo_not_a_nested_filter(registry):
    """Régression : (item_index - 1) % (items|length) ne serait JAMAIS
    reconnu comme un filtre entre parenthèses (split_filters ne coupe qu'à
    profondeur 0) — | redeviendrait l'opérateur bitwise Python, "length" un
    nom indéfini, toute l'expression retomberait en None silencieusement.
    Le composant précalcule "count" à plat avant la boucle pour l'éviter."""
    html = registry.render("xweb.carousel", {
        "id": "c", "show_nav": True,
        "items": [{"src": "/a.jpg"}, {"src": "/b.jpg"}, {"src": "/c.jpg"}],
    })
    assert 'href="#c-item-2"' in html  # précédent du premier (index 0) -> le dernier
    assert 'href="#c-item-0"' in html  # suivant du dernier (index 2) -> le premier
    assert 'href="#c-item-"' not in html  # jamais une ancre vide (preuve que ça n'est pas retombé en None)


def test_carousel_no_nav_by_default(registry):
    html = registry.render("xweb.carousel", {"items": [{"src": "/a.jpg"}]})
    assert "btn-circle" not in html


# ── xweb.mockup ──────────────────────────────────────────────────────────


def test_mockup_browser_is_the_default_variant(registry):
    html = registry.render("xweb.mockup", {"slot": Markup("<p>x</p>")})
    assert "mockup-browser" in html
    assert "<p>x</p>" in html


def test_mockup_browser_shows_url_when_given(registry):
    html = registry.render("xweb.mockup", {"url": "xweb.dev", "slot": Markup("x")})
    assert "xweb.dev" in html


def test_mockup_window_variant(registry):
    html = registry.render("xweb.mockup", {"variant": "window", "slot": Markup("x")})
    assert "mockup-window" in html
    assert "mockup-browser" not in html


def test_mockup_phone_variant_wraps_in_phone_display(registry):
    html = registry.render("xweb.mockup", {"variant": "phone", "slot": Markup('<img src="/x.jpg"/>')})
    assert "mockup-phone" in html
    assert "mockup-phone-camera" in html
    assert "mockup-phone-display" in html
    assert '/x.jpg' in html


# ── xweb.chat_bubble ─────────────────────────────────────────────────────


def test_chat_bubble_renders_message_escaped(registry):
    html = registry.render("xweb.chat_bubble", {"message": "<script>x</script>"})
    assert "<script>x</script>" not in html
    assert "&lt;script&gt;" in html


def test_chat_bubble_default_side_is_start(registry):
    html = registry.render("xweb.chat_bubble", {"message": "x"})
    assert "chat-start" in html
    assert "chat-end" not in html


def test_chat_bubble_end_side(registry):
    html = registry.render("xweb.chat_bubble", {"message": "x", "side": "end"})
    assert "chat-end" in html


def test_chat_bubble_header_omitted_without_author_or_time(registry):
    html = registry.render("xweb.chat_bubble", {"message": "x"})
    assert "chat-header" not in html


def test_chat_bubble_avatar_omitted_without_avatar_initial(registry):
    html = registry.render("xweb.chat_bubble", {"message": "x"})
    assert "chat-image" not in html


def test_chat_bubble_avatar_present_with_initial(registry):
    html = registry.render("xweb.chat_bubble", {"message": "x", "avatar_initial": "A"})
    assert "chat-image" in html
    assert ">A<" in html


# ── xweb.popup ───────────────────────────────────────────────────────────
# Menu contextuel positionné au curseur (contextmenu), pas ancré à un
# élément fixe — voir la docstring de xweb/components/popup.xml. La
# mécanique _hyperscript (halt the event, positionnement, ouverture/
# fermeture) est vérifiée pour de vrai contre _hyperscript.min.js
# vendorisé dans scripts/verify-hyperscript.mjs ; ces tests-ci ne
# couvrent que le HTML produit par le compilateur.


def test_popup_renders_zone_and_panel_with_matching_ids(registry):
    html = registry.render(
        "xweb.popup",
        {"id": "ctx-1", "slot": Markup("<span>Zone</span>"), "slot_menu": Markup("<li>Item</li>")},
    )
    assert "<span>Zone</span>" in html
    assert 'id="ctx-1-panel"' in html
    assert "ctx-1-panel" in html  # référencé par le _hyperscript de la zone


def test_popup_panel_uses_fixed_position_not_absolute(registry):
    # position: fixed (pas absolute) est le choix délibéré qui rend le
    # panneau positionnable aux coordonnées curseur peu importe où la zone
    # est imbriquée dans la page — voir la docstring du composant.
    html = registry.render("xweb.popup", {"slot": Markup("x"), "slot_menu": Markup("y")})
    assert "popover-panel" in html
    assert " fixed " in html or html.count("fixed") >= 1


def test_popup_contextmenu_handler_halts_the_event(registry):
    html = registry.render("xweb.popup", {"id": "p1", "slot": Markup("x"), "slot_menu": Markup("y")})
    assert "on contextmenu halt the event" in html


def test_popup_closes_on_click_elsewhere_and_escape(registry):
    html = registry.render("xweb.popup", {"slot": Markup("x"), "slot_menu": Markup("y")})
    assert "on click from elsewhere remove .popover-open from me" in html
    assert "Escape" in html


def test_popup_width_is_a_literal_class_not_interpolated_value(registry):
    html = registry.render("xweb.popup", {"width": "w-72", "slot": Markup("x"), "slot_menu": Markup("y")})
    assert "w-72" in html


def test_popup_default_id_lets_a_single_instance_work_unconfigured(registry):
    html = registry.render("xweb.popup", {"slot": Markup("x"), "slot_menu": Markup("y")})
    assert "xweb-popup-panel" in html


def test_popup_menu_slot_is_never_escaped(registry):
    html = registry.render(
        "xweb.popup", {"slot": Markup("x"), "slot_menu": Markup('<a href="#" class="text-error">Supprimer</a>')}
    )
    assert '<a href="#" class="text-error">Supprimer</a>' in html
