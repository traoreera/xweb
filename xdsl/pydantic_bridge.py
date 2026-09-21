"""Pont `data { ... }` → modèles Pydantic — le schéma DSL comme source de vérité.

Depuis qu'on a décidé (voir docs/dsl-design.md §data) de compenser l'absence
d'ORM par des schémas Pydantic, un bloc `data nom { champ: type @règles }`
a DEUX projections, toutes deux issues de la MÊME définition :

1. **Côté serveur — un vrai modèle Pydantic** (`build_model`) : typage réel
   (le `value_type` n'était qu'informatif pour `validate_dict`, il devient
   une annotation exécutée), champ `@required` → champ Pydantic requis, et
   chaque `@décorateur` attaché comme `AfterValidator`. Les règles ne sont
   PAS ré-implémentées en contraintes Pydantic natives (piège : pydantic
   ancre `pattern` en full-match quand validators.py fait du préfixe, `ge`
   refuse les non-nombres quand MinValue passe au travers...) — on réutilise
   les classes de xdsl/validators.py telles quelles, testées des deux côtés.
   Résultat : la sémantique des règles reste celle du moteur fermé, mais le
   typage et l'obligatoriété deviennent réellement appliqués.
2. **Côté client — le JSON Schema** (`model_json_schema()`, exporté par le
   compilateur comme `window.XWEB_SCHEMAS_JSON`) : réservé au rendu de champ
   façon `t-field` (étage suivant) et à tout consommateur JSON Schema — le
   miroir de feedback instantané `window.XWEB_SCHEMAS` (règles → validators.js)
   garde sa forme de listes de règles, c'est une projection d'un moteur à
   l'autre, pas un document JSON Schema.

La COMPOSITION est supportée (un champ n'est pas forcément un primitif) :
`value_type` peut être une RÉFÉRENCE à un autre `data` (`address: address`,
→ sous-modèle Pydantic imbriqué) ou `list[item]` avec item primitif ou
référence (`phones: list[phone]` → `list[PhoneModel]`). Le build est RÉCURSIF
sur la map complète des `data` déclarés (extract_models) — avec garde
anti-cycle : un graphe de schémas circulaire est une erreur de compilation
explicite, jamais une boucle infinie.

`validate_model()` rend le modèle utilisable comme remplaçant direct de
`validate_dict` : même forme de retour {champ: [messages]}, messages français
des règles identiques (levés par les Validator eux-mêmes), « missing » et
erreurs de type traduits ici pour conserver la paire `extract_schemas`/
`extract_models` interchangeables. Seule nuance: les messages de plusieurs
règles d'un même champ sont agrégés en UNE entrée par champ (validate_dict en
faisait une liste séparée) — pydantic ne remonte qu'une erreur par validator ;
sans impact sur les consumers xweb, qui traitent un message par champ. Les
erreurs des sous-modèles portent leurs CHEMINS complets (`address.street`,
`phones.0.number` — les indices numériques sont retirés pour relire le
wording de type, qui est par type de champ déclaré, pas par occurrence).

Écart assumé vs l'ancien chemin `validate_dict` : le type déclaré est DÉSORMAIS
appliqué. `age: int @min(0)` recevant `"abc"` ne passe plus silencieusement
(l'ancien moteur n'a jamais typé : float("abc") levait, MinValue passait au
travers, zéro erreur) — c'est tout l'intérêt du modèle comme couche de
données. Les règles, elles, gardent exactement leurs sémantiques de
passthrough (une règle typée string qui reçoit un nombre laisse passer).
"""

from __future__ import annotations

from typing import Annotated, Any, Optional

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    create_model,
)

from xdsl.parser import PRIMITIVE_TYPES, DataSchemaDef, split_value_type
from xdsl.validators import Validator, make_validator, validate_all

# value_type DSL → annotation Pydantic — MÊME table que validators.py::OneOf.
TYPE_MAP: dict[str, type[Any]] = {
    "string": str,
    "int": int,
    "float": float,
    "bool": bool,
    "list": list,
    "dict": dict,
}

# Traduction « type pydantic → ε message français » pour validate_model —
# fermée comme _FR_BY_TYPE de xweb/forms.py mais en wording DSL (paire OneOf :
# « Type invalide — attendu : ... »), les règles elles-mêmes portent déjà leur
# message français (levé par le Validator, jamais traduit ici).
_TYPE_ERRORS = {
    "string_type": "Doit être une chaîne de caractères.",
    "int_type": "Doit être un nombre entier.",
    "int_parsing": "Doit être un nombre entier valide.",
    "int_from_float": "Doit être un nombre entier, sans virgule.",
    "float_type": "Doit être un nombre.",
    "float_parsing": "Doit être un nombre valide.",
    "bool_type": "Doit être vrai ou faux.",
    "bool_parsing": "Doit être vrai ou faux.",
    "dict_type": "Doit être un objet valide.",
    "list_type": "Doit être une liste valide.",
}

_MISSING_MESSAGE = "Ce champ est obligatoire"
_VALUE_ERROR_PREFIX = "Value error, "


def _field_annotation(base: Any, rules: list[Validator], required: bool) -> tuple[Any, ...]:
    """Construit la paire (annotation, Field) d'un DataField, sur la base de
    type *base* (déjà résolu, primitif ou sous-modèle imbriqué).

    Les `@décorateurs` deviennent des AfterValidator — les classes Validator
    de xdsl/validators.py, le même moteur que xdsl/validators.js — jamais de
    contraintes Pydantic natives ré-implantées (dérive sémantique garantie).
    @required rend le champ requis AU MODÈLE (pydantic "missing" via Field(...))
    tout en restant une règle attachée (le cas `""`/`"   "` doit continuer à
    lever « Ce champ est obligatoire » comme dans validate_dict).
    """

    def _check(value: Any) -> Any:
        errors = validate_all(value, rules)
        if errors:
            raise ValueError(", ".join(errors))
        return value

    if required:
        annotation: Any = Annotated[base, AfterValidator(_check)]
        return annotation, Field(...)
    annotation = Annotated[Optional[base], AfterValidator(_check)]
    return annotation, Field(default=None)


class _ModelBuilder:
    """Construit des modèles Pydantic RÉCURSIFS depuis la map complète des
    `data nom { ... }` — la composition (`address: address`,
    `phones: list[phone]`) devient un sous-modèle imbriqué, résolu par nom,
    avec mémoïsation et garde anti-cycle (DAG obligatoire)."""

    def __init__(self, schemas: dict[str, DataSchemaDef]) -> None:
        self._schemas = schemas
        self._models: dict[str, type[BaseModel]] = {}
        self._stack: list[str] = []

    def build(self, name: str) -> type[BaseModel]:
        """Compile le `data {name}` en modèle Pydantic (et RÉCURSIVEMENT
        chaque `data` référencé par ses champs composés). Lève une ValueError
        française sur : `@décorateur` inconnu (même posture que
        extract_schemas — un typo doit planter à la construction, pas
        produire un modèle qui n'applique pas la règle), référence à un
        `data` jamais déclaré, ou référence circulaire."""
        cached = self._models.get(name)
        if cached is not None:
            return cached
        schema = self._schemas.get(name)
        if schema is None:
            raise ValueError(
                f"Schéma data {name!r} référencé mais jamais déclaré "
                f"(data {name} {{ ... }})"
            )
        if name in self._stack:
            cycle = " -> ".join(self._stack + [name])
            raise ValueError(
                f"Référence circulaire entre schémas data : {cycle} — "
                f"la composition doit former un graphe acyclique"
            )
        self._stack.append(name)

        fields: dict[str, tuple[Any, ...]] = {}
        for field in schema.fields:
            kind, item = split_value_type(field.value_type)
            if kind == "ref":
                base: Any = self.build(item)  # sous-modèle imbriqué
            elif kind == "list":
                if item in PRIMITIVE_TYPES:
                    base = list[TYPE_MAP.get(item, Any)]  # list[primitif]
                else:
                    base = list[self.build(item)]  # liste de sous-modèles
            else:
                base = TYPE_MAP.get(item, Any)
            rules = [make_validator(rule_name, *args) for rule_name, args in field.decorators]
            required = any(rule.name == "required" for rule in rules)
            annotation, field_info = _field_annotation(base, rules, required)
            fields[field.name] = (annotation, field_info)

        model = create_model(
            name,
            __config__=ConfigDict(extra="ignore"),
            **fields,
        )
        # value_type par champ (chemins DOTTED par la composition), relu par
        # validate_model pour le wording des erreurs de type — inaccessible
        # proprement depuis l'annotation pydantic (Optional/Annotated/sous-
        # modèles), d'où ce drapeau aplati sur la classe construite.
        model.__xdsl_type_map__ = self._flat_type_map(name)
        self._stack.pop()
        self._models[name] = model
        return model

    def _flat_type_map(self, name: str, prefix: str = "") -> dict[str, str]:
        """Carte aplatissante {chemin.dotted: value_type} pour le wording :
        `address.street`, `phones.0.number` (indices retirés au lookup, pas
        ici) — valeurs "telles qu'écrites" (`list[phone]`, `string`, ...)."""
        out: dict[str, str] = {}
        for field in self._schemas[name].fields:
            kind, item = split_value_type(field.value_type)
            key = f"{prefix}{field.name}"
            out[key] = field.value_type
            if kind == "ref":
                out.update(self._flat_type_map(item, f"{key}."))
            elif kind == "list" and item not in PRIMITIVE_TYPES:
                out.update(self._flat_type_map(item, f"{key}."))
        return out


def build_model(schema: DataSchemaDef, schemas: dict[str, DataSchemaDef] | None = None) -> type[BaseModel]:
    """Compile un `data nom { ... }` (et ses dépendances composées) en
    modèle Pydantic canonique. `schemas` est la map complète des `data` —
    quand il est None, seul *schema* est connu : une référence vers un autre
    `data` est alors une erreur explicite ("jamais déclaré"), le vrai usage
    composé passe par `extract_models()` (qui construit la map entière).

    `extra="ignore"` par défaut : comme validate_dict, les champs inconnus
    du payload ne sont pas une erreur."""
    schemas = {schema.name: schema} if schemas is None else schemas
    return _ModelBuilder(schemas).build(schema.name)


def validate_model(model: type[BaseModel], data: Any) -> dict[str, list[str]]:
    """Valide *data* contre le modèle — même contrat que validate_dict()
    ({champ: [messages]}, vide si valide), messages français des règles
    intacts (levés par les Validator eux-mêmes). « missing » → « Ce champ
    est obligatoire », erreurs de type → wording DSL « Type invalide » :
    les deux chemins d'extraction (extract_schemas/validate_dict et
    extract_models/validate_model) doivent rester interchangeables. Les
    erreurs composées portent leur chemin complet (`address.street`,
    `phones.0.number`)."""
    if not isinstance(data, dict):
        data = {}
    try:
        model.model_validate(data)
    except ValidationError as exc:
        errors: dict[str, list[str]] = {}
        type_map: dict = getattr(model, "__xdsl_type_map__", {})
        for err in exc.errors():
            loc = err.get("loc") or ()
            parts = [str(p) for p in loc]
            field = ".".join(parts) or "__root__"
            # Le wording de type est par type DÉCLARÉ, pas par occurrence :
            # `phones.0.number` cherche le type du champ `phones.number`.
            map_key = ".".join(p for p in parts if not p.isdigit()) or "__root__"
            error_type = err.get("type")
            msg = str(err.get("msg", ""))
            if error_type == "missing":
                errors.setdefault(field, []).append(_MISSING_MESSAGE)
            elif error_type in _TYPE_ERRORS or error_type.startswith("model_"):
                # `model_type`/`model_attributes_type` (une VALEUR non-objet
                # sur un champ composé, ex. `address: 5`) n'est pas dans le
                # dictionnaire fermé — il passe par le wording « Type
                # invalide — attendu : {value_type} » quand l'identité du
                # champ (ou son chemin composé) est connue, sinon le message
                # générique objet.
                name = type_map.get(field) or type_map.get(map_key)
                if name is not None:
                    errors.setdefault(field, []).append(
                        f"Type invalide — attendu : {name}"
                    )
                else:
                    errors.setdefault(field, []).append(_TYPE_ERRORS.get(error_type, "Doit être un objet valide."))
            elif error_type == "value_error" and msg.startswith(_VALUE_ERROR_PREFIX):
                errors.setdefault(field, []).append(msg[len(_VALUE_ERROR_PREFIX):])
            else:
                errors.setdefault(field, []).append(msg)
        return errors
    return {}


def validate_model_list(model: type[BaseModel], data: Any) -> dict[str, list[str]]:
    """Valide une RÉPONSE tableau (`receive { list: true }` côté serveur) :
    *data* est une liste, chaque élément est validé contre *model*, les
    erreurs sont préfixées par leur index (`0.name`, `1.street`) — la même
    convention de chemin que validators.js côte navigateur. Un payload qui
    n'est PAS une liste laisse une erreur au niveau racine
    (`__root__`: « Doit être une liste valide. »), jamais un silence."""
    if not isinstance(data, list):
        return {"__root__": [_TYPE_ERRORS["list_type"]]}
    errors: dict[str, list[str]] = {}
    for index, item in enumerate(data):
        item_errors = validate_model(model, item)
        for field, messages in item_errors.items():
            errors[f"{index}.{field}"] = messages
    return errors