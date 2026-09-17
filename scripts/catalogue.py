#!/usr/bin/env python3
"""Catalogue de présentation des composants xweb.

Génère une page HTML unique rendant chaque composant `xweb.*` du catalogue
(xweb/components/) avec un jeu de props de démo adaptées à chacun, dans une
grille de cartes (une carte par composant, label + extraits de props).

Usage:
    uv run scripts/catalogue.py                 # catalogue.html à la racine
    uv run scripts/catalogue.py --out /tmp/catalogue.html
    uv run scripts/catalogue.py --css ../xweb/static/app.css

Note : les composants "de structure" (shell/layout/email/pdf/csrf/toast_region
et l'ancien toggle_demo de plugins/demo) sont exclus du catalogue — ce sont
des tubes de page, pas des éléments présentables isolément.
"""

from __future__ import annotations

import argparse
import html as html_mod
import json
import os
import re
from pathlib import Path

from xweb.engine.registry import QwebRegistry

ROOT = Path(__file__).resolve().parent.parent

# Composants exclus du catalogue : tubes de page / racines document, helpers
# internes appelés uniquement par un autre composant, et l'ancien toggle_demo
# (validait le compilateur de plugins/demo, supprimé — AGENTS.md).
EXCLUDE = {
    "xweb.shell",
    "xweb.shell_head",
    "xweb.shell_minimal",
    "xweb.marketing_layout",
    "xweb.email_layout",
    "xweb.pdf_document",
    "xweb.drawer_toggle",
    "xweb.sidebar_toggle",
    "xweb.theme_toggle",
    "xweb.locale_switcher",
    "xweb.topbar_slot",
    "xweb.toast_region",
    "xweb.toasts_oob",
    "xweb.csrf",
    "xweb.toggle_demo",
    "xweb.error_page",
    # internes d'editable_table/kanban — rendus via leur parent
    "xweb.editable_table_header_cell",
    "xweb.editable_table_cell_text",
    "xweb.editable_table_cell_select",
    "xweb.editable_table_cell_checkbox",
    "xweb.editable_table_row",
    "xweb.kanban_card",
    "xweb.nav_items",
    "xweb.status_item",
}

# Contexte de base injecté dans chaque rendu — les composants de page en
# exigent certains (locale, request...). Valeurs neutres, jamais de secrets.
BASE_CTX = {
    "app_name": "xweb",
    "page_title": "Catalogue",
    "csrf_token": "demo-token",
    "locale": "fr",
    "locales": ["fr"],
    "request": "demo",
    "generated_at": "2026-01-01",
}

# Props de démo par composant : radical du nom (xweb.xxx -> "xxx") -> dict de
# props. Le catalogue affiche le rendu PARENT seulement ; pour editable_table,
# kanban, etc., c'est le jeu de props qui donne un rendu parlant.
DEMO = {
    "accordion": {"items": [{"title": "Pourquoi xweb ?", "content": "Parce que…"}, {"title": "Comment", "content": "Ainsi."}]},
    "alert": {"title": "Attention", "variant": "warning"},
    "avatar": {"initial": "ME", "src": "", "size": "md", "status": "online"},
    "avatar_group": {"items": [{"initial": "AD", "src": ""}, {"initial": "LI", "src": ""}, {"initial": "ZS", "src": ""}], "size": "sm"},
    "badge": {"href": "#", "color": "primary"},
    "button": {"label": "Demo", "variant": "primary"},
    "breadcrumbs": {"items": [{"label": "Accueil", "path": "/"}, {"label": "Bits", "path": "/bits"}]},
    "calendar": {"month_label": "Septembre 2026", "weeks": [
        [{"day": 31, "iso": "2026-08-31", "in_month": False, "is_today": False, "is_selected": False},
         {"day": 1, "iso": "2026-09-01", "in_month": True, "is_today": True, "is_selected": False},
         {"day": 2, "iso": "2026-09-02", "in_month": True, "is_today": False, "is_selected": False},
         {"day": 3, "iso": "2026-09-03", "in_month": True, "is_today": False, "is_selected": False},
         {"day": 4, "iso": "2026-09-04", "in_month": True, "is_today": False, "is_selected": False},
         {"day": 5, "iso": "2026-09-05", "in_month": True, "is_today": False, "is_selected": False},
         {"day": 6, "iso": "2026-09-06", "in_month": True, "is_today": False, "is_selected": False}],
    ]},
    "card": {"title": "Carte démo", "subheading": "Sous-titre", "padding": "md"},
    "carousel": {"items": [{"src": "", "caption": "Diapo 1"}, {"src": "", "caption": "Diapo 2"}]},
    "chat_bubble": {"side": "left", "message": "Salut !", "author": "Moi"},
    "checkbox": {"label": "Accepter", "description": "Les CGU", "checked": True},
    "collapse": {"title": "Déplier", "open": True},
    "combobox": {"name": "pick", "options": [{"label": "Un", "value": "1"}, {"label": "Deux", "value": "2"}], "placeholder": "Choisir…"},
    "countdown": {"value": 42, "label": "jours"},
    "datepicker": {"name": "date", "placeholder": "jj/mm/aaaa", "month_label": "Septembre 2026"},
    "divider": {},
    "drawer": {"id": "demo-drawer", "side_items": [{"label": "Profil", "path": "/"}], "side_end": False, "width": "xs"},
    "dropdown": {"label": "Menu", "trigger": "Dérouler", "position": "bottom"},
    "editable_table": {
        "id": "demo-table",
        "columns": [
            {"key": "name", "label": "Nom", "type": "text"},
            {"key": "role", "label": "Rôle", "type": "select",
             "options": [{"value": "admin", "label": "Admin", "color": "primary"},
                          {"value": "dev", "label": "Dev", "color": "secondary"}]},
            {"key": "active", "label": "Actif", "type": "checkbox"},
        ],
        "rows": [{"id": 1, "name": "Ada", "role": "admin", "active": True},
                  {"id": 2, "name": "Lin", "role": "dev", "active": False}],
        "save_url": "/save", "add_row_url": "/add", "delete_row_url": "/del",
        "reorder_url": "/reorder", "add_column_url": "/col", "rename_column_url": "/col",
    },
    "empty": {"icon": "inbox", "title": "Rien", "message": "Aucune donnée."},
    "field": {"label": "Nom", "required": True},
    "fieldset": {"legend": "Informations", "help": "Remplis tout."},
    "file_input": {"name": "fichier"},
    "grid": {},
    "icon": {"name": "sparkles"},
    "input": {"placeholder": "Tape ici…", "type": "text"},
    "kanban": {
        "columns": [
            {"id": 1, "title": "À faire",
             "cards": [{"id": 1, "title": "Tâche 1"}, {"id": 2, "title": "Tâche 2"}]},
            {"id": 2, "title": "Fait",
             "cards": [{"id": 3, "title": "Tâche 3", "tags": [{"label": "v2", "color": "secondary"}]}]},
        ],
        "move_url": "/move", "add_card_url": "/add", "delete_card_url": "/del",
    },
    "label": {"for_": "demo-input", "badge": "requis"},
    "list": {"items": [{"title": "Un", "subtitle": "sous-titre"}, {"title": "Deux", "icon": "sparkles"}]},
    "menu": {"items": [{"label": "Accueil", "path": "/"}, {"label": "Profil", "path": "/profil"}], "current_path": "/"},
    "modal": {"id": "demo-modal", "title": "Titre", "actions": "Fermer", "close_label": "×"},
    "mockup": {},
    "password": {"name": "pass", "placeholder": "••••••"},
    "popover": {"id": "demo-popover", "trigger_label": "Infos", "position": "bottom"},
    "progress": {"value": 60, "max": 100, "color": "primary"},
    "radio": {"name": "choix", "value": "a", "label": "Option A", "checked": True},
    "range": {"name": "vol", "min": 0, "max": 100, "value": 50},
    "rating": {"name": "note", "value": 3, "max": 5},
    "rectangle": {"extra_class": "bg-base-200 rounded-lg p-4 text-center"},
    "select": {"name": "ville", "options": [{"label": "Paris", "value": "paris"}, {"label": "Lyon", "value": "lyon"}], "placeholder": "Ville…"},
    "skeleton": {"width": 120, "height": 16, "circle": False},
    "spinner": {"size": "md", "color": "primary"},
    "stack": {"direction": "row", "gap": "md"},
    "stat": {"title": "Visiteurs", "value": "1 204", "desc": "+12% cette semaine", "icon": "sparkles"},
    "steps": {"items": [{"label": "Étape 1"}, {"label": "Étape 2", "active": True}, {"label": "Étape 3"}], "current": 2},
    "swap": {"name": "son", "slot_on": "☀", "slot_off": "☾"},
    "table": {
        "columns": [{"key": "name", "label": "Nom"}, {"key": "email", "label": "Email"}],
        "rows": [{"name": "Ada", "email": "ada@x"}, {"name": "Lin", "email": "lin@x"}],
    },
    "tabs": {"items": [{"label": "Onglet 1", "path": "/o1"}, {"label": "Onglet 2", "path": "/o2"}], "current_path": "/o1"},
    "textarea": {"name": "bio", "placeholder": "Ton histoire…", "rows": 3},
    "timeline": {"items": [{"label": "Étape 1", "description": "création", "date": "2026-01-01"}, {"label": "Étape 2", "date": "2026-01-02"}]},
    "toast": {"variant": "info"},
    "toggle": {"name": "actif", "label": "Activer", "checked": True},
    "tooltip": {"text": "Astuce !"},
    "error": {"message": "Oups."},
}

# Slot par défaut à injecter dans les composants qui acceptent un contenu
# (slot) pour un rendu parlant.
SLOT_MAP = {
    "alert": "Un message important.",
    "box": "Contenu neutre.",
    "button": "Demo",
    "card": "Le contenu de la carte.",
    "collapse": "Contenu repliable.",
    "container": "Contenu contraint.",
    "description": "Une description",
    "divider": "Libellé",
    "drawer": "Côté blanc du drawer.",
    "dropdown": "Contenu du menu.",
    "empty": "Toujours rien ici.",
    "error": "Explication de l'erreur.",
    "field": "Champ, texte, etc.",
    "fieldset": "Contenu du groupe.",
    "form": "—",
    "grid": "cellule A et cellule B.",
    "join": "un bouton + un input.",
    "kbd": "Ctrl",
    "label": "Champ labelisé",
    "modal": "Corps de la modale.",
    "mockup": "Contenu de la maquette.",
    "popover": "Le contenu du popover.",
    "popup": "Contenu du popup.",
    "progress": "",
    "radial_progress": "72",
    "radio": "Option C",
    "rectangle": "Contenu du rectangle.",
    "stack": "un • deux • trois",
    "tooltip": "Cible",
}


def component_docs(name: str) -> str:
    """Extrait le commentaire d'en-tête d'un composant (tronqué)."""
    path = ROOT / "xweb" / "components" / f"{name.split('.')[-1]}.xml"
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""
    first = text.split("-->", 1)[0].strip()
    lines = [
        ln.strip().strip("—•*#").strip()
        for ln in first.splitlines()
        if ln.strip() and not ln.strip().startswith("<!--")
    ]
    return " ".join(lines)[:220]


def render_one(registry: QwebRegistry, name: str) -> str:
    """Rend un composant avec ses props de démo.

    Pour un composant à slot, on appelle un mini template registré à la
    volée qui fait `<t t-call="xweb.X">SLOT</t>` avec les props référencées
    par nom (`t-att-items="items"`), pour que le contenu du slot soit rendu
    dedans — un composant à slot rendu sans contenu est une coquille vide.
    """
    short = name.split(".", 1)[-1]
    props = dict(BASE_CTX)
    props.update(DEMO.get(short, {}))

    slot_text = SLOT_MAP.get(short, "")
    ctx_refs = "".join(
        f' t-att-{k}="{k}"' for k in DEMO.get(short, {})
    )
    caller = f"__showcase_{name.replace('.', '_')}"
    if slot_text:
        registry.register_source(
            f'<template t-name="{caller}">'
            f'<t t-call="{name}"{ctx_refs}>{html_mod.escape(slot_text)}</t>'
            f"</template>",
            source_plugin="showcase",
        )
        return registry.render(caller, props)
    return registry.render(name, props)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "catalogue.html")
    parser.add_argument("--css", type=Path, default=None, help="chemin relatif du CSS pour la page")
    args = parser.parse_args()

    registry = QwebRegistry()
    registry.register_dir(ROOT / "xweb" / "components", source_plugin="xweb-core")

    names = sorted(
        t for t in registry._templates
        if t.startswith("xweb.") and t not in EXCLUDE
    )

    cards: list[str] = []
    stats = {"ok": 0, "err": 0}
    for name in names:
        try:
            html_body = render_one(registry, name)
            badge = "ok"
            stats["ok"] += 1
        except Exception as exc:
            html_body = f'<div class="text-error text-sm">{html_mod.escape(str(exc).splitlines()[0][:200])}</div>'
            badge = "err"
            stats["err"] += 1

        label = name.removeprefix("xweb.")
        docs = component_docs(name)
        extra = ', '.join(f'{k}={v!r}' for k, v in DEMO.get(label, {}).items()) if label in DEMO else ""
        cards.append(
            f'<section class="card bg-base-100 border border-base-300 rounded-box shadow-sm overflow-hidden">'
            f'<header class="flex items-center justify-between gap-2 px-4 py-2 border-b border-base-300 bg-base-200/40">'
            f'<code class="text-sm font-semibold">{html_mod.escape(label)}</code>'
            f'<span class="badge badge-{"success" if badge == "ok" else "error"} badge-sm">{badge}</span>'
            f'</header>'
            f'<div class="px-4 py-4 flex justify-center items-start bg-base-100">{html_body}</div>'
            f'<footer class="px-4 py-2 border-t border-base-300 text-xs text-base-content/60">'
            f'{html_mod.escape(docs)}'
            + (f'<div class="mt-1 font-mono text-[10px] broke-word">{html_mod.escape(extra)}</div>' if extra else "")
            + "</footer></section>"
        )

    css = args.css
    if css is None:
        css = Path(os.path.relpath(ROOT / "xweb" / "static" / "app.css", args.out.parent))
    css = css.as_posix()

    page = f"""<!doctype html>
<html data-theme="light">
<head>
<meta charset="utf-8"/>
<title>Catalogue xweb — {len(names)} composants</title>
<link rel="stylesheet" href="{css}"/>
</head>
<body class="min-h-screen bg-base-100 text-base-content">
<header class="sticky top-0 z-30 border-b border-base-300 bg-base-100/90 backdrop-blur">
  <div class="mx-auto flex max-w-7xl items-center gap-3 px-4 py-3">
    <h1 class="text-lg font-bold">Catalogue xweb</h1>
    <span class="badge badge-neutral badge-sm">{len(names)} composants</span>
    <span class="badge badge-success badge-sm">{stats["ok"]} ok</span>
    <span class="badge badge-error badge-sm" {'hidden' if stats['err'] == 0 else ''}>{stats["err"]} err</span>
    <span class="flex-1"></span>
    <input id="catalog-search" type="search" placeholder="Filtrer…" class="input input-sm input-bordered w-56"/>
  </div>
</header>
<main class="mx-auto max-w-7xl px-4 py-6 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4" id="catalog-grid">
{chr(10).join(cards)}
</main>
<script>
document.getElementById('catalog-search').addEventListener('input', function () {{
  const q = this.value.toLowerCase();
  for (const sec of document.querySelectorAll('#catalog-grid > section')) {{
    sec.hidden = q && !sec.textContent.toLowerCase().includes(q);
  }}
}});
</script>
</body>
</html>"""

    args.out.write_text(page, encoding="utf-8")
    print(f"Catalogue écrit : {args.out} ({len(names)} composants, {stats['ok']} ok, {stats['err']} err)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())