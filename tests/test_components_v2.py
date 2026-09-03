"""Composants ajoutés avec le shell reconstruit (docs/components.md) —
formulaires, navigation, retours. Chaque test vérifie un comportement
qu'un appelant (plugins/account, le shell) utilise réellement.
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


# ── icon ────────────────────────────────────────────────────────────────


def test_icon_renders_inline_svg_without_namespace_prefix(registry):
    html = registry.render("xweb.icon", {"name": "users", "extra_class": "size-4"})
    assert html.strip().startswith("<svg viewBox=")
    assert "{http://www.w3.org/2000/svg}" not in html
    assert 'class="shrink-0 size-4"' in html
    assert 'stroke-width="1.5"' in html


def test_icon_unknown_name_falls_back_to_question_mark_never_raises(registry):
    known = registry.render("xweb.icon", {"name": "question"})
    unknown = registry.render("xweb.icon", {"name": "does-not-exist"})
    assert 'd="' in unknown
    assert unknown == known


def test_icon_brand_logos_are_filled_not_stroked_and_distinct_per_provider(registry):
    # fill_paths (login.xml, boutons "Continuer avec X") — un groupe séparé
    # de paths : silhouette pleine (fill=currentColor), pas un tracé
    # Heroicons outline (fill=none, stroke=currentColor).
    google = registry.render("xweb.icon", {"name": "google", "extra_class": "size-4"})
    github = registry.render("xweb.icon", {"name": "github", "extra_class": "size-4"})
    assert 'fill="currentColor"' in google and 'fill="currentColor"' in github
    assert "stroke=" not in google and "stroke=" not in github
    assert google != github  # deux logos réellement distincts, pas le même tracé générique


def test_icon_unknown_oauth_provider_still_falls_back_to_question_mark(registry):
    # login.xml passe le nom du provider tel quel (t-att-name="provider") —
    # un provider futur non répertorié dans fill_paths/paths ne doit jamais
    # planter le rendu de la page de connexion.
    fallback = registry.render("xweb.icon", {"name": "some-future-oauth-provider"})
    assert 'd="' in fallback
    assert "fill=\"currentColor\"" not in fallback  # retombe sur le groupe outline, pas fill


# ── avatar / breadcrumbs / tabs / menu / dropdown ───────────────────────


def test_avatar_placeholder_with_initial_and_sizes(registry):
    html = registry.render("xweb.avatar", {"initial": "A", "size": "xs"})
    assert "avatar avatar-placeholder" in html and "w-6" in html and ">A<" in html
    with_img = registry.render("xweb.avatar", {"src": "/p.png", "alt": "Ada"})
    assert "avatar-placeholder" not in with_img and '<img src="/p.png" alt="Ada" />' in with_img


def test_breadcrumbs_last_item_is_not_a_link(registry):
    html = registry.render("xweb.breadcrumbs", {"items": [{"label": "Accueil", "href": "/"}, {"label": "Ici", "href": "/ici"}]})
    assert 'href="/"' in html
    assert 'href="/ici"' not in html and "Ici" in html


def test_tabs_active_from_flag_or_current_path(registry):
    items = [{"label": "A", "href": "/a"}, {"label": "B", "href": "/b"}]
    html = registry.render("xweb.tabs", {"items": items, "current_path": "/b"})
    assert html.count("tab-active") == 1 and 'href="/b" class="tab gap-2 tab-active"' in html
    html2 = registry.render("xweb.tabs", {"items": [{"label": "A", "href": "/a", "active": True}]})
    assert "tab-active" in html2


def test_menu_marks_active_and_renders_badge_and_slot(registry):
    html = registry.render("xweb.menu", {
        "items": [{"label": "A", "href": "/a", "badge": "3", "icon": "home"}, {"label": "B", "href": "/b"}],
        "current_path": "/a", "title": "Section", "slot": Markup("<li><a href='/extra'>Extra</a></li>"),
    })
    assert "menu-title" in html and "Section" in html
    assert 'href="/a" class="flex items-center gap-2 menu-active"' in html
    assert "badge" in html and ">3<" in html
    assert "/extra" in html


def test_dropdown_default_button_or_custom_trigger(registry):
    html = registry.render("xweb.dropdown", {"label": "Actions", "slot": Markup("<li><a>x</a></li>")})
    assert 'role="button" class="btn btn-sm gap-1"' in html and "Actions" in html
    custom = registry.render("xweb.dropdown", {"trigger": Markup("<b>T</b>"), "slot": Markup("")})
    assert "<b>T</b>" in custom and "btn btn-sm" not in custom


# ── modal / tooltip / kbd / divider / stat / empty / error_page ─────────


def test_modal_uses_native_dialog_and_unboosted_close_forms(registry):
    html = registry.render("xweb.modal", {"id": "m1", "title": "Titre", "slot": Markup("<p>corps</p>")})
    assert '<dialog id="m1" class="modal ">' in html
    assert html.count('<form method="dialog" hx-boost="false"') == 2
    assert "modal-backdrop" in html and "<p>corps</p>" in html
    trigger = registry.render("xweb.modal_trigger", {"target": "m1", "slot": "Ouvrir"})
    assert '_="on click call #m1.showModal()"' in trigger


def test_tooltip_kbd_divider(registry):
    assert 'data-tip="Aide"' in registry.render("xweb.tooltip", {"text": "Aide", "slot": "x", "position": "bottom"})
    assert "kbd kbd-xs" in registry.render("xweb.kbd", {"slot": "K", "size": "xs"})
    assert "divider divider-horizontal" in registry.render("xweb.divider", {"vertical": True})


def test_stat_and_empty_state(registry):
    html = registry.render("xweb.stat", {"title": "Utilisateurs", "value": "42", "desc": "+3", "icon": "users"})
    assert "stat-title" in html and "stat-value" in html and ">42<" in html and "stat-figure" in html
    empty = registry.render("xweb.empty", {"title": "Rien", "message": "Vide", "slot": Markup("<a>Créer</a>")})
    assert "Rien" in empty and "Vide" in empty and "<a>Créer</a>" in empty


def test_error_page_shows_code_message_and_home_link(registry):
    html = registry.render("xweb.error_page", {"code": "403", "message": "Rôle requis : admin", "home_path": "/home"})
    assert ">403<" in html and "Rôle requis : admin" in html and 'href="/home"' in html


# ── formulaires ─────────────────────────────────────────────────────────


def test_csrf_and_form_inject_hidden_token(registry):
    assert '<input type="hidden" name="csrf_token" value="abc" />' in registry.render("xweb.csrf", {"token": "abc"})
    form = registry.render("xweb.form", {"action": "/x", "token": "abc", "slot": Markup("<button/>")})
    assert 'method="post" action="/x"' in form and 'value="abc"' in form and "hx-boost" not in form
    get_form = registry.render("xweb.form", {"action": "/s", "method": "get", "token": "abc"})
    assert "csrf_token" not in get_form


def test_form_boost_false_from_string_or_bool(registry):
    for boost in ("false", False, "0"):
        assert 'hx-boost="false"' in registry.render("xweb.form", {"boost": boost, "token": "t"})


def test_field_shows_error_over_help_and_required_star(registry):
    html = registry.render("xweb.field", {"label": "Email", "for_": "email", "required": True, "error": "Requis", "help": "aide", "slot": Markup("<input/>")})
    assert 'for="email"' in html and "Requis" in html and "aide" not in html and "text-error" in html
    html2 = registry.render("xweb.field", {"label": "Email", "help": "aide", "slot": Markup("<input/>")})
    assert "aide" in html2 and 'role="alert"' not in html2


def test_input_new_attributes_and_invalid_state(registry):
    html = registry.render("xweb.input", {"name": "email", "id": "email", "required": True, "autofocus": True, "autocomplete": "email", "invalid": True, "minlength": 3})
    assert 'id="email"' in html and 'required="required"' in html and 'autofocus="autofocus"' in html
    assert 'autocomplete="email"' in html and 'minlength="3"' in html and "input-error" in html
    plain = registry.render("xweb.input", {"name": "x"})
    assert "input-error" not in plain and "autocomplete" not in plain


def test_password_field_toggles_visibility_with_hyperscript(registry):
    html = registry.render("xweb.password", {"name": "pw"})
    assert 'type="password" id="pw" name="pw"' in html
    assert "on click if #pw&#39;s type is &#39;password&#39; set #pw&#39;s type to &#39;text&#39;" in html
    assert 'autocomplete="current-password"' in html
    html2 = registry.render("xweb.password", {"name": "new", "autocomplete": "new-password", "minlength": 8})
    assert 'autocomplete="new-password"' in html2 and 'minlength="8"' in html2


def test_select_accepts_dicts_or_tuples_and_marks_selected(registry):
    html = registry.render("xweb.select", {"name": "s", "options": [{"value": "a", "label": "A"}, ("b", "B")], "value": "b", "placeholder": "Choisir"})
    assert '<option value="" disabled="disabled">Choisir</option>' in html
    assert '<option value="a">A</option>' in html
    assert '<option value="b" selected="selected">B</option>' in html
    none_selected = registry.render("xweb.select", {"options": [("a", "A")], "placeholder": "Choisir"})
    assert 'disabled="disabled" selected="selected"' in none_selected


def test_textarea_escapes_value_and_radio_toggle_range(registry):
    ta = registry.render("xweb.textarea", {"name": "t", "value": "<b>x</b>", "rows": 2})
    assert "&lt;b&gt;x&lt;/b&gt;</textarea>" in ta and 'rows="2"' in ta
    radio = registry.render("xweb.radio", {"name": "r", "value": "1", "label": "Un", "checked": True})
    assert 'type="radio" name="r" value="1" checked="checked"' in radio and "Un" in radio
    toggle = registry.render("xweb.toggle", {"name": "t", "label": "On", "color": "success"})
    assert 'type="checkbox" name="t" value="on"' in toggle and "toggle toggle-success" in toggle
    rng = registry.render("xweb.range", {"value": 3, "max": 10})
    assert 'type="range" min="0" max="10" step="1" value="3"' in rng


def test_progress_indeterminate_without_value(registry):
    assert "value=" not in registry.render("xweb.progress", {})
    assert 'value="40"' in registry.render("xweb.progress", {"value": 40})


# ── retours ─────────────────────────────────────────────────────────────


def test_toast_auto_dismiss_unless_timeout_zero(registry):
    html = registry.render("xweb.toast", {"variant": "success", "slot": "Fait", "timeout": 3})
    assert "alert alert-success" in html and '_="init wait 3s then remove me"' in html
    sticky = registry.render("xweb.toast", {"slot": "x", "timeout": 0})
    assert "init wait" not in sticky and "remove closest .alert" in sticky
    oob = registry.render("xweb.toasts_oob", {"slot": Markup("<div>t</div>")})
    assert 'id="xweb-toasts" hx-swap-oob="beforeend"' in oob


def test_table_auto_rows_custom_body_and_empty_state(registry):
    cols = [{"key": "a", "label": "A"}, {"key": "b", "label": "B", "class": "text-right"}]
    html = registry.render("xweb.table", {"columns": cols, "rows": [{"a": "x1", "b": 2}], "zebra": True})
    assert "table-zebra" in html and "<th>A</th>" in html and '<th class="text-right">B</th>' in html
    assert "x1" in html and '<td class="text-right">2</td>' in html
    custom = registry.render("xweb.table", {"columns": cols, "slot": Markup("<tr><td>custom</td></tr>")})
    assert "custom" in custom and "x1" not in custom
    empty = registry.render("xweb.table", {"columns": cols, "empty": "Rien ici"})
    assert 'colspan="99"' in empty and "Rien ici" in empty


def test_theme_toggle_persists_choice_in_localstorage(registry):
    html = registry.render("xweb.theme_toggle", {})
    assert 'id="theme-btn"' in html
    assert "localStorage.setItem(&#39;theme&#39;" in html
    assert "theme-light-only" in html and "theme-dark-only" in html
