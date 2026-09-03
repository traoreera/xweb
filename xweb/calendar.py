"""Grille mensuelle pour xweb.calendar/xweb.datepicker (docs/components.md).

QWeb n'a aucun builtin dans ses expressions (`eval(expr, {"__builtins__":
{}}, ctx)`, xweb/engine/compiler.py) — ni `datetime`, ni `calendar`, ni de
quoi faire de l'arithmétique de dates. La grille (semaines × jours, lundi
en premier) DOIT donc être calculée côté vue Python et passée déjà prête,
même convention que `_fmt_dt` ailleurs dans ce projet (CLAUDE.md : "les
calculs viennent déjà faits de la vue Python").
"""

from __future__ import annotations

import calendar as _calendar
from datetime import date

_MONTH_NAMES_FR = [
    "janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre",
]


def month_grid(year: int, month: int, *, today: date | None = None, selected: str | None = None) -> dict:
    """Grille de semaines prête pour xweb.calendar :

        {"month_label": "Septembre 2026",
         "weeks": [[{"day": 31, "iso": "2026-08-31", "in_month": False,
                      "is_today": False, "is_selected": False}, ...], ...]}

    Semaines complètes (7 jours), lundi en premier — les jours du mois
    précédent/suivant qui complètent la première/dernière semaine ont
    `in_month=False` (affichés grisés côté template, jamais masqués :
    une grille à trous casserait l'alignement des colonnes).

    `today`/`selected` hors du mois affiché ne lèvent jamais d'exception —
    les jours concernés ont simplement `is_today`/`is_selected` à False.
    `selected` est une date ISO ("YYYY-MM-DD") pour rester comparable
    directement à `cell['iso']`, jamais un objet `date` (ce que le
    formulaire/la query string transportent déjà sous cette forme)."""
    today = today or date.today()
    cal = _calendar.Calendar(firstweekday=0)  # 0 = lundi
    weeks = []
    for week in cal.monthdatescalendar(year, month):
        row = []
        for d in week:
            iso = d.isoformat()
            row.append({
                "day": d.day,
                "iso": iso,
                "in_month": d.month == month,
                "is_today": d == today,
                "is_selected": selected is not None and iso == selected,
            })
        weeks.append(row)
    return {"month_label": f"{_MONTH_NAMES_FR[month - 1].capitalize()} {year}", "weeks": weeks}
