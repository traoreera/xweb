#!/usr/bin/env python3
"""Pipeline xdsl : fichier .dsl -> .xml (QWeb) -> .html (rendu).

Usage:
    uv run scripts/dsl2html.py login.dsl
    uv run scripts/dsl2html.py login.dsl --out preview_auth.html --css ../xweb/static/app.css

    Si le fichier contient ``@include "xweb.shell"``, la sortie enveloppe
    chaque fragment dans le shell (sidebar, topbar, status bar) — la page
    d'aperçu est alors une vraie page HTML complète.

Étapes :
  1. compile_dsl() -> XML QWeb (chaque composant = un <template t-name=...>),
     écrit dans <base>.xml (racine <templates> pour lxml).
  2. Enregistre xweb/components/ + le .xml généré dans un QwebRegistry.
  3. Rend chaque composant en HTML et l'enveloppe dans une page d'aperçu
     branchée sur le vrai app.css.

Note : un composant renderable a besoin de ses dépendances xweb (rectangle,
form, input...). Les `t-call` vers des composants inconnus lèvent
TemplateError — on les affiche clairement.
"""

from __future__ import annotations

import argparse
import os
import re
import types
from pathlib import Path
from urllib.parse import quote

from markupsafe import Markup
from xweb.engine.registry import QwebRegistry

from xdsl.api import compile_dsl, compile_json_file, dump_dsl_json

ROOT = Path(__file__).resolve().parent.parent


def _layout_marker(xml_body: str) -> str | None:
    """Extrait le nom du layout depuis ``<!-- layout: xweb.shell -->``."""
    m = re.search(r'<!--\s*layout:\s*([^\s>]+)\s*-->', xml_body)
    return m.group(1) if m else None


def _fake_request(path: str = "/") -> types.SimpleNamespace:
    """Objet request minimal pour le shell de preview — satisfait
    request.url.include_query_params utilisé par locale_switcher."""
    def _include_query_params(**kwargs: str) -> str:
        params = "&".join(f"{k}={quote(v, safe='')}" for k, v in kwargs.items())
        return f"{path}?{params}" if params else path

    url = types.SimpleNamespace(path=path, include_query_params=_include_query_params)
    return types.SimpleNamespace(url=url, query_params={}, method="GET", headers={})


# Contexte minimal pour le shell — valeurs neutres, pas de secrets.
_SHELL_CTX = {
    "app_name": "xweb",
    "page_title": "Aperçu",
    "csrf_token": "demo-token",
    "locale": "fr",
    "locales": [],              # locale_switcher ignorant si listes vides
    "nav_tree": None,           # sidebar affichera « Aucun plugin… »
    "commands": [],
    "status_left": [],
    "status_right": [],
    "user": None,
    "account": None,
    "current_path": "/",
    "login_url": "/login",
    "account_path": "/account/",
    "logout_path": "/account/logout",
    "_": lambda s: s,           # identité pour tr()
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dsl", type=Path, help="fichier .dsl source ou .xdsl.json existant")
    parser.add_argument("--out", type=Path, default=None, help="fichier .html de sortie (défaut: <base>.html)")
    parser.add_argument("--xml", type=Path, default=None, help="fichier .xml intermédiaire (défaut: <base>.xml)")
    parser.add_argument("--json", action="store_true", help="écrire aussi <base>.xdsl.json (capsule No-Code, depuis un .dsl)")
    parser.add_argument("--css", type=Path, default=None, help="chemin CSS pour la page d'aperçu")
    parser.add_argument("--render", action="append", default=None, help="t-name(s) à rendre (défaut: tous)")
    args = parser.parse_args()

    source = args.dsl.read_text(encoding="utf-8")
    is_json = args.dsl.name.endswith(".xdsl.json")
    base = (
        args.dsl.parent / args.dsl.name.removesuffix(".xdsl.json")
        if is_json
        else args.dsl.with_suffix("")
    )
    xml_path = args.xml or Path(f"{base}.xml")
    html_path = args.out or Path(f"{base}.html")

    # 1. DSL/JSON -> XML
    if is_json:
        xml_body = compile_json_file(args.dsl)
    else:
        xml_body = compile_dsl(source, filename=str(args.dsl))
        if args.json:
            dump_dsl_json(source, f"{base}.xdsl.json", filename=args.dsl.name)
    with xml_path.open("w", encoding="utf-8") as f:
        f.write("<templates>\n" + xml_body + "</templates>\n")
    print(f"XML  : {xml_path}")
    if not is_json and args.json:
        print(f"JSON : {base}.xdsl.json")

    # Détection du layout
    layout = _layout_marker(xml_body)

    # 2. Enregistrement + rendu
    registry = QwebRegistry()
    registry.register_dir(ROOT / "xweb" / "components", source_plugin="xweb-core")
    registry.register_source(f"<templates>\n{xml_body}\n</templates>", source_plugin="site")

    names = re.findall(r'<template t-name="([^"]+)"', xml_body)
    render_names = args.render or names
    if not render_names:
        print("Aucun composant à rendre.")
        return 1

    parts: list[str] = []
    for name in render_names:
        try:
            parts.append(registry.render(name, {}))
        except Exception as exc:  # TemplateError / NameError...
            parts.append(f'<div style="color:#b91c1c;border:1px solid;padding:8px">'
                         f'<strong>{name}</strong> : {exc}</div>')
            print(f"ERREUR {name}: {exc}")

    # 3. Page d'aperçu
    css = args.css or (ROOT / "xweb" / "static" / "app.css")
    css_rel = Path(os.path.relpath(css, html_path.parent)).as_posix()

    if layout:
        # Le composant est enveloppé dans le shell. `content` doit être un
        # Markup (c'est ce que renvoie engine.render : un str échapperait
        # silencieusement tout le fragment via t-out).
        content = Markup("\n".join(parts))
        ctx = dict(_SHELL_CTX)
        ctx["content"] = content
        ctx["request"] = _fake_request()
        try:
            page = registry.render(layout, ctx)
        except Exception as exc:
            print(f"ERREUR rendu shell ({layout}): {exc}")
            page = (
                "<!doctype html>\n<html><body>\n"
                f'<div style="color:#b91c1c;border:1px solid;padding:8px">'
                f'Erreur rendu shell ({layout}) : {exc}</div>\n'
                + content + "\n</body></html>\n"
            )
        # Injecte le CSS dans <head> si absent — shell_head référence
        # /xweb-static/app.css (absolu, pour un serveur) ; la page d'aperçu
        # ouverte en fichier local a besoin du chemin relatif. On opère sur
        # un str brut : Markup.replace ré-échapperait les guillemets du href.
        static_rel = Path(os.path.relpath(ROOT / "xweb" / "static", html_path.parent)).as_posix()
        page = str(page)
        if 'rel="stylesheet"' not in page:
            page = page.replace("</head>", f'<link rel="stylesheet" href="{css_rel}"/>\n</head>', 1)
        else:
            page = page.replace('href="/xweb-static/app.css"', f'href="{css_rel}"')
        page = page.replace('src="/xweb-static/', f'src="{static_rel}/')
    else:
        page = (
            "<!doctype html>\n"
            '<html data-theme="light">\n'
            "<head>\n"
            '<meta charset="utf-8"/>\n'
            f"<title>Aperçu {base.name}</title>\n"
            f'<link rel="stylesheet" href="{css_rel}"/>\n'
            "</head>\n"
            '<body class="min-h-screen bg-base-100 text-base-content p-8 flex flex-wrap items-start justify-center gap-8">\n'
            + "\n".join(parts)
            + "\n</body>\n</html>\n"
        )

    html_path.write_text(page, encoding="utf-8")
    print(f"HTML : {html_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())