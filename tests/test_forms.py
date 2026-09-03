from pydantic import BaseModel, Field, field_validator
from starlette.datastructures import FormData

from xweb.forms import parse_form


class ContactForm(BaseModel):
    name: str
    email: str

    @field_validator("email")
    @classmethod
    def email_must_contain_at(cls, v: str) -> str:
        if "@" not in v:
            raise ValueError("adresse email invalide")
        return v


def test_parse_form_valid_returns_data_and_ok_true():
    form = FormData([("name", "Ada"), ("email", "ada@example.com")])
    result = parse_form(form, ContactForm)
    assert result.ok is True
    assert result.data.name == "Ada"
    assert result.errors == {}


def test_parse_form_invalid_returns_errors_and_preserves_submitted_values():
    """docs/forms.py's whole reason to exist: a 422 JSON is useless for a
    page that needs to re-render with field errors AND keep what the user
    typed — values must survive even when validation fails."""
    form = FormData([("name", "Ada"), ("email", "not-an-email")])
    result = parse_form(form, ContactForm)
    assert result.ok is False
    assert result.data is None
    assert "email" in result.errors
    assert result.values == {"name": "Ada", "email": "not-an-email"}


def test_parse_form_missing_field_reports_it():
    form = FormData([("name", "Ada")])
    result = parse_form(form, ContactForm)
    assert result.ok is False
    assert "email" in result.errors


# ── Traduction des messages (type pydantic -> français, xweb/forms.py) ──────


def test_missing_field_message_is_translated_to_french_by_default():
    form = FormData([("name", "Ada")])
    result = parse_form(form, ContactForm)
    assert result.errors["email"] == "Champ requis."


def test_value_error_from_a_field_validator_keeps_its_own_text_with_a_french_prefix():
    """field_validator lève déjà un texte en français ici (adresse email
    invalide) — seul le préfixe pydantic ("Value error, ") est traduit,
    le détail vient de l'appelant, voir la docstring de xweb/forms.py."""
    form = FormData([("name", "Ada"), ("email", "pas-un-email")])
    result = parse_form(form, ContactForm)
    assert result.errors["email"] == "Erreur : adresse email invalide"


def test_translate_false_keeps_pydantics_raw_english_text():
    form = FormData([("name", "Ada")])
    result = parse_form(form, ContactForm, translate=False)
    assert result.errors["email"] == "Field required"


class BoundedForm(BaseModel):
    age: int = Field(ge=18)
    bio: str = Field(min_length=3)


def test_ctx_values_are_interpolated_into_the_french_template_not_reparsed_from_english_text():
    """Régression : une bibliothèque essayée puis retirée (pydantic-i18n)
    confondait "greater than {}" et "greater than or equal to {}" en
    reparsant le texte anglais, produisant un message mi-anglais
    mi-français. ctx (déjà structuré par pydantic) élimine ce risque."""
    form = FormData([("age", "5"), ("bio", "x")])
    result = parse_form(form, BoundedForm)
    assert result.errors["age"] == "Doit être supérieur ou égal à 18."
    assert "or equal to" not in result.errors["age"]
    assert result.errors["bio"] == "Doit contenir au moins 3 caractères."


def test_int_parsing_error_is_translated():
    form = FormData([("age", "pas-un-nombre"), ("bio", "une bio suffisamment longue")])
    result = parse_form(form, BoundedForm)
    assert result.errors["age"] == "Doit être un nombre entier valide."


def test_unmapped_error_type_falls_back_to_english_never_raises():
    """Un type pydantic non couvert par _FR_BY_TYPE (ex. contrainte
    inhabituelle) dégrade sur le texte anglais — même principe que
    xweb/i18n.py::Catalog, jamais une exception pour une seule clé
    manquante."""
    from xweb.forms import _translate_one

    assert _translate_one({"type": "some_future_pydantic_type", "msg": "Some new message"}) == "Some new message"
    assert _translate_one({"type": None, "msg": "No type at all"}) == "No type at all"
