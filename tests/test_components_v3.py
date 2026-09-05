"""Composants ajoutés pour compléter le catalogue DaisyUI (docs/components.md
"Au-delà du catalogue xui") — steps, timeline, file_input, indicator,
skeleton, rating. Chacun testé en isolation (rendu, dégradation), même
découpage que test_components_v2.py.
"""

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


# ── xweb.steps ───────────────────────────────────────────────────────────


def test_steps_renders_one_li_per_item(registry):
    html = registry.render("xweb.steps", {"items": [{"label": "Compte"}, {"label": "Équipe"}, {"label": "Fini"}]})
    assert html.count('class="step ') + html.count('class="step step-primary') == 3
    assert "Compte" in html and "Équipe" in html and "Fini" in html


def test_steps_marks_primary_up_to_and_including_current_only(registry):
    html = registry.render("xweb.steps", {
        "items": [{"label": "A"}, {"label": "B"}, {"label": "C"}], "current": 1,
    })
    steps = [s for s in html.split("<li") if s.strip()]
    assert "step-primary" in steps[1] and "step-primary" in steps[2]  # A, B
    assert "step-primary" not in steps[3]  # C — après <li> ajouté par split, index décalé de 1


def test_steps_default_current_marks_nothing_primary(registry):
    html = registry.render("xweb.steps", {"items": [{"label": "A"}, {"label": "B"}]})
    assert "step-primary" not in html


def test_steps_vertical_flag_swaps_the_orientation_class(registry):
    html = registry.render("xweb.steps", {"items": [{"label": "A"}], "vertical": True})
    assert "steps-vertical" in html
    assert "steps-horizontal" not in html


def test_steps_description_is_optional_and_escaped(registry):
    html = registry.render("xweb.steps", {"items": [{"label": "A", "description": "<script>x</script>"}]})
    assert "<script>x</script>" not in html
    assert "&lt;script&gt;" in html


# ── xweb.timeline ────────────────────────────────────────────────────────


def test_timeline_renders_label_description_and_date(registry):
    html = registry.render("xweb.timeline", {"items": [
        {"label": "Créé", "description": "Par Ada", "date": "Hier"},
    ]})
    assert "Créé" in html and "Par Ada" in html and "Hier" in html


def test_timeline_first_item_has_no_leading_hr_last_has_no_trailing_hr(registry):
    """Convention DaisyUI : chaque <li> pose son propre <hr/> de chaque
    côté (CSS les fait fusionner visuellement en un seul trait continu) —
    3 items -> 4 <hr/> au total (1 + 2 + 1), jamais un avant le tout
    premier <li> ni un après le tout dernier."""
    html = registry.render("xweb.timeline", {"items": [{"label": "A"}, {"label": "B"}, {"label": "C"}]})
    first_li = html.split("<li>")[1]
    assert "<hr" not in first_li.split("<div")[0]  # rien avant timeline-middle du tout premier <li>
    assert html.count("<hr") == 4


def test_timeline_single_item_has_no_hr_at_all(registry):
    html = registry.render("xweb.timeline", {"items": [{"label": "Seul"}]})
    assert "<hr" not in html


def test_timeline_default_icon_is_check_circle(registry):
    html = registry.render("xweb.timeline", {"items": [{"label": "A"}]})
    # check_circle a un tracé distinctif — vérifié via le fragment de path SVG
    assert "M9 12.75 11.25 15 15 9.75" in html


def test_timeline_custom_icon_overrides_the_default(registry):
    html = registry.render("xweb.timeline", {"items": [{"label": "A", "icon": "warning"}]})
    assert "M12 9v3.75m-9.303 3.376" in html  # tracé de l'icône "warning"


def test_timeline_empty_items_renders_no_crash(registry):
    html = registry.render("xweb.timeline", {"items": []})
    assert "<ul" in html
    assert "<li" not in html


# ── xweb.file_input ──────────────────────────────────────────────────────


def test_file_input_renders_name_and_accept(registry):
    html = registry.render("xweb.file_input", {"name": "avatar", "accept": "image/*"})
    assert 'name="avatar"' in html
    assert 'accept="image/*"' in html
    assert 'type="file"' in html


def test_file_input_multiple_flag(registry):
    html = registry.render("xweb.file_input", {"name": "docs", "multiple": True})
    assert "multiple" in html


def test_file_input_invalid_adds_error_class(registry):
    html = registry.render("xweb.file_input", {"name": "x", "invalid": True})
    assert "file-input-error" in html


def test_file_input_no_accept_omits_the_attribute(registry):
    html = registry.render("xweb.file_input", {"name": "x"})
    assert "accept" not in html


# ── xweb.indicator ───────────────────────────────────────────────────────


def test_indicator_without_badge_renders_only_the_main_slot(registry):
    html = registry.render("xweb.indicator", {"slot": Markup('<button class="btn">Msg</button>')})
    assert "indicator-item" not in html
    assert '<button class="btn">Msg</button>' in html


def test_indicator_with_badge_renders_it_positioned(registry):
    html = registry.render("xweb.indicator", {
        "slot": Markup('<button class="btn">Msg</button>'),
        "slot_badge": Markup('<span class="badge badge-primary badge-xs"></span>'),
    })
    assert "indicator-item indicator-top indicator-end" in html
    assert "badge-primary" in html


def test_indicator_custom_position(registry):
    html = registry.render("xweb.indicator", {
        "slot": Markup("<div/>"), "slot_badge": Markup("<span/>"), "v": "bottom", "h": "start",
    })
    assert "indicator-bottom indicator-start" in html


# ── xweb.skeleton ────────────────────────────────────────────────────────


def test_skeleton_default_renders_full_width_bar(registry):
    html = registry.render("xweb.skeleton", {})
    assert "skeleton" in html and "w-full" in html and "h-4" in html


def test_skeleton_circle_adds_rounded_full(registry):
    html = registry.render("xweb.skeleton", {"circle": True, "width": "w-10", "height": "h-10"})
    assert "rounded-full" in html
    assert "w-10" in html and "h-10" in html


def test_skeleton_not_circle_omits_rounded_full(registry):
    html = registry.render("xweb.skeleton", {})
    assert "rounded-full" not in html


# ── xweb.rating ──────────────────────────────────────────────────────────


def test_rating_renders_max_visible_stars_plus_hidden_reset(registry):
    html = registry.render("xweb.rating", {"name": "r1", "max": 5})
    assert html.count("mask-star-2") == 5
    assert "rating-hidden" in html


def test_rating_checks_exactly_the_value_star(registry):
    html = registry.render("xweb.rating", {"name": "r1", "value": 3, "max": 5})
    assert html.count('checked="checked"') == 1
    stars = html.split("mask-star-2")
    assert "checked" in stars[3] and "3 étoiles" in stars[3]
    assert "checked" not in stars[2] and "checked" not in stars[4]


def test_rating_value_zero_checks_nothing(registry):
    html = registry.render("xweb.rating", {"name": "r1", "value": 0})
    assert 'checked="checked"' not in html


def test_rating_readonly_disables_every_input(registry):
    html = registry.render("xweb.rating", {"name": "r1", "value": 2, "readonly": True})
    assert html.count('disabled="disabled"') == 6  # 5 étoiles + le radio caché de reset
    not_readonly = registry.render("xweb.rating", {"name": "r1", "value": 2})
    assert "disabled" not in not_readonly


def test_rating_aria_label_singular_vs_plural(registry):
    html = registry.render("xweb.rating", {"name": "r1", "max": 2})
    assert 'aria-label="1 étoile"' in html
    assert 'aria-label="2 étoiles"' in html


def test_rating_custom_max(registry):
    html = registry.render("xweb.rating", {"name": "r1", "max": 10})
    assert html.count("mask-star-2") == 10
