"""Filtres noyau pour les expressions de templates (docs/language.md).

SET FERMÉ, délibérément : il n'existe AUCUNE API d'enregistrement de filtre.
Un plugin ne peut ni déclarer ni surcharger un filtre — rien de ce qui est
exécutable ne vient d'un plugin dans le moteur de rendu (docs/spec-v1.md,
principe 2 : les auteurs de templates sont du code de confiance, mais on
réduit quand même le champ d'attaque en gardant le jeu de filtres 100%
appartenant à xweb).

Un filtre est un callable(value, *args, **kwargs) -> valeur transformée.
Il NE produit jamais de Markup : le résultat final passe toujours par
escape() dans t-esc, la frontière de sécurité reste intacte (aucun filtre
ne peut émettre du HTML brut).

Aucun filtre n'accède au contexte/état requête : pure transformation de
valeur, déterministe, sans effet de bord.
"""

from __future__ import annotations

import re
from typing import Any

# Si apply_filters() ne connaît pas le segment après "|", _eval retombe sur
# un eval() Python normal — `a | b` (ou bitwise OR) continue de marcher. Ce
# set est LA liste fermée des noms reconnus comme filtres.
FILTER_NAMES: frozenset[str] = frozenset({
    "since", "date", "datetime", "time",
    "money", "number", "percent",
    "upper", "lower", "title", "capitalize",
    "truncate", "slug",
    "length", "count", "first", "last",
    "join", "default", "d", "default_if_empty", "yesno",
    "urlencode",
})


def _fmt_dt(value: Any) -> str:
    """Formate une valeur date/heure en chaîne lisible ; défensif (None,
    chaîne ISO, datetime déjà parsé) — ne lève jamais."""
    import datetime as _dt

    if value is None:
        return ""
    if isinstance(value, _dt.datetime):
        return value.strftime("%Y-%m-%d %H:%M")
    if isinstance(value, _dt.date):
        return value.strftime("%Y-%m-%d")
    s = str(value).strip()
    if not s:
        return ""
    # Chaîne ISO longue "2026-09-01T09:00:00+00:00" -> "2026-09-01 09:00"
    s2 = s.replace("T", " ")
    if len(s2) >= 16 and s2[4] == "-" and s2[7] == "-":
        return s2[:16]
    return s[:16]


def _since(value: Any, _now: Any = None) -> str:
    """Durée relative ("à l'instant", "il y a 5 min", "il y a 3 h", "il y a
    2 j"…). `_now` injectable pour les tests, sinon heure courante UTC."""
    import datetime as _dt

    if value is None:
        return ""
    if isinstance(value, str):
        try:
            value = _dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return value
    if not isinstance(value, _dt.datetime):
        return str(value)
    now = _now or _dt.datetime.now(_dt.timezone.utc)
    if value.tzinfo is None:
        value = value.replace(tzinfo=_dt.timezone.utc)
        now = now.replace(tzinfo=_dt.timezone.utc)
    delta = now - value
    secs = int(delta.total_seconds())
    if secs < 0:
        return "à l'instant"
    if secs < 60:
        return "à l'instant"
    mins = secs // 60
    if mins < 60:
        return f"il y a {mins} min"
    hours = mins // 60
    if hours < 24:
        return f"il y a {hours} h"
    days = hours // 24
    if days < 30:
        return f"il y a {days} j"
    months = days // 30
    if months < 12:
        return f"il y a {months} mois"
    years = days // 365
    return f"il y a {years} ans"


def _money(value: Any, *args: Any, **kwargs: Any) -> str:
    """Montant monétaire français : "1 234,56 €". Sans dépendance (pas de
    babel) — séparateur de milliers espace, décimale virgule, symbole €."""
    if value is None or value == "":
        return ""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    neg = number < 0
    number = abs(number)
    whole = int(number)
    cents = int(round((number - whole) * 100))
    whole_s = f"{whole:,}".replace(",", " ")
    return f"{'-' if neg else ''}{whole_s},{cents:02d} €"


def _number(value: Any, *args: Any, **kwargs: Any) -> str:
    """Nombre formaté français : "1 234,56"."""
    if value is None or value == "":
        return ""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    whole = int(number)
    cents = int(round((number - whole) * 100))
    whole_s = f"{whole:,}".replace(",", " ")
    if cents == 0 and number == whole:
        return whole_s
    return f"{whole_s},{cents:02d}"


def _percent(value: Any, *args: Any, **kwargs: Any) -> str:
    """Pourcentage : "0.125" -> "12,5 %", "1" -> "100 %"."""
    if value is None or value == "":
        return ""
    try:
        number = float(value) * 100
    except (TypeError, ValueError):
        return str(value)
    if number == int(number):
        return f"{int(number)} %"
    return f"{str(number).replace('.', ',')} %"


def _upper(value: Any, *args: Any, **kwargs: Any) -> str:
    return "" if value is None else str(value).upper()


def _lower(value: Any, *args: Any, **kwargs: Any) -> str:
    return "" if value is None else str(value).lower()


def _title(value: Any, *args: Any, **kwargs: Any) -> str:
    return "" if value is None else str(value).title()


def _capitalize(value: Any, *args: Any, **kwargs: Any) -> str:
    return "" if value is None else str(value).capitalize()


def _truncate(value: Any, *args: Any, **kwargs: Any) -> str:
    """Troncature à n caractères (défaut 80) avec "…" quand il y a coupe."""
    n = int(args[0]) if args else int(kwargs.get("n", 80))
    if value is None:
        return ""
    s = str(value)
    if len(s) <= n:
        return s
    return s[: max(0, n - 1)] + "…"


def _slug(value: Any, *args: Any, **kwargs: Any) -> str:
    """Slug ASCII simple (minuscules, tirets) — sans dépendance externe."""
    import re as _re
    import unicodedata as _ud

    if value is None:
        return ""
    s = str(value)
    s = _ud.normalize("NFKD", s)
    s = s.encode("ascii", "ignore").decode("ascii")
    s = s.lower()
    s = _re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def _length(value: Any, *args: Any, **kwargs: Any) -> int:
    """len() — le builtin est absent de _eval (AGENTS.md)."""
    if value is None:
        return 0
    try:
        return len(value)
    except TypeError:
        return 0


def _first(value: Any, *args: Any, **kwargs: Any) -> Any:
    if value is None:
        return None
    try:
        return value[0]
    except (TypeError, IndexError, KeyError):
        return None


def _last(value: Any, *args: Any, **kwargs: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, list):
        return value[-1] if value else None
    try:
        return value[-1]
    except (TypeError, IndexError, KeyError):
        return None


def _join(value: Any, *args: Any, **kwargs: Any) -> str:
    """join(sep[, attr]) — joint les éléments d'un itérable, éventuellement
    un attribut de chaque élément (join:', '|ro'ems -> "a, b")."""
    sep = str(args[0]) if args else str(kwargs.get("sep", ", "))
    attr = args[1] if len(args) > 1 else kwargs.get("attr")
    if value is None:
        return ""
    items = []
    for item in value:
        if attr is not None and isinstance(item, dict):
            items.append(str(item.get(attr, "")))
        elif attr is not None:
            items.append(str(getattr(item, attr, "")))
        else:
            items.append(str(item))
    return sep.join(items)


def _default(value: Any, *args: Any, **kwargs: Any) -> Any:
    """Valeur de repli quand la valeur est vide (None, "", [], {}, 0)."""
    if value in (None, "", [], {}, 0, False):
        return args[0] if args else kwargs.get("fallback", "")
    return value


def _default_if_empty(value: Any, *args: Any, **kwargs: Any) -> Any:
    """Repli quand None/"" uniquement (0 et False conservés)."""
    if value is None or value == "":
        return args[0] if args else kwargs.get("fallback", "")
    return value


def _yesno(value: Any, *args: Any, **kwargs: Any) -> str:
    """true/falsy/vide -> "Oui"/"Non"/"—" (surmontable par 3 args)."""
    y, n, e = (args + ("Oui", "Non", "—"))[:3] if args else ("Oui", "Non", "—")
    if value is None or value == "":
        return e
    return y if bool(value) else n


def _urlencode(value: Any, *args: Any, **kwargs: Any) -> str:
    import urllib.parse as _up

    if value is None:
        return ""
    return _up.quote_plus(str(value))


# name -> callable. Set fermé : ajouter un filtre = ajouter une entrée ICI,
# jamais via un plugin.
_FILTERS: dict[str, Any] = {
    "since": _since,
    "date": lambda v, *a, **k: _fmt_dt(v),
    "datetime": lambda v, *a, **k: _fmt_dt(v),
    "time": lambda v, *a, **k: _fmt_dt(v).split(" ")[-1] if _fmt_dt(v) else "",
    "money": _money,
    "number": _number,
    "percent": _percent,
    "upper": _upper,
    "lower": _lower,
    "title": _title,
    "capitalize": _capitalize,
    "truncate": _truncate,
    "slug": _slug,
    "length": _length,
    "count": _length,
    "first": _first,
    "last": _last,
    "join": _join,
    "default": _default,
    "d": _default,
    "default_if_empty": _default_if_empty,
    "yesno": _yesno,
    "urlencode": _urlencode,
}


def split_filters(expr: str) -> list[str]:
    """Découpe une expression sur les "|" de premier niveau, mais seulement
    quand le segment suivant est un NOM de filtre connu. Exemple :

        "created_at since"      -> pas de pipe, rien
        "price | money"         -> ["price", "money"]
        "names | join:', '""    -> ["names", "join:', '"]
        "a | b" (bitwise OR)    -> laissé tel quel (b inconnu comme filtre)

    Les pipes entre parenthèses/guillemets/chaînes ne sont jamais traités.
    """
    segs: list[str] = []
    depth = 0
    quote: str | None = None
    esc = False
    current: list[str] = []
    i = 0
    n = len(expr)
    while i < n:
        ch = expr[i]
        if quote is not None:
            current.append(ch)
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == quote:
                quote = None
            i += 1
            continue
        if ch in "\"'":
            quote = ch
            current.append(ch)
            i += 1
            continue
        if ch in "([{":
            depth += 1
            current.append(ch)
            i += 1
            continue
        if ch in ")]}":
            depth -= 1
            current.append(ch)
            i += 1
            continue
        if ch == "|" and depth == 0:
            # regarder le prochain identifiant => nom de filtre ?
            j = i + 1
            while j < n and expr[j] in " \t":
                j += 1
            m = j
            while m < n and (expr[m].isalnum() or expr[m] == "_"):
                m += 1
            candidate = expr[j:m]
            if candidate in FILTER_NAMES:
                segs.append("".join(current).strip())
                current = []
                # on recompose "| name" pour garder la syntaxe du filtre
                current.append("|")
                current.append(expr[j:m])
                i = m
                continue
            # nom de filtre inconnu -> on laisse, c'est un opérateur Python
            current.append(ch)
            i += 1
            continue
        current.append(ch)
        i += 1
    segs.append("".join(current).strip())
    return segs


def apply_filters(expr: str, ctx: dict, base_value: Any) -> tuple[Any, bool]:
    """Applique une chaîne de filtres "| a | b:args" à une valeur déjà évaluée.

    Retourne (value, consumed) — consumed=False si l'expression ne portait
    aucun filtre connu (l'appelant la laisse alors à eval() normal).
    """
    parts = split_filters(expr)
    if len(parts) <= 1:
        return base_value, False

    pipe = re.compile(r"^(\s*)\|(\s*)([A-Za-z_][A-Za-z0-9_]*)(.*)$")
    value = base_value
    consumed = False
    for seg in parts[1:]:
        m = pipe.match(seg)
        if not m or not m.group(3):
            continue
        name = m.group(3)
        fn = _FILTERS.get(name)
        if fn is None:
            # filtre inconnu : on laisse la valeur telle quelle (jamais une
            # erreur — cohérent avec "undefined est falsy, pas un crash")
            consumed = True
            continue
        consumed = True
        remainder = m.group(4) or ""
        args, kwargs = _parse_args(remainder)
        try:
            value = fn(value, *args, **kwargs)
        except Exception:
            # un filtre ne doit jamais faire échouer le rendu d'une page :
            # en cas d'erreur de formatage on renvoie la valeur brute
            value = value
    return value, consumed


def _parse_args(tail: str) -> tuple[list, dict]:
    """Parse la queue d'un filtre `:arg1,arg2,key=val` en littéraux simples
    (tuple pour les positionnels, kwargs pour les nommés). Un seul argument
    sans virgule (join:',', truncate:10) est bien un littéral unique."""
    tail = tail.strip()
    if not tail.startswith(":"):
        return [], {}
    inner = tail[1:]
    # découper les virgules de premier niveau (hors quotes/parenthèses)
    parts = _split_top_commas(inner)
    if not parts:
        return [], {}
    positional: list = []
    kwargs: dict = {}
    for p in parts:
        p = p.strip()
        if "=" in p:
            k, _, v = p.partition("=")
            kwargs[k.strip()] = _safe_literal(v.strip())
        else:
            positional.append(_safe_literal(p))
    return positional, kwargs


def _split_top_commas(text: str) -> list[str]:
    out: list[str] = []
    buf: list[str] = []
    depth = 0
    quote: str | None = None
    esc = False
    for ch in text:
        if quote is not None:
            buf.append(ch)
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == quote:
                quote = None
            continue
        if ch in "\"'":
            quote = ch
            buf.append(ch)
            continue
        if ch in "([{":
            depth += 1
            buf.append(ch)
            continue
        if ch in ")]}":
            depth -= 1
            buf.append(ch)
            continue
        if ch == "," and depth == 0:
            out.append("".join(buf))
            buf = []
            continue
        buf.append(ch)
    if buf:
        out.append("".join(buf))
    return out


def _safe_literal(part: str) -> Any:
    """Évalue un littéral Python simple (str/nombre/bool/None) depuis un
    template de confiance — borné par l'absence de builtins."""
    try:
        return eval(part, {"__builtins__": {}}, {})  # noqa: S307 — littéral d'un template de confiance, sans builtins
    except Exception:
        return part
