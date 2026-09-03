"""xweb.kanban — xweb/components/kanban.xml (docs/components.md).

La mécanique de glisser-déposer elle-même (_hyperscript : dragstart/
dragover/drop, `put ... at end of ...`) est vérifiée pour de vrai contre le
fichier vendorisé dans scripts/verify-hyperscript.mjs (jsdom) — pas ici,
Python n'exécute aucun _hyperscript. Ici : le rendu (props, structure,
dégradation) et l'exemple concret plugins/demo (page + persistance de
/plugins/demo/kanban/move) via un vrai cycle ASGI.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from xweb.engine.registry import QwebRegistry

ROOT = Path(__file__).parent.parent
COMPONENTS_DIR = ROOT / "xweb" / "components"


@pytest.fixture
def registry() -> QwebRegistry:
    r = QwebRegistry()
    r.register_dir(COMPONENTS_DIR)
    return r


# ---------------------------------------------------------------------
# xweb.kanban en isolation
# ---------------------------------------------------------------------


def test_kanban_renders_one_column_per_entry_with_its_cards(registry):
    html = registry.render("xweb.kanban", {
        "columns": [
            {"id": "todo", "title": "À faire", "cards": [{"id": "c1", "title": "Une tâche"}]},
            {"id": "done", "title": "Fait", "cards": []},
        ],
        "move_url": "/x/move",
    })
    assert 'data-column-id="todo"' in html
    assert 'data-column-id="done"' in html
    assert "À faire" in html and "Fait" in html
    assert 'id="c1"' in html
    assert "Une tâche" in html


def test_kanban_card_id_becomes_the_dom_id_for_hyperscript_getelementbyid(registry):
    """xweb/components/kanban.xml — document.getElementById(draggedId) au
    drop retrouve la carte PAR SON id DOM, qui doit donc être card['id']
    tel quel, pas un id généré ou préfixé."""
    html = registry.render("xweb.kanban", {
        "columns": [{"id": "a", "title": "A", "cards": [{"id": "unique-42", "title": "x"}]}],
    })
    assert 'id="unique-42"' in html


def test_kanban_card_subtitle_is_optional(registry):
    html = registry.render("xweb.kanban", {
        "columns": [{"id": "a", "title": "A", "cards": [{"id": "c1", "title": "Sans sous-titre"}]}],
    })
    assert "Sans sous-titre" in html
    with_sub = registry.render("xweb.kanban", {
        "columns": [{"id": "a", "title": "A", "cards": [{"id": "c1", "title": "x", "subtitle": "Un détail"}]}],
    })
    assert "Un détail" in with_sub


def test_kanban_omits_hx_post_when_move_url_is_empty(registry):
    """move_url='' (défaut) -> visuel seulement, pas d'appel serveur —
    t-att-hx-post="move_url or None" n'émet rien pour une valeur falsy
    (xweb/engine/compiler.py::_render_attrs)."""
    html = registry.render("xweb.kanban", {
        "columns": [{"id": "a", "title": "A", "cards": [{"id": "c1", "title": "x"}]}],
    })
    assert "hx-post" not in html


def test_kanban_sets_hx_post_to_move_url_when_given(registry):
    html = registry.render("xweb.kanban", {
        "columns": [{"id": "a", "title": "A", "cards": [{"id": "c1", "title": "x"}]}],
        "move_url": "/plugins/demo/kanban/move",
    })
    assert 'hx-post="/plugins/demo/kanban/move"' in html


def test_kanban_with_no_columns_renders_an_empty_board_not_a_crash(registry):
    html = registry.render("xweb.kanban", {})
    assert "kanban" in html
    assert "kanban-column" not in html


# ---------------------------------------------------------------------
# plugins/demo — page + persistance réelle de /kanban/move (cycle ASGI)
# ---------------------------------------------------------------------


def load_demo_pkg():
    src = ROOT / "plugins" / "demo" / "src"
    if "demo_kanban_test_src" not in sys.modules:
        pkg = types.ModuleType("demo_kanban_test_src")
        pkg.__path__ = [str(src)]
        sys.modules["demo_kanban_test_src"] = pkg
    return __import__("demo_kanban_test_src.main", fromlist=["main"])


class FakePluginCtx:
    name = "demo"
    tenant_id = None
    caller = None

    def get_service(self, name):
        return None


@pytest.fixture
def demo_client(monkeypatch):
    # mount_xweb_page résout l'utilisateur courant via le vrai xcore
    # (xcore.kernel.api.rbac._resolve_user, qui exige un backend d'auth
    # chargé) — même contournement que tests/test_i18n.py/test_mount.py :
    # visiteur anonyme, ce que cette page publique de démo accepte de toute
    # façon (pas de ctx.require_user()/require_role() dessus).
    async def fake_resolve(request):
        return None

    monkeypatch.setattr("xweb.context.resolve_user_or_anonymous", fake_resolve)

    main_mod = load_demo_pkg()
    # Repartir d'un plateau frais à chaque test — _KANBAN_BOARD est un état
    # de MODULE partagé (comme en vrai, docs/components.md#xweb.kanban) ;
    # sans ce reset un test influencerait le suivant.
    import copy
    fresh = copy.deepcopy(main_mod._KANBAN_BOARD)
    monkeypatch.setattr(main_mod, "_KANBAN_BOARD", fresh)

    registry = QwebRegistry()
    registry.register_dir(COMPONENTS_DIR)
    registry.register_dir(ROOT / "plugins" / "demo" / "templates", source_plugin="demo")

    class Ctx:
        def get_service(self, name):
            return types.SimpleNamespace(engine=registry) if name == "ext.xweb" else None

    plugin = main_mod.Plugin()
    plugin.ctx = Ctx()
    router: APIRouter = plugin.get_router()

    app = FastAPI()
    app.include_router(router, prefix="/plugins/demo")
    return TestClient(app), main_mod


def test_kanban_page_renders_the_seeded_board(demo_client):
    client, _ = demo_client
    r = client.get("/plugins/demo/kanban")
    assert r.status_code == 200
    assert "kanban-column" in r.text
    assert "Écrire les specs" in r.text


def test_kanban_move_persists_the_card_in_the_new_column(demo_client):
    client, main_mod = demo_client
    # kc-1 part de "todo" -> déplacé vers "done"
    r = client.post("/plugins/demo/kanban/move", data={"card_id": "kc-1", "column_id": "done"})
    assert r.status_code == 204
    assert any(c["id"] == "kc-1" for c in main_mod._KANBAN_BOARD["done"]["cards"])
    assert not any(c["id"] == "kc-1" for c in main_mod._KANBAN_BOARD["todo"]["cards"])
    # Vraie persistance -> une deuxième requête (nouvelle page) voit le changement
    r2 = client.get("/plugins/demo/kanban")
    assert r2.status_code == 200


def test_kanban_move_with_unknown_card_id_is_a_noop_not_an_error(demo_client):
    client, main_mod = demo_client
    before = copy_state = {k: len(v["cards"]) for k, v in main_mod._KANBAN_BOARD.items()}
    r = client.post("/plugins/demo/kanban/move", data={"card_id": "does-not-exist", "column_id": "done"})
    assert r.status_code == 204
    after = {k: len(v["cards"]) for k, v in main_mod._KANBAN_BOARD.items()}
    assert before == after


def test_kanban_move_with_unknown_column_id_is_a_noop_not_an_error(demo_client):
    client, main_mod = demo_client
    r = client.post("/plugins/demo/kanban/move", data={"card_id": "kc-1", "column_id": "nowhere"})
    assert r.status_code == 204
    assert any(c["id"] == "kc-1" for c in main_mod._KANBAN_BOARD["todo"]["cards"])
