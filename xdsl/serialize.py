"""Sérialisation AST <-> JSON — contrat de données du moteur No-Code.

Le JSON est UNE représentation 1-1 de l'AST xdsl (mêmes dataclasses que
le parser produit) : ``dataclasses.asdict`` ferait l'affaire mais sans
discriminateur de type — un ``Element`` et un ``TextNode`` se
ressembleraient. Chaque nœud porte donc un champ ``"type"`` discriminant,
et les valeurs sont réhydratées dans les classes exactes du parser à la
desérialisation (``ast_from_json``).

Pipeline
--------
    source .dsl ──Parser──▶ AST ──ast_to_json──▶ .xdsl.json (éditeur)
    .xdsl.json  ──ast_from_json──▶ AST ──Compiler──▶ XML QWeb

Le compilateur ne change pas : un fichier .xdsl.json chargé par l'éditeur
(branche No-Code) produit exactement le même XML que le .dsl texte
équivalent à la main. Round-trip garanti par tests :
    XML(parse(dsl)) == XML(from_json(to_json(parse(dsl))))
"""

from __future__ import annotations

import json
from dataclasses import asdict, fields, is_dataclass
from enum import Enum
from typing import Any

from .parser import (
    AST,
    Assignment,
    Attribute,
    AttributeValue,
    ChannelDef,
    ChannelOnMessage,
    ComponentDef,
    CopyDef,
    DataField,
    DataSchemaDef,
    Element,
    EndpointDef,
    ForLoop,
    IfBlock,
    Import,
    PatchDef,
    Position,
    Props,
    ReceiveSpec,
    SlotNode,
    Style,
    TextNode,
    XpathPatch,
)

# Discriminant JSON -> constructeur dataclass.
_NODE_TYPES = {
    "ast": AST,
    "component": ComponentDef,
    "import": Import,
    "props": Props,
    "style": Style,
    "attribute": Attribute,
    "attr_value": AttributeValue,
    "xpath_patch": XpathPatch,
    "patch": PatchDef,
    "copy": CopyDef,
    "if": IfBlock,
    "for": ForLoop,
    "assignment": Assignment,
    "text": TextNode,
    "slot": SlotNode,
    "element": Element,
    "data_field": DataField,
    "data_schema": DataSchemaDef,
    "receive_spec": ReceiveSpec,
    "endpoint": EndpointDef,
    "channel_onmessage": ChannelOnMessage,
    "channel": ChannelDef,
}
_TYPE_BY_CLASS = {cls.__name__: name for name, cls in _NODE_TYPES.items()}

# Champs dataclass dont le contenu doit être traité comme opaque (JSON-safe
# tel quel : scalaires Python) plutôt que re-dispatché comme nœud.
_OPAQUE_FIELDS = {"css", "defaults"}


def _type_name(node: Any) -> str:
    name = _TYPE_BY_CLASS.get(type(node).__name__)
    if name is None:
        raise ValueError(f"Type de nœud non sérialisable: {type(node).__name__}")
    return name


def _value_to_json(value: Any) -> Any:
    """Sérialise la valeur d'un champ de nœud."""
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return _node_to_dict(value)
    if isinstance(value, (list, tuple)):
        return [_value_to_json(v) for v in value]
    if isinstance(value, dict):
        return {k: _value_to_json(v) for k, v in value.items()}
    return value


def _node_to_dict(node: Any) -> dict:
    out: dict = {"type": _type_name(node)}
    for f in fields(node):
        if f.name in _OPAQUE_FIELDS:
            out[f.name] = getattr(node, f.name)
            continue
        out[f.name] = _value_to_json(getattr(node, f.name))
    return out


def _dict_to_node(data: dict) -> Any:
    """Réhydrate un nœud depuis son dict JSON (recursion children incluse)."""
    node_type = data.get("type")
    if node_type is None:
        raise ValueError(f"Nœud JSON sans champ 'type': {data!r}")
    cls = _NODE_TYPES.get(node_type)
    if cls is None:
        raise ValueError(f"Type de nœud JSON inconnu: {node_type!r}")

    kwargs: dict = {}
    for f in fields(cls):
        if f.name == "elif_blocks":
            kwargs["elif_blocks"] = [
                (cond, [_dict_to_node(c) for c in nodes])
                for cond, nodes in data.get("elif_blocks", [])
            ]
            continue
        if f.name == "children":
            kwargs["children"] = [_dict_to_node(c) for c in data.get("children", [])]
            continue
        if f.name not in data:
            continue
        kwargs[f.name] = _value_from_json(data[f.name], f.type)
    return cls(**kwargs)


def _value_from_json(value: Any, annotation: str | None = None) -> Any:
    """Réhydrate une valeur de champ depuis JSON."""
    if annotation is not None and "Position" in annotation and isinstance(value, str):
        return Position(value)
    if isinstance(value, list):
        return [_value_from_json(v) for v in value]
    if isinstance(value, dict):
        if value.get("type") in _NODE_TYPES:
            return _dict_to_node(value)
        # dict de style/attributs : {prop: {value, quoted}} — les valeurs
        # peuvent être des AttributeValue.
        return {k: _value_from_json(v) for k, v in value.items()}
    return value


def ast_to_dict(ast: AST) -> dict:
    """Convertit un AST en dict JSON-able."""
    return _node_to_dict(ast)


def ast_from_dict(data: dict) -> AST:
    """Reconstruit un AST depuis un dict JSON (issu d'ast_to_dict)."""
    return _dict_to_node(data)


def ast_to_json(ast: AST, *, indent: int = 2) -> str:
    """Sérialise un AST en JSON."""
    return json.dumps(ast_to_dict(ast), ensure_ascii=False, indent=indent)


def ast_from_json(source: str) -> AST:
    """Parse un JSON d'AST (produit par ast_to_json) en AST xdsl."""
    return ast_from_dict(json.loads(source))