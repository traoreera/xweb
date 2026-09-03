"""i18n — traduction des templates (docs/i18n.md, docs/spec-v1.md §5).

Le français est la langue SOURCE de tout le projet (CLAUDE.md — commentaires
et UI en français) : un catalogue ne mappe donc jamais un "code" abstrait
vers un texte, mais littéralement `{"texte source français": "traduction"}`
— convention gettext (msgid = le texte lui-même), pas un système de clés
séparées à maintenir en double.

Deux façons de marquer du texte traduisible dans un template :

    <h1 t-tr="1">Organisation</h1>              -- texte statique (le cas
                                                    courant — voir t-tr,
                                                    engine/compiler.py)
    <t t-esc="_('Bonjour ' + name)"/>            -- valeur composée à
                                                    l'exécution ; `_` est
                                                    injecté dans le contexte
                                                    de rendu (mount.py),
                                                    jamais importé ici par
                                                    le compilateur

`_` réalise toujours un fallback silencieux vers le texte source si la
locale résolue n'a pas d'entrée pour ce texte, ou si la locale demandée
n'existe pas du tout (catalogue absent) — jamais une KeyError qui ferait
planter une page entière parce qu'une seule chaîne n'a pas encore été
traduite. C'est délibéré et symétrique avec le reste de xweb (conflit
XPath, permission→rôle inconnu, icône inconnue…) : un texte non traduit
DOIT rester lisible (en français), pas produire une erreur ou un vide.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Callable

from starlette.requests import Request

logger = logging.getLogger(__name__)

SOURCE_LOCALE = "fr"
LOCALE_COOKIE = "xweb_locale"
LOCALE_QUERY_PARAM = "lang"

Translator = Callable[[str], str]


class Catalog:
    """Charge `<locales_dir>/<code>.json` pour chaque code de `locales`
    (SOURCE_LOCALE exclu — le français n'a besoin d'aucun fichier, `_()`
    y est l'identité). Un fichier manquant ou invalide dégrade en
    catalogue vide (log un warning) plutôt que d'empêcher le boot pour
    une seule locale mal formée."""

    def __init__(self, locales_dir: Path | str | None, locales: list[str]) -> None:
        self.available: list[str] = [SOURCE_LOCALE, *[loc for loc in locales if loc != SOURCE_LOCALE]]
        self._tables: dict[str, dict[str, str]] = {}
        if not locales_dir:
            return
        directory = Path(locales_dir)
        for code in self.available:
            if code == SOURCE_LOCALE:
                continue
            path = directory / f"{code}.json"
            if not path.is_file():
                logger.warning("i18n: catalogue introuvable pour '%s' (%s) — fallback français", code, path)
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(data, dict):
                    raise ValueError("le catalogue doit être un objet JSON plat {source: traduction}")
                # "_comment"/"_xxx" — convention JSON courante pour une note
                # de fichier (locales/en.json) ; aucun texte source français
                # ne commence jamais par "_", donc ignorer ces clés ne perd
                # aucune vraie traduction.
                self._tables[code] = {str(k): str(v) for k, v in data.items() if not str(k).startswith("_")}
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                logger.warning("i18n: catalogue '%s' illisible (%s) — fallback français", code, exc)

    def translator_for(self, locale: str) -> Translator:
        """Fonction de traduction liée à `locale`, prête à poser dans
        ctx["_"]. Toujours un identity-fallback, jamais une exception —
        voir docstring du module."""
        table = self._tables.get(locale)
        if not table:
            return lambda source: source
        return lambda source: table.get(source, source)

    def coverage(self, locale: str) -> tuple[int, int]:
        """(nombre de clés traduites, nombre total de clés du français
        source) — utilisé par `xweb inspect`/health-check pour signaler
        une locale partiellement traduite, jamais pour bloquer quoi que
        ce soit."""
        table = self._tables.get(locale) or {}
        return len(table), len(table)


def resolve_locale(request: Request, catalog: Catalog) -> str:
    """Ordre de résolution : ?lang= explicite > cookie xweb_locale (posé
    par xweb.locale_switcher, symétrique du thème) > Accept-Language du
    navigateur > SOURCE_LOCALE. Ne retourne jamais un code absent de
    catalog.available — un choix invalide ou une locale sans catalogue
    retombe sur le français plutôt que de planter ou d'afficher du texte
    non traduit à moitié."""
    requested = request.query_params.get(LOCALE_QUERY_PARAM) or request.cookies.get(LOCALE_COOKIE)
    if requested and requested in catalog.available:
        return requested

    accept_language = request.headers.get("accept-language", "")
    for part in accept_language.split(","):
        code = part.split(";")[0].strip().split("-")[0].lower()
        if code in catalog.available:
            return code

    return SOURCE_LOCALE
