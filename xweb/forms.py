"""Validation de formulaires xweb par Pydantic.

Porté depuis xui/forms.py — pas d'injection automatique FastAPI (son 422
JSON par défaut est inutilisable pour une page HTML, où on veut ré-afficher
le même template avec un message par champ et les valeurs déjà saisies
conservées). `parse_form()` valide donc explicitement dans la route et
renvoie un FormResult prêt à passer au contexte de rendu (`docs/plugins.md` §2).

## Traduction des messages — par `type`, jamais par texte anglais

Pydantic sort ses messages en anglais par défaut ("Field required"...) —
alors que le français est la langue source de tout ce projet (CLAUDE.md,
`xweb/i18n.py`). Deux approches essayées, une seule retenue :

  1. **Essayée puis abandonnée** : la bibliothèque `pydantic-i18n` (PyPI,
     MIT) — matche le texte anglais par regex contre des gabarits connus.
     Testée pour de vrai (pas juste lue) contre ce projet : elle confond
     deux gabarits qui partagent un préfixe commun — "Input should be
     greater than {}" matche PARTIELLEMENT à l'intérieur de "Input should
     be greater than or equal to 18", produisant "Doit être supérieur à
     or equal to 18." (moitié traduit, moitié pas). La bibliothèque ne
     trie jamais ses gabarits par longueur avant de construire son regex
     d'alternatives (`PydanticI18n._init_pattern`) — un vrai bug, pas une
     erreur d'usage de notre côté. Retirée (`uv remove pydantic-i18n`).
  2. **Retenue** : chaque erreur pydantic porte un `type` — un identifiant
     STABLE ("missing", "string_too_short", "greater_than_equal"...),
     documenté comme faisant partie de l'API publique de pydantic
     (https://docs.pydantic.dev/latest/errors/validation_errors/), et un
     `ctx` avec les valeurs numériques déjà extraites (`{"min_length": 3}`,
     `{"ge": 18}`...) — jamais besoin de reparser le texte du message pour
     retrouver un nombre. Matcher sur `type` plutôt que sur le texte anglais
     règle à la fois le bug ci-dessus (pas de chevauchement possible entre
     des identifiants exacts) ET la fragilité du pattern `_FR` déjà utilisé
     ailleurs dans ce dépôt pour traduire les erreurs d'une API JSON externe
     (`plugins/account/src/api.py`, avant sa suppression) — un `type` ne
     change pas si pydantic reformule un message d'une version à l'autre.

`_FR_BY_TYPE` ne couvre que les types les plus courants dans un formulaire
HTML (champ requis, longueur, type de base, comparaison numérique) — la
liste complète des ~50 types existe (`pydantic_core.list_all_errors()`)
mais la plupart (unions discriminées, dataclasses, arguments de fonction
validés...) ne concernent jamais un formulaire HTML. Un type absent de ce
dict retombe sur le message anglais tel quel, jamais une exception — même
principe de dégradation que `xweb/i18n.py::Catalog.translator_for`.

Limite connue : `EmailStr` délègue à `email-validator`, une bibliothèque
tierce qui lève sa PROPRE exception avec son propre texte anglais, absorbée
par pydantic comme `type="value_error"` — seul le préfixe est traduit ici
("Erreur : ..."), le détail derrière vient d'une bibliothèque avec son
propre système de messages, hors de portée de ce module.
"""

from __future__ import annotations

from typing import Any, Generic, Mapping, TypeVar

from pydantic import BaseModel, ValidationError
from starlette.datastructures import FormData

ModelT = TypeVar("ModelT", bound=BaseModel)

# type pydantic -> gabarit français, avec les placeholders nommés de ctx
# (ex. {min_length}, {ge}) — jamais un texte anglais reparsé pour en
# extraire un nombre, voir docstring du module.
_FR_BY_TYPE: dict[str, str] = {
    "missing": "Champ requis.",
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
    "none_required": "Doit être vide.",
    "date_type": "Doit être une date valide.",
    "date_parsing": "Doit être une date valide.",
    "datetime_type": "Doit être une date et heure valides.",
    "datetime_parsing": "Doit être une date et heure valides.",
    "string_too_short": "Doit contenir au moins {min_length} caractères.",
    "string_too_long": "Doit contenir au plus {max_length} caractères.",
    "string_pattern_mismatch": "Ne correspond pas au format attendu.",
    "string_ascii": "Ne doit contenir que des caractères ASCII.",
    "greater_than": "Doit être supérieur à {gt}.",
    "greater_than_equal": "Doit être supérieur ou égal à {ge}.",
    "less_than": "Doit être inférieur à {lt}.",
    "less_than_equal": "Doit être inférieur ou égal à {le}.",
    "multiple_of": "Doit être un multiple de {multiple_of}.",
    "extra_forbidden": "Champ non attendu.",
}

_VALUE_ERROR_PREFIX = "Value error, "


def _translate_one(err: Mapping[str, Any]) -> str:
    msg = str(err.get("msg", ""))
    error_type = err.get("type")
    if error_type == "value_error" and msg.startswith(_VALUE_ERROR_PREFIX):
        # Le détail après le préfixe vient de la bibliothèque appelante
        # (un field_validator, email-validator via EmailStr...) — pas
        # traduit ici, voir "Limite connue" dans la docstring du module.
        return "Erreur : " + msg[len(_VALUE_ERROR_PREFIX):]
    template = _FR_BY_TYPE.get(str(error_type))
    if template is None:
        return msg
    try:
        return template.format(**(err.get("ctx") or {}))
    except (KeyError, IndexError):
        # ctx n'a pas la clé attendue par le gabarit (changement interne
        # de pydantic non répercuté ici) — dégrade sur l'anglais plutôt
        # que de lever, même principe que le reste du module.
        return msg


class FormResult(Generic[ModelT]):
    def __init__(self, data: ModelT | None, errors: dict[str, str], values: dict[str, str]) -> None:
        self.data = data
        self.errors = errors
        self.values = values

    @property
    def ok(self) -> bool:
        return self.data is not None

    @property
    def has_errors(self) -> bool:
        return bool(self.errors)


def parse_form(form: FormData, model: type[ModelT], *, translate: bool = True) -> FormResult[ModelT]:
    """Valide les champs d'un FormData Starlette contre un modèle Pydantic.

    Toujours des chaînes en entrée (un <form> HTML n'envoie que du
    texte) — Pydantic se charge de la coercition et du message d'erreur
    par champ en cas d'échec.

    `translate=True` par défaut (français, langue source du projet, voir
    CLAUDE.md) — `translate=False` garde le texte brut de pydantic (anglais).
    """
    values = {k: v for k, v in form.items() if isinstance(v, str)}
    try:
        return FormResult(data=model(**values), errors={}, values=values)
    except ValidationError as exc:
        errors: dict[str, str] = {}
        for err in exc.errors():
            field = ".".join(str(p) for p in err["loc"]) or "__root__"
            errors[field] = _translate_one(err) if translate else str(err["msg"])
        return FormResult(data=None, errors=errors, values=values)
