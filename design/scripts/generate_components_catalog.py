"""Extrait le catalogue réel des composants xweb.* (nom + props déclarées)
depuis xweb/components/*.xml, et écrit ../src/components-catalog.json,
consommé par ../src/completions.js pour proposer :
  - les NOMS de composants comme complétion de balise (popover, table, ...)
  - leurs PROPS réelles une fois à l'intérieur (trigger_label:, position:, ...)

Ancré dans le vrai fichier source, jamais une liste recopiée à la main qui
dériverait au premier composant ajouté/modifié — même discipline que
scripts/catalogue.py (qui a son propre usage, un rendu visuel de démo, pas
un export JSON pour un éditeur).

Convention EXTRACTÉE ici (déjà utilisée partout dans xweb/components/,
563 occurrences sur 71 fichiers au moment d'écrire ce script) : chaque
`<template t-name="...">` déclare ses props comme une séquence de
  <t t-set="nom_prop" t-default="expr_python"/>
en DIRECTS ENFANTS du <template>, avant le reste du contenu — un t-set
plus profond dans l'arbre (une boucle, une condition) est une variable
locale, pas une prop, donc PAS extrait ici.

Usage : uv run python design/scripts/generate_components_catalog.py
"""

from __future__ import annotations

import json
from pathlib import Path

from lxml import etree

ROOT = Path(__file__).resolve().parent.parent.parent  # design/scripts/ -> design/ -> repo root
COMPONENTS_DIR = ROOT / "xweb" / "components"
OUT_PATH = Path(__file__).resolve().parent.parent / "src" / "components-catalog.json"


def _extract_props(template_el: etree._Element) -> list[dict]:
    """Props = enfants <t t-set="..." t-default="..."/> DIRECTS du
    <template>, dans l'ordre — s'arrête au premier enfant qui n'est pas
    un tel t-set (le reste est le contenu réel du composant, pas des
    props)."""
    props: list[dict] = []
    for child in template_el:
        tag = etree.QName(child).localname if child.tag is not etree.Comment else None
        if tag != "t":
            if isinstance(child.tag, str):
                break
            continue  # commentaire XML — on saute, la préambule de props continue
        t_set = child.get("t-set")
        t_default = child.get("t-default")
        if t_set is None or t_default is None:
            break
        props.append({"name": t_set, "default": t_default})
    return props


def main() -> int:
    catalog: dict[str, dict] = {}
    for xml_file in sorted(COMPONENTS_DIR.glob("*.xml")):
        raw = xml_file.read_text(encoding="utf-8")
        wrapped = raw if raw.strip().startswith("<templates>") else f"<templates>\n{raw}\n</templates>"
        try:
            root = etree.fromstring(wrapped.encode("utf-8"))
        except etree.XMLSyntaxError as exc:
            print(f"AVERTISSEMENT : {xml_file.name} ignoré (XML invalide) — {exc}")
            continue
        for template_el in root.findall(".//template"):
            name = template_el.get("t-name")
            if not name:
                continue
            catalog[name] = {
                "props": _extract_props(template_el),
                "file": xml_file.name,
            }

    OUT_PATH.write_text(json.dumps(catalog, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"écrit : {OUT_PATH} ({len(catalog)} composants)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
