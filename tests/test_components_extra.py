"""Les 7 composants restants du catalogue xui (docs/components.md) :
collapse, accordion, drawer, popover, combobox, calendar, datepicker.

La mécanique _hyperscript interactive (popover : ouvrir/fermer, combobox :
filtrer/sélectionner, calendar->datepicker : événement calendar:select) est
vérifiée pour de vrai contre le fichier vendorisé dans
scripts/verify-hyperscript.mjs (jsdom) — Python n'exécute aucun
_hyperscript. Ici : rendu, props, dégradation, et xweb/calendar.py::
month_grid() qui, lui, est du pur Python testable directement.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from xweb.calendar import month_grid
from xweb.engine.registry import QwebRegistry

COMPONENTS_DIR = Path(__file__).parent.parent / "xweb" / "components"


@pytest.fixture
def registry() -> QwebRegistry:
    r = QwebRegistry()
    r.register_dir(COMPONENTS_DIR)
    return r


# ---------------------------------------------------------------------
# xweb.collapse — <details>/<summary> natif, zéro JS
# ---------------------------------------------------------------------


def test_collapse_renders_details_with_title_and_content(registry):
    html = registry.render("xweb.collapse", {"title": "Une question", "slot": "Une réponse"})
    assert "<details" in html
    assert "collapse-arrow" in html  # variant par défaut
    assert "Une question" in html
    assert "Une réponse" in html


def test_collapse_open_prop_renders_the_open_boolean_attribute(registry):
    closed = registry.render("xweb.collapse", {"title": "x", "slot": "y"})
    assert "open=" not in closed
    opened = registry.render("xweb.collapse", {"title": "x", "slot": "y", "open": True})
    assert 'open="open"' in opened


def test_collapse_variant_none_omits_the_collapse_arrow_class(registry):
    html = registry.render("xweb.collapse", {"title": "x", "slot": "y", "variant": ""})
    assert "collapse-arrow" not in html
    assert "collapse-plus" not in html


# ---------------------------------------------------------------------
# xweb.accordion — plusieurs <details> groupés par `name` (exclusivité native)
# ---------------------------------------------------------------------


def test_accordion_renders_one_details_per_item_sharing_the_same_name(registry):
    html = registry.render("xweb.accordion", {
        "name": "faq",
        "items": [{"title": "Q1", "content": "R1"}, {"title": "Q2", "content": "R2"}],
    })
    assert html.count("<details") == 2
    assert html.count('name="faq"') == 2
    assert "Q1" in html and "R1" in html
    assert "Q2" in html and "R2" in html


def test_accordion_item_open_flag_is_per_item(registry):
    html = registry.render("xweb.accordion", {
        "items": [{"title": "Q1", "content": "R1", "open": True}, {"title": "Q2", "content": "R2"}],
    })
    assert html.count('open="open"') == 1


def test_accordion_content_is_escaped_not_raw_html(registry):
    """xweb.accordion utilise t-esc sur item['content'] — cohérent avec la
    convention par défaut (CLAUDE.md : t-esc pour tout ce qui vient d'un
    dict de données, jamais t-out sans raison explicite)."""
    html = registry.render("xweb.accordion", {"items": [{"title": "x", "content": "<script>alert(1)</script>"}]})
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


# ---------------------------------------------------------------------
# xweb.drawer / xweb.drawer_toggle — checkbox-driven, zéro JS
# ---------------------------------------------------------------------


def test_drawer_renders_checkbox_content_and_side_items(registry):
    html = registry.render("xweb.drawer", {
        "id": "d1",
        "slot": "Contenu principal",
        "side_items": [{"label": "Accueil", "href": "/", "icon": "home"}],
    })
    assert 'id="d1"' in html and "drawer-toggle" in html
    assert "Contenu principal" in html
    assert "Accueil" in html and 'href="/"' in html


def test_drawer_toggle_label_targets_the_same_id(registry):
    html = registry.render("xweb.drawer_toggle", {"target": "d1"})
    assert 'for="d1"' in html


def test_drawer_with_no_side_items_renders_an_empty_side_panel_not_a_crash(registry):
    html = registry.render("xweb.drawer", {"id": "d2", "slot": "x"})
    assert 'id="d2"' in html


# ---------------------------------------------------------------------
# xweb.popover — rendu (mécanique clic/Escape vérifiée en jsdom, voir
# scripts/verify-hyperscript.mjs)
# ---------------------------------------------------------------------


def test_popover_renders_trigger_and_panel_with_matching_ids(registry):
    html = registry.render("xweb.popover", {"id": "p1", "trigger_label": "Filtres", "slot": "<b>x</b>"})
    assert "Filtres" in html
    assert 'id="p1-panel"' in html
    assert "popover-panel" in html


def test_popover_position_top_uses_bottom_full_class(registry):
    html = registry.render("xweb.popover", {"id": "p1", "position": "top", "slot": "x"})
    assert "bottom-full" in html
    assert "top-full" not in html


# ---------------------------------------------------------------------
# xweb.combobox — rendu (filtrage/sélection vérifiés en jsdom)
# ---------------------------------------------------------------------


def test_combobox_renders_hidden_and_visible_inputs_plus_options(registry):
    html = registry.render("xweb.combobox", {
        "id": "c1", "name": "pays", "options": [{"value": "fr", "label": "France"}, {"value": "de", "label": "Allemagne"}],
    })
    assert 'name="pays"' in html
    assert 'id="c1"' in html
    assert 'id="c1-input"' in html
    assert 'data-value="fr"' in html
    assert "France" in html and "Allemagne" in html


def test_combobox_with_no_options_shows_a_placeholder_row_not_a_crash(registry):
    html = registry.render("xweb.combobox", {"id": "c1", "options": []})
    assert "Aucune option." in html


# ---------------------------------------------------------------------
# xweb/calendar.py::month_grid — pur Python, testable directement
# ---------------------------------------------------------------------


def test_month_grid_covers_full_weeks_monday_first():
    grid = month_grid(2026, 9)  # septembre 2026 commence un mardi
    assert grid["month_label"] == "Septembre 2026"
    for week in grid["weeks"]:
        assert len(week) == 7
    # premier jour de la première semaine est un jour du mois précédent (août)
    first_cell = grid["weeks"][0][0]
    assert first_cell["in_month"] is False
    assert first_cell["iso"] < "2026-09-01"


def test_month_grid_marks_today_and_selected():
    grid = month_grid(2026, 9, today=date(2026, 9, 15), selected="2026-09-20")
    flat = [cell for week in grid["weeks"] for cell in week]
    today_cells = [c for c in flat if c["is_today"]]
    selected_cells = [c for c in flat if c["is_selected"]]
    assert len(today_cells) == 1 and today_cells[0]["iso"] == "2026-09-15"
    assert len(selected_cells) == 1 and selected_cells[0]["iso"] == "2026-09-20"


def test_month_grid_today_outside_displayed_month_marks_nothing_not_a_crash():
    grid = month_grid(2026, 9, today=date(2020, 1, 1))
    flat = [cell for week in grid["weeks"] for cell in week]
    assert not any(c["is_today"] for c in flat)


def test_month_grid_without_selected_marks_nothing_selected():
    grid = month_grid(2026, 9)
    flat = [cell for week in grid["weeks"] for cell in week]
    assert not any(c["is_selected"] for c in flat)


# ---------------------------------------------------------------------
# xweb.calendar / xweb.datepicker — rendu (événement calendar:select
# vérifié en jsdom)
# ---------------------------------------------------------------------


def test_calendar_renders_the_grid_with_data_iso_on_each_day(registry):
    grid = month_grid(2026, 9)
    html = registry.render("xweb.calendar", {"id": "cal1", **grid})
    assert 'id="cal1"' in html
    assert grid["month_label"] in html
    assert 'data-iso="2026-09-01"' in html


def test_calendar_prev_next_links_omitted_when_urls_are_empty(registry):
    grid = month_grid(2026, 9)
    html = registry.render("xweb.calendar", {"id": "cal1", **grid})
    assert "<a " not in html  # pas de navigation sans prev_url/next_url


def test_calendar_prev_next_links_rendered_when_urls_given(registry):
    grid = month_grid(2026, 9)
    html = registry.render("xweb.calendar", {"id": "cal1", **grid, "prev_url": "?m=8", "next_url": "?m=10"})
    assert 'href="?m=8"' in html
    assert 'href="?m=10"' in html


def test_datepicker_renders_input_and_embeds_the_calendar_with_a_derived_id(registry):
    grid = month_grid(2026, 9)
    html = registry.render("xweb.datepicker", {"id": "dp1", "name": "date", "value": "2026-09-15", **grid})
    assert 'name="date"' in html
    assert 'id="dp1-panel"' in html
    assert 'id="dp1-calendar"' in html  # t-att-id="id + '-calendar'" sur le t-call
    assert 'value="2026-09-15"' in html
