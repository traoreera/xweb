"""Données du catalogue de composants affiché sur la landing page
(templates/components_showcase.xml, templates/components_pdf.xml).

Module séparé de main.py — uniquement des données statiques/calculées,
aucune logique de boot ni de câblage xcore ici. `showcase_context()` est
appelé par la vue de la route "/" (main.py) et par la route PDF
"/components.pdf" — les deux partagent exactement les mêmes données
(table_columns/table_rows), pour que le PDF téléchargé corresponde
réellement à ce qui est affiché sur la page, pas une donnée dupliquée à la
main qui pourrait diverger avec le temps.

xweb.calendar/xweb.datepicker exigent une grille déjà calculée côté vue
Python (xweb/calendar.py — aucun builtin date dans une expression QWeb,
CLAUDE.md "aucun builtin") — c'est fait ici, une seule fois.
"""

from __future__ import annotations

from datetime import date

from xweb.calendar import month_grid

# Un composant par ligne, groupé par section du catalogue
# (templates/components_showcase.xml) — sert à la fois d'exemple pour
# xweb.table dans la page ET de contenu de l'export PDF (mêmes données).
_TABLE_ROWS = [
    {"name": "xweb.button", "category": "Boutons & actions", "status": "Fait"},
    {"name": "xweb.form", "category": "Formulaire", "status": "Fait"},
    {"name": "xweb.calendar / datepicker", "category": "Formulaire", "status": "Fait"},
    {"name": "xweb.kanban", "category": "Avancé", "status": "Fait"},
    {"name": "xweb.modal / drawer / popover", "category": "Overlays", "status": "Fait"},
    {"name": "xweb.table / tabs / accordion", "category": "Disclosure", "status": "Fait"},
    {"name": "xweb.toast / alert", "category": "Système", "status": "Fait"},
]

_TABLE_COLUMNS = [
    {"key": "name", "label": "Composant"},
    {"key": "category", "label": "Catégorie"},
    {"key": "status", "label": "Statut"},
]


def showcase_context() -> dict:
    cal = month_grid(date.today().year, date.today().month, today=date.today())
    return {
        "component_count": 45,
        "kanban_columns": [
            {"id": "todo", "title": "À faire", "cards": [
                {"id": "kc-1", "title": "Écrire les specs", "subtitle": "Design"},
                {"id": "kc-2", "title": "Revue de sécurité"},
            ]},
            {"id": "doing", "title": "En cours", "cards": [
                {"id": "kc-3", "title": "Catalogue de composants", "subtitle": "xweb"},
            ]},
            {"id": "done", "title": "Fait", "cards": [
                {"id": "kc-4", "title": "Moteur QWeb"},
            ]},
        ],
        "table_columns": _TABLE_COLUMNS,
        "table_rows": _TABLE_ROWS,
        "menu_items": [
            {"href": "#", "label": "Tableau de bord", "icon": "grid"},
            {"href": "#", "label": "Notifications", "icon": "bell", "badge": "3"},
            {"href": "#", "label": "Paramètres", "icon": "cog"},
        ],
        "tabs_items": [
            {"label": "Aperçu", "href": "#", "icon": "grid", "active": True},
            {"label": "Activité", "href": "#", "icon": "clock"},
            {"label": "Paramètres", "href": "#", "icon": "cog"},
        ],
        "breadcrumb_items": [{"label": "Accueil", "href": "/"}, {"label": "Composants"}],
        "accordion_items": [
            {"title": "Qu'est-ce que xweb ?", "content": "Un moteur de rendu QWeb et un SDK de plugin pour xcore.", "open": True},
            {"title": "Combien de composants ?", "content": "45, tous en XML, aucun bundle JS à compiler."},
        ],
        "select_options": [{"value": "fr", "label": "Français"}, {"value": "en", "label": "English"}],
        "combobox_options": [
            {"value": "paris", "label": "Paris"},
            {"value": "lyon", "label": "Lyon"},
            {"value": "marseille", "label": "Marseille"},
        ],
        "avatar_group_items": [{"initial": "A"}, {"initial": "B"}, {"initial": "C"}],
        "calendar": cal,
        "editable_table_columns": editable_table_columns(),
        "editable_table_rows": editable_table_rows(),
    }


# ── Démo persistée de xweb.editable_table (routes dans main.py) ────────────
#
# État de MODULE partagé entre toutes les requêtes — comme _KANBAN_BOARD
# le faisait dans l'ancien plugins/demo (docs/components.md#xweb.kanban) :
# une vraie démo publique, pas un mock. Aucune base de données ici, en
# mémoire seulement — redémarrer le serveur réinitialise la démo, ce qui
# est le comportement attendu pour une page d'accueil publique.

EDITABLE_TABLE_COLUMNS = [
    {"key": "name", "label": "Tâche", "type": "text"},
    {"key": "status", "label": "Statut", "type": "select", "options": [
        {"value": "todo", "label": "À faire", "color": "neutral"},
        {"value": "active", "label": "En cours", "color": "info"},
        {"value": "done", "label": "Terminé", "color": "success"},
    ]},
    {"key": "urgent", "label": "Urgent", "type": "checkbox"},
]

_editable_table_rows: list[dict] = [
    {"id": "row-1", "name": "Écrire les specs", "status": "done", "urgent": False},
    {"id": "row-2", "name": "Catalogue de composants", "status": "active", "urgent": True},
    {"id": "row-3", "name": "Export PDF", "status": "todo", "urgent": False},
]
_editable_table_seq = 3


def editable_table_rows() -> list[dict]:
    return _editable_table_rows


def editable_table_set_cell(row_id: str, column: str, value) -> dict | None:
    for row in _editable_table_rows:
        if row["id"] == row_id:
            row[column] = value
            return row
    return None


def editable_table_add_row() -> dict:
    global _editable_table_seq
    _editable_table_seq += 1
    row = {"id": f"row-{_editable_table_seq}", "name": "", "status": "todo", "urgent": False}
    _editable_table_rows.append(row)
    return row


def editable_table_delete_row(row_id: str) -> None:
    _editable_table_rows[:] = [r for r in _editable_table_rows if r["id"] != row_id]


def editable_table_reorder(order: list[str]) -> None:
    by_id = {r["id"]: r for r in _editable_table_rows}
    # ids inconnus (course avec une suppression concurrente) simplement
    # ignorés plutôt qu'une KeyError — même posture de dégradation que le
    # reste de xweb (docs/i18n.md, xweb/cookies.py...).
    _editable_table_rows[:] = [by_id[i] for i in order if i in by_id]


_editable_table_columns: list[dict] = EDITABLE_TABLE_COLUMNS
_editable_table_col_seq = 0


def editable_table_columns() -> list[dict]:
    return _editable_table_columns


def editable_table_add_column() -> dict:
    """Toujours type="text" — un type "select" a besoin d'un éditeur
    d'options, hors scope v1 (docs/components.md#editable_table)."""
    global _editable_table_col_seq
    _editable_table_col_seq += 1
    col = {"key": f"col_{_editable_table_col_seq}", "label": "Nouvelle colonne", "type": "text"}
    _editable_table_columns.append(col)
    for row in _editable_table_rows:
        row[col["key"]] = ""
    return col


def editable_table_rename_column(key: str, label: str) -> dict | None:
    for col in _editable_table_columns:
        if col["key"] == key:
            col["label"] = label
            return col
    return None
