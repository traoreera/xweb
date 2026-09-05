"""Garde-fou permanent contre le piège "aucun builtin dans une expression
QWeb" (CLAUDE.md — `xweb/engine/compiler.py::_eval` : `eval(expr,
{"__builtins__": {}}, ctx)`, un nom non défini -> NameError avalé en None,
JAMAIS une erreur visible). Ce piège a déjà mordu deux fois dans ce dépôt :

  - `len(col.get('cards') or [])` dans xweb/components/kanban.xml — le
    compteur de cartes par colonne restait toujours vide.
  - `str(notification['id'])` dans xweb/components/notifications.xml —
    "marquer comme lue" ne faisait strictement rien au clic (hx-post
    jamais émis), sans la moindre erreur nulle part.

Les deux étaient invisibles en lisant le code, invisibles au chargement du
template, invisibles même au premier rendu réussi (l'attribut est juste
absent/vide, pas une exception) — seul un test qui grep VRAIMENT chaque
expression pour un nom de builtin peut les attraper avant qu'un visiteur
ne s'en aperçoive. Ce test scanne exactement les mêmes attributs que
`_eval`/`_eval_formatted` évaluent réellement (voir compiler.py) — pas une
regex hasardeuse sur le texte brut du fichier.
"""

from __future__ import annotations

import re
from pathlib import Path

from lxml import etree

ROOT = Path(__file__).parent.parent
SCANNED_DIRS = [ROOT / "xweb" / "components", ROOT / "templates"]

# Builtins Python plausibles dans une expression de template (concaténation,
# comptage, tri, formatage...) — pas exhaustif à 100% des ~150 builtins
# réels, mais couvre tout ce qu'un auteur de template serait tenté d'écrire
# en pensant "ça doit marcher, c'est juste du Python".
SUSPECT_BUILTINS = [
    "len", "str", "int", "float", "bool", "list", "dict", "set", "tuple",
    "sorted", "reversed", "enumerate", "zip", "map", "filter", "min", "max",
    "sum", "abs", "round", "any", "all", "isinstance", "type", "repr",
    "format", "range", "next", "iter", "hash", "vars", "dir", "callable",
    "issubclass", "super", "open", "eval", "exec", "compile", "globals",
    "locals", "getattr", "setattr", "hasattr", "delattr", "property",
    "frozenset", "bytes", "bytearray", "complex", "divmod", "pow", "ord",
    "chr", "hex", "oct", "bin", "ascii", "slice", "print", "id",
]
_BUILTIN_CALL = re.compile(r"\b(" + "|".join(SUSPECT_BUILTINS) + r")\s*\(")
_INTERP = re.compile(r"\{\{(.*?)\}\}")  # même regex que compiler.py::_eval_formatted

# Attributs dont la valeur est passée telle quelle à _eval() — voir
# compiler.py::_render_element_body (t-esc/t-if/t-elif/t-value/t-default),
# ::_render_children (t-foreach), et t-att-* (prop/attribut calculé).
DIRECT_EVAL_ATTRS = {"t-esc", "t-if", "t-elif", "t-value", "t-foreach", "t-default"}


def _find_builtin_calls_in_file(path: Path) -> list[str]:
    root = etree.parse(str(path)).getroot()
    findings = []
    for el in root.iter():
        for name, value in el.attrib.items():
            exprs: list[str] = []
            if name in DIRECT_EVAL_ATTRS or name.startswith("t-att-"):
                exprs.append(value)
            elif name.startswith("t-attf-"):
                exprs.extend(m.group(1) for m in _INTERP.finditer(value))
            for expr in exprs:
                m = _BUILTIN_CALL.search(expr)
                if m:
                    findings.append(
                        f"{path.relative_to(ROOT)}:{el.sourceline} <{el.tag} {name}=\"{value}\"> "
                        f"— builtin '{m.group(1)}' absent du contexte d'évaluation QWeb"
                    )
    return findings


def test_no_python_builtin_calls_in_any_component_or_template_expression():
    findings = []
    for d in SCANNED_DIRS:
        for f in sorted(d.glob("*.xml")):
            findings.extend(_find_builtin_calls_in_file(f))
    assert findings == [], (
        "expression(s) QWeb utilisant un builtin Python absent du contexte d'évaluation "
        "(NameError avalé en None, jamais une erreur visible — CLAUDE.md) :\n"
        + "\n".join(findings)
    )
