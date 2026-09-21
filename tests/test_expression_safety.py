"""Securite des expressions de template (`_check_expr_safe`, engine/compiler).

`_eval` execute un `eval` Python reel (builtins retires, contexte = donnees
du render). Ce n'est PAS une sandbox : sans garde, `().__class__.__mro__[1]`
.__subclasses__()` serait un escape Python classique. `_check_expr_safe`
coupe donc au niveau AST tout acces attribut dunder et tout lambda.

Le modele reste: les auteurs de templates sont de confiance -- on ne
vise PAS a rendre le DSL sur pour un utilisateur non fiable, on empecher
Une expression qui TAITE des donnees hostiles (une cle de contexte venue
d'une requete) de recuperer, elle, les classes de l'interpreteur.
"""

import pytest

from xweb.engine.compiler import TemplateError
from xweb.engine.registry import QwebRegistry


def _render_str(expr: str, ctx: dict | None = None) -> str:
    r = QwebRegistry()
    r.register_source(f'<template t-name="test.safe"><t t-esc="{expr}"/></template>')
    return r.render("test.safe", ctx or {}).strip()


def test_dunder_class_alone_is_allowed():
    # __class__ seul est autorisé pour le type-checking (ex: x.__class__.__name__)
    assert _render_str("().__class__.__name__") == "tuple"
    class User:
        role = "admin"
    assert _render_str("user.__class__.__name__", {"user": User()}) == "User"


def test_dangerous_dunder_mro_is_blocked():
    with pytest.raises(TemplateError, match="dunder dangereux"):
        _render_str("().__class__.__mro__")


def test_dangerous_dunder_subclasses_is_blocked():
    with pytest.raises(TemplateError, match="dunder dangereux"):
        _render_str("().__class__.__subclasses__()")


def test_dangerous_dunder_globals_is_blocked():
    with pytest.raises(TemplateError, match="dunder dangereux"):
        _render_str("d.get.__globals__", {"d": {}})


def test_dangerous_dunder_bases_is_blocked():
    with pytest.raises(TemplateError, match="dunder dangereux"):
        _render_str("().__class__.__bases__")


def test_lambda_is_blocked():
    with pytest.raises(TemplateError, match="lambda"):
        _render_str("lambda: 1")


def test_filter_arg_dunder_is_neutralized_not_evaluated():
    """Un dunder DANGEREUX dans un arg de filtre n'est pas exécuté — il devient
    du texte littéral (philosophie défensive de _safe_literal).
    __class__ seul est autorisé, mais __mro__ etc. sont bloqués."""
    # __class__ seul passe (littéral)
    result = _render_str("x | default: (1).__class__", {"x": None})
    # (1).__class__ N'EST PAS évalué (sinon on aurait "1" ou "<class 'int'>"),
    # il reste la chaîne littérale "(1).__class__"
    assert result == "(1).__class__"
    # Par contre un dunder dangereux dans l'arg de filtre devient littéral
    result2 = _render_str("x | default: (1).__class__.__mro__", {"x": None})
    assert result2 == "(1).__class__.__mro__"


def test_subscript_key_named_dunder_stays_allowed():
    # Use single quotes in expression to avoid XML attribute conflict
    assert _render_str("x['__class__']", {"x": {"__class__": "ok"}}) == "ok"


def test_legit_attribute_access_on_object_stays_allowed():
    class User:
        role = "admin"

    assert _render_str("user.role", {"user": User()}) == "admin"


def test_legit_expression_and_filters_unaffected():
    assert _render_str("price + tax", {"price": 2, "tax": 3}) == "5"
    assert _render_str("member['role'] == 'admin'", {"member": {"role": "admin"}}).strip() in ("True", "1")
    assert _render_str("price | money", {"price": 9}) == "9,00 €"


def test_malformed_expression_still_raises_template_error():
    with pytest.raises(TemplateError, match="expression failed"):
        _render_str("price +")
