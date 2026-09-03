"""xweb/engine/filters.py — set fermé de filtres de valeur (docs/language.md
#filtres). Rendu réel via QwebRegistry (pas d'appel direct à apply_filters)
pour couvrir aussi le branchement dans compiler.py::_eval — c'est là qu'un
vrai bug est apparu en écrivant ces tests (voir
test_default_filter_recovers_a_genuinely_undefined_name ci-dessous)."""

from __future__ import annotations

from pathlib import Path

import pytest

from xweb.engine.registry import QwebRegistry


@pytest.fixture
def registry(tmp_path: Path) -> QwebRegistry:
    (tmp_path / "t.xml").write_text(
        """<templates>
<template t-name="t.money"><t t-esc="v | money"/></template>
<template t-name="t.number"><t t-esc="v | number"/></template>
<template t-name="t.percent"><t t-esc="v | percent"/></template>
<template t-name="t.upper"><t t-esc="v | upper"/></template>
<template t-name="t.truncate"><t t-esc="v | truncate:5"/></template>
<template t-name="t.slug"><t t-esc="v | slug"/></template>
<template t-name="t.length"><t t-esc="v | length"/></template>
<template t-name="t.join"><t t-esc="v | join:', '"/></template>
<template t-name="t.join_attr"><t t-esc="v | join:', ',name"/></template>
<template t-name="t.default"><t t-esc="v | default:'N/A'"/></template>
<template t-name="t.default_present"><t t-esc="v | default:'N/A'"/></template>
<template t-name="t.default_zero"><t t-esc="v | default_if_empty:'N/A'"/></template>
<template t-name="t.yesno"><t t-esc="v | yesno"/></template>
<template t-name="t.since"><t t-esc="v | since"/></template>
<template t-name="t.chain"><t t-esc="v | upper | truncate:5"/></template>
<template t-name="t.bitwise"><t t-esc="a | b"/></template>
<template t-name="t.unknown_filter"><t t-esc="v | not_a_real_filter"/></template>
<template t-name="t.no_pipe"><t t-esc="v"/></template>
</templates>""",
        encoding="utf-8",
    )
    r = QwebRegistry()
    r.register_dir(tmp_path)
    return r


def test_money_formats_french_locale(registry):
    assert registry.render("t.money", {"v": 1234.5}) == "1 234,50 €"


def test_number_formats_french_locale(registry):
    assert registry.render("t.number", {"v": 1234.5}) == "1 234,50"


def test_percent_formats_ratio(registry):
    assert registry.render("t.percent", {"v": 0.125}) == "12,5 %"


def test_upper_uppercases(registry):
    assert registry.render("t.upper", {"v": "bonjour"}) == "BONJOUR"


def test_truncate_cuts_and_marks_with_ellipsis(registry):
    assert registry.render("t.truncate", {"v": "bonjour le monde"}) == "bonj…"


def test_truncate_leaves_short_strings_untouched(registry):
    assert registry.render("t.truncate", {"v": "hi"}) == "hi"


def test_slug_strips_accents_and_punctuation(registry):
    assert registry.render("t.slug", {"v": "Café à Paris !"}) == "cafe-a-paris"


def test_length_of_a_list(registry):
    assert registry.render("t.length", {"v": [1, 2, 3]}) == "3"


def test_length_of_none_is_zero_not_an_error(registry):
    assert registry.render("t.length", {"v": None}) == "0"


def test_join_default_separator(registry):
    assert registry.render("t.join", {"v": ["a", "b", "c"]}) == "a, b, c"


def test_join_with_attribute_on_dict_items(registry):
    items = [{"name": "Ada"}, {"name": "Grace"}]
    assert registry.render("t.join_attr", {"v": items}) == "Ada, Grace"


def test_default_filter_returns_fallback_for_falsy_present_value(registry):
    assert registry.render("t.default", {"v": ""}) == "N/A"
    assert registry.render("t.default", {"v": None}) == "N/A"


def test_default_filter_passes_through_a_real_value(registry):
    assert registry.render("t.default_present", {"v": "hello"}) == "hello"


def test_default_if_empty_keeps_zero_and_false(registry):
    assert registry.render("t.default_zero", {"v": 0}) == "0"
    assert registry.render("t.default_zero", {"v": False}) == "False"
    assert registry.render("t.default_zero", {"v": None}) == "N/A"


def test_yesno_maps_truthy_falsy_and_empty(registry):
    assert registry.render("t.yesno", {"v": True}) == "Oui"
    assert registry.render("t.yesno", {"v": False}) == "Non"
    assert registry.render("t.yesno", {"v": ""}) == "—"


def test_since_recent_timestamp_reads_as_just_now():
    import datetime as dt

    from xweb.engine.filters import _since

    now = dt.datetime(2026, 9, 3, 12, 0, 0, tzinfo=dt.timezone.utc)
    recent = now - dt.timedelta(seconds=5)
    assert _since(recent, now) == "à l'instant"
    assert _since(now - dt.timedelta(hours=3), now) == "il y a 3 h"


def test_filters_chain_left_to_right(registry):
    assert registry.render("t.chain", {"v": "bonjour le monde"}) == "BONJ…"


def test_pipe_without_a_known_filter_name_stays_a_python_bitwise_or(registry):
    # split_filters() ne coupe QUE sur un nom reconnu (FILTER_NAMES) — "a | b"
    # avec b absent de ce set doit rester l'opérateur Python normal.
    assert registry.render("t.bitwise", {"a": 5, "b": 2}) == "7"


def test_unrecognized_filter_name_never_raises(registry):
    # "v | not_a_real_filter" : not_a_real_filter n'est pas dans
    # FILTER_NAMES (le set fermé), donc split_filters() ne le traite même
    # pas comme un filtre — l'expression retombe sur eval() Python normal
    # ("v | not_a_real_filter" = OR bitwise avec un nom non défini), qui
    # lève NameError, récupéré comme n'importe quel nom absent du contexte
    # (falsy, jamais un crash) — pas le chemin apply_filters()/_FILTERS,
    # qui ne sert que si un nom DANS FILTER_NAMES manquait par erreur dans
    # le dict _FILTERS (garde-fou de maintenance, pas une faute de frappe
    # d'auteur de template).
    assert registry.render("t.unknown_filter", {"v": "hello"}) == ""


def test_plain_expression_without_any_pipe_is_unaffected(registry):
    assert registry.render("t.no_pipe", {"v": "hello"}) == "hello"


def test_default_filter_recovers_a_genuinely_undefined_name(registry):
    # Régression réelle trouvée en écrivant ces tests : _eval()
    # (xweb/engine/compiler.py) attrapait NameError et renvoyait None
    # directement, AVANT même de regarder s'il y avait une chaîne de
    # filtres à appliquer — "missing | default:'N/A'" rendait donc vide
    # au lieu de "N/A", pour le cas d'usage même que ce filtre existe pour
    # couvrir (une variable de contexte absente, pas juste falsy).
    assert registry.render("t.default", {}) == "N/A"


def test_yesno_recovers_a_genuinely_undefined_name_as_the_empty_branch(registry):
    assert registry.render("t.yesno", {}) == "—"


def test_apply_filters_defensive_branch_for_a_name_missing_from_the_dict(monkeypatch):
    # Le garde-fou réel de apply_filters() (xweb/engine/filters.py) : un nom
    # PRÉSENT dans FILTER_NAMES mais absent de _FILTERS (dérive de
    # maintenance entre les deux) ne doit jamais lever, juste laisser la
    # valeur inchangée — testé directement, ce cas n'est pas atteignable
    # depuis un template tant que les deux structures restent synchronisées.
    from xweb.engine import filters as filters_mod

    monkeypatch.setitem(filters_mod._FILTERS, "upper", None)
    value, consumed = filters_mod.apply_filters("v | upper", {}, "hello")
    assert consumed is True
    assert value == "hello"
