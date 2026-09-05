"""xweb.box / xweb.stack / xweb.grid / xweb.container — primitifs de
layout génériques, ajoutés pour que le canvas du Studio (docs/studio.md
§1 : "chaque nœud du canvas EST un appel à un composant déjà enregistré")
ait de quoi arranger plusieurs autres composants sur une page — xweb
n'avait jusqu'ici aucun composant de ce genre (vérifié : aucun t-name
container/row/col/grid/stack/box/section avant cet ajout).

Toutes les classes de ces quatre composants sortent de dictionnaires
littéraux (comme xweb.avatar) — un test dédié vérifie que chaque valeur
de sortie possible apparaît bien en texte source du fichier .xml, la
condition exacte qui évite le piège d'interpolation Tailwind
(CLAUDE.md#theming) sans avoir besoin d'un safelist dans xweb/static/xweb.css.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from markupsafe import Markup

from xweb.engine.registry import QwebRegistry

COMPONENTS_DIR = Path(__file__).parent.parent / "xweb" / "components"


@pytest.fixture
def registry() -> QwebRegistry:
    r = QwebRegistry()
    r.register_dir(COMPONENTS_DIR)
    return r


# ── xweb.box ─────────────────────────────────────────────────────────────


def test_box_renders_slot_and_extra_class(registry):
    html = registry.render("xweb.box", {"extra_class": "p-4 bg-base-200", "slot": Markup("<p>x</p>")})
    assert "<p>x</p>" in html
    assert 'class="p-4 bg-base-200"' in html


def test_box_imposes_no_layout_class_of_its_own(registry):
    html = registry.render("xweb.box", {"slot": Markup("x")})
    assert "flex" not in html
    assert "grid" not in html


# ── xweb.stack ───────────────────────────────────────────────────────────


def test_stack_default_is_column_with_medium_gap(registry):
    html = registry.render("xweb.stack", {"slot": Markup("x")})
    assert "flex-col" in html
    assert "gap-4" in html
    assert "flex-row" not in html


def test_stack_row_direction(registry):
    html = registry.render("xweb.stack", {"direction": "row", "slot": Markup("x")})
    assert "flex-row" in html
    assert "flex-col" not in html


@pytest.mark.parametrize(
    "gap,expected",
    [("none", "gap-0"), ("xs", "gap-1"), ("sm", "gap-2"), ("md", "gap-4"), ("lg", "gap-6"), ("xl", "gap-8")],
)
def test_stack_gap_scale(registry, gap, expected):
    html = registry.render("xweb.stack", {"gap": gap, "slot": Markup("x")})
    assert expected in html


@pytest.mark.parametrize(
    "align,expected",
    [
        ("start", "items-start"),
        ("center", "items-center"),
        ("end", "items-end"),
        ("stretch", "items-stretch"),
        ("baseline", "items-baseline"),
    ],
)
def test_stack_align_maps_to_items_class(registry, align, expected):
    html = registry.render("xweb.stack", {"align": align, "slot": Markup("x")})
    assert expected in html


@pytest.mark.parametrize(
    "justify,expected",
    [
        ("start", "justify-start"),
        ("center", "justify-center"),
        ("end", "justify-end"),
        ("between", "justify-between"),
        ("around", "justify-around"),
        ("evenly", "justify-evenly"),
    ],
)
def test_stack_justify_maps_to_justify_class(registry, justify, expected):
    html = registry.render("xweb.stack", {"justify": justify, "slot": Markup("x")})
    assert expected in html


def test_stack_wrap_adds_flex_wrap_only_when_true(registry):
    html = registry.render("xweb.stack", {"wrap": True, "slot": Markup("x")})
    assert "flex-wrap" in html
    html2 = registry.render("xweb.stack", {"slot": Markup("x")})
    assert "flex-wrap" not in html2


def test_stack_renders_slot_content(registry):
    html = registry.render("xweb.stack", {"slot": Markup("<span>A</span><span>B</span>")})
    assert "<span>A</span><span>B</span>" in html


# ── xweb.grid ────────────────────────────────────────────────────────────


def test_grid_default_is_two_columns_medium_gap(registry):
    html = registry.render("xweb.grid", {"slot": Markup("x")})
    assert "grid-cols-2" in html
    assert "gap-4" in html


@pytest.mark.parametrize("cols,expected", [(1, "grid-cols-1"), (3, "grid-cols-3"), (4, "grid-cols-4"), (12, "grid-cols-12")])
def test_grid_cols_scale(registry, cols, expected):
    html = registry.render("xweb.grid", {"cols": cols, "slot": Markup("x")})
    assert expected in html


def test_grid_unknown_cols_falls_back_to_two(registry):
    html = registry.render("xweb.grid", {"cols": 99, "slot": Markup("x")})
    assert "grid-cols-2" in html


def test_grid_renders_slot_content(registry):
    html = registry.render("xweb.grid", {"slot": Markup("<div>1</div><div>2</div>")})
    assert "<div>1</div><div>2</div>" in html


# ── xweb.container ───────────────────────────────────────────────────────


def test_container_default_is_7xl_centered_padded(registry):
    html = registry.render("xweb.container", {"slot": Markup("x")})
    assert "max-w-7xl" in html
    assert "mx-auto" in html
    assert "px-4 sm:px-6 lg:px-8" in html


@pytest.mark.parametrize("width,expected", [("sm", "max-w-sm"), ("md", "max-w-md"), ("full", "max-w-full"), ("none", "max-w-none")])
def test_container_max_width_scale(registry, width, expected):
    html = registry.render("xweb.container", {"max_width": width, "slot": Markup("x")})
    assert expected in html


def test_container_center_false_omits_mx_auto(registry):
    html = registry.render("xweb.container", {"center": False, "slot": Markup("x")})
    assert "mx-auto" not in html


def test_container_padded_false_omits_padding(registry):
    html = registry.render("xweb.container", {"padded": False, "slot": Markup("x")})
    assert "px-4" not in html


# ── Piège Tailwind (CLAUDE.md#theming) — chaque classe produite par un
# dictionnaire littéral doit apparaître en texte SOURCE du fichier, sinon
# elle serait invisible au scanner Tailwind malgré un test de rendu vert.


@pytest.mark.parametrize(
    "filename,classes",
    [
        ("stack.xml", ["flex-row", "flex-col", "gap-0", "gap-1", "gap-2", "gap-4", "gap-6", "gap-8",
                       "items-start", "items-center", "items-end", "items-stretch", "items-baseline",
                       "justify-start", "justify-center", "justify-end", "justify-between", "justify-around", "justify-evenly",
                       "flex-wrap"]),
        ("grid.xml", ["grid-cols-1", "grid-cols-2", "grid-cols-3", "grid-cols-4", "grid-cols-5", "grid-cols-6", "grid-cols-12",
                      "gap-0", "gap-1", "gap-2", "gap-4", "gap-6", "gap-8"]),
        ("container.xml", ["max-w-sm", "max-w-md", "max-w-lg", "max-w-xl", "max-w-2xl", "max-w-3xl", "max-w-4xl",
                           "max-w-5xl", "max-w-6xl", "max-w-7xl", "max-w-full", "max-w-none", "mx-auto",
                           "px-4 sm:px-6 lg:px-8"]),
    ],
)
def test_layout_primitive_classes_are_literal_source_text(filename, classes):
    source = (COMPONENTS_DIR / filename).read_text(encoding="utf-8")
    for cls in classes:
        assert cls in source, f"{cls!r} absent du texte source de {filename} — invisible au scanner Tailwind"
