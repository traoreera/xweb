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

(ROOT / ".verify-validators.json").write_text(
    json.dumps({"vectors": results, "schema": SCHEMA_JSON, "dict_cases": dict_results}, ensure_ascii=False, indent=2),
    encoding="utf-8",
)
print("écrit :", ROOT / ".verify-validators.json")
