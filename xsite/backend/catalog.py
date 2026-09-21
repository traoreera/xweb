"""xsite/backend/catalog.py — extraction du catalogue de composants xweb.*
depuis xweb/components/*.xml, à chaud au boot.

Seule partie de ce site où du contenu est construit en Python plutôt qu'en
xdsl — et ce n'est pas du HTML : ce sont des DONNÉES (docstring, props,
rendu déjà fait par le moteur, extraits de code) passées en contexte aux
templates de xsite/templates/components.dsl, qui en font la mise en page.

Ancré dans le vrai code source, jamais une liste recopiée à la main :
- la docstring vient du commentaire XML en tête de chaque fichier ;
- les props viennent des <t t-set="x" t-default="y"/> déclarés en enfants
  directs du <template> (même convention que design/scripts/
  generate_components_catalog.py et docs_site_data.py à la racine — pas
  encore factorisée en un module partagé entre les trois, dette connue) ;
- le rendu de démo est produit par le VRAI QwebRegistry avec un jeu de
  props plausibles par composant (DEMO ci-dessous).
"""

from __future__ import annotations

import html as html_mod
from pathlib import Path

from lxml import etree

from xweb.engine.registry import QwebRegistry

ROOT = Path(__file__).resolve().parent.parent.parent
COMPONENTS_DIR = ROOT / "xweb" / "components"

# Composants "de structure" — tubes de page (shell, layout email/pdf...) ou
# helpers internes appelés uniquement par leur parent (une ligne de kanban,
# une cellule d'editable_table) : pas présentables isolément, exclus du
# catalogue public. Même liste que scripts/catalogue.py (EXCLUDE), reprise
# ici pour que xsite/ reste autonome (pas d'import cross-projet vers
# scripts/, qui n'est pas un paquet destiné à être une dépendance).
EXCLUDE = {
    "xweb.shell", "xweb.shell_head", "xweb.shell_minimal", "xweb.marketing_layout",
    "xweb.email_layout", "xweb.pdf_document", "xweb.drawer_toggle", "xweb.sidebar_toggle",
    "xweb.theme_toggle", "xweb.locale_switcher", "xweb.topbar_slot", "xweb.toast_region",
    "xweb.toasts_oob", "xweb.csrf", "xweb.error_page",
    "xweb.editable_table_header_cell", "xweb.editable_table_cell_text",
    "xweb.editable_table_cell_select", "xweb.editable_table_cell_checkbox",
    "xweb.editable_table_row", "xweb.kanban_card", "xweb.nav_items", "xweb.status_item",
}

BASE_CTX = {
    "app_name": "xweb", "page_title": "Démo", "csrf_token": "demo-token",
    "locale": "fr", "locales": ["fr"], "request": "demo",
}

# Props de démo par composant — radical du nom (xweb.xxx -> "xxx"). Même
# esprit que scripts/catalogue.py::DEMO, jeu volontairement plus court (ce
# catalogue vise la RÉFÉRENCE, pas la démo visuelle exhaustive) : un
# composant absent d'ici est rendu avec ses seuls défauts déclarés.
DEMO: dict[str, dict] = {
    "accordion": {"items": [{"title": "Pourquoi xweb ?", "content": "Parce que…"}, {"title": "Comment", "content": "Ainsi."}]},
    "alert": {"title": "Attention", "variant": "warning"},
    "avatar": {"initial": "ME", "size": "md", "status": "online"},
    "badge": {"color": "primary"},
    "breadcrumbs": {"items": [{"label": "Accueil", "path": "/"}, {"label": "Composants", "path": ""}]},
    "button": {"variant": "primary"},
    "calendar": {"month_label": "Septembre 2026", "weeks": [[
        {"day": 1, "iso": "2026-09-01", "in_month": True, "is_today": True, "is_selected": False},
        {"day": 2, "iso": "2026-09-02", "in_month": True, "is_today": False, "is_selected": False},
    ]]},
    "card": {"title": "Carte démo", "subheading": "Sous-titre"},
    "chat_bubble": {"side": "left", "message": "Salut !", "author": "Moi"},
    "checkbox": {"label": "Accepter", "checked": True},
    "collapse": {"title": "Déplier", "open": True},
    "combobox": {"name": "pick", "options": [{"label": "Un", "value": "1"}], "placeholder": "Choisir…"},
    "countdown": {"value": 42, "label": "jours"},
    "datepicker": {"name": "date", "placeholder": "jj/mm/aaaa"},
    "drawer": {"id": "demo-drawer", "side_items": [{"label": "Profil", "path": "/"}]},
    "dropdown": {"label": "Menu", "trigger": "Dérouler"},
    "empty": {"icon": "inbox", "title": "Rien", "message": "Aucune donnée."},
    "field": {"label": "Nom", "required": True},
    "icon": {"name": "sparkles"},
    "input": {"placeholder": "Tape ici…", "type": "text"},
    "kanban": {"columns": [{"id": 1, "title": "À faire", "cards": [{"id": 1, "title": "Tâche 1"}]}]},
    "label": {"for_": "demo-input", "badge": "requis"},
    "list": {"items": [{"title": "Un", "subtitle": "sous-titre"}]},
    "menu": {"items": [{"label": "Accueil", "path": "/"}], "current_path": "/"},
    "modal": {"id": "demo-modal", "title": "Titre", "actions": "Fermer"},
    "password": {"name": "pass", "placeholder": "••••••"},
    "popover": {"id": "demo-popover", "trigger_label": "Infos", "position": "bottom"},
    "progress": {"value": 60, "max": 100, "color": "primary"},
    "radio": {"name": "choix", "value": "a", "label": "Option A", "checked": True},
    "range": {"name": "vol", "min": 0, "max": 100, "value": 50},
    "rating": {"name": "note", "value": 3, "max": 5},
    "select": {"name": "ville", "options": [{"label": "Paris", "value": "paris"}], "placeholder": "Ville…"},
    "spinner": {"size": "md", "color": "primary"},
    "stat": {"title": "Visiteurs", "value": "1 204", "icon": "sparkles"},
    "table": {"columns": [{"key": "name", "label": "Nom"}], "rows": [{"name": "Ada"}]},
    "tabs": {"items": [{"label": "Onglet 1", "path": "/o1"}], "current_path": "/o1"},
    "textarea": {"name": "bio", "placeholder": "Ton histoire…"},
    "toast": {"variant": "info"},
    "toggle": {"name": "actif", "label": "Activer", "checked": True},
    "tooltip": {"text": "Astuce !"},
}

SLOT_MAP: dict[str, str] = {
    "alert": "Un message important.",
    "button": "Demo",
    "card": "Le contenu de la carte.",
    "collapse": "Contenu repliable.",
    "dropdown": "Contenu du menu.",
    "empty": "Toujours rien ici.",
    "field": "Champ, texte, etc.",
    "modal": "Corps de la modale.",
    "popover": "Le contenu du popover.",
    "tooltip": "Cible",
}


def _component_docstring(short: str) -> str:
    path = COMPONENTS_DIR / f"{short}.xml"
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
    return " ".join(lines)[:280]


def _extract_props(template_el: etree._Element) -> list[tuple[str, str]]:
    props: list[tuple[str, str]] = []
    for child in template_el:
        if not isinstance(child.tag, str):
            continue
        if etree.QName(child).localname != "t":
            break
        t_set, t_default = child.get("t-set"), child.get("t-default")
        if t_set is None or t_default is None:
            break
        props.append((t_set, t_default))
    return props


def _raw_xml_source(template_el: etree._Element) -> str:
    return etree.tostring(template_el, pretty_print=True, encoding="unicode").strip()


def _py_default_to_xdsl(value: object) -> str | None:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return f'"{value.replace(chr(34), chr(92) + chr(34))}"'
    return None


def _xdsl_usage(short: str) -> str:
    demo = DEMO.get(short, {})
    lines = [f"{short} {{"]
    complex_keys = []
    for key, value in demo.items():
        xdsl_val = _py_default_to_xdsl(value)
        if xdsl_val is None:
            complex_keys.append(key)
            continue
        lines.append(f"    {key}: {xdsl_val}")
    slot = SLOT_MAP.get(short)
    if slot:
        lines.append(f'    "{slot}"')
    lines.append("}")
    snippet = "\n".join(lines)
    if complex_keys:
        snippet += f"\n// {', '.join(complex_keys)} : voir xweb/components/{short}.xml pour la forme exacte."
    return snippet


def _qweb_usage(name: str, short: str) -> str:
    """t-call réel — un attribut littéral est une chaîne de confiance,
    jamais interprétée (docs/language.md#t-call) : une string reste nue,
    un bool/nombre a besoin de t-att-x="expr"."""
    demo = DEMO.get(short, {})
    literal, computed, complex_keys = [], [], []
    for key, value in demo.items():
        if isinstance(value, str):
            literal.append(f'{key}="{html_mod.escape(value, quote=True)}"')
        elif isinstance(value, bool):
            computed.append(f't-att-{key}="{value}"')
        elif isinstance(value, (int, float)):
            computed.append(f't-att-{key}="{value}"')
        else:
            complex_keys.append(key)
    attrs = " ".join(literal + computed)
    slot = SLOT_MAP.get(short, "")
    opening = f'<t t-call="{name}"' + (f" {attrs}" if attrs else "") + (">" if slot else "/>")
    lines = [opening]
    if slot:
        lines.append(f"    {slot}")
        lines.append("</t>")
    if complex_keys:
        lines.append(f"<!-- {', '.join(complex_keys)} : passé depuis le contexte Python, pas un littéral -->")
    return "\n".join(lines)


def _shorthand_usage(name: str, short: str) -> str:
    """<xweb:nom ...> — sucre XML natif au moteur, désucré au PARSE (avant
    même que le compilateur/registre ne voient quoi que ce soit)."""
    tag = f"xweb:{short}" if name.startswith("xweb.") else name
    demo = DEMO.get(short, {})
    literal = [f'{k}="{html_mod.escape(v, quote=True)}"' for k, v in demo.items() if isinstance(v, str)]
    attrs = " ".join(literal)
    slot = SLOT_MAP.get(short, "")
    opening = f"<{tag}" + (f" {attrs}" if attrs else "") + (">" if slot else "/>")
    lines = [opening]
    if slot:
        lines.append(f"    {slot}")
        lines.append(f"</{tag}>")
    return "\n".join(lines)


def build_catalog(engine: QwebRegistry) -> tuple[list[dict], dict[str, int]]:
    """Une entrée par composant xweb.* catalogué — dicts bruts, consommés
    par xsite/backend/routes.py pour peupler site.component_detail (les
    templates xdsl construisent tout l'HTML, ce module ne fournit QUE les
    données)."""
    names = sorted(t for t in engine._templates if t.startswith("xweb.") and t not in EXCLUDE)
    stats = {"ok": 0, "err": 0}
    out: list[dict] = []

    xml_index: dict[str, etree._Element] = {}
    for xml_file in sorted(COMPONENTS_DIR.glob("*.xml")):
        raw = xml_file.read_text(encoding="utf-8")
        wrapped = raw if raw.strip().startswith("<templates>") else f"<templates>\n{raw}\n</templates>"
        try:
            root = etree.fromstring(wrapped.encode("utf-8"))
        except etree.XMLSyntaxError:
            continue
        for t in root.findall(".//template"):
            n = t.get("t-name")
            if n:
                xml_index[n] = t

    for name in names:
        short = name.split(".", 1)[-1]
        props = dict(BASE_CTX)
        props.update(DEMO.get(short, {}))
        slot_text = SLOT_MAP.get(short, "")

        try:
            if slot_text:
                ctx_refs = "".join(f' t-att-{k}="{k}"' for k in DEMO.get(short, {}))
                caller = f"__site_showcase_{name.replace('.', '_')}"
                engine.register_source(
                    f'<template t-name="{caller}"><t t-call="{name}"{ctx_refs}>'
                    f"{html_mod.escape(slot_text)}</t></template>",
                    source_plugin="site-showcase",
                )
                rendered = engine.render(caller, props)
            else:
                rendered = engine.render(name, props)
            status = "ok"
            stats["ok"] += 1
        except Exception as exc:
            rendered = f'<div class="text-error text-sm">{html_mod.escape(str(exc).splitlines()[0][:200])}</div>'
            status = "err"
            stats["err"] += 1

        el = xml_index.get(name)
        real_props = _extract_props(el) if el is not None else []
        out.append({
            "name": name,
            "short": short,
            "docstring": _component_docstring(short) or "Pas de docstring en tête de fichier.",
            "summary": (_component_docstring(short) or "")[:90],
            "rendered": rendered,
            "status": status,
            "props_rows": [{"prop": p, "default": d} for p, d in real_props],
            "xdsl_usage": _xdsl_usage(short),
            "xweb_usage": _qweb_usage(name, short),
            "shorthand_usage": _shorthand_usage(name, short),
            "source": _raw_xml_source(el) if el is not None else "",
        })

    return out, stats
