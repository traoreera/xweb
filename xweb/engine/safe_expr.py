"""Garde structurelle partagée par les DEUX points d'`eval` des templates.

- `_eval` (`engine/compiler.py`) : évalue l'expression principale d'une
  directive (t-if, t-esc, t-att-*, ...).
- `_safe_literal` (`engine/filters.py`) : évalue les littéraux d'arguments
  de filtre (`| default:expr`, `| join:', '`, ...).

Les deux font un `eval` Python réel (builtins retirés). Ce n'est PAS une
sandbox : `().__class__.__mro__[1].__subclasses__()` est un escape Python
classique. La coupe se fait ici, au niveau AST, AVANT tout eval : tout accès
attribut dont le nom est un dunder DANGEREUX (`__class__`, `__globals__`,
`__mro__`, `__subclasses__`, `__init__`, `__dict__`, `__bases__`,
`__closure__`, `__code__`, `__func__`, `__self__`, `__reduce__`,
`__reduce_ex__`, `__getstate__`, `__setstate__`) et toute lambda sont
refusés — deux formes dont aucun template ou argument de filtre légitime
n'a besoin. Les dunders métadonnées (`__name__`, `__module__`,
`__qualname__`, `__doc__`, `__annotations__`) restent autorisés. L'accès
par sous-script (`x["__class__"]`) reste autorisé : c'est une clé de
DONNÉE, pas une propriété de l'interpréteur.
"""

from __future__ import annotations

import ast

# Attributs dunders DANGEREUX — ceux qui permettent l'escalade de privilèges
# vers l'interpréteur Python (chaîne d'escape classique).
# Les dunders "métadonnées" (__name__, __module__, __qualname__, __doc__,
# __annotations__) et __class__ (nécessaire pour le type-checking légitime
# comme `x.__class__.__name__ == 'str'`) sont autorisés.
# __class__ seul ne suffit pas à l'escape : il faut __mro__ ou __bases__
# + __subclasses__ pour atteindre object et ses sous-classes.
DANGEROUS_DUNDERS = frozenset({
    "__globals__",
    "__mro__",
    "__subclasses__",
    "__init__",
    "__dict__",
    "__bases__",
    "__closure__",
    "__code__",
    "__func__",
    "__self__",
    "__reduce__",
    "__reduce_ex__",
    "__getstate__",
    "__setstate__",
})


def parse_expr_safe(expr: str) -> tuple[ast.AST | None, str | None]:
    """Parse *expr* en mode eval : (arbre, None) si valide, ou
    (None, message d'erreur) si la syntaxe est invalide."""
    try:
        return ast.parse(expr, mode="eval"), None
    except (SyntaxError, ValueError) as exc:
        return None, str(exc)


# Ensemble plus strict pour les littéraux (args de filtre) : bloque aussi
# __class__ car un littéral n'a pas besoin de type-checking
LITERAL_DANGEROUS_DUNDERS = DANGEROUS_DUNDERS | {"__class__"}


def find_unsafe_node(tree: ast.AST, *, strict: bool = False) -> str | None:
    """Retourne la raison (message) d'une violation de sécurité de l'arbre,
    None si l'expression est autorisée.
    
    Si strict=True, utilise LITERAL_DANGEROUS_DUNDERS (bloque aussi __class__)."""
    dangerous = LITERAL_DANGEROUS_DUNDERS if strict else DANGEROUS_DUNDERS
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in dangerous:
            return f"accès à l'attribut dunder dangereux {node.attr!r}"
        if isinstance(node, ast.Lambda):
            return "lambda"
    return None