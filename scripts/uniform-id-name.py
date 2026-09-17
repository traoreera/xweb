#!/usr/bin/env python3
"""Uniformise id/name sur tout le catalogue xweb/components — édition textuelle.

lxml sert UNIQUEMENT à localiser (tag racine émis, numéros de lignes). Les
modifications sont ensuite appliquées ligne par ligne sur le texte source,
pour que le restant du fichier (commentaires français, attributs posés sur
plusieurs lignes) reste bit à bit intact.

Pour chaque <template t-name> :
  - déclare <t t-set="id" t-default="''"/> si le composant n'a déjà ni
    `t-set="id"` ni `t-att-id` (id déjà posé quelque part) ;
  - déclare <t t-set="name" t-default="''"/> si le composant n'a déjà pas
    de `t-set="name"` (prop sémantique — accordion/<details>, checkbox,
    radio, swap, toggle… — que l'on ne veut pas toucher) ;
  - pose t-att-id / t-att-name sur la RACINE = premier enfant réellement
    émis (descend <t>, saute <style>/<script>).

Idempotent : ne réécrit que les fichiers réellement modifiés.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from lxml import etree

ROOT = Path(__file__).resolve().parent.parent
COMPONENTS = ROOT / "xweb" / "components"
BACKUP = Path("/tmp/xweb-id-name-backup")


def _root_element(node):
    """Premier enfant élément réellement émis par un template."""
    if node.text is not None and node.text.strip():
        return None  # texte brut en tête — pas de racine unique
    for child in node:
        if not isinstance(child.tag, str):
            continue
        if child.tag in ("style", "script"):
            continue
        if child.tag == "t":
            if child.get("t-set") is not None:
                continue
            if child.get("t-call") is not None:
                return child
            inner = _root_element(child)
            if inner is not None:
                return inner
            continue
        return child
    return None


def _indent(line: str) -> str:
    return line[: len(line) - len(line.lstrip())]


def _branch_roots(template) -> list:
    """Racine (premier enfant non-t) de CHAQUE branche d'émission du
    template : l'élément racine unique pour un template simple, ou l'une
    des racines pour chaque <t t-if>/<t t-else> au niveau du template
    (button émet <a> OU <button> selon href — l'attache id doit aller sur
    les deux)."""
    roots: list = []
    for child in template:
        if not isinstance(child.tag, str):
            continue
        if child.tag == "t":
            if child.get("t-if") is not None or child.get("t-else") is not None:
                for c in child:
                    if isinstance(c.tag, str):
                        if c.tag != "t":
                            roots.append(c)
                            break
                        if c.get("t-call") is not None:
                            roots.append(c)
                            break
            continue
        if isinstance(child.tag, str):
            roots.append(child)
    return roots


def _set_insertion_point(lines: list[str], template, root_el) -> tuple[int, str]:
    """(index de ligne, indentation) où insérer un t-set : après le dernier
    <t t-set> du template situé AVANT l'élément racine émis. Si aucun, la
    ligne qui suit <template>. `template`/`root_el` sont des nœuds lxml —
    leurs sourcelines gèrent les t-set écrits sur plusieurs lignes."""
    anchor = None
    for el in template.iter():
        if el.tag == "t" and el.get("t-set") is not None and el.sourceline:
            if root_el is None or el.sourceline < root_el.sourceline:
                anchor = el
    if anchor is None:
        return template.sourceline, "    "

    # Ligne de fin de l'ancre (multiligne possible : `<t t-set=...\n t-value=.../>`)
    start = anchor.sourceline - 1
    end_line = start
    for i in range(start, len(lines)):
        end_line = i
        if "/>" in lines[i]:
            break
    return end_line + 1, _indent(lines[anchor.sourceline - 1])


def _attach_attr(lines: list[str], line_no: int, tag: str, attr: str) -> None:
    """Insère *attr* après la balise ouvrante `<tag>` — *line_no* est la
    ligne du DERNIER attribut (là où lxml pointe sourceline pour une
    balise multiligne), on remonte donc jusqu'à la ligne qui contient
    réellement `<tag`. Ne fait rien si l'attribut est déjà présent
    (idempotence)."""
    if attr.partition("=")[0] in lines[line_no]:
        return
    for i in range(line_no, max(0, line_no - 12), -1):
        line = lines[i]
        idx = line.find(f"<{tag}")
        if idx == -1:
            continue
        before = line[:idx]
        if before and not before[-1].isspace() and not before.endswith(">"):
            continue
        if attr.partition("=")[0] in line:
            return
        lines[i] = line[: idx + len(tag) + 1] + " " + attr + line[idx + len(tag) + 1 :]
        return


def transform(path: Path, *, dry_run: bool = False) -> tuple[bool, list[str]]:
    tree = etree.parse(str(path))
    root = tree.getroot()
    original_text = path.read_text(encoding="utf-8")
    lines = original_text.splitlines()

    set_inserts: list[tuple[int, str]] = []  # (index ligne, insertion)
    attr_edits: list[tuple[int, str, str, str]] = []  # (ligne, tag, attr)
    ops: list[str] = []

    for template in root.xpath("//*[local-name()='template']"):
        tname = template.get("t-name", "?")
        tline = template.sourceline - 1
        if "<template" not in lines[tline]:
            continue

        # bornes du template (jusqu'au </template> exclusif)
        depth = 0
        end = len(lines)
        for i in range(tline, len(lines)):
            depth += lines[i].count("<template") - lines[i].count("</template")
            if depth == 0 and i > tline:
                end = i
                break
        body = "\n".join(lines[tline:end])
        has_id_set = "t-set=\"id\"" in body
        has_name_set = "t-set=\"name\"" in body
        has_att_id = "t-att-id" in body

        # Les racines de CHAQUE branche t-if/t-else au niveau du template
        # (button : <a> ET <button> ; badge : <a> ET <span>) — une prop id
        # posée sur une seule branche la rend inerte sur l'autre.
        roots_el = _branch_roots(template)
        if not roots_el:
            continue
        needs_id_set = not has_id_set
        needs_att_id = any("t-att-id" not in etree.tostring(r, encoding="unicode") for r in roots_el)
        needs_name_set = not has_name_set
        needs_att_name = needs_name_set and any(
            "t-att-name" not in etree.tostring(r, encoding="unicode") for r in roots_el
        )
        if not (needs_id_set or needs_att_id or needs_name_set or needs_att_name):
            continue

        # 1. attaches d'attributs (ne changent pas les numéros de ligne).
        #    t-att-name n'est posé QUE quand on ajoute la prop name : les
        #    composants où name est déjà une prop sémantique (accordion ->
        #    <details name="faq">, checkbox, ...) ne doivent pas s'en voir
        #    doubler le rendu.
        if needs_att_id:
            for r in roots_el:
                if "t-att-id" in etree.tostring(r, encoding="unicode"):
                    continue  # id déjà dérivé sur cette branche (ex. popup -> "id + '-panel'")
                attr_edits.append((r.sourceline - 1, r.tag, "t-att-id=\"id or None\""))
            ops.append(f"{tname}: +id-att")
        if needs_att_name:
            for r in roots_el:
                if "t-att-name" in etree.tostring(r, encoding="unicode"):
                    continue
                attr_edits.append((r.sourceline - 1, r.tag, "t-att-name=\"name or None\""))
            ops.append(f"{tname}: +name")

        # 2. insertions de t-set (décalent les lignes — on traite après,
        #    en remontant le fichier). L'ancre t-set se cale sur la PREMIÈRE
        #    racine (sourceline minimale).
        anchor_root = min(roots_el, key=lambda r: r.sourceline or 0)
        if needs_id_set:
            pos, indent = _set_insertion_point(lines, template, anchor_root)
            set_inserts.append((pos, 0, f"{indent}<t t-set=\"id\" t-default=\"''\"/>"))
            ops.append(f"{tname}: +id-set")
        if needs_name_set:
            pos, indent = _set_insertion_point(lines, template, anchor_root)
            set_inserts.append((pos, 1, f"{indent}<t t-set=\"name\" t-default=\"''\"/>"))

    if not ops:
        return False, []

    # Applique les attaches d'abord (numéros de ligne inchangés).
    for line_no, tag, attr in attr_edits:
        _attach_attr(lines, line_no, tag, attr)

    # Puis les insertions de lignes, en remontant pour ne pas décaler.
    # Pour une même position, on insère id avant name (order croissant).
    for pos, order, text in sorted(set_inserts, key=lambda t: (-t[0], t[1])):
        lines.insert(pos, text)

    new_text = "\n".join(lines) + "\n"
    if new_text == original_text:
        return False, []

    if not dry_run:
        path.write_text(new_text, encoding="utf-8")
    return True, ops


def main() -> int:
    BACKUP.mkdir(parents=True, exist_ok=True)
    modified: list[str] = []
    for path in sorted(COMPONENTS.glob("*.xml")):
        backup = BACKUP / path.name
        if not backup.exists():
            shutil.copy2(path, backup)
        changed, ops = transform(path)
        if changed:
            modified.append(f"{path.name} ({len(ops)} op{'s' if len(ops) > 1 else ''})")
    print(f"{len(modified)} fichiers modifiés :")
    for m in modified:
        print(f"  {m}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())