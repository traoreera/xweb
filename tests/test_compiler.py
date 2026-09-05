"""Phase 1 validation (xweb Blueprint §7) — does the compiler design
documented in docs/language.md actually work? Each test below traces
back to a specific claim made in the design docs; see the comment on
each test for which one.
"""

import re
from pathlib import Path

import pytest

from xweb.engine.compiler import TemplateError
from xweb.engine.parser import TemplateSyntaxError, parse_templates
from xweb.engine.registry import QwebRegistry

COMPONENTS_DIR = Path(__file__).parent.parent / "xweb" / "components"

# The compiler deliberately preserves XML .tail text verbatim (dropping it
# was a real bug caught while writing engine/compiler.py — see its
# _render_children docstring), which means insignificant source
# indentation shows up in raw render output until a minifier exists
# (xweb Blueprint §7, not built yet). Tests that care about a piece of
# text landing inside a specific tag use a whitespace-tolerant regex
# rather than exact-adjacency string checks.


@pytest.fixture
def registry() -> QwebRegistry:
    r = QwebRegistry()
    r.register_dir(COMPONENTS_DIR)
    return r


# ---------------------------------------------------------------------
# button.xml — t-if/t-else, t-att-*, t-attf-*, t-esc
# ---------------------------------------------------------------------


def test_button_renders_button_tag_without_href(registry):
    html = registry.render(
        "xweb.button",
        {"slot": "Valider", "variant": "primary", "size": "md", "extra_class": "", "type": "submit"},
    )
    assert html.strip().startswith("<button")
    assert 'type="submit"' in html
    assert "btn btn-primary btn-md" in html
    assert re.search(r"<button[^>]*>\s*Valider\s*</button>", html)
    assert "<a " not in html


def test_button_renders_anchor_when_href_given(registry):
    html = registry.render(
        "xweb.button",
        {"slot": "Voir", "href": "/plugins/crm/contacts", "variant": "text", "size": "sm", "extra_class": ""},
    )
    assert html.strip().startswith("<a ")
    assert 'href="/plugins/crm/contacts"' in html
    assert "</a>" in html
    assert "<button" not in html


def test_button_escapes_slot_content(registry):
    """docs/language.md#t-esc — t-esc is always HTML-escaped."""
    html = registry.render(
        "xweb.button", {"slot": "<script>alert(1)</script>", "variant": "danger", "size": "md", "extra_class": ""}
    )
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_button_att_disabled_true_renders_boolean_attribute(registry):
    html = registry.render(
        "xweb.button", {"slot": "x", "variant": "primary", "size": "md", "extra_class": "", "disabled": True}
    )
    assert 'disabled="disabled"' in html


def test_button_att_disabled_false_omits_attribute(registry):
    html = registry.render(
        "xweb.button", {"slot": "x", "variant": "primary", "size": "md", "extra_class": "", "disabled": False}
    )
    assert "disabled" not in html


def test_undefined_variable_is_falsy_not_a_crash():
    """docs/language.md — an undefined name evaluates to None (falsy),
    it does not raise. href undefined -> the t-else branch (<button>)."""
    r = QwebRegistry()
    r.register_dir(COMPONENTS_DIR)
    html = r.render("xweb.button", {"slot": "x", "variant": "primary", "size": "md", "extra_class": ""})
    assert html.strip().startswith("<button")


def test_button_defaults_to_a_reasonable_button_without_any_props(registry):
    """Anciennement "le vrai trou" (button.xml n'avait aucun t-default,
    contrairement à badge/card/stat) — corrigé
    (know/features/button-missing-defaults.md) : un appel sans props
    produit un bouton par défaut raisonnable, pas "btn btn- btn-"."""
    html = registry.render("xweb.button", {"slot": "x"})
    assert html.strip().startswith("<button")
    assert "btn btn-primary btn-md" in html
    assert 'type="button"' in html  # jamais "submit" implicite du navigateur


def test_t_default_fills_in_only_when_caller_omitted_the_prop():
    r = QwebRegistry()
    r.register_source(
        """<template t-name="test.sized">
            <t t-set="size" t-default="'md'"/>
            <t t-esc="size"/>
        </template>"""
    )
    assert r.render("test.sized", {}).strip() == "md"
    assert r.render("test.sized", {"size": "lg"}).strip() == "lg"


def test_t_default_does_not_override_an_explicit_none():
    """t-default only fills in when the caller didn't pass the prop AT
    ALL — a caller who explicitly passed None (e.g. "no icon") means it,
    that's different from "didn't say"."""
    r = QwebRegistry()
    r.register_source(
        """<template t-name="test.explicit_none">
            <t t-set="icon" t-default="'fallback'"/>
            <t t-if="icon is None">pas d icone</t>
            <t t-else="1"><t t-esc="icon"/></t>
        </template>"""
    )
    assert r.render("test.explicit_none", {"icon": None}).strip() == "pas d icone"
    assert r.render("test.explicit_none", {}).strip() == "fallback"


# ---------------------------------------------------------------------
# t-foreach
# ---------------------------------------------------------------------


def test_foreach_renders_once_per_item_with_loop_vars():
    r = QwebRegistry()
    r.register_source(
        """<template t-name="test.list">
            <ul>
                <li t-foreach="items" t-as="item" t-esc="item"
                    t-att-data-first="item_first" t-att-data-last="item_last"/>
            </ul>
        </template>"""
    )
    html = r.render("test.list", {"items": ["a", "b", "c"]})
    assert html.count("<li") == 3
    # True renders as the HTML boolean-attribute idiom (attr="attr"), same
    # convention already established for disabled="disabled" on button.xml —
    # not the Python str(True) == "True" one might first expect.
    assert 'data-first="data-first"' in html
    assert 'data-last="data-last"' in html
    assert ">a<" in html and ">b<" in html and ">c<" in html


def test_foreach_empty_iterable_renders_nothing():
    r = QwebRegistry()
    r.register_source('<template t-name="test.list"><ul><li t-foreach="items" t-as="i" t-esc="i"/></ul></template>')
    html = r.render("test.list", {"items": []})
    assert html == "<ul></ul>"


# ---------------------------------------------------------------------
# t-call — docs/language.md#t-call, isolated scope + slot
# ---------------------------------------------------------------------


def test_t_call_passes_explicit_props_and_slot(registry):
    r = QwebRegistry()
    r.register_dir(COMPONENTS_DIR)
    r.register_source(
        """<template t-name="test.page">
            <div class="page">
                <t t-call="xweb.button" variant="primary" size="lg" extra_class="">Nouveau</t>
            </div>
        </template>"""
    )
    html = r.render("test.page", {})
    assert "btn btn-primary btn-lg" in html
    assert re.search(r"<button[^>]*>\s*Nouveau\s*</button>", html)


def test_t_call_nested_component_in_slot_is_not_double_escaped(registry):
    """Trouvé en écrivant card.xml : slot est toujours du Markup produit
    par notre propre compilateur (jamais du texte brut d'un appelant
    direct) — button.xml faisait t-esc="slot" jusqu'ici, ce qui aurait
    transformé un composant imbriqué en &lt;button&gt; littéral affiché
    au lieu d'être rendu. Jamais détecté avant : aucun test ne mettait de
    markup dans un slot."""
    r = QwebRegistry()
    r.register_dir(COMPONENTS_DIR)
    r.register_source(
        """<template t-name="test.nested">
            <t t-call="xweb.button" variant="primary" size="md" extra_class="">
                <t t-call="xweb.button" variant="ghost" size="sm" extra_class="">Interieur</t>
                Exterieur
            </t>
        </template>"""
    )
    html = r.render("test.nested", {})
    assert "&lt;button" not in html, "le bouton imbriqué a été échappé au lieu d'être rendu"
    assert html.count("<button") == 2
    assert "Interieur" in html and "Exterieur" in html


def test_t_call_does_not_leak_caller_context():
    """Isolated-scope design decision (docs/language.md#t-call) — a
    variable set in the caller must NOT be visible inside the callee
    unless passed explicitly as a prop."""
    r = QwebRegistry()
    r.register_source('<template t-name="test.leaky"><t t-esc="secret"/></template>')
    r.register_source(
        """<template t-name="test.caller">
            <t t-set="secret" t-value="'should not leak'"/>
            <t t-call="test.leaky"/>
        </template>"""
    )
    html = r.render("test.caller", {})
    assert "should not leak" not in html


def test_t_call_unknown_target_raises():
    r = QwebRegistry()
    r.register_source('<template t-name="test.caller"><t t-call="nope.missing"/></template>')
    with pytest.raises(TemplateError):
        r.render("test.caller", {})


# ---------------------------------------------------------------------
# htmx / _hyperscript passthrough — the central bet of xweb Blueprint §2
# ---------------------------------------------------------------------


def test_hx_and_hyperscript_attributes_pass_through_untouched(registry):
    html = registry.render("xweb.toggle_demo", {"label": "Bascule"})
    assert 'hx-post="/plugins/demo/toggle"' in html
    assert 'hx-target="#status"' in html
    assert '_="on click toggle .dark on the documentElement"' in html
    assert re.search(r"<button[^>]*>\s*Bascule\s*</button>", html)


def test_toggle_demo_file_is_valid_xml_despite_underscore_attribute():
    """The whole point (xweb Blueprint §2): unlike Alpine's @click/:class,
    which are not legal XML attribute names at all, hx-* and _ parse with
    zero preprocessing. This test fails loudly if that stops being true."""
    source = (COMPONENTS_DIR / "toggle_demo.xml").read_text()
    templates = parse_templates(source, filename="toggle_demo.xml")
    assert "xweb.toggle_demo" in templates


# ---------------------------------------------------------------------
# t-set scoping
# ---------------------------------------------------------------------


def test_t_set_visible_to_later_siblings_not_to_earlier_ones():
    r = QwebRegistry()
    r.register_source(
        """<template t-name="test.scope">
            <t t-esc="x"/>
            <t t-set="x" t-value="'set'"/>
            <t t-esc="x"/>
        </template>"""
    )
    html = r.render("test.scope", {})
    # first t-esc runs before t-set: x undefined -> nothing; second: "set"
    assert html.strip() == "set"


def test_t_set_does_not_leak_out_of_a_child_block():
    r = QwebRegistry()
    r.register_source(
        """<template t-name="test.nested">
            <div><t t-set="x" t-value="1"/></div>
            <t t-esc="x"/>
        </template>"""
    )
    html = r.render("test.nested", {})
    assert html.strip() == "<div></div>"  # x set inside the <div> block never reaches the top-level t-esc


# ---------------------------------------------------------------------
# void elements, malformed XML
# ---------------------------------------------------------------------


def test_script_text_is_not_html_escaped():
    """Trouvé en calculant le hash CSP du script anti-flash de shell.xml
    (docs/theming.md#build) : escape() transformait ' en &#39; dans un
    <script> — un navigateur ne décode jamais les entités là-dedans
    (raw text element HTML5), &#39; y est exécuté littéralement ->
    SyntaxError. Testé sur le cas réel, pas un exemple inventé."""
    r = QwebRegistry()
    r.register_source(
        "<template t-name=\"test.script\">"
        "<script>localStorage.getItem('theme') || 'light';</script>"
        "</template>"
    )
    html = r.render("test.script", {})
    assert "&#39;" not in html
    assert "localStorage.getItem('theme') || 'light';" in html


def test_style_text_is_not_html_escaped_either():
    r = QwebRegistry()
    r.register_source(
        '<template t-name="test.style"><style>a[href^="x"]{color:red}</style></template>'
    )
    html = r.render("test.style", {})
    assert "&quot;" not in html
    assert 'a[href^="x"]{color:red}' in html


def test_void_element_self_closes():
    r = QwebRegistry()
    r.register_source('<template t-name="test.input"><input t-att-value="v" type="text"/></template>')
    html = r.render("test.input", {"v": "hi"})
    assert html == '<input value="hi" type="text" />'


def test_malformed_xml_raises_template_syntax_error():
    with pytest.raises(TemplateSyntaxError):
        parse_templates("<template t-name=\"x\"><div></template>", filename="bad.xml")


def test_missing_t_name_raises():
    with pytest.raises(TemplateSyntaxError):
        parse_templates("<template><div/></template>", filename="bad.xml")


# ---------------------------------------------------------------------
# t-tr — docs/i18n.md. La clé de traduction est le texte source lui-même
# (convention gettext), le traducteur vit dans ctx["_"], jamais importé par
# le compilateur (xweb/mount.py est seul à savoir ce qu'est une locale).
# ---------------------------------------------------------------------


def test_t_tr_passes_source_text_through_unchanged_without_a_translator_in_context():
    """Rendu hors mount_xweb_page (CLI xweb, tests) — ctx["_"] absent, le
    texte français d'origine sort tel quel, jamais une exception."""
    r = QwebRegistry()
    r.register_source('<template t-name="test.tr"><h1 t-tr="1">Organisation</h1></template>')
    assert r.render("test.tr", {}) == "<h1>Organisation</h1>"


def test_t_tr_calls_the_translator_in_context_with_the_stripped_source_text():
    r = QwebRegistry()
    r.register_source('<template t-name="test.tr"><h1 t-tr="1">  Organisation  </h1></template>')
    calls = []

    def translate(source):
        calls.append(source)
        return "Organization"

    html = r.render("test.tr", {"_": translate})
    assert html == "<h1>Organization</h1>"
    assert calls == ["Organisation"]  # espaces d'indentation retirés avant la clé


def test_t_tr_falls_back_to_source_text_when_translator_has_no_entry():
    r = QwebRegistry()
    r.register_source('<template t-name="test.tr"><h1 t-tr="1">Pas encore traduit</h1></template>')
    html = r.render("test.tr", {"_": lambda s: {"Organisation": "Organization"}.get(s, s)})
    assert html == "<h1>Pas encore traduit</h1>"


def test_t_tr_escapes_the_translated_output():
    r = QwebRegistry()
    r.register_source('<template t-name="test.tr"><p t-tr="1">a</p></template>')
    html = r.render("test.tr", {"_": lambda s: "<script>alert(1)</script>"})
    assert "&lt;script&gt;" in html and "<script>alert(1)</script>" not in html


def test_t_tr_normalizes_internal_whitespace_from_multiline_source():
    """Un texte source indenté sur plusieurs lignes (mise en forme du
    fichier .xml, sans signification pour le HTML rendu) collapse en une
    seule ligne à espaces simples — sinon la clé de traduction dépendrait
    de l'indentation exacte du gabarit, cassée au moindre reformatage."""
    r = QwebRegistry()
    r.register_source(
        '<template t-name="test.tr"><p t-tr="1">\n'
        "                Ligne un\n"
        "                ligne deux — d'un bloc indenté.\n"
        "            </p></template>"
    )
    calls = []
    html = r.render("test.tr", {"_": lambda s: calls.append(s) or s})
    assert calls == ["Ligne un ligne deux — d'un bloc indenté."]
    assert html == "<p>Ligne un ligne deux — d&#39;un bloc indenté.</p>"


def test_t_tr_ignores_element_children_same_as_t_esc_and_t_out():
    """Cohérent avec t-esc/t-out existants (déjà le cas avant t-tr, voir
    _render_element_body) — pas une régression propre à t-tr."""
    r = QwebRegistry()
    r.register_source('<template t-name="test.tr"><h1 t-tr="1">Titre<b>ignoré</b></h1></template>')
    html = r.render("test.tr", {})
    assert html == "<h1>Titre</h1>"
    assert "ignoré" not in html


def test_t_tr_on_an_empty_node_renders_nothing_and_never_calls_the_translator():
    r = QwebRegistry()
    r.register_source('<template t-name="test.tr"><span t-tr="1"/></template>')
    calls = []
    html = r.render("test.tr", {"_": lambda s: calls.append(s) or s})
    assert html == "<span></span>"
    assert calls == []


def test_t_tr_on_the_same_element_as_t_call_is_a_no_op_documented_trap():
    """Trouvé pour de vrai en câblant l'export EN sur le parcours d'auth
    (docs/i18n.md) : `<t t-call="xweb.button" t-tr="1">Se connecter</t>`
    ne traduit RIEN — `_render_element_body` retourne juste après avoir
    délégué à `_render_call` dès que `t-call` est présent (voir le début
    de la fonction), donc `t_tr` n'est même jamais lu pour cet élément.
    `_render_call` capture les enfants BRUTS comme slot, sans jamais
    consulter t-esc/t-out/t-tr sur l'élément porteur du t-call lui-même —
    ce n'est pas un cas particulier de t-tr, c'est general à tout t-call.
    Le correctif n'est pas dans le compilateur : imbriquer <t t-tr="1">...
    à l'intérieur du t-call (voir le test suivant)."""
    r = QwebRegistry()
    r.register_source('<template t-name="test.btn"><button><t t-out="slot"/></button></template>')
    r.register_source('<template t-name="test.page"><t t-call="test.btn" t-tr="1">Se connecter</t></template>')
    html = r.render("test.page", {"_": lambda s: {"Se connecter": "Log in"}.get(s, s)})
    assert html == "<button>Se connecter</button>"  # jamais traduit — le piège


def test_t_tr_nested_inside_a_t_call_slot_translates_correctly():
    """Le correctif réel (et la convention adoptée dans plugins/account/
    templates/*.xml, docs/i18n.md) : le <t t-tr="1"> DANS le corps du
    t-call est un enfant comme un autre, rendu normalement par
    _render_children — donc bien traduit."""
    r = QwebRegistry()
    r.register_source('<template t-name="test.btn"><button><t t-out="slot"/></button></template>')
    r.register_source('<template t-name="test.page"><t t-call="test.btn"><t t-tr="1">Se connecter</t></t></template>')
    html = r.render("test.page", {"_": lambda s: {"Se connecter": "Log in"}.get(s, s)})
    assert html == "<button>Log in</button>"


# ---------------------------------------------------------------------
# Filtres noyau (xweb/engine/filters.py) — set FERMÉ, aucun enregistrement
# plugin possible. Le résultat final reste échappé (t-esc).
# ---------------------------------------------------------------------


# helpers -------------------------------------------------------------------


def _render_str(expr: str, ctx: dict | None = None) -> str:
    r = QwebRegistry()
    r.register_source(f'<template t-name="test.f"><t t-esc="{expr}"/></template>')
    return r.render("test.f", ctx or {}).strip()


# valeur + formatage ---------------------------------------------------------


def test_filter_money():
    assert _render_str("price | money", {"price": 1234.5}) == "1 234,50 €"
    assert _render_str("price | money", {"price": 9}) == "9,00 €"


def test_filter_number():
    assert _render_str("n | number", {"n": 1234.56}) == "1 234,56"
    assert _render_str("n | number", {"n": 1000}) == "1 000"


def test_filter_percent():
    assert _render_str("r | percent", {"r": 0.125}) == "12,5 %"
    assert _render_str("r | percent", {"r": 1}) == "100 %"


def test_filter_upper_lower_title():
    assert _render_str("s | upper", {"s": "acme"}) == "ACME"
    assert _render_str("s | lower", {"s": "ACME"}) == "acme"
    assert _render_str("s | title", {"s": "bonjour monde"}) == "Bonjour Monde"


def test_filter_truncate():
    assert _render_str("s | truncate:5", {"s": "abcdefg"}) == "abcd…"
    assert _render_str("s | truncate:10", {"s": "courte"}) == "courte"


def test_filter_slug():
    assert _render_str("s | slug", {"s": "Ça va l'Être ?"}) == "ca-va-l-etre"


# utilitaires ---------------------------------------------------------------


def test_filter_length():
    assert _render_str("items | length", {"items": [1, 2, 3]}) == "3"
    assert _render_str("items | length", {"items": None}) == "0"


def test_filter_join():
    assert _render_str("items | join", {"items": ["a", "b", "c"]}) == "a, b, c"
    assert _render_str("items | join:';'", {"items": ["a", "b"]}) == "a;b"


def test_filter_default():
    assert _render_str("x | default:'N/A'", {"x": ""}) == "N/A"
    assert _render_str("x | default:'N/A'", {"x": "ok"}) == "ok"


def test_filter_yesno():
    assert _render_str("x | yesno", {"x": True}) == "Oui"
    assert _render_str("x | yesno", {"x": False}) == "Non"
    assert _render_str("x | yesno", {"x": None}) == "—"


def test_filter_first_last():
    assert _render_str("items | first", {"items": [7, 8]}) == "7"
    assert _render_str("items | last", {"items": [7, 8]}) == "8"


def test_filter_since():
    import datetime as dt
    now = dt.datetime.now(dt.timezone.utc)
    r = QwebRegistry()
    r.register_source('<template t-name="test.f"><t t-esc="d | since"/></template>')
    html = r.render("test.f", {"d": now - dt.timedelta(minutes=2)})
    assert "il y a 2 min" in html


# robustesse : pas de régression du eval normal -----------------------------


def test_filter_unknown_name_falls_back_to_bitwise_or():
    # `|` suivi d'un nom INCONNU de filtre ne découpe PAS -> a | b passe par
    # eval() normal (bitwise OR), pas un crash.
    assert _render_str("a | b", {"a": 4, "b": 1}) == "5"


def test_filter_does_not_break_undefined_variable():
    assert _render_str("missing | money") == ""


def test_filter_result_is_still_escaped():
    r = QwebRegistry()
    r.register_source('<template t-name="test.f"><t t-esc="s | upper"/></template>')
    html = r.render("test.f", {"s": "<script>alert(1)</script>"})
    assert "alert" not in html
    assert "<script>" not in html


# ---------------------------------------------------------------------
# t-call — slots nommés (know/features/composable-header-slot.md)
# ---------------------------------------------------------------------


def test_named_slot_is_exposed_as_slot_prefixed_name():
    r = QwebRegistry()
    r.register_source(
        '<template t-name="test.card"><div>'
        '<t t-if="slot_header"><header><t t-out="slot_header"/></header></t>'
        '<main><t t-out="slot"/></main>'
        "</div></template>"
    )
    r.register_source(
        '<template t-name="test.page"><t t-call="test.card">'
        '<t t-set-slot="header"><b>Titre</b></t>'
        "Contenu principal"
        "</t></template>"
    )
    html = r.render("test.page", {})
    assert "<header><b>Titre</b></header>" in html
    assert "<main>Contenu principal</main>" in html


def test_named_slot_content_does_not_leak_into_default_slot():
    r = QwebRegistry()
    r.register_source('<template t-name="test.card"><t t-out="slot"/>|<t t-out="slot_header"/></template>')
    r.register_source(
        '<template t-name="test.page"><t t-call="test.card">'
        '<t t-set-slot="header">EN-TETE</t>'
        "RESTE"
        "</t></template>"
    )
    html = r.render("test.page", {})
    assert html.strip() == "RESTE|EN-TETE"


def test_named_slot_renders_in_the_callers_context_not_isolated():
    r = QwebRegistry()
    r.register_source('<template t-name="test.card"><t t-out="slot_header"/></template>')
    r.register_source(
        '<template t-name="test.page"><t t-call="test.card">'
        '<t t-set-slot="header"><t t-esc="caller_var"/></t>'
        "</t></template>"
    )
    html = r.render("test.page", {"caller_var": "valeur-appelant"})
    assert html.strip() == "valeur-appelant"


def test_no_named_slot_given_renders_it_as_none_not_an_error():
    """slot_header non fourni est simplement ABSENT de call_ctx — même
    piège "not <nom absent>" déjà connu pour toute prop de t-call
    (docs/language.md), pas spécifique aux slots nommés : la cible doit
    déclarer t-default comme pour n'importe quelle autre prop."""
    r = QwebRegistry()
    r.register_source(
        '<template t-name="test.card">'
        '<t t-set="slot_header" t-default="None"/>'
        '<t t-if="not slot_header">pas de header</t>'
        "</template>"
    )
    r.register_source('<template t-name="test.page"><t t-call="test.card">contenu</t></template>')
    assert "pas de header" in r.render("test.page", {})


# ---------------------------------------------------------------------
# t-call — t-attf-* interpolé comme prop (know/features/t-call-needs-interpolated-prop-syntax.md)
# ---------------------------------------------------------------------


def test_tattf_on_t_call_interpolates_into_the_prop_value():
    r = QwebRegistry()
    r.register_source('<template t-name="test.link"><a t-att-href="url">x</a></template>')
    r.register_source('<template t-name="test.page"><t t-call="test.link" t-attf-url="/sessions/{{sid}}/revoke"/></template>')
    html = r.render("test.page", {"sid": "abc123"})
    assert 'href="/sessions/abc123/revoke"' in html


def test_tattf_prop_value_is_not_pre_escaped_target_escapes_it_itself():
    """Une prop t-attf-* est une valeur Python brute, comme t-att-* — pas
    du HTML déjà échappé. C'est le t-esc/t-att-* de la CIBLE qui échappe,
    une seule fois, pas ici en plus."""
    r = QwebRegistry()
    r.register_source('<template t-name="test.echo"><t t-esc="v"/></template>')
    r.register_source('<template t-name="test.page"><t t-call="test.echo" t-attf-v="{{name}} &amp; co"/></template>')
    html = r.render("test.page", {"name": "<b>Ada</b>"})
    assert "&lt;b&gt;Ada&lt;/b&gt; &amp; co" in html


def test_tattf_slot_is_never_a_prop_name():
    """t-attf-slot ne doit jamais écraser le contenu réel du slot — "slot"
    reste réservé à ce que porte le corps du t-call."""
    r = QwebRegistry()
    r.register_source('<template t-name="test.echo"><t t-out="slot"/></template>')
    r.register_source('<template t-name="test.page"><t t-call="test.echo" t-attf-slot="{{x}}">vrai contenu</t></template>')
    html = r.render("test.page", {"x": "usurpé"})
    assert html.strip() == "vrai contenu"


# ---------------------------------------------------------------------
# `_()` — filet de sécurité identité (know/features/underscore-safe-default-in-expressions.md)
# ---------------------------------------------------------------------


def test_underscore_call_without_context_falls_back_to_identity_not_none():
    r = QwebRegistry()
    r.register_source('<template t-name="test.f"><t t-esc="_(\'Bonjour\')"/></template>')
    assert r.render("test.f", {}).strip() == "Bonjour"


def test_underscore_inside_t_call_isolated_context_still_works():
    """Le cas réel du bug : _() DANS un t-foreach/littéral passé à un
    t-call qui n'a jamais reçu `_` explicitement — avant ce correctif,
    NameError sur `_` faisait échouer TOUTE l'expression englobante."""
    r = QwebRegistry()
    r.register_source(
        '<template t-name="test.list">'
        '<t t-foreach="items" t-as="i"><li><t t-esc="i"/></li></t>'
        "</template>"
    )
    r.register_source(
        '<template t-name="test.page">'
        "<t t-call=\"test.list\" t-att-items=\"[_('a'), _('b')]\"/>"
        "</template>"
    )
    html = r.render("test.page", {})  # pas de `_` forwardé du tout
    assert "<li>a</li>" in html and "<li>b</li>" in html


def test_underscore_explicit_context_still_takes_priority_over_default():
    r = QwebRegistry()
    r.register_source('<template t-name="test.f"><t t-esc="_(\'Bonjour\')"/></template>')
    html = r.render("test.f", {"_": lambda s: s.upper()})
    assert html.strip() == "BONJOUR"
