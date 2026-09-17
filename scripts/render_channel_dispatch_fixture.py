"""Compile un composant xdsl avec DEUX `channel` (un SSE, un WS), tous deux
`onmessage { dispatch: true }`, chacun écouté par du VRAI hyperscript (`_:
on ... from document`) — écrit le HTML rendu dans
.verify-channel-dispatch.html, lu ensuite par
scripts/verify-channel-dispatch.mjs (jsdom + vrai htmx.min.js + vrai
_hyperscript.min.js + vrai live_channel.js, contre
scripts/live_channel_test_server.py). Même esprit que
render_channel_fixture.py : le HTML testé en JS doit venir du VRAI pipeline
xdsl -> QWeb -> QwebRegistry.
"""

import textwrap
from pathlib import Path

from xweb.engine.registry import QwebRegistry

from xdsl.api import compile_dsl

ROOT = Path(__file__).parent.parent

SRC = textwrap.dedent("""
    channel chat_sse {
        url: "http://127.0.0.1:8931/stream"
        channels: ["chat"]
        transport: "sse"
        onmessage {
            dispatch: true
            event: "chat_sse:message"
        }
    }

    channel notif_ws {
        url: "ws://127.0.0.1:8931/ws"
        channels: ["notif"]
        transport: "ws"
        onmessage {
            dispatch: true
            event: "notif_ws:message"
        }
    }

    component dispatch_demo {
        div {
            use_channel: chat_sse
            div {
                id: "sse-log"
                _ {
                    on chat_sse:message from document
                        if event.detail.channel is 'chat'
                            put event.detail.data.text into me
                        end
                }
            }
        }
        div {
            use_channel: notif_ws
            div {
                id: "ws-log"
                _ {
                    on notif_ws:message from document
                        put event.detail.data.count into me
                }
            }
        }
    }
""")

xml = compile_dsl(SRC, filename="channel_dispatch_demo.dsl")

registry = QwebRegistry()
registry.register_source(f"<templates>\n{xml}\n</templates>", filename="<channel_dispatch_demo>")
html = registry.render("dispatch_demo", {})

(ROOT / ".verify-channel-dispatch.html").write_text(html, encoding="utf-8")
print("écrit :", ROOT / ".verify-channel-dispatch.html", f"({len(html)} octets)")
