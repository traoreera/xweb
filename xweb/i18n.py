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
    (source_locale exclu — cette locale n'a besoin d'aucun fichier, `_()`
    y est l'identité). Un fichier manquant ou invalide dégrade en
    catalogue vide (log un warning) plutôt que d'empêcher le boot pour
    une seule locale mal formée.

    `source_locale` (défaut `SOURCE_LOCALE`, "fr") — configurable depuis
    `services.extensions.xweb.config.source_locale` (`integration.yaml`) :
    avant ce paramètre, "fr" était une CONSTANTE de module utilisée
    partout dans cette classe, pas "la locale considérée comme source du
    projet" au sens configurable malgré son nom — un projet dont le texte
    source des templates est dans une autre langue n'avait aucun moyen de
    faire jouer ce rôle d'identité à sa propre langue
    (know/features/configurable-source-locale.md). Rétrocompatible : ne
    rien passer garde le comportement d'origine, toujours "fr"."""

    def __init__(self, locales_dir: Path | str | None, locales: list[str], *, source_locale: str = SOURCE_LOCALE) -> None:
        self.source_locale = source_locale
        if source_locale in locales:
            # Filtrage silencieux avant ce correctif — un projet qui croit
            # avoir configuré locales: [fr, en] pour une vraie traduction
            # française n'aurait jamais eu de fr.json chargé, sans le
            # savoir (know/features/configurable-source-locale.md).
            logger.warning(
                "i18n: source_locale '%s' est aussi listée dans locales — ignorée pour le chargement "
                "de catalogue (aucun fichier n'est jamais chargé pour la locale source), "
                "probablement une configuration involontaire", source_locale,
            )
        self.available: list[str] = [source_locale, *[loc for loc in locales if loc != source_locale]]
        self._tables: dict[str, dict[str, str]] = {}
        if not locales_dir:
            return
        directory = Path(locales_dir)
        for code in self.available:
            if code == source_locale:
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
    navigateur > catalog.source_locale. Ne retourne jamais un code absent
    de catalog.available — un choix invalide ou une locale sans catalogue
    retombe sur la locale source plutôt que de planter ou d'afficher du
    texte non traduit à moitié. Le repli final lit catalog.source_locale
    (configurable), jamais la constante de module SOURCE_LOCALE en dur —
    sinon un projet à source_locale="en" retomberait quand même sur "fr"
    ici (know/features/configurable-source-locale.md)."""
    requested = request.query_params.get(LOCALE_QUERY_PARAM) or request.cookies.get(LOCALE_COOKIE)
    if requested and requested in catalog.available:
        return requested

    accept_language = request.headers.get("accept-language", "")
    for part in accept_language.split(","):
        code = part.split(";")[0].strip().split("-")[0].lower()
        if code in catalog.available:
            return code

    return catalog.source_locale
