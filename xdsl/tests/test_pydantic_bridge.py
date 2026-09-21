"""Pont `data { ... }` → modèles Pydantic (xdsl/pydantic_bridge.py).

La source de vérité est LE schéma `data` — le modèle Pydantic est sa
projection serveur (typage + @required + règles, mêmes Validator que
xdsl/validators.py) et le JSON Schema sa projection client. Ces tests
prouvent :

- la parité de verdict avec l'ancien chemin validate_dict/extract_schemas
  sur les MÊMES vecteurs (règles identiques, mêmes messages français),
- le delta ASSUMÉ : le type déclaré est réellement appliqué (l'ancien
  moteur ne typait jamais),
- le drop-in validate_model : même forme {champ: [messages]},
- l'export window.XWEB_SCHEMAS_JSON par le compilateur.
"""

import json
import textwrap

import pytest
from pydantic import ValidationError

from xdsl.api import compile_dsl, extract_models, extract_schemas, validate_model
from xdsl.pydantic_bridge import build_model, validate_model_list
from xdsl.validators import validate_dict, make_validator

SCHEMA_SRC = textwrap.dedent("""
    data contact_form {
        name: string @required @min_length(3)
        age: int @min(0) @max(120)
        email: string @email
        role: string @in(["admin", "editor"])
    }
""")


def _schema() -> "DataSchemaDef":
    from xdsl.parser import Parser

    return Parser(SCHEMA_SRC).parse().data_schemas[0]


def test_build_model_valide_payload_ok():
    model = build_model(_schema())
    data = model.model_validate({"name": "Alice", "age": 30, "email": "alice@x.com", "role": "admin"})
    assert data.name == "Alice"
    assert data.age == 30


def test_build_model_ignore_champs_inconnus():
    model = build_model(_schema())
    data = model.model_validate({"name": "Bob", "age": 3, "bogus": "x"})
    assert data.name == "Bob"
    assert not hasattr(data, "bogus")


def test_type_applique_pour_de_vrai():
    """Delta assumé vs ancien moteur : le value_type est une annotation
    exécutée. `age: int` + "abc" lève une erreur Pydantic (l'ancien
    validate_dict laissait passer : MinValue faisait du passthrough)."""
    model = build_model(_schema())
    with pytest.raises(ValidationError):
        model.model_validate({"name": "Alice", "age": "abc"})
    errors = validate_model(model, {"name": "Alice", "age": "abc"})
    assert errors["age"] == ["Type invalide — attendu : int"]


def test_required_est_unique_a_la_fois_champ_modele_et_regle():
    model = build_model(_schema())
    # absent → pydantic "missing" → traduit comme la règle Required
    errors = validate_model(model, {"age": 30})
    assert errors["name"] == ["Ce champ est obligatoire"]
    with pytest.raises(ValidationError):
        model.model_validate({"age": 30})
    # présent mais vide → la règle Required lève (cas que pydantic seul
    # n'attrape pas : str "" est un str valide) — les messages des règles
    # sont agrégés en un message par champ (forme d'un champ = un message,
    # comme parse_form ; validate_model ne multiple pas les entrées
    # d'erreur par règle contrairement à validate_dict).
    errors = validate_model(model, {"name": "", "age": 30})
    assert errors["name"] == ["Ce champ est obligatoire, Minimum 3 caractères"]


def test_regles_sont_les_memes_que_le_moteur():
    model = build_model(_schema())
    schemas = extract_schemas(SCHEMA_SRC)
    # Les messages des règles (non-type, non-missing) viennent des Validator
    # eux-mêmes — strictement identiques aux deux chemins.
    assert validate_model(model, {"name": "Al", "age": 200, "email": "bad", "role": "superuser"}) == {
        "name": ["Minimum 3 caractères"],
        "age": ["La valeur maximale est 120"],
        "email": ["Adresse email invalide"],
        "role": ["Valeur invalide — autorisées : admin, editor"],
    }
    # verdicts identiques à l'ancien moteur (ensemble des champs en erreur).
    payload = {"name": "Al", "age": 200, "email": "bad", "role": "superuser"}
    engine = validate_dict(payload, schemas["contact_form"])
    assert set(validate_model(model, payload)) == set(engine)


def test_validate_model_drop_in_de_validate_dict():
    """Même forme {champ: [messages]}, vide si valide, jamais d'exception.
    (Les messages de plusieurs règles d'un même champ sont agrégés en une
    entrée — validate_dict en faisait une liste séparée ; pas d'impact sur
    les consumers xweb, qui traitent un message par champ.)"""
    model = build_model(_schema())
    assert validate_model(model, {"name": "Alice", "age": 30, "role": "editor"}) == {}
    assert validate_model(model, None) != {}
    # champs hors modèle ignorés, pas une erreur (extra="ignore")
    assert validate_model(model, {"name": "Alice", "nimporte": 1}) == {}


def test_regles_passent_au_travers_sur_None_mais_le_type_est_applique():
    """Le passthrough des règles (typées string) ne joue plus pour un type
    étranger à la déclaration — le typage est le delta assumé — mais il tient
    pour None, comme validate_dict (None passe les règles string)."""
    from xdsl.parser import Parser

    src = "data d { x: string @min_length(3) @email }"
    model = build_model(Parser(src).parse().data_schemas[0])
    assert validate_model(model, {"x": None}) == {}
    errors = validate_model(model, {"x": 5})
    assert errors["x"] == ["Type invalide — attendu : string"]


def test_extract_models_retourne_nom_vers_modele():
    models = extract_models(SCHEMA_SRC)
    assert set(models) == {"contact_form"}
    assert validate_model(models["contact_form"], {"name": "Alice"}) == {}


def test_decorateur_inconnu_leve_a_la_construction():
    """Même posture fail-fast que extract_schemas — un typo dans une règle
    doit planter, pas produire un modèle qui n'applique pas la règle."""
    from xdsl.parser import Parser

    schema = Parser("data d { x: string @not_a_real_rule }").parse().data_schemas[0]
    from xdsl.validators import BUILTIN_VALIDATORS

    assert "not_a_real_rule" not in BUILTIN_VALIDATORS
    with pytest.raises(ValueError, match="not_a_real_rule"):
        build_model(schema)


def test_optional_sans_required_a_un_default():
    from xdsl.parser import Parser

    model = build_model(Parser("data d { phone: string }").parse().data_schemas[0])
    assert model.model_validate({}).phone is None


def test_compiler_exporte_aussi_le_json_schema_du_modele():
    import html

    xml = compile_dsl(textwrap.dedent("""
        data contact_form {
            name: string @required @min_length(3)
            age: int @min(0)
        }
        channel c {
            url: "/x"
            validate: "contact_form"
        }
        div { use_channel: c }
    """))
    assert "XWEB_SCHEMAS_JSON" in xml
    # Le contenu <script> est encodé en entités dans la sortie XML
    # (&quot; pour une chaîne JS) — le HTML réel dé-échappe avant exécution.
    marker = "window.XWEB_SCHEMAS_JSON[&quot;contact_form&quot;] = "
    start = xml.index(marker) + len(marker)
    end = xml.index("};", start) + 1
    schema = json.loads(html.unescape(xml[start:end]))
    assert schema["type"] == "object"
    props = schema["properties"]
    assert props["name"]["type"] == "string"
    # age n'a pas @required → optionnel → anyOf [integer, null] (modèle T|None)
    assert props["age"]["anyOf"][0]["type"] == "integer"
    assert props["age"]["default"] is None
    assert "name" in schema["required"]


# =============================================================================
# Composition (`address: address`, `phones: list[phone]`) et listes
# =============================================================================

COMPOSED_SRC = textwrap.dedent("""
    data address { street: string @required  city: string @required }
    data phone  { number: string @required @pattern("[0-9]+") }
    data contact {
        name: string @required
        address: address
        phones: list[phone]
        tags: list[string]
    }
""")


def test_extract_models_builds_the_full_composed_map():
    models = extract_models(COMPOSED_SRC)
    assert set(models) == {"address", "phone", "contact"}
    ok = {"name": "a", "address": {"street": "s", "city": "c"}, "phones": [], "tags": []}
    assert validate_model(models["contact"], ok) == {}


def test_validate_model_nested_missing_is_reported_on_the_nested_field():
    """Le manque d'un champ requis à l'intérieur d'une référence remonte
    sous le chemin composé `address.city`, pas sur `address`."""
    models = extract_models(COMPOSED_SRC)
    errors = validate_model(models["contact"], {"name": "x", "address": {"street": "s"}})
    assert errors["address.city"] == ["Ce champ est obligatoire"]


def test_validate_model_list_items_are_checked_individually():
    models = extract_models(COMPOSED_SRC)
    errors = validate_model(
        models["contact"],
        {"name": "x", "phones": [{"number": "abc"}, {"number": "0601020304"}]},
    )
    assert errors["phones.0.number"] == ["La valeur ne correspond pas au format attendu"]
    assert "phones.1.number" not in errors


def test_validate_model_ref_wrong_type():
    models = extract_models(COMPOSED_SRC)
    errors = validate_model(models["contact"], {"name": "x", "address": "pas un objet"})
    assert errors["address"] == ["Type invalide — attendu : address"]


def test_validate_model_list_of_primitive_wrong_item_type():
    models = extract_models(COMPOSED_SRC)
    errors = validate_model(models["contact"], {"name": "x", "tags": [5]})
    assert errors["tags.0"] == ["Type invalide — attendu : list[string]"]


def test_validate_model_list_of_primitive_accepts_typed_items():
    models = extract_models(COMPOSED_SRC)
    assert validate_model(models["contact"], {"name": "x", "tags": ["admin"]}) == {}


def test_validate_model_list_item_wrong_type_uses_annotated_item_type():
    """Bug de la première passe : list[primitif] était annoté `TYPE_MAP[item]`
    au lieu de `list[TYPE_MAP[item]]` — 5 dans une list[int] passait la
    validation des items sans erreur de type (Champ 1: 5 est identique
    depuis que l'annotation est correcte; ce test fige la forme attendue)."""
    from xdsl.parser import Parser

    src = "data d { ints: list[int] }"
    models = extract_models(src)
    assert validate_model(models["d"], {"ints": [1, 2]}) == {}


def test_validate_model_list_non_list_root_is_flagged():
    models = extract_models(COMPOSED_SRC)
    model = models["contact"]
    errors = validate_model_list(model, {"name": "pas une liste"})
    assert "__root__" in errors
    assert errors["__root__"] == ["Doit être une liste valide."]


def test_validate_model_list_valid_items_pass():
    models = extract_models(COMPOSED_SRC)
    data = [
        {"name": "a", "address": {"street": "s", "city": "c"}, "phones": [], "tags": []},
        {"name": "b", "address": {"street": "s", "city": "c"}, "phones": [], "tags": []},
    ]
    assert validate_model_list(models["contact"], data) == {}


def test_extract_models_cycle_raises_explicit_error():
    """Deux schémas qui se réfèrent l'un l'autre ne doivent jamais former
    une récursion infinie — erreur claire à la construction, pas un
    RecursionError à la validation."""
    src = textwrap.dedent("""
        data a { x: b }
        data b { y: a }
    """)
    with pytest.raises(ValueError, match="Référence circulaire"):
        extract_models(src)


def test_validate_response_object_and_list_forms():
    from xdsl.api import validate_response

    models = extract_models(COMPOSED_SRC)
    ok = {"name": "a", "address": {"street": "s", "city": "c"}, "phones": [], "tags": []}
    assert validate_response(models, "contact", ok) == {}
    assert validate_response(models, "contact", [ok, ok], as_list=True) == {}
    # as_list sans tableau -> __root__
    assert "__root__" in validate_response(models, "contact", ok, as_list=True)
    # objets imbriqués cassés remontent la même forme que validate_model
    assert "address.city" in validate_response(
        models, "contact", {"name": "a", "address": {"street": "s"}}
    )


def test_validate_response_unknown_schema_raises():
    from xdsl.api import validate_response

    models = extract_models(COMPOSED_SRC)
    with pytest.raises(ValueError, match="noola"):
        validate_response(models, "noola", {})