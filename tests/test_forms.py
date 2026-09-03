from pydantic import BaseModel, field_validator
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
