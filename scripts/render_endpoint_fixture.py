"""Vecteur de test shared serveur/client pour endpoint `receive` — rend le
DSL composé via le VRAI pipeline (Parser -> Compiler -> QwebRegistry, qui
aplatit les \n des attributs comme dans une vraie page) et écrit le HTML
rendu dans .verify-endpoint-dsl.html, lu ensuite par
scripts/verify-endpoint-dsl.mjs pour exécuter le hyperscript généré dans
jsdom avec le VRAI htmx/_hyperscript/validators.js.

Le DSL porte un schéma COMPOSÉ (address/phone + list[phone]) et un endpoint
qui le valide (`receive { list: true }`), pour prouver aussi la descente
dans l'imbrication coté client — pas juste la règle plate.
"""

from pathlib import Path

from xdsl.api import compile_dsl
from xweb.engine.registry import QwebRegistry

ROOT = Path(__file__).parent.parent

SOURCE = """
data address { street: string @required  city: string @required }
data phone  { number: string @required @pattern("[0-9]+") }
data contact {
    name: string @required
    address: address
}
endpoint list_contacts {
    method: GET
    url: "/api/contacts"
    receive { type: json  schema: contact  list: true  target: "#rows"  event: "contacts:loaded" }
    onsuccess { p { "Contacts chargés" } }
    onerror { p { "Erreur de chargement" } }
}
component test {
    button { use: list_contacts }
    table {
        tbody { id: "rows" }
    }
}
"""

xml = compile_dsl(SOURCE)
reg = QwebRegistry()
reg.register_dir(ROOT / "xweb" / "components")
reg.register_source(xml, filename="<fixture>")
html = reg.render("test", {"csrf_token": "tok"})

(ROOT / ".verify-endpoint-dsl.html").write_text(html, encoding="utf-8")
print("écrit :", ROOT / ".verify-endpoint-dsl.html")
print("longueur:", len(html))