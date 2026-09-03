"""docs/shell.md — ContributionRegistry généralise xui/nav.py."""

import pytest

from xweb.contrib import Contribution, ContributionRegistry, NavRegistry


def test_register_and_list():
    r = ContributionRegistry()
    r.register(Contribution(id="crm.ribbon", plugin="crm_app", label="CRM"))
    assert [c.id for c in r.list()] == ["crm.ribbon"]


def test_duplicate_id_raises_naming_the_owning_plugin():
    r = ContributionRegistry()
    r.register(Contribution(id="x", plugin="plugin_a"))
    with pytest.raises(ValueError, match="plugin_a"):
        r.register(Contribution(id="x", plugin="plugin_b"))


def test_unregister_plugin_removes_only_its_own_contributions():
    r = ContributionRegistry()
    r.register(Contribution(id="a", plugin="plugin_a"))
    r.register(Contribution(id="b", plugin="plugin_b"))
    r.unregister_plugin("plugin_a")
    assert [c.id for c in r.list()] == ["b"]


def test_list_sorted_by_order_then_label():
    r = ContributionRegistry()
    r.register(Contribution(id="z", plugin="p", label="Zebra", order=10))
    r.register(Contribution(id="a", plugin="p", label="Apple", order=10))
    r.register(Contribution(id="first", plugin="p", label="Xxx", order=1))
    assert [c.id for c in r.list()] == ["first", "a", "z"]


def test_list_filters_by_permission():
    r = ContributionRegistry()
    r.register(Contribution(id="public", plugin="p"))
    r.register(Contribution(id="admin_only", plugin="p", permission="admin"))
    assert [c.id for c in r.list({"user"})] == ["public"]
    assert set(c.id for c in r.list({"admin", "user"})) == {"public", "admin_only"}


def test_permission_equal_to_authenticated_constant_filters_like_any_other_string():
    """AUTHENTICATED (xweb/contrib.py) n'est pas un mécanisme à part —
    juste une valeur de permission comme une autre, injectée dans
    user_roles par xweb/mount.py::_base_render_context() pour tout
    utilisateur connecté (voir tests/test_mount.py pour cette partie-là).
    Ici : le registre ne sait rien de spécial sur cette valeur."""
    from xweb.contrib import AUTHENTICATED

    r = ContributionRegistry()
    r.register(Contribution(id="public", plugin="p"))
    r.register(Contribution(id="logged_in_only", plugin="p", permission=AUTHENTICATED))
    assert [c.id for c in r.list(set())] == ["public"]  # anonyme (docs/shell.md)
    assert set(c.id for c in r.list({AUTHENTICATED})) == {"public", "logged_in_only"}


def test_list_with_user_roles_none_means_no_filtering_at_all():
    """Cohérent avec docs/plugins.md — mount_xweb_page appelle toujours
    avec des rôles résolus, mais un appel direct (CLI, script) sans rôles
    ne doit pas tout masquer par accident."""
    r = ContributionRegistry()
    r.register(Contribution(id="admin_only", plugin="p", permission="admin"))
    assert [c.id for c in r.list(None)] == ["admin_only"]


# ---------------------------------------------------------------------
# NavRegistry.tree()
# ---------------------------------------------------------------------


def test_tree_builds_parent_child_hierarchy():
    r = NavRegistry()
    r.register(Contribution(id="crm", plugin="crm_app", label="CRM", path="/crm", order=1))
    r.register(Contribution(id="crm.contacts", plugin="crm_app", label="Contacts", parent_id="crm", path="/crm/contacts"))
    tree = r.tree()
    assert len(tree) == 1
    assert tree[0]["id"] == "crm"
    assert tree[0]["children"][0]["id"] == "crm.contacts"


def test_tree_orphaned_parent_id_promotes_child_to_root():
    """Divergence délibérée par rapport à xui/nav.py : l'original laisse
    un enfant invisible si son parent est filtré par permission (le
    parent_id existe toujours dans self._nodes, mais never atteint par
    build() puisque le parent lui-même n'a jamais été émis). Ici, un
    parent_id qui ne pointe vers rien de VISIBLE promeut l'enfant à la
    racine plutôt que de le faire disparaître silencieusement — un
    élément de nav ne doit jamais s'évanouir juste parce que sa
    catégorie parente n'est pas visible pour cet utilisateur."""
    r = NavRegistry()
    r.register(Contribution(id="orphan", plugin="p", label="Orphelin", parent_id="does-not-exist"))
    tree = r.tree()
    assert [n["id"] for n in tree] == ["orphan"]


def test_tree_parent_filtered_by_permission_promotes_child():
    r = NavRegistry()
    r.register(Contribution(id="admin_section", plugin="p", label="Admin", permission="admin"))
    r.register(Contribution(id="child", plugin="p", label="Toujours visible", parent_id="admin_section"))
    tree = r.tree({"user"})  # pas le rôle admin
    assert [n["id"] for n in tree] == ["child"]  # promu à la racine, pas invisible


def test_tree_children_sorted_same_as_siblings():
    r = NavRegistry()
    r.register(Contribution(id="p", plugin="x", label="Parent"))
    r.register(Contribution(id="c2", plugin="x", label="Z", parent_id="p", order=2))
    r.register(Contribution(id="c1", plugin="x", label="A", parent_id="p", order=1))
    tree = r.tree()
    assert [c["id"] for c in tree[0]["children"]] == ["c1", "c2"]


# ---------------------------------------------------------------------
# Ajouts du shell reconstruit — href/title, status bar par côté
# ---------------------------------------------------------------------


def test_contribution_href_prefers_action_url_and_title_falls_back_to_label():
    c = Contribution(id="c", plugin="p", label="Ping", path="/p", action_url="/do")
    assert c.href == "/do" and c.title == "Ping"
    d = Contribution(id="d", plugin="p", label="Ruban", path="/r", tooltip="Le ruban")
    assert d.href == "/r" and d.title == "Le ruban"
    assert d.to_dict()["href"] == "/r" and d.to_dict()["title"] == "Le ruban"


def test_status_bar_sides_default_left_unknown_side_never_lost():
    from xweb.contrib import StatusBarRegistry

    r = StatusBarRegistry()
    r.register(Contribution(id="l", plugin="p", label="gauche"))
    r.register(Contribution(id="r", plugin="p", label="droite", side="right"))
    r.register(Contribution(id="typo", plugin="p", label="typo", side="rigth"))
    left, right = r.sides()
    assert [c.id for c in left] == ["l", "typo"]
    assert [c.id for c in right] == ["r"]


def test_len_counts_registered_items():
    r = ContributionRegistry()
    assert len(r) == 0
    r.register(Contribution(id="a", plugin="p"))
    assert len(r) == 1
