"""xweb.editable_table — xweb/components/editable_table.xml.

La mécanique glisser-déposer/clic-pour-éditer elle-même (_hyperscript) est
vérifiée pour de vrai contre le fichier vendorisé dans
scripts/verify-editable-table.mjs (jsdom) — pas ici, Python n'exécute
aucun _hyperscript. Ici : uniquement le rendu (props, structure,
dégradation), même découpage que test_kanban.py.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from xweb.engine.registry import QwebRegistry

ROOT = Path(__file__).parent.parent
COMPONENTS_DIR = ROOT / "xweb" / "components"


@pytest.fixture
def registry() -> QwebRegistry:
    r = QwebRegistry()
    r.register_dir(COMPONENTS_DIR)
    return r


COLUMNS = [
    {"key": "name", "label": "Nom", "type": "text"},
    {"key": "status", "label": "Statut", "type": "select", "options": [
        {"value": "active", "label": "Actif", "color": "success"},
        {"value": "paused", "label": "En pause", "color": "warning"},
    ]},
    {"key": "done", "label": "Fait", "type": "checkbox"},
]
ROWS = [
    {"id": "r1", "name": "Ada Lovelace", "status": "active", "done": True},
    {"id": "r2", "name": "Grace Hopper", "status": "paused", "done": False},
]


def test_renders_one_row_per_entry_with_typed_cells(registry):
    html = registry.render("xweb.editable_table", {"columns": COLUMNS, "rows": ROWS, "save_url": "/x"})
    assert 'id="r1"' in html and 'id="r2"' in html
    assert "Ada Lovelace" in html and "Grace Hopper" in html
    assert "Actif" in html and "En pause" in html
    assert 'type="checkbox"' in html


def test_text_cell_has_both_display_span_and_hidden_input(registry):
    html = registry.render("xweb.editable_table", {"columns": COLUMNS, "rows": ROWS, "save_url": "/x"})
    assert "cell-display" in html
    assert 'style="display:none"' in html  # état initial de l'input — jamais une classe "hidden"


def test_checkbox_reflects_the_row_value(registry):
    html = registry.render("xweb.editable_table", {"columns": COLUMNS, "rows": ROWS, "save_url": "/x"})
    # r1.done=True -> checked="checked" apparaît ; r2.done=False -> pas de checked pour cette case
    checked_count = html.count('checked="checked"')
    assert checked_count == 1


def test_select_cell_shows_a_colored_dot_for_the_options_color(registry):
    """Redessiné depuis : point coloré + texte simple, plus de badge —
    bg-{{color}} sur le point, pas badge-{{color}} sur une étiquette."""
    html = registry.render("xweb.editable_table", {"columns": COLUMNS, "rows": ROWS, "save_url": "/x"})
    assert "bg-success" in html  # r1 = active
    assert "bg-warning" in html  # r2 = paused


def test_add_row_button_omitted_when_add_row_url_is_empty(registry):
    html = registry.render("xweb.editable_table", {"columns": COLUMNS, "rows": ROWS, "save_url": "/x"})
    assert "Nouvelle ligne" not in html


def test_add_row_button_present_when_add_row_url_given(registry):
    html = registry.render("xweb.editable_table", {"columns": COLUMNS, "rows": ROWS, "save_url": "/x", "add_row_url": "/rows"})
    assert "Nouvelle ligne" in html
    assert 'hx-post="/rows"' in html


def test_add_row_button_targets_this_instances_own_tbody_by_id(registry):
    """Régression : hx-target="tbody" (bare, sans id) ciblait le PREMIER
    <tbody> de toute la page — trouvé sur la landing page, qui affiche
    aussi xweb.table juste au-dessus (deux <tbody>), en testant pour de
    vrai contre un serveur réel (scripts/verify-editable-table-live.mjs).
    id= (comme xweb.kanban/modal/drawer) scope le ciblage par instance."""
    html = registry.render("xweb.editable_table", {
        "columns": COLUMNS, "rows": ROWS, "save_url": "/x", "add_row_url": "/rows", "id": "my-table",
    })
    assert 'id="my-table-tbody"' in html
    assert 'hx-target="#my-table-tbody"' in html
    assert 'hx-target="tbody"' not in html


def test_add_row_button_uses_the_default_id_when_none_given(registry):
    html = registry.render("xweb.editable_table", {"columns": COLUMNS, "rows": ROWS, "save_url": "/x", "add_row_url": "/rows"})
    assert 'id="xweb-editable-table-tbody"' in html
    assert 'hx-target="#xweb-editable-table-tbody"' in html


def test_delete_button_omitted_when_delete_row_url_is_empty(registry):
    html = registry.render("xweb.editable_table", {"columns": COLUMNS, "rows": ROWS, "save_url": "/x"})
    assert "hx-delete" not in html


def test_delete_button_targets_the_right_row_when_delete_row_url_given(registry):
    html = registry.render("xweb.editable_table", {"columns": COLUMNS, "rows": ROWS, "save_url": "/x", "delete_row_url": "/rows"})
    assert 'hx-delete="/rows/r1"' in html
    assert 'hx-delete="/rows/r2"' in html


def test_reorder_hx_post_omitted_when_reorder_url_is_empty(registry):
    """t-att-hx-post="reorder_url or None" — même convention que move_url
    sur xweb.kanban : falsy -> l'attribut n'est jamais émis. hx-trigger/
    hx-vals restent posés (comme sur xweb.kanban) — inertes sans hx-post,
    htmx n'agit jamais sur un hx-trigger seul."""
    html = registry.render("xweb.editable_table", {"columns": COLUMNS, "rows": ROWS, "save_url": "/x"})
    assert "hx-post=" not in html


def test_reorder_hx_post_present_when_reorder_url_given(registry):
    html = registry.render("xweb.editable_table", {"columns": COLUMNS, "rows": ROWS, "save_url": "/x", "reorder_url": "/reorder"})
    assert 'hx-post="/reorder"' in html
    assert 'hx-trigger="table:reordered"' in html


def test_no_rows_renders_an_empty_body_not_a_crash(registry):
    html = registry.render("xweb.editable_table", {"columns": COLUMNS, "rows": [], "save_url": "/x"})
    assert "<table" in html
    assert 'id="r1"' not in html


def test_no_columns_renders_a_table_with_no_data_cells_not_a_crash(registry):
    html = registry.render("xweb.editable_table", {"columns": [], "rows": ROWS, "save_url": "/x"})
    assert "<table" in html


def test_cell_value_is_escaped_never_raw_html(registry):
    """t-esc partout pour une valeur de cellule (CLAUDE.md — échappement
    par défaut pour toute donnée qui vient d'un formulaire/d'une API)."""
    rows = [{"id": "r1", "name": "<script>alert(1)</script>", "status": "", "done": False}]
    html = registry.render("xweb.editable_table", {"columns": COLUMNS, "rows": rows, "save_url": "/x"})
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_editable_table_row_can_be_rendered_alone_as_a_fragment(registry):
    """add_row_url répond avec xweb.editable_table_row seul — c'est ce
    fragment qu'une route POST doit pouvoir rendre indépendamment."""
    html = registry.render("xweb.editable_table_row", {"row": ROWS[0], "columns": COLUMNS, "save_url": "/x"})
    assert html.strip().startswith("<tr")
    assert "Ada Lovelace" in html


# ── Ajout/renommage de colonne ──────────────────────────────────────────────


def test_add_column_button_omitted_when_add_column_url_is_empty(registry):
    html = registry.render("xweb.editable_table", {"columns": COLUMNS, "rows": ROWS, "save_url": "/x"})
    assert "Ajouter une colonne" not in html


def test_add_column_button_present_and_targets_the_whole_table(registry):
    html = registry.render("xweb.editable_table", {"columns": COLUMNS, "rows": ROWS, "save_url": "/x", "add_column_url": "/cols"})
    assert 'hx-post="/cols"' in html
    assert 'hx-target="closest .editable-table"' in html
    assert 'hx-swap="outerHTML"' in html


def test_headers_are_plain_text_when_rename_column_url_is_empty(registry):
    html = registry.render("xweb.editable_table", {"columns": COLUMNS, "rows": ROWS, "save_url": "/x"})
    assert "cell-display" not in html.split("</thead>")[0]  # aucune bascule éditable dans le <thead>


def test_headers_are_editable_when_rename_column_url_given(registry):
    html = registry.render("xweb.editable_table", {"columns": COLUMNS, "rows": ROWS, "save_url": "/x", "rename_column_url": "/cols"})
    thead = html.split("</thead>")[0]
    assert "cell-display" in thead
    assert 'hx-patch="/cols/name"' in thead
    assert 'hx-patch="/cols/status"' in thead


def test_editable_table_header_cell_can_be_rendered_alone_as_a_fragment(registry):
    html = registry.render("xweb.editable_table_header_cell", {"col": COLUMNS[0], "rename_column_url": "/cols"})
    assert html.strip().startswith("<th")
    assert "Nom" in html
