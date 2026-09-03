"""Phase 2 validation (xweb Blueprint §7, docs/inheritance.md) — the
actual reason xweb exists (xweb Blueprint §0): a plugin extends a
template it doesn't own, without forking it. Each test traces to a
specific claim in docs/inheritance.md.
"""

import logging

import pytest

from xweb.engine.compiler import TemplateError
from xweb.engine.registry import QwebRegistry

BUTTON = """<template t-name="xweb.button">
    <button type="button" class="btn">
        <t t-esc="slot"/>
    </button>
</template>"""


@pytest.fixture
def registry() -> QwebRegistry:
    r = QwebRegistry()
    r.register_source(BUTTON, source_plugin="core")
    return r


# ---------------------------------------------------------------------
# The worked example from docs/inheritance.md — CRM badge on <button>
# ---------------------------------------------------------------------


def test_position_inside_adds_content_without_touching_original(registry):
    registry.register_source(
        """<template t-name="crm_app.button_badge" t-inherit="xweb.button" t-inherit-mode="extension">
            <xpath expr="//button" position="inside">
                <span class="badge badge-accent">CRM</span>
            </xpath>
        </template>""",
        source_plugin="crm_app",
    )
    html = registry.render("xweb.button", {"slot": "Valider"})
    assert "Valider" in html
    assert '<span class="badge badge-accent">CRM</span>' in html
    # the original template on disk is untouched — a second, unpatched
    # registry proves the patch lives only in the registry that loaded it
    fresh = QwebRegistry()
    fresh.register_source(BUTTON)
    assert "badge" not in fresh.render("xweb.button", {"slot": "Valider"})


def test_position_attributes_adds_without_a_conflicting_class(registry):
    registry.register_source(
        """<template t-name="crm_app.button_tag" t-inherit="xweb.button">
            <xpath expr="//button" position="attributes">
                <attribute name="data-crm">1</attribute>
            </xpath>
        </template>"""
    )
    html = registry.render("xweb.button", {"slot": "x"})
    assert 'data-crm="1"' in html
    assert 'class="btn"' in html  # original attribute survives untouched


def test_position_before_and_after(registry):
    registry.register_source(
        """<template t-name="p.before" t-inherit="xweb.button">
            <xpath expr="//button" position="before"><span id="lead">L</span></xpath>
        </template>"""
    )
    registry.register_source(
        """<template t-name="p.after" t-inherit="xweb.button">
            <xpath expr="//button" position="after"><span id="trail">T</span></xpath>
        </template>"""
    )
    html = registry.render("xweb.button", {"slot": "x"})
    assert html.index('id="lead"') < html.index("<button") < html.index('id="trail"')


def test_position_replace_swaps_the_node(registry):
    registry.register_source(
        """<template t-name="p.replace" t-inherit="xweb.button">
            <xpath expr="//button" position="replace"><a class="btn" t-esc="slot"/></xpath>
        </template>"""
    )
    html = registry.render("xweb.button", {"slot": "Voir"})
    assert "<a " in html
    assert "<button" not in html


def test_multiple_matches_all_patched(registry):
    r = QwebRegistry()
    r.register_source(
        """<template t-name="test.two"><div><button class="btn"/><button class="btn"/></div></template>"""
    )
    r.register_source(
        """<template t-name="p.all" t-inherit="test.two">
            <xpath expr="//button" position="attributes"><attribute name="data-x">1</attribute></xpath>
        </template>"""
    )
    html = r.render("test.two", {})
    assert html.count('data-x="1"') == 2


# ---------------------------------------------------------------------
# Priority ordering (docs/inheritance.md#résolution)
# ---------------------------------------------------------------------


def test_lower_priority_number_applies_first(registry):
    """Both insert 'inside' at the end — applied in priority order means
    the lower-numbered one's content ends up closer to the original
    node, the higher-numbered one's content lands after it."""
    registry.register_source(
        """<template t-name="p.late" t-inherit="xweb.button" priority="10">
            <xpath expr="//button" position="inside"><span id="late">late</span></xpath>
        </template>"""
    )
    registry.register_source(
        """<template t-name="p.early" t-inherit="xweb.button" priority="1">
            <xpath expr="//button" position="inside"><span id="early">early</span></xpath>
        </template>"""
    )
    html = registry.render("xweb.button", {"slot": "x"})
    assert html.index('id="early"') < html.index('id="late"')


def test_conflict_on_replace_keeps_lowest_priority_and_warns(registry, caplog):
    registry.register_source(
        """<template t-name="p.b" t-inherit="xweb.button" priority="20">
            <xpath expr="//button" position="replace"><a id="loser" t-esc="slot"/></xpath>
        </template>""",
        source_plugin="plugin_b",
    )
    registry.register_source(
        """<template t-name="p.a" t-inherit="xweb.button" priority="5">
            <xpath expr="//button" position="replace"><a id="winner" t-esc="slot"/></xpath>
        </template>""",
        source_plugin="plugin_a",
    )
    with caplog.at_level(logging.WARNING):
        html = registry.render("xweb.button", {"slot": "x"})
    assert 'id="winner"' in html
    assert 'id="loser"' not in html
    assert any("conflict" in r.message for r in caplog.records)
    assert any("plugin_a" in r.message and "plugin_b" in r.message for r in caplog.records)


def test_non_conflicting_ops_on_same_patch_still_apply_when_one_loses(registry, caplog):
    """A patch that both replaces (loses the conflict) AND does an
    unrelated attributes op must still get the attributes op applied —
    losing a conflict drops only that one op, not the whole patch
    (docs/inheritance.md#conflits: "ignorée pour ce nœud précis")."""
    registry.register_source(
        """<template t-name="p.winner" t-inherit="xweb.button" priority="1">
            <xpath expr="//button" position="replace"><a t-esc="slot"/></xpath>
        </template>"""
    )
    registry.register_source(
        """<template t-name="p.loser" t-inherit="xweb.button" priority="9">
            <xpath expr="//button" position="replace"><a id="ignored" t-esc="slot"/></xpath>
            <xpath expr="//a" position="attributes"><attribute name="data-still-applied">1</attribute></xpath>
        </template>"""
    )
    with caplog.at_level(logging.WARNING):
        html = registry.render("xweb.button", {"slot": "x"})
    assert 'id="ignored"' not in html
    assert 'data-still-applied="1"' in html  # the <a> from p.winner is still there for p.loser's second op to target


# ---------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------


def test_xpath_matching_nothing_raises(registry):
    registry.register_source(
        """<template t-name="p.bad" t-inherit="xweb.button">
            <xpath expr="//nonexistent" position="inside"><span>x</span></xpath>
        </template>"""
    )
    with pytest.raises(TemplateError, match="matched no node"):
        registry.render("xweb.button", {"slot": "x"})


def test_unsupported_inherit_mode_raises(registry):
    """"primary" est un mode connu depuis docs/inheritance.md#primary
    (voir la section plus bas) — seul un mode vraiment inconnu doit
    encore lever ici."""
    with pytest.raises(TemplateError, match="t-inherit-mode"):
        registry.register_source(
            """<template t-name="p.bogus" t-inherit="xweb.button" t-inherit-mode="bogus">
                <xpath expr="//button" position="inside"><span/></xpath>
            </template>"""
        )


def test_replace_on_template_root_raises():
    """/template (not //button) — the node with no parent is the
    <template> element itself, not its child <button> (which has
    <template> as a perfectly ordinary parent)."""
    r = QwebRegistry()
    r.register_source('<template t-name="test.root"><button class="btn"/></template>')
    r.register_source(
        """<template t-name="p.root" t-inherit="test.root">
            <xpath expr="/template" position="replace"><a/></xpath>
        </template>"""
    )
    with pytest.raises(TemplateError, match="template root"):
        r.render("test.root", {})


# ---------------------------------------------------------------------
# Cache invalidation (docs/inheritance.md, xweb Blueprint §5 — the
# three-tier diagram's whole point: registering a new patch must be
# visible on the next render, not stuck behind a stale cached tree)
# ---------------------------------------------------------------------


def test_check_all_surfaces_conflicts_without_any_render_call(registry, caplog):
    """Décidé : jamais d'exception sur un conflit xpath (docs/inheritance.md#conflits)
    — un position="replace" en désaccord entre deux plugins ne doit jamais
    500 toutes les pages qui utilisent xweb.button. check_all() est le
    filet qui reste : les conflits sortent au boot (XwebExtension.init()),
    pas seulement quand une page les déclenche par hasard."""
    registry.register_source(
        """<template t-name="p.b" t-inherit="xweb.button" priority="20">
            <xpath expr="//button" position="replace"><a id="loser" t-esc="slot"/></xpath>
        </template>""",
        source_plugin="plugin_b",
    )
    registry.register_source(
        """<template t-name="p.a" t-inherit="xweb.button" priority="5">
            <xpath expr="//button" position="replace"><a id="winner" t-esc="slot"/></xpath>
        </template>""",
        source_plugin="plugin_a",
    )
    with caplog.at_level(logging.WARNING):
        registry.check_all()  # PAS render() — c'est tout le point du test
    assert any("conflict" in r.message for r in caplog.records)


def test_unregister_plugin_removes_its_own_templates_and_its_patches_elsewhere():
    """Trouvé en câblant le hot-reload (docs/spec-v1.md §3, shell.xml
    Phase 4) : source_plugin n'était tracé QUE pour les patches, jamais
    pour les templates de base — un plugin déchargé aurait laissé ses
    propres templates orphelins dans le registre indéfiniment."""
    r = QwebRegistry()
    r.register_source(BUTTON, source_plugin="core")
    r.register_source(
        '<template t-name="crm_app.contacts_list"><div>contacts</div></template>',
        source_plugin="crm_app",
    )
    r.register_source(
        """<template t-name="crm_app.button_badge" t-inherit="xweb.button">
            <xpath expr="//button" position="inside"><span>CRM</span></xpath>
        </template>""",
        source_plugin="crm_app",
    )
    assert r.render("crm_app.contacts_list", {}) is not None
    assert "CRM" in r.render("xweb.button", {"slot": "x"})

    r.unregister_plugin("crm_app")

    assert r.get("crm_app.contacts_list") is None  # son propre template — retiré
    assert "CRM" not in r.render("xweb.button", {"slot": "x"})  # son patch sur xweb.button — retiré aussi
    assert r.render("xweb.button", {"slot": "x"}) is not None  # xweb.button lui-même (owner="core") — intact


def test_registering_a_patch_after_first_render_invalidates_cache(registry):
    first = registry.render("xweb.button", {"slot": "x"})
    assert "badge" not in first
    version_before = registry.version

    registry.register_source(
        """<template t-name="p.late_badge" t-inherit="xweb.button">
            <xpath expr="//button" position="inside"><span class="badge">new</span></xpath>
        </template>"""
    )
    assert registry.version > version_before

    second = registry.render("xweb.button", {"slot": "x"})
    assert "badge" in second


# ---------------------------------------------------------------------
# t-inherit-mode="primary" — docs/inheritance.md#primary : duplication
# complète sous le NOM DU PATCH, la cible reste intacte pour tout le
# monde d'autre.
# ---------------------------------------------------------------------


def test_primary_duplicates_under_its_own_name_leaving_the_target_untouched(registry):
    registry.register_source(
        """<template t-name="crm_app.custom_button" t-inherit="xweb.button" t-inherit-mode="primary">
            <xpath expr="//button" position="inside"><span class="badge">CRM</span></xpath>
        </template>""",
        source_plugin="crm_app",
    )
    duplicate = registry.render("crm_app.custom_button", {"slot": "x"})
    original = registry.render("xweb.button", {"slot": "x"})
    assert "CRM" in duplicate
    assert "CRM" not in original  # la cible n'est jamais patchée en place, contrairement à extension


def test_primary_is_callable_via_t_call_like_any_other_template(registry):
    registry.register_source(
        """<template t-name="crm_app.custom_button" t-inherit="xweb.button" t-inherit-mode="primary">
            <xpath expr="//button" position="inside"><span class="badge">CRM</span></xpath>
        </template>""",
        source_plugin="crm_app",
    )
    registry.register_source(
        """<template t-name="crm_app.page">
            <div><t t-call="crm_app.custom_button">Nouveau</t></div>
        </template>"""
    )
    html = registry.render("crm_app.page", {})
    assert "CRM" in html and "Nouveau" in html


def test_primary_chain_each_link_independent_of_the_next(registry):
    """A (base) -> B (primary de A) -> C (primary de B) : chaque duplication
    n'affecte que sa propre copie, jamais les autres."""
    r = QwebRegistry()
    r.register_source('<template t-name="a"><div>A</div></template>')
    r.register_source('<template t-name="b" t-inherit="a" t-inherit-mode="primary"><xpath expr="//div" position="inside"><span>B</span></xpath></template>')
    r.register_source('<template t-name="c" t-inherit="b" t-inherit-mode="primary"><xpath expr="//div" position="inside"><span>C</span></xpath></template>')
    assert r.render("a", {}) == "<div>A</div>"
    assert r.render("b", {}) == "<div>A<span>B</span></div>"
    assert r.render("c", {}) == "<div>A<span>B</span><span>C</span></div>"


def test_extension_mode_patch_can_further_extend_a_primary_duplicate(registry):
    """Une fois matérialisé (première résolution), un template primary-mode
    n'est plus distingué d'un vrai template de base — un patch extension
    normal peut le cibler."""
    registry.register_source(
        """<template t-name="crm_app.custom_button" t-inherit="xweb.button" t-inherit-mode="primary">
            <xpath expr="//button" position="inside"><span class="badge">CRM</span></xpath>
        </template>""",
        source_plugin="crm_app",
    )
    registry.register_source(
        """<template t-name="crm_app.custom_button_ext" t-inherit="crm_app.custom_button" t-inherit-mode="extension">
            <xpath expr="//button" position="attributes"><attribute name="data-extra">1</attribute></xpath>
        </template>""",
        source_plugin="ext_plugin",
    )
    html = registry.render("crm_app.custom_button", {"slot": "x"})
    assert "CRM" in html
    assert 'data-extra="1"' in html
    assert "data-extra" not in registry.render("xweb.button", {"slot": "x"})  # jamais remonté à la cible d'origine


def test_primary_targeting_a_missing_template_raises_a_clear_error(registry):
    registry.register_source(
        """<template t-name="crm_app.orphan" t-inherit="does.not.exist" t-inherit-mode="primary">
            <xpath expr="//x" position="inside"><span/></xpath>
        </template>"""
    )
    with pytest.raises(TemplateError, match="does.not.exist"):
        registry.render("crm_app.orphan", {})


def test_primary_without_any_xpath_is_a_pure_copy():
    r = QwebRegistry()
    r.register_source('<template t-name="a"><div class="x">hello</div></template>')
    r.register_source('<template t-name="b" t-inherit="a" t-inherit-mode="primary"></template>')
    assert r.render("b", {}) == r.render("a", {})


def test_unregister_plugin_removes_a_primary_template_even_if_never_resolved(registry):
    """Un template primary-mode jamais rendu ne vit encore que dans un
    dict interne séparé (pas encore matérialisé en vrai template) —
    unregister_plugin() ne doit pas planter dessus (pas de KeyError)."""
    registry.register_source(
        """<template t-name="crm_app.custom_button" t-inherit="xweb.button" t-inherit-mode="primary">
            <xpath expr="//button" position="inside"><span>CRM</span></xpath>
        </template>""",
        source_plugin="crm_app",
    )
    registry.unregister_plugin("crm_app")  # ne doit pas lever
    assert registry.get("crm_app.custom_button") is None


def test_unregister_plugin_removes_a_primary_template_after_it_was_resolved(registry):
    registry.register_source(
        """<template t-name="crm_app.custom_button" t-inherit="xweb.button" t-inherit-mode="primary">
            <xpath expr="//button" position="inside"><span>CRM</span></xpath>
        </template>""",
        source_plugin="crm_app",
    )
    assert registry.render("crm_app.custom_button", {"slot": "x"}) is not None  # matérialisé
    registry.unregister_plugin("crm_app")
    assert registry.get("crm_app.custom_button") is None
    assert registry.render("xweb.button", {"slot": "x"}) is not None  # la cible d'origine, elle, jamais touchée


def test_check_all_resolves_primary_templates_eagerly_at_boot():
    """docs/inheritance.md#conflits — même philosophie que les conflits
    XPath extension-mode : une cible introuvable pour un patch primary-mode
    doit remonter au boot (check_all(), engine/integration/xcore.py::
    XwebExtension.init()), pas seulement à la première page qui le rend."""
    r = QwebRegistry()
    r.register_source('<template t-name="crm_app.orphan" t-inherit="does.not.exist" t-inherit-mode="primary"></template>')
    with pytest.raises(TemplateError, match="does.not.exist"):
        r.check_all()


def test_len_counts_a_primary_template_once_materialized(registry):
    before = len(registry)
    registry.register_source(
        """<template t-name="crm_app.custom_button" t-inherit="xweb.button" t-inherit-mode="primary">
            <xpath expr="//button" position="inside"><span>CRM</span></xpath>
        </template>""",
        source_plugin="crm_app",
    )
    registry.check_all()
    assert len(registry) == before + 1
