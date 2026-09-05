"""xweb.notification_bell / xweb.notification_panel / xweb.toast_region /
xweb.notification_toast — xweb/components/notifications.xml
(docs/components.md). L'exemple bout en bout (cloche réelle sur la landing,
état persisté dans landing_data.py, routes /notifications/*) est vérifié en
direct contre un vrai serveur — voir main.py et
scripts/verify-notifications-live.mjs — pas ici : Python n'exécute aucun
htmx/_hyperscript. Ici : uniquement le rendu (props, structure,
dégradation), même découpage que test_kanban.py/test_editable_table.py.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from xweb.engine.registry import QwebRegistry

ROOT = Path(__file__).parent.parent
COMPONENTS_DIR = ROOT / "xweb" / "components"


@pytest.fixture
def registry() -> QwebRegistry:
    r = QwebRegistry()
    r.register_dir(COMPONENTS_DIR)
    return r


NOTIFICATIONS = [
    {"id": "n-1", "title": "Nouveau composant", "message": "xweb.kanban a changé de look.", "level": "info", "read": False, "created_label": "Il y a 5 min"},
    {"id": "n-2", "title": "Export prêt", "level": "success", "read": True},
]


# ── xweb.notification_bell ──────────────────────────────────────────────────


def test_bell_omits_hx_get_when_notifications_url_is_empty(registry):
    html = registry.render("xweb.notification_bell", {"unread_count": 2})
    assert "hx-get" not in html


def test_bell_sets_hx_get_to_notifications_url_when_given(registry):
    html = registry.render("xweb.notification_bell", {"notifications_url": "/n/panel"})
    assert 'hx-get="/n/panel"' in html
    assert 'hx-target="#xweb-notification-panel"' in html


def test_bell_badge_hidden_when_unread_count_is_zero(registry):
    html = registry.render("xweb.notification_bell", {"unread_count": 0})
    assert "bg-primary px-1" not in html


def test_bell_badge_shows_the_exact_count_under_100(registry):
    html = registry.render("xweb.notification_bell", {"unread_count": 7})
    assert re.search(r">\s*7\s*<", html)  # texte du <span>, entouré d'espaces d'indentation
    assert "99+" not in html


def test_bell_badge_caps_at_99_plus(registry):
    html = registry.render("xweb.notification_bell", {"unread_count": 142})
    assert "99+" in html
    assert ">142<" not in html


def test_bell_placeholder_panel_keeps_the_id_the_panel_swap_targets(registry):
    """xweb.notification_panel doit toujours re-rendre le même id — c'est
    ce que hx-target du bouton cloche cible (outerHTML)."""
    html = registry.render("xweb.notification_bell", {})
    assert 'id="xweb-notification-panel"' in html


# ── xweb.notification_panel ─────────────────────────────────────────────────


def test_panel_empty_state_when_no_notifications(registry):
    html = registry.render("xweb.notification_panel", {"notifications": []})
    assert "Tout est à jour" in html
    assert "n-1" not in html


def test_panel_renders_each_notification_title_and_message(registry):
    html = registry.render("xweb.notification_panel", {"notifications": NOTIFICATIONS})
    assert "Nouveau composant" in html and "xweb.kanban a changé de look." in html
    assert "Export prêt" in html


def test_panel_unread_dot_only_on_unread_items(registry):
    html = registry.render("xweb.notification_panel", {"notifications": NOTIFICATIONS})
    # n-1 (read=False) a le point primary ; n-2 (read=True) ne l'a pas —
    # compté globalement, une seule entrée non lue dans le jeu de données.
    assert html.count("size-1.5 shrink-0 rounded-full bg-primary") == 1


def test_panel_mark_all_read_button_needs_both_unread_and_url(registry):
    html_no_url = registry.render("xweb.notification_panel", {"notifications": NOTIFICATIONS, "unread_count": 1})
    assert "Tout lire" not in html_no_url
    html_no_unread = registry.render("xweb.notification_panel", {"notifications": NOTIFICATIONS, "unread_count": 0, "mark_all_read_url": "/x"})
    assert "Tout lire" not in html_no_unread
    html_both = registry.render("xweb.notification_panel", {"notifications": NOTIFICATIONS, "unread_count": 1, "mark_all_read_url": "/x"})
    assert "Tout lire" in html_both
    assert 'hx-post="/x"' in html_both


def test_panel_mark_read_hx_post_only_on_unread_items(registry):
    """mark_read_url + '/' + id seulement si l'item n'est pas déjà lu —
    (mark_read_url and not is_read) else None (xweb/components/
    notifications.xml)."""
    html = registry.render("xweb.notification_panel", {"notifications": NOTIFICATIONS, "mark_read_url": "/n/read"})
    assert 'hx-post="/n/read/n-1"' in html  # non lue
    assert 'hx-post="/n/read/n-2"' not in html  # déjà lue


def test_panel_inbox_link_omitted_when_inbox_url_is_empty(registry):
    html = registry.render("xweb.notification_panel", {"notifications": NOTIFICATIONS})
    assert "Voir toutes les notifications" not in html


def test_panel_inbox_link_present_when_inbox_url_given(registry):
    html = registry.render("xweb.notification_panel", {"notifications": NOTIFICATIONS, "inbox_url": "/inbox"})
    assert 'href="/inbox"' in html


def test_panel_notification_value_is_escaped_never_raw_html(registry):
    rows = [{"id": "n-1", "title": "<script>alert(1)</script>", "read": False}]
    html = registry.render("xweb.notification_panel", {"notifications": rows})
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


# ── xweb.toast_region / xweb.notification_toast ─────────────────────────────


def test_toast_region_renders_the_fixed_container(registry):
    html = registry.render("xweb.toast_region", {})
    assert 'id="xweb-toasts"' in html


def test_notification_toast_renders_title_and_message(registry):
    html = registry.render("xweb.notification_toast", {"title": "Sauvegardé", "message": "Vos changements sont pris en compte."})
    assert "Sauvegardé" in html
    assert "Vos changements sont pris en compte." in html


def test_notification_toast_does_not_collide_with_xweb_toast(registry):
    """Régression : les deux templates coexistaient sous le même t-name
    'xweb.toast' (register_dir écrasait silencieusement l'un des deux selon
    l'ordre alphabétique de scan) — voir tests/test_component_registry.py
    pour la vérification "zéro warning" au niveau du registre entier."""
    bell_html = registry.render("xweb.notification_toast", {"title": "x"})
    slot_html = registry.render("xweb.toast", {"variant": "success"})
    assert "x" in bell_html
    assert 'alert-success' in slot_html
