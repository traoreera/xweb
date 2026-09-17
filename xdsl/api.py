"""API publique xdsl — convertit du DSL en XML QWeb.

Un fichier `.xdsl.json` est le format d'échange No-Code : une capsule
enveloppant l'AST sérialisé 1-1 (`xdsl/serialize.py`, même arbre que le
parser produit). L'éditeur lit/écrit cette capsule ; le moteur la
désérialise et compile le même XML que le `.dsl` texte équivalent.

    .dsl ──Parser──▶ AST ──ast_to_json (capsule)──▶ .xdsl.json (éditeur)
    .xdsl.json ──ast_from_json──▶ AST ──Compiler──▶ XML QWeb
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .compiler import Compiler
from .parser import AST, Parser
from .serialize import ast_from_dict, ast_to_dict
from .validators import Validator, make_validator

# Version du format de capsule `.xdsl.json` — incrémenter à chaque rupture
# de schéma de l'AST, l'éditeur refuse les versions qu'il ne connaît pas.
XDsl_FORMAT = "xdsl.json"
XDsl_VERSION = 1


def compile_dsl(source: str, filename: str = "<stdin>") -> str:
    """Convertit du xdsl en XML QWeb.

    Args:
        source: Code source xdsl.
        filename: Nom du fichier (pour les messages d'erreur).

    Returns:
        Chaîne XML prête pour lxml.

    Example:
        >>> xml = compile_dsl('''
        ... component auth.login {
        ...     import { button } from "xweb"
        ...     button { label: "Connexion" }
        ... }
        ... ''')
    """
    parser = Parser(source, filename)
    ast = parser.parse()

    compiler = Compiler(ast)
    return compiler.compile()


def extract_schemas(source: str, filename: str = "<stdin>") -> dict[str, dict[str, list[Validator]]]:
    """Convertit chaque `data nom { champ: type @decorateurs }` déclaré
    dans *source* en schéma `xdsl.validators` prêt pour `validate_dict()`.

    Une route Python (le seul endroit où "valider les données reçues" a
    vraiment un sens — QWeb/xweb n'a pas de runtime navigateur, voir
    docs/dsl-design.md#requêtes-réseau) importe ce schéma et l'applique aux
    données soumises, plutôt que de redéfinir les mêmes règles une 2e fois
    à la main côté serveur :

        schemas = extract_schemas(open("contacts.dsl").read())
        errors = validate_dict(request_json, schemas["contact_form"])

    Les attributs HTML5 natifs (required, minlength, pattern…) posés sur
    les <input> par le compilateur viennent du MÊME `@décorateur` — un seul
    endroit où la règle est écrite, utilisée aux deux bouts.
    """
    ast = Parser(source, filename).parse()
    schemas: dict[str, dict[str, list[Validator]]] = {}
    for schema in ast.data_schemas:
        schemas[schema.name] = {
            field.name: [make_validator(name, *args) for name, args in field.decorators]
            for field in schema.fields
        }
    return schemas


def compile_file(path: str) -> str:
    """Compile un fichier .dsl en XML.

    Args:
        path: Chemin vers le fichier .dsl.

    Returns:
        Chaîne XML prête pour lxml.
    """
    with open(path, encoding="utf-8") as f:
        source = f.read()

    return compile_dsl(source, filename=path)


# ---------------------------------------------------------------------------
# Capsule `.xdsl.json` (No-Code)
# ---------------------------------------------------------------------------


def _capsule(ast: AST, *, filename: str | None = None) -> dict[str, Any]:
    return {"format": XDsl_FORMAT, "version": XDsl_VERSION, "filename": filename, "ast": ast_to_dict(ast)}


def dsl_to_json(source: str, *, filename: str | None = None) -> str:
    """Parse du xdsl et sérialise l'AST dans la capsule `.xdsl.json`."""
    return json.dumps(
        _capsule(Parser(source, filename or "<stdin>").parse(), filename=filename),
        ensure_ascii=False,
        indent=2,
    )


def dump_dsl_json(source: str, path: str | Path, *, filename: str | None = None) -> None:
    """Parse du xdsl et écrit la capsule `.xdsl.json` dans *path*."""
    text = dsl_to_json(source, filename=filename)
    Path(path).write_text(text, encoding="utf-8")


def json_to_xml(json_source: str) -> str:
    """Compile une capsule `.xdsl.json` en XML QWeb (le même XML que le
    `.dsl` texte équivalent)."""
    return _compile_ast(json_to_ast(json_source))


def _compile_ast(ast: AST) -> str:
    return Compiler(ast).compile()


def json_to_ast(json_source: str) -> AST:
    """Désérialise une capsule `.xdsl.json` en AST xdsl."""
    data = json.loads(json_source)
    if data.get("format") != XDsl_FORMAT:
        raise ValueError(
            f"Fichier .xdsl.json invalide : format attendu {XDsl_FORMAT!r}, "
            f"trouvé {data.get('format')!r}"
        )
    if data.get("version") != XDsl_VERSION:
        raise ValueError(
            f"Version {data.get('version')!r} du format .xdsl.json non supportée "
            f"(cette build gère la version {XDsl_VERSION})"
        )
    return ast_from_dict(data["ast"])


def compile_json_file(path: str | Path) -> str:
    """Compile un fichier `.xdsl.json` en XML QWeb."""
    return json_to_xml(Path(path).read_text(encoding="utf-8"))
