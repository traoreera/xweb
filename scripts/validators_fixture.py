"""Vecteurs de test partagés serveur/client pour la validation déclarative
— exécute chaque règle avec le VRAI xdsl/validators.py (source de vérité)
et écrit les résultats attendus en JSON, lu ensuite par
scripts/verify-validators.mjs pour piloter le VRAI xweb/static/validators.js
sur les MÊMES entrées. Le seul moyen de prouver que le port JS se comporte
identiquement au moteur Python, plutôt que "semble correct" à la lecture.
"""

import json
from pathlib import Path

from xdsl.validators import make_validator

ROOT = Path(__file__).parent.parent

# (nom de règle, args, valeur testée)
VECTORS = [
    ("required", [], None),
    ("required", [], ""),
    ("required", [], "   "),
    ("required", [], "x"),
    ("required", [], 0),
    ("required", [], False),
    ("min_length", [3], "ab"),
    ("min_length", [3], "abc"),
    ("min_length", [3], "abcd"),
    ("min_length", [3], 5),
    ("max_length", [3], "abcd"),
    ("max_length", [3], "abc"),
    ("min", [0], -1),
    ("min", [0], 0),
    ("min", [0], "abc"),
    ("min", [0], None),
    ("max", [120], 121),
    ("max", [120], 120),
    ("email", [], "bad"),
    ("email", [], "alice@example.com"),
    ("email", [], 5),
    ("pattern", [r"[0-9]+"], "abc"),
    ("pattern", [r"[0-9]+"], "123abc"),
    ("in", [["admin", "editor"]], "admin"),
    ("in", [["admin", "editor"]], "other"),
    ("in", [["admin", "editor"]], 5),
]

results = []
for rule, args, value in VECTORS:
    validator = make_validator(rule, *args)
    outcome = validator(value)
    results.append({
        "rule": rule,
        "args": args,
        "value": value,
        "valid": outcome.valid,
        "errors": outcome.errors,
    })

# Schéma multi-champs, pour valider validate_dict / XwebValidate(schemaName, data)
# de bout en bout (pas juste règle par règle).
SCHEMA = {
    "name": [("required", []), ("min_length", [3])],
    "email": [("required", []), ("email", [])],
}
SCHEMA_JSON = {field: [[rule, list(args)] for rule, args in rules] for field, rules in SCHEMA.items()}

from xdsl.validators import validate_dict  # noqa: E402

DICT_CASES = [
    {"name": "Al", "email": "bad"},
    {"name": "Alice", "email": "alice@example.com"},
    {},
]
dict_results = []
schema_validators = {f: [make_validator(r, *a) for r, a in rules] for f, rules in SCHEMA.items()}
for data in DICT_CASES:
    errors = validate_dict(data, schema_validators)
    dict_results.append({"data": data, "errors": errors, "valid": errors == {}})

# ---------------------------------------------------------------------------
# COMPOSITION (`address: address`, `phones: list[phone]`) — la source de
# vérité est le VRAI extract_models/validate_model/validate_model_list
# (pydantic) ; validators.js doit produire les MÊMES erreurs, clés
# normalisées (Python utilise `phones.0.number`, JS `phones[0].number` —
# même chemin, deux conventions).
# ---------------------------------------------------------------------------
from xdsl.api import extract_models, validate_model, validate_model_list  # noqa: E402
from xdsl.compiler import _schema_to_json  # noqa: E402
from xdsl.parser import Parser  # noqa: E402

COMPOSED_SRC = """
data address { street: string @required  city: string @required }
data phone  { number: string @required @pattern("[0-9]+") }
data contact {
    name: string @required
    address: address
    phones: list[phone]
    tags: list[string]
}
"""
composed_models = extract_models(COMPOSED_SRC)
composed_schemas = {
    s.name: _schema_to_json(s) for s in Parser(COMPOSED_SRC).parse().data_schemas
}

COMPOSED_CASES = [
    {
        "schema": "contact",
        "list": False,
        "data": {
            "name": "Alice",
            "address": {"street": "1 rue", "city": "Paris"},
            "phones": [{"number": "0601020304"}],
            "tags": ["admin"],
        },
    },
    {
        "schema": "contact",
        "list": False,
        "data": {"name": "Alice", "address": {"street": "1 rue"}},  # city requis absent
    },
    {
        "schema": "contact",
        "list": False,
        "data": {
            "name": "x",
            "address": {"street": "s", "city": "c"},
            "phones": [{"number": "abc"}],  # @pattern("[0-9]+") violé au nested
            "tags": [5],  # list[string] mais int
        },
    },
    {
        "schema": "contact",
        "list": False,
        "data": {"name": "Alice", "address": "pas un objet"},  # ref en string
    },
    {
        "schema": "contact",
        "list": True,
        "data": [
            {"name": "Alice", "address": {"street": "s", "city": "c"}, "phones": [], "tags": []},
            {"name": "Bob", "address": {"street": "s"}},  # city manquant au 2e item
        ],
    },
    {
        "schema": "contact",
        "list": True,
        "data": {"name": "pas une liste"},
    },
]
composed_results = []
for case in COMPOSED_CASES:
    model = composed_models[case["schema"]]
    if case["list"]:
        errors = validate_model_list(model, case["data"])
    else:
        errors = validate_model(model, case["data"])
    composed_results.append(
        {"schema": case["schema"], "list": case["list"], "data": case["data"], "errors": errors}
    )

(ROOT / ".verify-validators.json").write_text(
    json.dumps(
        {
            "vectors": results,
            "schema": SCHEMA_JSON,
            "dict_cases": dict_results,
            "composed_schemas": composed_schemas,
            "composed_cases": composed_results,
        },
        ensure_ascii=False,
        indent=2,
    ),
    encoding="utf-8",
)
print("écrit :", ROOT / ".verify-validators.json")
