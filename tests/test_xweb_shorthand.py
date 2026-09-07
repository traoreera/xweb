"""Raccourci <xweb:...> — le sucre syntaxique désucé au parse
(engine/parser.py} vers la forme canonique <t t-call="xweb.<nom>">.

Contrat : le compilateur, le registre, l'héritage et l'export du Studio
ne voient jamais que du t-call ; les deux syntaxes coexistent dans un même
fichier ; un nom invalide, un `slot`/`t-call` réservé, ou une cible absente
du registre est une erreur au parse/enregistrement, jamais un silence.
"""

from pathlib import Path

import pytest

from xweb.engine.compiler import TemplateError
from xweb.engine.parser import TemplateSyntaxError, parse_templates
from xweb.engine.registry import QwebRegistry

COMPONENTS_DIR = Path(__file__).parent.parent / "xweb" / "components"

_XWEB_BUTTON_PAGE = """<template t-name="demo.shorthand_page">
  <xweb:button variant="primary" type="submit">Se connecter</xweb:button>
</template>"""

_XWEB_BUTTON_PAGE_CANONICAL = """<template t-name="demo.canonical_page">
  <t t-call="xweb.button" variant="primary" type="submit">Se connecter</t>
</template>"""


@pytest.fixture
def registry() -> QwebRegistry:
    r = QwebRegistry()
    r.register_dir(COMPONENTS_DIR)
    return r


# ---------------------------------------------------------------------
# Parse — la forme canonique exacte, pas une variante
# ---------------------------------------------------------------------


def test_shorthand_node_becomes_exact_t_call():
    templates = parse_templates(_XWEB_BUTTON_PAGE, filename="short.xml")
    calls = [el for el in templates["demo.shorthand_page"].iter() if el.get("t-call") == "xweb.button"]
    assert len(calls) == 1
    el = calls[0]
    assert el.tag == "t"
    assert el.get("variant") == "primary"
    assert el.get("type") == "submit"
    assert el.text == "Se connecter"


def test_shorthand_nested_shorthand_both_desugared():
    templates = parse_templates(
        """<template t-name="demo.nested">
  <xweb:card>
    <xweb:button>Go</xweb:button>
  </xweb:card>
</template>""",
        filename="nested.xml",
    )
    calls = [el.get("t-call") for el in templates["demo.nested"].iter() if el.get("t-call")]
    assert calls == ["xweb.card", "xweb.button"]


def test_shorthand_dotted_name_is_the_full_t_call_target():
    """Sans point → xweb.<nom> ; avec point → cible complète telle quelle :
    <xweb:auth.login_page> doit produire t-call="auth.login_page", pas
    "xweb.auth.login_page" — le raccourci couvre n'importe quel t-name."""
    templates = parse_templates(
        """<template t-name="demo.page"><xweb:auth.login_page/></template>""",
        filename="dotted.xml",
    )
    calls = [el.get("t-call") for el in templates["demo.page"].iter() if el.get("t-call")]
    assert calls == ["auth.login_page"]


def test_shorthand_explicit_xweb_prefix_dotted_is_honored():
    templates = parse_templates(
        """<template t-name="demo.page"><xweb:xweb.button>ok</xweb:xweb.button></template>""",
        filename="exp.xml",
    )
    calls = [el.get("t-call") for el in templates["demo.page"].iter() if el.get("t-call")]
    assert calls == ["xweb.button"]


def test_shorthand_targets_collected_on_parsed_result():
    templates = parse_templates(
        """<templates>
  <template t-name="demo.a"><xweb:button/></template>
  <template t-name="demo.b"><xweb:input/></template>
</templates>""",
        filename="multi.xml",
    )
    assert sorted(templates.shorthand_targets) == ["xweb.button", "xweb.input"]


# ---------------------------------------------------------------------
# Sigiles des props — miroir exact des trois formes du compilateur
# ---------------------------------------------------------------------


def test_shorthand_equals_sigil_becomes_t_att():
    templates = parse_templates(
        """<template t-name="demo.csrf"><xweb:csrf token="=csrf_token"/></template>""",
        filename="csrf.xml",
    )
    el = templates["demo.csrf"][0]
    assert el.get("t-att-token") == "csrf_token"
    assert el.get("token") is None


def test_shorthand_interpolation_sigil_becomes_t_attf():
    templates = parse_templates(
        """<template t-name="demo.badge"><xweb:badge count="items-{{n}}"/></template>""",
        filename="badge.xml",
    )
    el = templates["demo.badge"][0]
    assert el.get("t-attf-count") == "items-{{n}}"
    assert el.get("count") is None


def test_shorthand_plain_attr_stays_literal():
    templates = parse_templates(
        """<template t-name="demo.btn"><xweb:button extra_class="btn ceci"/></template>""",
        filename="lit.xml",
    )
    el = templates["demo.btn"][0]
    assert el.get("extra_class") == "btn ceci"
    assert el.get("t-att-extra_class") is None
    assert el.get("t-attf-extra_class") is None


def test_shorthand_directives_pass_through_unscathed():
    templates = parse_templates(
        """<template t-name="demo.rows">
  <xweb:row t-foreach="items" t-as="it">
    <span t-esc="it"/>
  </xweb:row>
</template>""",
        filename="rows.xml",
    )
    el = templates["demo.rows"][0]
    assert el.get("t-call") == "xweb.row"
    assert el.get("t-foreach") == "items"
    assert el.get("t-as") == "it"


# ---------------------------------------------------------------------
# Rendu — le raccourci produit EXACTEMENT le HTML canonique
# ---------------------------------------------------------------------


def test_shorthand_renders_identically_to_canonical(registry):
    registry.register_source(_XWEB_BUTTON_PAGE, filename="short.xml")
    registry.register_source(_XWEB_BUTTON_PAGE_CANONICAL, filename="canon.xml")
    html_short = registry.render("demo.shorthand_page")
    html_canonical = registry.render("demo.canonical_page")
    assert html_short == html_canonical
    assert "Se connecter" in html_short


def test_shorthand_render_with_interpolated_prop(registry):
    registry.register_source(
        """<template t-name="demo.badge_page"><xweb:badge color="vert-{{n}}">ok</xweb:badge></template>""",
        filename="b.xml",
    )
    html = registry.render("demo.badge_page", {"n": 3})
    assert "vert-3" in html


def test_shorthand_named_slot_and_default_slot_round_trip(registry):
    registry.register_source(
        """<template t-name="xweb.panel">
  <div class="panel">
    <header t-esc="slot_header or ''"/>
    <div t-out="slot"/>
  </div>
</template>""",
        filename="panel.xml",
    )
    registry.register_source(
        """<template t-name="demo.panel_page">
  <xweb:panel>
    <t t-set-slot="header">Titre</t>Corps
  </xweb:panel>
</template>""",
        filename="page.xml",
    )
    html = registry.render("demo.panel_page")
    assert "Titre" in html
    assert "Corps" in html
    assert "class=\"panel\"" in html


def test_shorthand_foreach_render(registry):
    registry.register_source(
        """<template t-name="xweb.row"><div t-esc="slot"/></template>""",
        filename="row.xml",
    )
    registry.register_source(
        """<template t-name="demo.rows_page">
  <xweb:row t-foreach="items" t-as="it"><span t-esc="it"/></xweb:row>
</template>""",
        filename="rows.xml",
    )
    html = registry.render("demo.rows_page", {"items": ["a", "b", "c"]})
    assert html.count("<div>") == 3
    assert "a" in html and "b" in html and "c" in html


def test_shorthand_dotted_target_renders_non_xweb_template(registry):
    registry.register_source(
        """<template t-name="auth.login_page">
  <form><h1 t-esc="title or 'Connexion'"/><div t-out="slot"/></form>
</template>""",
        filename="auth.xml",
    )
    registry.register_source(
        """<template t-name="demo.using_auth">
  <xweb:auth.login_page title="=page_title">
    <input name="email" type="email"/>
  </xweb:auth.login_page>
</template>""",
        filename="page.xml",
    )
    html = registry.render("demo.using_auth", {"page_title": "Mon entrée"})
    assert "<h1>Mon entrée</h1>" in html
    assert '<input name="email" type="email" />' in html


# ---------------------------------------------------------------------
# Erreurs — jamais un silence, contrairement aux t-* du rendu
# ---------------------------------------------------------------------


def test_unknown_shorthand_target_raises_at_register_time():
    r = QwebRegistry()
    with pytest.raises(TemplateSyntaxError, match="absente"):
        r.register_source(
            """<template t-name="demo.page"><xweb:missing_name/></template>""",
            filename="bad_box.xml",
        )


def test_unknown_shorthand_target_raises_even_if_defined_same_source_but_patch():
    """Un patch extension-mode ne définit pas de template — une cible qui
    n'existe que sous forme de patch ne peut pas être un <xweb:?> valable."""
    r = QwebRegistry()
    r.register_source('<template t-name="base"><div t-esc="slot"/></template>')
    with pytest.raises(TemplateSyntaxError):
        r.register_source(
            """<template t-name="patch" t-inherit="base">
  <some xpath="//div" position="inside"><xweb:almost/></some>
</template>""",
            filename="patch.xml",
        )


def test_same_source_defines_the_target_so_registration_succeeds():
    r = QwebRegistry()
    r.register_source(
        """<templates>
  <template t-name="xweb.row"><div t-esc="slot"/></template>
  <template t-name="demo.page"><xweb:row>hi</xweb:row></template>
</templates>""",
        filename="selfref.xml",
    )
    assert "hi" in r.render("demo.page")


def test_invalid_component_name_raises_at_parse():
    with pytest.raises(TemplateSyntaxError, match="invalide"):
        parse_templates(
            """<template t-name="demo.page"><xweb:a-b/></template>""",
            filename="hyphen.xml",
        )


def test_leading_dot_component_name_raises_at_parse():
    with pytest.raises(TemplateSyntaxError, match="QName"):
        parse_templates(
            """<template t-name="demo.page"><xweb:.foo/></template>""",
            filename="dot.xml",
        )


def test_double_dot_component_name_raises_at_parse():
    with pytest.raises(TemplateSyntaxError, match="invalide"):
        parse_templates(
            """<template t-name="demo.page"><xweb:foo..bar/></template>""",
            filename="doubledot.xml",
        )


def test_reserved_slot_attribute_raises_at_parse():
    with pytest.raises(TemplateSyntaxError, match="r[ée]serv"):
        parse_templates(
            """<template t-name="demo.page"><xweb:card slot="x"/></template>""",
            filename="slot.xml",
        )


def test_forbidden_t_call_attribute_raises_at_parse():
    with pytest.raises(TemplateSyntaxError, match="interdit"):
        parse_templates(
            """<template t-name="demo.page"><xweb:card t-call="autre"/></template>""",
            filename="tc.xml",
        )


# ---------------------------------------------------------------------
# Namespace — réservé, injecté automatiquement, pas de double injection
# ---------------------------------------------------------------------


def test_namespace_auto_injected_when_shorthand_used():
    templates = parse_templates(_XWEB_BUTTON_PAGE, filename="auto.xml")
    calls = [el for el in templates["demo.shorthand_page"].iter() if el.get("t-call")]
    assert calls


def test_explicit_namespace_declaration_left_untouched():
    templates = parse_templates(
        """<templates xmlns:xweb="urn:xweb">
  <template t-name="demo.page"><xweb:button>ok</xweb:button></template>
</templates>""",
        filename="explicit.xml",
    )
    el = templates["demo.page"][0]
    assert el.get("t-call") == "xweb.button"


def test_template_without_shorthand_parses_and_renders_unscathed(registry):
    registry.register_source(
        """<template t-name="demo.plain"><span t-esc="label"/></template>""",
        filename="plain.xml",
    )
    assert registry.render("demo.plain", {"label": "ok"}) == "<span>ok</span>"