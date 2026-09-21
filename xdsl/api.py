"""API publique xdsl — convertit du DSL en XML QWeb.

Un fichier `.xdsl.json` est le format d'échange No-Code : une capsule
enveloppant l'AST sérialisé 1-1 (`xdsl/serialize.py`, même arbre que le
parser produit). L'éditeur lit/écrit cette capsule ; le moteur la
désérialise et compile le même XML que le `.dsl` texte équivalent.

    .dsl ──Parser──▶ AST ──ast_to_json (capsule)──▶ .xdsl.json (éditeur)
    .xdsl.json ──ast_from_json──▶ AST ──Compiler──▶ XML QWeb

La capsule est signée HMAC-SHA256 pour garantir l'intégrité et
l'authorship (variable d'env XDSL_CAPSULE_SECRET, défaut dev).
"""

from __future__ import annotations

import hmac
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from .compiler import Compiler
from .parser import AST, Parser, split_value_type
from .pydantic_bridge import (
    _ModelBuilder,
    validate_model,
    validate_model_list,
)
from .serialize import ast_from_dict, ast_to_dict
from .validators import Validator, make_validator

# Version du format de capsule `.xdsl.json` — incrémenter à chaque rupture
# de schéma de l'AST, l'éditeur refuse les versions qu'il ne connaît pas.
XDsl_FORMAT = "xdsl.json"
XDsl_VERSION = 1

# Variable d'environnement pour la clé de signature HMAC.
# En production, DOIT être définie avec une valeur secrète forte.
# Valeur de développement uniquement — NE PAS UTILISER EN PRODUCTION.
_CAPSULE_SECRET_ENV = "XDSL_CAPSULE_SECRET"
_CAPSULE_AUTHOR_ENV = "XDSL_CAPSULE_AUTHOR"
_DEV_SECRET = "xdsl-dev-secret-change-in-production"
_DEV_AUTHOR = "local-dev"


def _signature_secret() -> str:
    return os.environ.get(_CAPSULE_SECRET_ENV, _DEV_SECRET)


def _capsule_author() -> str:
    return os.environ.get(_CAPSULE_AUTHOR_ENV, _DEV_AUTHOR)


def _capsule_payload(data: dict[str, Any]) -> str:
    """Sérialisation canonique pour signature (clés triées, pas d'espaces)."""
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sign_capsule(data: dict[str, Any]) -> str:
    """Calcule la signature HMAC-SHA256 du payload canonique."""
    return hmac.new(
        _signature_secret().encode(), _capsule_payload(data).encode(), hashlib.sha256
    ).hexdigest()


def _verify_capsule(data: dict[str, Any], signature: str) -> bool:
    """Vérifie la signature HMAC en temps constant."""
    expected = _sign_capsule(data)
    return hmac.compare_digest(signature, expected)


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

    LIMITE (erreur explicite, jamais silencieuse) : un champ de type
    COMPOSÉ (`address: address`, `phones: list[phone]`) n'est pas
    exprimable par ce schéma PLAT de listes de règles — `validate_dict`
    ne saurait pas descendre dans l'objet. Ce chemin (légacy) lève une
    ValueError française qui renvoie vers extract_models/validate_model,
    le chemin canonique pour un schéma composé."""
    ast = Parser(source, filename).parse()
    schemas: dict[str, dict[str, list[Validator]]] = {}
    for schema in ast.data_schemas:
        for field in schema.fields:
            kind, _ = split_value_type(field.value_type)
            if kind != "primitive":
                raise ValueError(
                    f"data {schema.name}.{field.name}: type composé "
                    f"« {field.value_type} » — le chemin plat "
                    f"extract_schemas/validate_dict ne sait pas descendre "
                    f"dans l'imbrication, utilisez extract_models/"
                    f"validate_model (ou validate_model_list pour une "
                    f"réponse tableau)"
                )
        schemas[schema.name] = {
            field.name: [make_validator(name, *args) for name, args in field.decorators]
            for field in schema.fields
        }
    return schemas


def extract_models(source: str, filename: str = "<stdin>") -> dict[str, type[BaseModel]]:
    """Projection Pydantic de chaque `data nom { ... }` — la source de
    vérité côté serveur (même AST que extract_schemas, mais en modèles) :

        from xdsl.api import extract_models, validate_model

        models = extract_models(open("contacts.dsl").read())
        errors = validate_model(models["contact_form"], request_json)
        # ou : contacts = models["contact_form"].model_validate(request_json)
        # (accès attribut, coercition typée, objet prêt à persister — le
        # rendu champ « façon t-field » lira model_json_schema()).

    Remplaçant drop-in de validate_dict + extract_schemas (même forme de
    retour, messages des règles agrégés par champ — voir pydantic_bridge)
    avec une différence assumée : le type déclaré est réellement appliqué
    (l'ancien moteur ne typait jamais — voir pydantic_bridge).

    La COMPOSITION est supportée : `address: address` et
    `phones: list[phone]` produisent des sous-modèles Pydantic imbriqués
    (build récursif sur la map entière, références circulaires refusées au
    build — voir pydantic_bridge._ModelBuilder)."""
    ast = Parser(source, filename).parse()
    schemas = {schema.name: schema for schema in ast.data_schemas}
    builder = _ModelBuilder(schemas)
    return {name: builder.build(name) for name in schemas}


def validate_response(
    models: dict[str, type[BaseModel]], schema_name: str, payload: Any, *, as_list: bool = False
) -> dict[str, list[str]]:
    """Valide une RÉPONSE HTTP (`data` du bloc `receive { schema: ... }` —
    même schéma, le serveur n'a pas à redéclarer la forme qu'il envoie,
    c'est le même `data` utilisé pour `send` et pour la validation) :
    *as_list=False* (objet, `receive` sans `list: true`) → validate_model,
    *as_list=True* (tableau, `receive { list: true }`) → validate_model_list
    (erreurs préfixées `0.name`,...). Lève une ValueError française sur un
    nom de schéma inconnu."""
    model = models.get(schema_name)
    if model is None:
        raise ValueError(
            f"Schéma data {schema_name!r} inconnu — déclarez "
            f"data {schema_name} {{ ... }} avant de le référencer"
        )
    if as_list:
        return validate_model_list(model, payload)
    return validate_model(model, payload)


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
    """Construit la capsule sans signature (la signature est ajoutée par dsl_to_json)."""
    return {
        "format": XDsl_FORMAT,
        "version": XDsl_VERSION,
        "author": _capsule_author(),
        "filename": filename,
        "ast": ast_to_dict(ast),
    }


def dsl_to_json(source: str, *, filename: str | None = None) -> str:
    """Parse du xdsl et sérialise l'AST dans la capsule `.xdsl.json` signée."""
    capsule = _capsule(Parser(source, filename or "<stdin>").parse(), filename=filename)
    capsule["signature"] = _sign_capsule(capsule)
    return json.dumps(capsule, ensure_ascii=False, indent=2)


def dump_dsl_json(source: str, path: str | Path, *, filename: str | None = None) -> None:
    """Parse du xdsl et écrit la capsule `.xdsl.json` signée dans *path*."""
    text = dsl_to_json(source, filename=filename)
    Path(path).write_text(text, encoding="utf-8")


def json_to_xml(json_source: str) -> str:
    """Compile une capsule `.xdsl.json` en XML QWeb (le même XML que le
    `.dsl` texte équivalent)."""
    return _compile_ast(json_to_ast(json_source))


def _compile_ast(ast: AST) -> str:
    return Compiler(ast).compile()


def json_to_ast(json_source: str) -> AST:
    """Désérialise une capsule `.xdsl.json` signée en AST xdsl.

    La signature HMAC est vérifiée — une capsule non signée, altérée
    ou signée avec une clé différente est refusée (ValueError).
    """
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
    signature = data.pop("signature", None)
    if not isinstance(signature, str) or not signature:
        raise ValueError(
            "Capsule .xdsl.json non signée — refusée (sécuriser les échanges No-Code)"
        )
    if not _verify_capsule(data, signature):
        raise ValueError(
            "Signature HMAC de la capsule invalide — contenu altéré ou clé différente"
        )
    return ast_from_dict(data["ast"])


def compile_json_file(path: str | Path) -> str:
    """Compile un fichier `.xdsl.json` en XML QWeb."""
    return json_to_xml(Path(path).read_text(encoding="utf-8"))
