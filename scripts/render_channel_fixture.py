"""Compile un composant xdsl utilisant `channel`/`use_channel:` et écrit le
HTML rendu dans .verify-channel-dsl.html, lu ensuite par
scripts/verify-channel-dsl.mjs (jsdom) — même esprit que
render_editable_table_fixture.py : le HTML testé en JS doit venir du VRAI
pipeline xdsl -> QWeb -> QwebRegistry, jamais retapé à la main côté Node.
"""

import textwrap
from pathlib import Path

from xweb.engine.registry import QwebRegistry

from xdsl.api import compile_dsl

ROOT = Path(__file__).parent.parent

SRC = textwrap.dedent("""
    data contact_form {
        count: int @min(0)
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
            bind: { "#counter": "count" }
        }
    }

    component channel_demo {
        div {
            use_channel: contacts_feed
            span { id: "counter"  "0" }
            div { id: "contacts-table"  "table" }
        }
    }
""")

xml = compile_dsl(SRC, filename="channel_demo.dsl")

registry = QwebRegistry()
registry.register_source(f"<templates>\n{xml}\n</templates>", filename="<channel_demo>")
html = registry.render("channel_demo", {})

(ROOT / ".verify-channel-dsl.html").write_text(html, encoding="utf-8")
print("écrit :", ROOT / ".verify-channel-dsl.html", f"({len(html)} octets)")
