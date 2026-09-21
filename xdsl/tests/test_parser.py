"""Tests pour le lexer et parser xdsl."""

from __future__ import annotations

import textwrap

import pytest

from xdsl.parser import (
    AST,
    Assignment,
    Attribute,
    AttributeValue,
    ChannelDef,
    ChannelOnMessage,
    ComponentDef,
    CopyDef,
    Element,
    ForLoop,
    IfBlock,
    Import,
    Lexer,
    LexerError,
    ParseError,
    Parser,
    PatchDef,
    Position,
    Props,
    SlotNode,
    Style,
    TextNode,
    TokenKind,
    XpathPatch,
    split_value_type,
)


# =============================================================================
# Tests du Lexer
# =============================================================================


class TestLexerBasic:
    """Tests de base du lexer."""

    def test_empty_source(self):
        tokens = Lexer("").tokenize()
        assert len(tokens) == 1
        assert tokens[0].kind == TokenKind.EOF

    def test_single_identifier(self):
        tokens = Lexer("component").tokenize()
        assert tokens[0].kind == TokenKind.COMPONENT
        assert tokens[0].value == "component"

    def test_multiple_tokens(self):
        tokens = Lexer("component xweb.button {").tokenize()
        kinds = [t.kind for t in tokens]
        assert TokenKind.COMPONENT in kinds
        assert TokenKind.IDENT in kinds
        assert TokenKind.LBRACE in kinds

    def test_keywords_recognized(self):
        keywords = [
            "component", "import", "from", "if", "elif", "else",
            "for", "in", "patch", "copy", "as", "priority",
            "slot", "raw", "tr", "style", "props", "xpath",
        ]
        for kw in keywords:
            tokens = Lexer(kw).tokenize()
            assert tokens[0].kind != TokenKind.IDENT, f"'{kw}' devrait être un keyword"


class TestLexerStrings:
    """Tests de tokenisation des chaînes."""

    def test_double_quoted_string(self):
        tokens = Lexer('"hello world"').tokenize()
        assert tokens[0].kind == TokenKind.STRING
        assert tokens[0].value == "hello world"

    def test_single_quoted_string(self):
        tokens = Lexer("'hello'").tokenize()
        assert tokens[0].kind == TokenKind.STRING
        assert tokens[0].value == "hello"

    def test_escaped_quotes(self):
        tokens = Lexer('"hello \\"world\\""').tokenize()
        assert tokens[0].value == 'hello "world"'

    def test_escaped_newline(self):
        tokens = Lexer('"line1\\nline2"').tokenize()
        assert tokens[0].value == "line1\nline2"


class TestLexerInterpolation:
    """Tests de tokenisation des interpolations."""

    def test_simple_interpolation(self):
        tokens = Lexer('${name}').tokenize()
        assert tokens[0].kind == TokenKind.INTERPOLATION
        assert tokens[0].value == "name"

    def test_nested_braces(self):
        tokens = Lexer('${obj.key}').tokenize()
        assert tokens[0].value == "obj.key"


class TestLexerComments:
    """Tests de tokenisation des commentaires."""

    def test_line_comment(self):
        tokens = Lexer("// comment\nident").tokenize()
        # Le commentaire est ignoré, mais le newline reste
        non_newline = [t for t in tokens if t.kind != TokenKind.NEWLINE and t.kind != TokenKind.EOF]
        assert non_newline[0].kind == TokenKind.IDENT
        assert non_newline[0].value == "ident"

    def test_block_comment(self):
        tokens = Lexer("/* comment */ ident").tokenize()
        assert tokens[0].kind == TokenKind.IDENT


class TestLexerNumbers:
    """Tests de tokenisation des nombres."""

    def test_integer(self):
        tokens = Lexer("42").tokenize()
        assert tokens[0].kind == TokenKind.NUMBER
        assert tokens[0].value == "42"

    def test_negative_integer(self):
        tokens = Lexer("-5").tokenize()
        assert tokens[0].kind == TokenKind.NUMBER
        assert tokens[0].value == "-5"

    def test_float(self):
        tokens = Lexer("3.14").tokenize()
        assert tokens[0].kind == TokenKind.NUMBER
        assert tokens[0].value == "3.14"


class TestLexerOperators:
    """Tests de tokenisation des opérateurs."""

    def test_assign(self):
        tokens = Lexer("x = 5").tokenize()
        assert tokens[1].kind == TokenKind.ASSIGN

    def test_assign_default(self):
        tokens = Lexer("x ?= 5").tokenize()
        assert tokens[1].kind == TokenKind.ASSIGN_DEFAULT

    def test_arrow(self):
        tokens = Lexer("->").tokenize()
        assert tokens[0].kind == TokenKind.ARROW

    def test_pipe(self):
        """`|` (chaînage de filtre QWeb, xweb/engine/filters.py) — avant ce
        token, le lexer ignorait silencieusement `|` (branche "caractère
        inconnu"), mangleant `price | money` en `price money`."""
        tokens = Lexer("price | money").tokenize()
        kinds = [t.kind for t in tokens if t.kind != TokenKind.EOF]
        assert TokenKind.PIPE in kinds

    def test_comparison_operators_two_char_first(self):
        """`<=`/`>=`/`!=`/`==` doivent être tokenisés en UN token AVANT les
        variantes mono-caractère — sinon `x < 5` est manglé (caractère
        inconnu avalé) et `x != y` devient `x = y` (bug silencieux)."""
        for src, kind in (
            ("x == 5", TokenKind.EQ),
            ("x != 5", TokenKind.NE),
            ("x <= 5", TokenKind.LE),
            ("x >= 5", TokenKind.GE),
            ("x < 5", TokenKind.LT),
            ("x > 5", TokenKind.GT),
        ):
            kinds = [t.kind for t in Lexer(src).tokenize() if t.kind != TokenKind.EOF]
            assert kind in kinds, f"{src!r} doit contenir {kind.name}"

    def test_question_token(self):
        """`?` seul (ternaire) émet QUESTION ; `?=` reste ASSIGN_DEFAULT
        (l'ordre 2-caractères-bref d'abord doit gagner)."""
        tokens = Lexer("a ? b : c").tokenize()
        kinds = [t.kind for t in tokens if t.kind != TokenKind.EOF]
        assert TokenKind.QUESTION in kinds
        assert TokenKind.COLON in kinds
        default = Lexer("x ?= 5").tokenize()
        assert default[1].kind == TokenKind.ASSIGN_DEFAULT


# =============================================================================
# Tests du Parser
# =============================================================================


class TestParserComponent:
    """Tests de parsing des composants."""

    def test_empty_component(self):
        source = """
component xweb.button {
}
"""
        ast = Parser(source).parse()
        assert len(ast.components) == 1
        assert ast.components[0].name == "xweb.button"
        assert ast.components[0].children == []

    def test_component_with_text_child(self):
        source = """
component xweb.greeting {
    "Bonjour"
}
"""
        ast = Parser(source).parse()
        assert len(ast.components) == 1
        assert len(ast.components[0].children) == 1
        assert isinstance(ast.components[0].children[0], TextNode)

    def test_component_with_element_child(self):
        source = """
component xweb.card {
    div { class: "card"
        slot
    }
}
"""
        ast = Parser(source).parse()
        comp = ast.components[0]
        assert len(comp.children) == 1
        elem = comp.children[0]
        assert isinstance(elem, Element)
        assert elem.tag == "div"

    def test_component_dotted_name(self):
        source = """
component auth.login_page {
}
"""
        ast = Parser(source).parse()
        assert ast.components[0].name == "auth.login_page"


class TestParserImport:
    """Tests de parsing des imports."""

    def test_single_import(self):
        source = """
component auth.login {
    import { button } from "xweb"
}
"""
        ast = Parser(source).parse()
        comp = ast.components[0]
        assert len(comp.imports) == 1
        assert comp.imports[0].names == ["button"]
        assert comp.imports[0].source == "xweb"
        assert comp.imports[0].relative is False

    def test_multiple_imports(self):
        source = """
component auth.login {
    import { button, input, form } from "xweb"
}
"""
        ast = Parser(source).parse()
        comp = ast.components[0]
        assert comp.imports[0].names == ["button", "input", "form"]

    def test_relative_import(self):
        source = """
component auth.login {
    import { nav } from "./"
}
"""
        ast = Parser(source).parse()
        comp = ast.components[0]
        assert comp.imports[0].relative is True


class TestParserProps:
    """Tests de parsing des props."""

    def test_props_with_defaults(self):
        source = """
component auth.form {
    props: { email: ""; password: ""; remember: false }

    form {
        input { label: email }
    }
}
"""
        ast = Parser(source).parse()
        comp = ast.components[0]
        assert comp.props is not None
        assert comp.props.defaults["email"] == ""
        assert comp.props.defaults["password"] == ""
        assert comp.props.defaults["remember"] is False

    def test_props_with_number(self):
        source = """
component xweb.badge {
    props: { count: 0 }

    span { count }
}
"""
        ast = Parser(source).parse()
        comp = ast.components[0]
        assert comp.props.defaults["count"] == 0


class TestParserIf:
    """Tests de parsing des conditions."""

    def test_simple_if(self):
        source = """
component test {
    if (is_admin) {
        "Admin"
    }
}
"""
        ast = Parser(source).parse()
        comp = ast.components[0]
        assert len(comp.children) == 1
        if_block = comp.children[0]
        assert isinstance(if_block, IfBlock)
        assert if_block.condition == "is_admin"
        assert len(if_block.children) == 1

    def test_if_else(self):
        source = """
component test {
    if (logged_in) {
        "Bienvenue"
    } else {
        "Connectez-vous"
    }
}
"""
        ast = Parser(source).parse()
        if_block = ast.components[0].children[0]
        assert isinstance(if_block, IfBlock)
        assert len(if_block.else_children) == 1

    def test_if_elif_else(self):
        source = """
component test {
    if (x == 1) {
        "un"
    } elif (x == 2) {
        "deux"
    } else {
        "autre"
    }
}
"""
        ast = Parser(source).parse()
        if_block = ast.components[0].children[0]
        assert isinstance(if_block, IfBlock)
        assert len(if_block.elif_blocks) == 1
        assert if_block.elif_blocks[0][0] == "x == 2"
        assert len(if_block.else_children) == 1


class TestParserFor:
    """Tests de parsing des boucles."""

    def test_simple_for(self):
        source = """
component test {
    for item in items {
        div { item.name }
    }
}
"""
        ast = Parser(source).parse()
        comp = ast.components[0]
        assert len(comp.children) == 1
        for_loop = comp.children[0]
        assert isinstance(for_loop, ForLoop)
        assert for_loop.variable == "item"
        assert for_loop.iterable == "items"
        assert len(for_loop.children) == 1


class TestParserAssignment:
    """Tests de parsing des affectations."""

    def test_simple_assignment(self):
        source = """
component test {
    x = 42
}
"""
        ast = Parser(source).parse()
        comp = ast.components[0]
        assert len(comp.children) == 1
        assign = comp.children[0]
        assert isinstance(assign, Assignment)
        assert assign.name == "x"
        assert assign.value == "42"
        assert assign.default is False

    def test_default_assignment(self):
        source = """
component test {
    title ?= "Titre par défaut"
}
"""
        ast = Parser(source).parse()
        assign = ast.components[0].children[0]
        assert isinstance(assign, Assignment)
        assert assign.default is True


class TestParserElement:
    """Tests de parsing des éléments HTML."""

    def test_simple_element(self):
        source = """
component test {
    div { "Hello" }
}
"""
        ast = Parser(source).parse()
        elem = ast.components[0].children[0]
        assert isinstance(elem, Element)
        assert elem.tag == "div"

    def test_tr_brace_is_the_html_tag_not_the_translate_keyword(self):
        """Régression : `tr` est par ailleurs le mot-clé de traduction
        (`tr "texte"`) — sans désambiguïsation sur `{` vs `"`/expr,
        <tr> (table row) était tout simplement injoignable en xdsl."""
        source = """
component test {
    table { columns: [] ; rows: []
        tr { td { "x" } }
    }
}
"""
        ast = Parser(source).parse()
        table = ast.components[0].children[0]
        tr = table.children[0]
        assert isinstance(tr, Element)
        assert tr.tag == "tr"
        assert tr.children[0].tag == "td"

    def test_tr_string_is_still_the_translate_keyword(self):
        source = 'component test { tr "Bonjour" }'
        ast = Parser(source).parse()
        node = ast.components[0].children[0]
        assert isinstance(node, TextNode)
        assert node.translate is True
        assert node.content == "Bonjour"

    def test_element_with_attributes(self):
        source = """
component test {
    button { label: "OK"; variant: "primary" }
}
"""
        ast = Parser(source).parse()
        elem = ast.components[0].children[0]
        assert isinstance(elem, Element)
        assert len(elem.attributes) == 2

    def test_element_with_children(self):
        source = """
component test {
    div { class: "container"
        h1 { "Titre" }
        p { "Paragraphe" }
    }
}
"""
        ast = Parser(source).parse()
        elem = ast.components[0].children[0]
        assert isinstance(elem, Element)
        assert elem.tag == "div"
        assert len(elem.children) == 2

    def test_dotted_component_call(self):
        """Appel d'un composant par son nom qualifié (doc "Slots"):
        auth.login { } → Element(tag="auth.login")."""
        source = """
component auth {
    auth.login { }
}
"""
        ast = Parser(source).parse()
        elem = ast.components[0].children[0]
        assert isinstance(elem, Element)
        assert elem.tag == "auth.login"

    def test_dotted_expression_text_unchanged(self):
        """item.email (dotted sans accolade) reste du texte, pas un élément."""
        source = """
component test {
    item.email
}
"""
        ast = Parser(source).parse()
        child = ast.components[0].children[0]
        assert isinstance(child, TextNode)
        assert child.content == "item.email"

    def test_dotted_component_call_subslot(self):
        """Pattern doc "Slots" : xweb.card { h2; p } implique tag dotted + enfants."""
        source = """
component test {
    xweb.card {
        h2 { "Titre" }
        p { "Contenu" }
    }
}
"""
        ast = Parser(source).parse()
        elem = ast.components[0].children[0]
        assert isinstance(elem, Element)
        assert elem.tag == "xweb.card"
        assert len(elem.children) == 2

    def test_duplicate_attribute_is_an_error(self):
        """Un attribut répété (ex. name: deux fois) est une erreur de parse
        claire, pas un XMLSyntaxError opaque au moment de l'enregistrement
        (lxml: 'Attribute t-att-name redefined')."""
        source = """
component test {
    input {
        id: "password"
        name: "password"
        type: "password"
        name: "password"
    }
}
"""
        with pytest.raises(ParseError, match="en double.*name"):
            Parser(source).parse()

    def test_same_attribute_name_in_siblings_is_fine(self):
        """name identique sur DEUX éléments frères n'est pas un doublon."""
        source = """
component test {
    div {
        input { id: "a"; name: "x" }
        input { id: "b"; name: "x" }
    }
}
"""
        ast = Parser(source).parse()
        root = ast.components[0].children[0]
        assert all(isinstance(c, Element) for c in root.children)


class TestParserSlot:
    """Tests de parsing du slot."""

    def test_slot_node(self):
        source = """
component xweb.card {
    div { slot }
}
"""
        ast = Parser(source).parse()
        elem = ast.components[0].children[0]
        assert isinstance(elem, Element)
        assert len(elem.children) == 1
        assert isinstance(elem.children[0], SlotNode)


class TestParserStyle:
    """Tests de parsing du style."""

    def test_style_block(self):
        source = """
component auth.login {
    style: ".login { padding: 2rem; }"

    div { class: "login" }
}
"""
        ast = Parser(source).parse()
        comp = ast.components[0]
        assert comp.style is not None
        assert comp.style.css == ".login { padding: 2rem; }"


class TestParserPatch:
    """Tests de parsing des patches."""

    def test_simple_patch(self):
        source = """
patch xweb.form {
    xpath "//button" {
        inside: span { "CGU" }
    }
}
"""
        ast = Parser(source).parse()
        assert len(ast.patches) == 1
        patch = ast.patches[0]
        assert patch.target == "xweb.form"
        assert len(patch.xpath_patches) == 1

    def test_patch_with_priority(self):
        source = """
patch xweb.form priority: 10 {
    xpath "//button" {
        inside: span { "Premium" }
    }
}
"""
        ast = Parser(source).parse()
        patch = ast.patches[0]
        assert patch.priority == 10


class TestParserCopy:
    """Tests de parsing des copies (primary) — uniquement des blocs xpath,
    voir CopyDef (xdsl/parser.py) pour pourquoi un corps littéral n'a
    plus le droit de compiler silencieusement dans le vide."""

    def test_simple_copy(self):
        source = """
copy xweb.form as auth.login_form {
    xpath "//form" { inside: p { "note" } }
}
"""
        ast = Parser(source).parse()
        assert len(ast.copies) == 1
        copy = ast.copies[0]
        assert copy.source == "xweb.form"
        assert copy.alias == "auth.login_form"
        assert len(copy.xpath_patches) == 1
        assert copy.xpath_patches[0].expr == "//form"

    def test_literal_element_body_raises(self):
        with pytest.raises(ParseError):
            Parser('copy xweb.form as auth.login_form { div { "Custom form" } }').parse()


class TestParserChannel:
    """Tests de parsing des channels SSE/WS déclaratifs (`channel { }`)
    et de leur usage sur un élément (`use_channel: nom`)."""

    def test_minimal_channel(self):
        source = """
channel contacts_feed {
    url: "/stream"
}
"""
        ast = Parser(source).parse()
        assert len(ast.channels) == 1
        ch = ast.channels[0]
        assert isinstance(ch, ChannelDef)
        assert ch.name == "contacts_feed"
        assert ch.url == "/stream"
        assert ch.channels == []
        assert ch.transport == "auto"
        assert ch.connect_timeout_ms is None
        assert ch.validate is None
        assert ch.persist is None
        assert ch.onmessage == ChannelOnMessage()

    def test_full_channel_with_onmessage(self):
        source = """
channel contacts_feed {
    url: "/stream"
    channels: ["chat", "notif"]
    transport: "sse"
    connect_timeout_ms: 5000
    validate: "contact_form"
    persist: "last_contact"
    onmessage {
        refresh: "#contacts-table"
        event: "contacts:changed"
        dispatch: true
        bind: { "#counter": "count" }
    }
}
"""
        ast = Parser(source).parse()
        ch = ast.channels[0]
        assert ch.channels == ["chat", "notif"]
        assert ch.transport == "sse"
        assert ch.connect_timeout_ms == 5000
        assert ch.validate == "contact_form"
        assert ch.persist == "last_contact"
        assert ch.onmessage.refresh == "#contacts-table"
        assert ch.onmessage.event == "contacts:changed"
        assert ch.onmessage.dispatch is True
        assert ch.onmessage.bindings == [("#counter", "count")]

    def test_onmessage_without_bind_has_empty_bindings(self):
        source = """
channel c {
    url: "/x"
    onmessage { refresh: "#t" }
}
"""
        ch = Parser(source).parse().channels[0]
        assert ch.onmessage.bindings == []

    def test_onmessage_dispatch_defaults_to_false(self):
        ch = Parser('channel c { url: "/x"  onmessage { refresh: "#t" } }').parse().channels[0]
        assert ch.onmessage.dispatch is False

    def test_unknown_channel_key_raises(self):
        with pytest.raises(ParseError):
            Parser('channel c { bogus: "1" }').parse()

    def test_unknown_onmessage_key_raises(self):
        with pytest.raises(ParseError):
            Parser('channel c { url: "/x"  onmessage { bogus: "1" } }').parse()

    def test_use_channel_is_a_plain_attribute_on_the_element(self):
        """`use_channel:` n'est pas un mot-clé du parser (contrairement à
        `use:` pour endpoint) — c'est juste un attribut ordinaire, résolu
        plus tard par le compiler (`Compiler._resolve_use_channel`)."""
        source = """
component test {
    div { use_channel: contacts_feed
        span { "0" }
    }
}
"""
        ast = Parser(source).parse()
        div = ast.components[0].children[0]
        assert isinstance(div, Element)
        names = [a.name for a in div.attributes]
        assert "use_channel" in names
        use_channel_attr = next(a for a in div.attributes if a.name == "use_channel")
        assert use_channel_attr.value == "contacts_feed"


class TestParserIntegration:
    """Tests d'intégration complets."""

    def test_login_component(self):
        source = """
component auth.login_form {
    import { input, button, form } from "xweb"

    props: { email: ""; password: "" }

    style: "
        .login-card { background: var(--base-200); padding: 2rem; }
        .login-btn { width: 100%; }
    "

    form { class: "login-card"; hx-post: "/login"
        input { label: "Email"; type: "email"; bind: email }
        input { label: "Mot de passe"; type: "password"; bind: password }
        button { label: "Connexion"; variant: "primary"; class: "login-btn" }
    }
}
"""
        ast = Parser(source).parse()
        comp = ast.components[0]
        assert comp.name == "auth.login_form"
        assert len(comp.imports) == 1
        assert comp.props is not None
        assert comp.style is not None
        assert len(comp.children) == 1
        assert isinstance(comp.children[0], Element)

    def test_list_with_loop(self):
        source = """
component crm.contacts {
    for contact in contacts {
        div { class: "contact"
            span { contact.name }
            span { contact.email }
        }
    }
}
"""
        ast = Parser(source).parse()
        comp = ast.components[0]
        assert len(comp.children) == 1
        for_loop = comp.children[0]
        assert isinstance(for_loop, ForLoop)
        assert for_loop.variable == "contact"
        assert for_loop.iterable == "contacts"


# =============================================================================
# @include — directive layout
# =============================================================================


class TestInclude:
    def test_include_sets_layout(self):
        source = '@include "xweb.shell"\n'
        ast = Parser(source).parse()
        assert ast.layout == "xweb.shell"

    def test_include_with_components(self):
        source = '''
@include "xweb.shell"

component test {
    span { "hello" }
}
'''
        ast = Parser(source).parse()
        assert ast.layout == "xweb.shell"
        assert len(ast.components) == 1
        assert ast.components[0].name == "test"

    def test_include_with_single_quotes(self):
        source = "@include 'xweb.shell_minimal'\n"
        ast = Parser(source).parse()
        assert ast.layout == "xweb.shell_minimal"

    def test_no_include(self):
        source = 'component test { span { "hi" } }\n'
        ast = Parser(source).parse()
        assert ast.layout is None

    def test_include_error_without_string(self):
        """@include sans string lève une erreur."""
        source = "@include xweb\n"
        with pytest.raises(ParseError):
            Parser(source).parse()


# =============================================================================
# Hyperscript — attribut _ brut
# =============================================================================


class TestHyperscript:
    def test_inline_mode(self):
        source = '''
component test {
    div {
        _ : on click toggle .hidden on #modal
    }
}
'''
        ast = Parser(source).parse()
        elem = ast.components[0].children[0]
        assert isinstance(elem, Element)
        attr = elem.attributes[0]
        assert attr.name == "_"
        assert attr.value == "on click toggle .hidden on #modal"
        assert attr.dynamic is False

    def test_inline_mode_closes_on_element_brace(self):
        """div { _ : ... } sur une même ligne — la } finale ne doit PAS être
        avalée dans le script (elle ferme l'élément, pas l'hyperscript)."""
        source = 'component test { div { _ : on click log me } }\n'
        ast = Parser(source).parse()
        elem = ast.components[0].children[0]
        assert isinstance(elem, Element)
        assert elem.attributes[0].name == "_"
        assert elem.attributes[0].value == "on click log me"

    def test_block_mode_preserves_newlines(self):
        """Le bloc capture le script hyperscript en préservant les newlines :
        hyperscript sépare ses déclarations par des sauts de ligne (deux
        handlers `on ...`), les écraser par des espaces casserait le script
        (le second handler deviendrait le corps du premier)."""
        source = '''
component test {
    div {
        _ {
            on load
                wait 2s
                transition opacity to 0
            on click remove me
        }
    }
}
'''
        ast = Parser(source).parse()
        elem = ast.components[0].children[0]
        assert isinstance(elem, Element)
        script = elem.attributes[0].value
        assert script.startswith("on load")
        assert "wait 2s" in script
        assert "transition opacity to 0" in script
        assert "on click remove me" in script
        # Les newlines internes sont conservées — deux handlers distincts
        assert "\n" in script

    def test_block_mode_with_nested_braces(self):
        """Un js(...) contenant { } dans le bloc reste équilibré."""
        source = '''
component test {
    div {
        _ {
            js(me) return {a: 1, b: [1, 2]} end
            on click toggle .hidden
        }
    }
}
'''
        ast = Parser(source).parse()
        elem = ast.components[0].children[0]
        assert isinstance(elem, Element)
        script = elem.attributes[0].value
        assert "js(me) return {a: 1, b: [1, 2]} end" in script
        assert "on click toggle .hidden" in script

    def test_block_mode_lexer_error(self):
        with pytest.raises(LexerError):
            Parser('component test { div { _ { on load\n').parse()

    def test_inline_interpolation_flag(self):
        source = '''
component test {
    div {
        _ : on click put ${user.name} into me
    }
}
'''
        ast = Parser(source).parse()
        attr = ast.components[0].children[0].attributes[0]
        assert attr.name == "_"
        assert attr.interpolated is True
        assert "${user.name}" in attr.value

    def test_inline_interp_brace_not_terminator(self):
        """Le } de ${...} ne termine pas le mode ligne — le script continue
        jusqu'à la fin de la ligne réelle."""
        source = 'component test { div { _ : on click put ${user.name} into me } }\n'
        ast = Parser(source).parse()
        elem = ast.components[0].children[0]
        assert isinstance(elem, Element)
        assert elem.attributes[0].interpolated is True
        assert elem.attributes[0].value == "on click put ${user.name} into me"

    def test_block_interpolation_preserves_newlines(self):
        """Le mode bloc préserve les newlines ET les ${...} (qui deviennent
        t-attf-_ au compile). Les newlines ne sont pas écrasées."""
        source = '''
component test {
    div {
        _ {
            on load
                if ${is_admin}
                    add .admin to me
                end
            on click log "clicked ${item.id}"
        }
    }
}
'''
        ast = Parser(source).parse()
        attr = ast.components[0].children[0].attributes[0]
        assert attr.interpolated is True
        assert "\n" in attr.value
        assert "${is_admin}" in attr.value
        assert "${item.id}" in attr.value

    def test_underscore_alone_still_ident(self):
        """`_` seul (sans : ni { après les espaces) reste un identifiant DSL."""
        source = '''
component test {
    x = _
}
'''
        ast = Parser(source).parse()
        comp = ast.components[0]
        assert len(comp.children) == 1
        assert isinstance(comp.children[0], Assignment)
        """`_` seul (sans : ni { après les espaces) reste un identifiant DSL."""
        source = '''
component test {
    x = _
}
'''
        ast = Parser(source).parse()
        comp = ast.components[0]
        assert len(comp.children) == 1
        assert isinstance(comp.children[0], Assignment)


# =========================================================================
# Tests : liste de classes [ ] et dict de style { }
# =========================================================================


class TestClassList:
    """Parsing de class: ["a", expr, "${x}"]."""

    def test_all_static(self):
        src = 'div { class: ["flex", "items-center"] }'
        elem = Parser(src).parse().children[0]
        attr = elem.attributes[0]
        assert attr.name == "class"
        assert isinstance(attr.value, list)
        assert len(attr.value) == 2
        assert all(isinstance(v, AttributeValue) for v in attr.value)
        assert attr.value[0] == AttributeValue(value="flex", quoted=True)
        assert attr.value[1] == AttributeValue(value="items-center", quoted=True)

    def test_with_expression(self):
        src = 'div { class: ["btn", pressed] }'
        elem = Parser(src).parse().children[0]
        attr = elem.attributes[0]
        assert isinstance(attr.value, list)
        assert attr.value[0].quoted is True
        assert attr.value[1].quoted is False
        assert attr.value[1].value == "pressed"

    def test_with_interpolation(self):
        src = 'div { class: ["${size}-gap"] }'
        elem = Parser(src).parse().children[0]
        attr = elem.attributes[0]
        assert isinstance(attr.value, list)
        assert attr.value[0].quoted is True
        assert attr.value[0].value == "${size}-gap"

    def test_multiline(self):
        src = '''div {
    class: [
        "flex"
        "items-center"
    ]
}'''
        elem = Parser(src).parse().children[0]
        attr = elem.attributes[0]
        assert isinstance(attr.value, list)
        assert len(attr.value) == 2
        assert attr.value[0].value == "flex"
        assert attr.value[1].value == "items-center"

    def test_comma_separated(self):
        src = 'div { class: ["a", "b", "c"] }'
        elem = Parser(src).parse().children[0]
        attr = elem.attributes[0]
        assert isinstance(attr.value, list)
        assert len(attr.value) == 3

    def test_remains_list_on_component(self):
        """class: [...] sur un t-call produit un Attribute avec value=list."""
        src = '''import { Button } from "xweb"
component A { Button { class: ["a", "b"] } }
'''
        comp2 = Parser(src).parse().components[0]
        btn_elem = comp2.children[0]
        assert isinstance(btn_elem, Element)
        class_attr = btn_elem.attributes[0]
        assert class_attr.name == "class"
        assert isinstance(class_attr.value, list)

    def test_list_of_dict_literals_does_not_hang(self):
        """Régression réelle (trouvée en écrivant docs_site.dsl) : un item de
        liste qui est un littéral dict (`items: [{"label": ..., "path": ...}]`
        — la forme attendue par xweb.breadcrumbs/xweb.table/xweb.tabs déclarée
        INLINE dans un .dsl) bouclait à l'infini. `_read_expression` s'arrête
        inconditionnellement sur un `{` à profondeur 0 (`{` = début du corps
        d'un élément dans TOUS ses autres appels) et rendait une chaîne vide
        SANS avancer le curseur — `_parse_list` retestait alors éternellement
        le même token `{`, jamais RBRACKET. Un timeout dur (signal.alarm, pas
        de dépendance pytest-timeout) transforme une régression future en
        échec de test net plutôt qu'un pytest qui ne rend jamais la main."""
        import signal

        src = 'div { items: [{"label": "Accueil", "path": "/"}, {"label": "Bits", "path": "/bits"}] }'

        def _on_alarm(signum, frame):
            raise TimeoutError("Parser.parse() n'a pas terminé en 3s — boucle infinie probable")

        old_handler = signal.signal(signal.SIGALRM, _on_alarm)
        signal.alarm(3)
        try:
            elem = Parser(src).parse().children[0]
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old_handler)

        attr = elem.attributes[0]
        assert attr.name == "items"
        assert isinstance(attr.value, list)
        assert len(attr.value) == 2
        assert all(v.quoted is False for v in attr.value)
        assert '"label"' in attr.value[0].value and '"Accueil"' in attr.value[0].value
        assert '"path"' in attr.value[1].value and '"/bits"' in attr.value[1].value


class TestStyleDict:
    """Parsing de style: { prop: "val" }."""

    def test_all_static(self):
        src = 'div { style: { color: "red" padding: "2rem" } }'
        elem = Parser(src).parse().children[0]
        attr = elem.attributes[0]
        assert attr.name == "style"
        assert isinstance(attr.value, dict)
        assert len(attr.value) == 2
        assert attr.value["color"] == AttributeValue(value="red", quoted=True)
        assert attr.value["padding"] == AttributeValue(value="2rem", quoted=True)

    def test_with_expression(self):
        src = 'div { style: { opacity: global_opacity } }'
        elem = Parser(src).parse().children[0]
        attr = elem.attributes[0]
        assert isinstance(attr.value, dict)
        assert attr.value["opacity"].quoted is False
        assert attr.value["opacity"].value == "global_opacity"

    def test_with_interpolation(self):
        src = 'div { style: { color: "${is_urgent and \'a\' or \'b\'}" } }'
        elem = Parser(src).parse().children[0]
        attr = elem.attributes[0]
        assert isinstance(attr.value, dict)
        assert attr.value["color"].quoted is True
        assert "${" in attr.value["color"].value

    def test_kebab_key_must_be_quoted(self):
        """Les clés kebab-case nécessitent des guillemets (le lexer ignore le -)."""
        src = 'div { style: { "background-color": "red" } }'
        elem = Parser(src).parse().children[0]
        attr = elem.attributes[0]
        assert isinstance(attr.value, dict)
        assert "background-color" in attr.value

    def test_multiline(self):
        src = '''div {
    style: {
        color: "red"
        padding: "2rem"
    }
}'''
        elem = Parser(src).parse().children[0]
        attr = elem.attributes[0]
        assert isinstance(attr.value, dict)
        assert len(attr.value) == 2

    def test_mixed_static_and_dynamic(self):
        src = 'div { style: { color: "red" opacity: expr } }'
        elem = Parser(src).parse().children[0]
        attr = elem.attributes[0]
        assert isinstance(attr.value, dict)
        assert attr.value["color"].quoted is True
        assert attr.value["opacity"].quoted is False

    def test_old_style_string_unchanged(self):
        """style: "..." (string) reste un attribut classique (non-dict)."""
        src = 'div { style: "color: red" }'
        elem = Parser(src).parse().children[0]
        attr = elem.attributes[0]
        assert isinstance(attr.value, str)
        assert attr.value == "color: red"


# =============================================================================
# `data` — composition et listes typées
# =============================================================================


class TestDataCompositionAndListTypes:
    """`address: address` (référence), `phones: list[phone]` (liste typée) —
    le parsing porte ces deux formes sur DataField.value_type, avec
    split_value_type() comme classification unique partagée par tous les
    étages (parser, pydantic_bridge, compiler, validators.js)."""

    COMPOSED = textwrap.dedent("""
        data address { street: string @required  city: string @required }
        data contact {
            name: string @required
            address: address
            phones: list[phone]
            tags: list[string]
        }
    """)

    @pytest.fixture()
    def schemas(self):
        return {s.name: s for s in Parser(self.COMPOSED).parse().data_schemas}

    def test_list_of_ref_keeps_the_bracket_type_string(self, schemas):
        field = next(f for f in schemas["contact"].fields if f.name == "phones")
        assert field.value_type == "list[phone]"

    def test_list_of_primitive_keeps_the_bracket_type_string(self, schemas):
        field = next(f for f in schemas["contact"].fields if f.name == "tags")
        assert field.value_type == "list[string]"

    def test_ref_field_is_the_bare_name(self, schemas):
        field = next(f for f in schemas["contact"].fields if f.name == "address")
        assert field.value_type == "address"

    def test_split_value_type_classifies_primitives(self):
        assert split_value_type("string") == ("primitive", "string")
        assert split_value_type("int") == ("primitive", "int")
        assert split_value_type("list") == ("primitive", "list")
        assert split_value_type("dict") == ("primitive", "dict")

    def test_split_value_type_classifies_ref(self):
        assert split_value_type("address") == ("ref", "address")

    def test_split_value_type_classifies_typed_lists(self):
        assert split_value_type("list[phone]") == ("list", "phone")
        assert split_value_type("list[string]") == ("list", "string")

    def test_receive_list_true_is_parsed(self):
        src = """
            endpoint list_contacts { method: GET  url: "/api/contacts"
                receive { type: json  schema: contact  list: true } }
            component test { button { use: list_contacts } }
        """
        ep = Parser(src).parse().endpoints[0]
        assert ep.receive.list is True
        assert ep.receive.schema == "contact"

    def test_receive_list_absent_defaults_to_false(self):
        src = """
            endpoint get_contact { method: GET  url: "/api/contacts/1"
                receive { schema: contact } }
            component test { div { use: get_contact } }
        """
        ep = Parser(src).parse().endpoints[0]
        assert ep.receive.list is False

    def test_receive_list_non_bool_is_a_parse_error(self):
        src = """
            endpoint get_contact { method: GET  url: "/x"
                receive { schema: contact  list: "oui" } }
            component test { div { use: get_contact } }
        """
        with pytest.raises(ParseError, match="list n'accepte que true/false"):
            Parser(src).parse()
