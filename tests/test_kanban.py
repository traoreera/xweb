"""xweb.kanban — xweb/components/kanban.xml (docs/components.md).

La mécanique de glisser-déposer elle-même (_hyperscript : dragstart/
dragover/drop, `put ... at end of ...`) est vérifiée pour de vrai contre le
fichier vendorisé dans scripts/verify-hyperscript.mjs (jsdom) — pas ici,
Python n'exécute aucun _hyperscript. Ici : uniquement le rendu (props,
structure, dégradation), en isolation. L'exemple concret bout en bout qui
vivait ici (plugins/demo, page + persistance de /plugins/demo/kanban/move
via un vrai cycle ASGI) a été retiré avec plugins/ — à réécrire contre le
prochain plugin qui utilise xweb.kanban, voir docs/plugins.md §5.
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


# ---------------------------------------------------------------------
# xweb.kanban en isolation
# ---------------------------------------------------------------------


def test_kanban_renders_one_column_per_entry_with_its_cards(registry):
    html = registry.render("xweb.kanban", {
        "columns": [
            {"id": "todo", "title": "À faire", "cards": [{"id": "c1", "title": "Une tâche"}]},
            {"id": "done", "title": "Fait", "cards": []},
        ],
        "move_url": "/x/move",
    })
    assert 'data-column-id="todo"' in html
    assert 'data-column-id="done"' in html
    assert "À faire" in html and "Fait" in html
    assert 'id="c1"' in html
    assert "Une tâche" in html


def test_kanban_card_id_becomes_the_dom_id_for_hyperscript_getelementbyid(registry):
    """xweb/components/kanban.xml — document.getElementById(draggedId) au
    drop retrouve la carte PAR SON id DOM, qui doit donc être card['id']
    tel quel, pas un id généré ou préfixé."""
    html = registry.render("xweb.kanban", {
        "columns": [{"id": "a", "title": "A", "cards": [{"id": "unique-42", "title": "x"}]}],
    })
    assert 'id="unique-42"' in html


def test_kanban_card_subtitle_is_optional(registry):
    html = registry.render("xweb.kanban", {
        "columns": [{"id": "a", "title": "A", "cards": [{"id": "c1", "title": "Sans sous-titre"}]}],
    })
    assert "Sans sous-titre" in html
    with_sub = registry.render("xweb.kanban", {
        "columns": [{"id": "a", "title": "A", "cards": [{"id": "c1", "title": "x", "subtitle": "Un détail"}]}],
    })
    assert "Un détail" in with_sub


def test_kanban_omits_hx_post_when_move_url_is_empty(registry):
    """move_url='' (défaut) -> visuel seulement, pas d'appel serveur —
    t-att-hx-post="move_url or None" n'émet rien pour une valeur falsy
    (xweb/engine/compiler.py::_render_attrs)."""
    html = registry.render("xweb.kanban", {
        "columns": [{"id": "a", "title": "A", "cards": [{"id": "c1", "title": "x"}]}],
    })
    assert "hx-post" not in html


def test_kanban_sets_hx_post_to_move_url_when_given(registry):
    html = registry.render("xweb.kanban", {
        "columns": [{"id": "a", "title": "A", "cards": [{"id": "c1", "title": "x"}]}],
        "move_url": "/plugins/demo/kanban/move",
    })
    assert 'hx-post="/plugins/demo/kanban/move"' in html


def test_kanban_with_no_columns_renders_an_empty_board_not_a_crash(registry):
    html = registry.render("xweb.kanban", {})
    assert "kanban" in html
    assert "kanban-column" not in html


def test_kanban_column_card_count_is_rendered_via_the_length_filter(registry):
    """len(...) est un builtin Python, invisible du contexte d'évaluation
    QWeb (CLAUDE.md) -> NameError avalé en None, compteur toujours vide.
    Régression : xweb/components/kanban.xml utilise `| length`, pas len()."""
    html = registry.render("xweb.kanban", {
        "columns": [{"id": "a", "title": "A", "cards": [{"id": "c1", "title": "x"}, {"id": "c2", "title": "y"}]}],
    })
    header = html.split("kanban-column-title")[1]
    assert ">2<" in header or "2" in header.split("</span>")[0]


# ── Bouton supprimer une carte ──────────────────────────────────────────────


def test_kanban_card_delete_button_omitted_when_delete_card_url_is_empty(registry):
    html = registry.render("xweb.kanban", {
        "columns": [{"id": "a", "title": "A", "cards": [{"id": "c1", "title": "x"}]}],
    })
    assert "hx-delete" not in html
    assert "Supprimer la carte" not in html


def test_kanban_card_delete_button_targets_the_right_card_when_delete_card_url_given(registry):
    html = registry.render("xweb.kanban", {
        "columns": [{"id": "a", "title": "A", "cards": [{"id": "c1", "title": "x"}, {"id": "c2", "title": "y"}]}],
        "delete_card_url": "/x/cards",
    })
    assert 'hx-delete="/x/cards/c1"' in html
    assert 'hx-delete="/x/cards/c2"' in html
    assert 'hx-target="closest .kanban-card"' in html
    assert 'aria-label="Supprimer la carte"' in html


def test_kanban_card_can_be_rendered_alone_as_a_fragment_with_delete_url(registry):
    """xweb.kanban_card doit rester appelable seul (add_card_url rend ce
    fragment), y compris avec son propre delete_url — même garantie que
    xweb.editable_table_row."""
    html = registry.render("xweb.kanban_card", {
        "card": {"id": "c1", "title": "x"}, "delete_url": "/x/cards",
    })
    assert html.strip().startswith("<div")
    assert 'hx-delete="/x/cards/c1"' in html
