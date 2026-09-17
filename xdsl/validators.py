"""Moteur de validation déclarative pour les endpoints DSL.

Chaque règle de validation est un objet ``Validator`` qui prend une
valeur et retourne ``True`` si elle est valide, ``False`` sinon. Le
message d'erreur est en français (public cible : développeurs francophones
utilisant xweb).

Usage typique (via le compiler) :
    rules = [Required(), MinLength(3), Email()]
    errors = validate_all("ab", rules)  # → ["Ce champ est obligatoire", "Minimum 3 caractères"]
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------

@dataclass
class ValidationResult:
    """Résultat de la validation d'une valeur."""
    valid: bool
    errors: list[str] = field(default_factory=list)


class Validator:
    """Base abstraite pour toutes les règles de validation."""

    name: str = ""
    message: str = ""

    def check(self, value: Any) -> bool:
        """Retourne True si la valeur passe la règle."""
        raise NotImplementedError

    def __call__(self, value: Any) -> ValidationResult:
        if self.check(value):
            return ValidationResult(valid=True)
        return ValidationResult(valid=False, errors=[self.message])


# ---------------------------------------------------------------------------
# Règles intégrées
# ---------------------------------------------------------------------------

class Required(Validator):
    """Le champ doit être présent et non vide."""
    name = "required"
    message = "Ce champ est obligatoire"

    def check(self, value: Any) -> bool:
        if value is None:
            return False
        if isinstance(value, str) and not value.strip():
            return False
        return True


class MinLength(Validator):
    """Longueur minimale d'une chaîne."""
    name = "min_length"

    def __init__(self, min_len: int) -> None:
        self.min_len = min_len
        self.message = f"Minimum {min_len} caractère{'s' if min_len > 1 else ''}"

    def check(self, value: Any) -> bool:
        if not isinstance(value, str):
            return True  # ne s'applique qu'aux strings
        return len(value) >= self.min_len


class MaxLength(Validator):
    """Longueur maximale d'une chaîne."""
    name = "max_length"

    def __init__(self, max_len: int) -> None:
        self.max_len = max_len
        self.message = f"Maximum {max_len} caractère{'s' if max_len > 1 else ''}"

    def check(self, value: Any) -> bool:
        if not isinstance(value, str):
            return True
        return len(value) <= self.max_len


class MinValue(Validator):
    """Valeur minimale (nombre)."""
    name = "min"

    def __init__(self, min_val: float) -> None:
        self.min_val = min_val
        self.message = f"La valeur minimale est {min_val}"

    def check(self, value: Any) -> bool:
        try:
            return float(value) >= self.min_val
        except (TypeError, ValueError):
            return True


class MaxValue(Validator):
    """Valeur maximale (nombre)."""
    name = "max"

    def __init__(self, max_val: float) -> None:
        self.max_val = max_val
        self.message = f"La valeur maximale est {max_val}"

    def check(self, value: Any) -> bool:
        try:
            return float(value) <= self.max_val
        except (TypeError, ValueError):
            return True


class Email(Validator):
    """Format email valide."""
    name = "email"
    message = "Adresse email invalide"
    _pattern = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")

    def check(self, value: Any) -> bool:
        if not isinstance(value, str):
            return True
        return bool(self._pattern.match(value))


class Pattern(Validator):
    """Expression régulière personnalisée."""
    name = "pattern"

    def __init__(self, regex: str, message: str = "") -> None:
        self.regex = re.compile(regex)
        self.message = message or f"La valeur ne correspond pas au format attendu"

    def check(self, value: Any) -> bool:
        if not isinstance(value, str):
            return True
        return bool(self.regex.match(value))


class In(Validator):
    """La valeur doit être dans une liste de valeurs autorisées."""
    name = "in"

    def __init__(self, allowed: list[str]) -> None:
        self.allowed = allowed
        self.message = f"Valeur invalide — autorisées : {', '.join(allowed)}"

    def check(self, value: Any) -> bool:
        return str(value) in self.allowed


class OneOf(Validator):
    """La valeur doit être l'un des types listés (pour validation type brute)."""
    name = "one_of"

    def __init__(self, types: list[str]) -> None:
        self.types = types
        self.message = f"Type invalide — attendu : {', '.join(types)}"

    def check(self, value: Any) -> bool:
        type_map = {
            "string": str, "int": int, "float": (int, float),
            "bool": bool, "list": list, "dict": dict,
        }
        for t in self.types:
            expected = type_map.get(t)
            if expected and isinstance(value, expected):
                return True
        return False


# ---------------------------------------------------------------------------
# Registre de rules pour le DSL
# ---------------------------------------------------------------------------

# Noms DSL → classe Validator (pour le parser/compiler)
BUILTIN_VALIDATORS: dict[str, type[Validator]] = {
    "required": Required,
    "min_length": MinLength,
    "max_length": MaxLength,
    "min": MinValue,
    "max": MaxValue,
    "email": Email,
    "pattern": Pattern,
    "in": In,
}


def make_validator(name: str, *args: Any) -> Validator:
    """Crée un validator à partir de son nom DSL et de ses arguments.

    Exemples:
        make_validator("required") → Required()
        make_validator("min_length", 3) → MinLength(3)
        make_validator("email") → Email()
    """
    cls = BUILTIN_VALIDATORS.get(name)
    if cls is None:
        raise ValueError(f"Règle de validation inconnue : {name!r}")
    try:
        return cls(*args)
    except TypeError:
        raise ValueError(f"Argument(s) invalide(s) pour la règle {name!r}")


# ---------------------------------------------------------------------------
# API publique
# ---------------------------------------------------------------------------

def validate_all(value: Any, rules: list[Validator]) -> list[str]:
    """Valide une valeur contre une liste de règles.
    Retourne la liste des messages d'erreur (vide si valide)."""
    errors: list[str] = []
    for rule in rules:
        result = rule(value)
        if not result.valid:
            errors.extend(result.errors)
    return errors


def validate_dict(data: dict[str, Any], schema: dict[str, list[Validator]]) -> dict[str, list[str]]:
    """Valide un dict de données contre un schéma de validation.
    Retourne un dict {field: [errors]} — vide si tout est valide."""
    errors: dict[str, list[str]] = {}
    for field_name, rules in schema.items():
        value = data.get(field_name)
        field_errors = validate_all(value, rules)
        if field_errors:
            errors[field_name] = field_errors
    return errors
