"""Round-trip AST <-> JSON (xdsl/serialize.py) — contrat No-Code.

Chaque nœud porte un discriminant ``"type"`` ; la désérialisation doit
redonner EXACTEMENT les dataclasses du parser (champs enfants inclus —
les listes d'enfants de ComponentDef/Element/IfBlock/ForLoop/XpathPatch/
CopyDef, et les tuples elif), faute de quoi l'éditeur .xdsl.json écrit un
arbre qui ne se recompile pas à l'identique.
"""

import textwrap

import pytest

from xdsl.compiler import Compiler
from xdsl.parser import Parser
from xdsl.serialize import ast_from_json, ast_to_json

ROOT_SRC = textwrap.dedent(
    """\
    component test.cards {
        import { button } from "xweb"
        import { badge } from "./local"
        props: {
            title: "Défaut"
            count: 0
        }
        style: ".title { color: red; }"
        title ?= "Titre"

        if (count > 0) {
            button { label: count; class: ["btn", expr] }
        } elif (count == 0) {
            badge { text: "vide" }
        } else {
            span { "rien" }
        }

        for item in items {
            div { class: "card"
                p { slot }
                p { raw item }
            }
        }
    }

    patch xweb.form {
        xpath "//button" { inside: div { class: "helper" } }
    }

    copy xweb.form as auth.login_form {
        xpath "//button" { attributes: a { data-copied: "true" } }
    }
    """
)


def _roundtrip(source: str):
    ast = Parser(source).parse()
    back = ast_from_json(ast_to_json(ast))
    assert back == ast, "round-trip AST<>JSON doit restituer l'AST à l'identique"
    return ast, back


def test_roundtrip_all_node_types():
    """Couvre Import, Props, Style, Assignment, IfBlock + elif/else,
    ForLoop, Element + Attributs (dynamiques, class-list, textes), Slot,
    PatchDef + XpathPatch (Position), CopyDef."""
    ast, back = _roundtrip(ROOT_SRC)
    assert len(ast.components) == 1
    assert len(ast.patches) == 1
    assert len(ast.copies) == 1
    ifblock = ast.components[0].children[1]
    assert len(ifblock.elif_blocks) == 1
    assert len(ifblock.else_children) == 1
    assert list(back.components[0].children[1].elif_blocks[0][1]) == list(
        ifblock.elif_blocks[0][1]
    )


def test_roundtrip_compile_identical():
    """La réhydratation recompile vers le MÊME XML que l'AST d'origine —
    la garantie qui compte pour l'éditeur No-Code."""
    ast = Parser(ROOT_SRC).parse()
    back = ast_from_json(ast_to_json(ast))
    assert Compiler(back).compile() == Compiler(ast).compile()


def test_roundtrip_login_dsl():
    """Le fichier de démo réel (imports dotted, rectangles stylés,
    class-list, prop id/name sur chaque input)."""
    with open("login.dsl", encoding="utf-8") as f:
        source = f.read()
    _roundtrip(source)


def test_missing_type_is_rejected():
    from xdsl.serialize import ast_from_dict

    with pytest.raises(ValueError, match="sans champ 'type'"):
        ast_from_dict({"components": []})


def test_capsule_roundtrip(tmp_path):
    """Écriture et relecture du format `.xdsl.json` (capsule
    avec version) depuis xdsl/api.py — le XML recompilé doit
    rester identique au passage par le fichier."""
    from xdsl.api import compile_dsl, compile_json_file, dump_dsl_json, dsl_to_json

    src = open("login.dsl", encoding="utf-8").read()
    xml_ref = compile_dsl(src, "login.dsl")
    capsule = dsl_to_json(src, filename="login.dsl")

    p = tmp_path / "login.xdsl.json"
    dump_dsl_json(src, p, filename="login.dsl")
    assert p.exists()

    # Le JSON lu depuis le fichier doit recompiler vers le MÊME XML.
    assert compile_json_file(p) == xml_ref

    # Vérification de la version et du format.
    import json
    data = json.loads(p.read_text())
    assert data["format"] == "xdsl.json"
    assert data["version"] == 1


def test_capsule_rejects_wrong_format():
    from xdsl.api import json_to_xml

    with pytest.raises(ValueError, match="format attendu"):
        json_to_xml('{"format": "wrong", "version": 1, "ast": {}}')


def test_capsule_rejects_wrong_version():
    from xdsl.api import json_to_xml

    with pytest.raises(ValueError, match="Version.*non supportée"):
        json_to_xml('{"format": "xdsl.json", "version": 999, "ast": {}}')


def test_unknown_type_is_rejected():
    from xdsl.serialize import ast_from_dict

    with pytest.raises(ValueError, match="Type de nœud JSON inconnu"):
        ast_from_dict({"type": "mystere"})


def test_data_and_endpoint_roundtrip():
    """Régression réelle trouvée en écrivant ce test : DataField.type et
    ReceiveSpec.type portaient le même nom que la clé discriminante
    "type" du sérialiseur — la sérialisation écrasait silencieusement le
    discriminant de nœud avec la valeur du champ, cassant la
    désérialisation (AttributeError: 'dict' object has no attribute
    'target'). Renommés en value_type/kind — voir leurs docstrings dans
    xdsl/parser.py. Ce test couvre spécifiquement ce piège : sans lui, un
    futur champ nommé `type` sur un nœud xdsl le referait en silence."""
    src = textwrap.dedent("""
        import { toast } from "xweb"

        data contact_form {
            name: string @required @min_length(3)
            role: string @in(["admin", "editor"])
        }

        endpoint save_contact {
            method: POST
            url: "/api/contacts"
            send: contact_form
            headers: { "Content-Type": "application/json" }
            auth: cookie
            receive { type: json  schema: contact_form  target: "#t"  event: "done" }
            onloading { p { "..." } }
            onsuccess { toast { "OK" } }
            onerror { toast { "KO" } }
        }

        component test {
            form { use: save_contact }
        }
    """)
    ast1 = Parser(src).parse()
    xml_ref = Compiler(ast1).compile()

    ast2 = ast_from_json(ast_to_json(ast1))
    assert Compiler(ast2).compile() == xml_ref

    # Les valeurs elles-mêmes ont bien survécu, pas juste la recompilation.
    schema = ast2.data_schemas[0]
    assert schema.fields[0].decorators[1] == ["min_length", [3]] or schema.fields[0].decorators[1] == (
        "min_length",
        [3],
    )
    ep = ast2.endpoints[0]
    assert ep.receive.kind == "json"
    assert ep.receive.target == "#t"
    assert ep.auth == "cookie"


def test_channel_roundtrip():
    """`channel { }` / `use_channel:` — même piège potentiel que le test
    ci-dessus (ChannelOnMessage.bindings est un list[tuple[str, str]],
    comme DataField.decorators) : on compare la recompilation, pas
    l'égalité stricte des dataclasses (un tuple round-trippe en liste via
    JSON, `("a", "b") != ["a", "b"]`)."""
    src = textwrap.dedent("""
        data contact_form {
            name: string @required @min_length(3)
        }

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

        component test {
            div { use_channel: contacts_feed
                span { id: "counter"  "0" }
            }
        }
    """)
    ast1 = Parser(src).parse()
    xml_ref = Compiler(ast1).compile()

    ast2 = ast_from_json(ast_to_json(ast1))
    assert Compiler(ast2).compile() == xml_ref

    ch = ast2.channels[0]
    assert ch.name == "contacts_feed"
    assert ch.url == "/stream"
    assert list(ch.channels) == ["chat", "notif"]
    assert ch.transport == "sse"
    assert ch.connect_timeout_ms == 5000
    assert ch.validate == "contact_form"
    assert ch.persist == "last_contact"
    assert ch.onmessage.dispatch is True
    assert ch.onmessage.refresh == "#contacts-table"
    assert ch.onmessage.event == "contacts:changed"
    assert [tuple(b) for b in ch.onmessage.bindings] == [("#counter", "count")]


def test_composed_data_and_receive_list_roundtrip():
    """Régression ciblant les ajouts de la composition : `list[phone]`
    (DataField.value_type devient `list[phone]`) et `receive { list: true }`
    (ReceiveSpec.list) doivent SURVIVRE au .xdsl.json — recompilation
    identique ET valeurs désérialisées correctes."""
    src = textwrap.dedent("""
        data address { street: string @required  city: string @required }
        data phone  { number: string @required @pattern("[0-9]+") }
        data contact {
            name: string @required
            address: address
            phones: list[phone]
            tags: list[string]
        }

        endpoint list_contacts {
            method: GET
            url: "/api/contacts"
            receive { type: json  schema: contact  target: "#rows"  event: "contacts:loaded"  list: true }
            onsuccess { p { "Contacts chargés" } }
            onerror { p { "Erreur" } }
        }

        component test {
            button { use: list_contacts }
        }
    """)
    ast1 = Parser(src).parse()
    xml_ref = Compiler(ast1).compile()

    ast2 = ast_from_json(ast_to_json(ast1))
    assert Compiler(ast2).compile() == xml_ref

    fields = {f.name: f.value_type for f in ast2.data_schemas[2].fields}
    assert fields["address"] == "address"
    assert fields["phones"] == "list[phone]"
    assert fields["tags"] == "list[string]"
    ep = ast2.endpoints[0]
    assert ep.receive.schema == "contact"
    assert ep.receive.list is True


def test_capsule_signature_roundtrip():
    """La capsule générée par dsl_to_json contient une signature HMAC
    et json_to_ast la vérifie — round-trip complet signature incluse."""
    import os
    from xdsl.api import dsl_to_json, json_to_ast
    os.environ["XDSL_CAPSULE_SECRET"] = "test-secret"
    os.environ["XDSL_CAPSULE_AUTHOR"] = "test-author"

    src = textwrap.dedent("""
        component test {
            button { label: "OK" }
        }
    """)
    capsule_json = dsl_to_json(src, filename="test.dsl")
    import json
    data = json.loads(capsule_json)
    assert data["format"] == "xdsl.json"
    assert data["version"] == 1
    assert data["author"] == "test-author"
    assert "signature" in data
    assert isinstance(data["signature"], str) and len(data["signature"]) == 64  # SHA256 hex

    # json_to_ast vérifie la signature et recompile
    ast = json_to_ast(capsule_json)
    xml = Compiler(ast).compile()
    assert "OK" in xml


def test_capsule_unsigned_rejected():
    """Une capsule sans signature est refusée par json_to_ast."""
    import os
    import json
    from xdsl.api import json_to_ast
    os.environ["XDSL_CAPSULE_SECRET"] = "test-secret"
    os.environ["XDSL_CAPSULE_AUTHOR"] = "test-author"

    capsule_no_sig = json.dumps({
        "format": "xdsl.json",
        "version": 1,
        "author": "test-author",
        "filename": "test.dsl",
        "ast": {"type": "Module", "components": [], "patches": [], "copies": []}
    })

    capsule_no_sig = json.dumps({
        "format": "xdsl.json",
        "version": 1,
        "author": "test-author",
        "filename": "test.dsl",
        "ast": {"type": "Module", "components": [], "patches": [], "copies": []}
    })

    with pytest.raises(ValueError, match="non signée"):
        json_to_ast(capsule_no_sig)


def test_capsule_tampered_rejected():
    """Une capsule altérée (signature invalide) est refusée."""
    import os
    import json
    from xdsl.api import dsl_to_json, json_to_ast
    os.environ["XDSL_CAPSULE_SECRET"] = "test-secret"
    os.environ["XDSL_CAPSULE_AUTHOR"] = "test-author"

    src = textwrap.dedent("""
        component test {
            button { label: "OK" }
        }
    """)
    capsule_json = dsl_to_json(src, filename="test.dsl")
    data = json.loads(capsule_json)
    # Altérer l'AST (changer le label du button)
    data["ast"]["components"][0]["children"][0]["attributes"][0]["value"] = "TAMPERED"
    tampered = json.dumps(data)

    with pytest.raises(ValueError, match="Signature HMAC.*invalide"):
        json_to_ast(tampered)


def test_capsule_wrong_secret_rejected():
    """Une capsule signée avec une clé différente est refusée."""
    import os
    from xdsl.api import dsl_to_json, json_to_ast
    os.environ["XDSL_CAPSULE_SECRET"] = "secret-A"
    os.environ["XDSL_CAPSULE_AUTHOR"] = "test-author"

    src = textwrap.dedent("""
        component test {
            button { label: "OK" }
        }
    """)
    capsule_json = dsl_to_json(src, filename="test.dsl")

    # Changer la clé pour la vérification
    os.environ["XDSL_CAPSULE_SECRET"] = "secret-B"

    with pytest.raises(ValueError, match="Signature HMAC.*invalide"):
        json_to_ast(capsule_json)