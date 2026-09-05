"""Rend xweb.editable_table pour de vrai et écrit le HTML dans
.verify-editable-table.html, lu ensuite par scripts/verify-editable-table.mjs
(jsdom) — le HTML testé en JS doit venir du VRAI moteur QWeb, jamais retapé
à la main dans le script Node (sinon le test ne prouve rien sur le vrai
template). Même esprit que verify-demo-page.mjs, en local plutôt que contre
un serveur qui tourne : xweb.editable_table n'a pas encore de route réelle,
uniquement le composant.
"""

from pathlib import Path

from xweb.engine.registry import QwebRegistry

ROOT = Path(__file__).parent.parent

registry = QwebRegistry()
registry.register_dir(ROOT / "xweb" / "components")
registry.check_all()

COLUMNS = [
    {"key": "name", "label": "Nom", "type": "text"},
    {"key": "status", "label": "Statut", "type": "select", "options": [
        {"value": "active", "label": "Actif", "color": "success"},
        {"value": "paused", "label": "En pause", "color": "warning"},
    ]},
    {"key": "done", "label": "Fait", "type": "checkbox"},
]
ROWS = [
    {"id": "r1", "name": "Ada Lovelace", "status": "paused", "done": True},
    {"id": "r2", "name": "Grace Hopper", "status": "paused", "done": False},
]

html = registry.render("xweb.editable_table", {
    "columns": COLUMNS, "rows": ROWS,
    "save_url": "/demo/table/cell", "add_row_url": "/demo/table/row",
    "delete_row_url": "/demo/table/row", "reorder_url": "/demo/table/reorder",
    "add_column_url": "/demo/table/column", "rename_column_url": "/demo/table/column",
})

(ROOT / ".verify-editable-table.html").write_text(html, encoding="utf-8")
print("écrit :", ROOT / ".verify-editable-table.html", f"({len(html)} octets)")
