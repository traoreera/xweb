import base64
import hashlib
import re
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from xweb.engine.registry import QwebRegistry
from xweb.security import XWEB_THEME_SCRIPT_HASH, SecurityHeadersMiddleware

COMPONENTS_DIR = Path(__file__).parent.parent / "xweb" / "components"


def make_app(**middleware_kwargs) -> FastAPI:
    app = FastAPI()

    @app.get("/x")
    async def x():
        return {"ok": True}

    app.add_middleware(SecurityHeadersMiddleware, **middleware_kwargs)
    return app


def test_default_is_report_only():
    r = TestClient(make_app()).get("/x")
    assert "Content-Security-Policy-Report-Only" in r.headers
    assert "Content-Security-Policy" not in r.headers
    assert r.headers["X-Frame-Options"] == "DENY"
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"


def test_report_only_false_uses_enforcing_header():
    r = TestClient(make_app(report_only=False)).get("/x")
    assert "Content-Security-Policy" in r.headers
    assert "Content-Security-Policy-Report-Only" not in r.headers


def test_excluded_path_gets_no_security_headers():
    r = TestClient(make_app(exclude_paths=["/x"])).get("/x")
    assert "Content-Security-Policy-Report-Only" not in r.headers
    assert "X-Frame-Options" not in r.headers


def test_theme_script_hash_matches_the_real_rendered_shell():
    """Garde-fou promis dans le docstring de security.py — casse si
    quelqu'un modifie le script anti-flash de xweb/components/shell.xml sans
    régénérer XWEB_THEME_SCRIPT_HASH, plutôt que de laisser un hash
    silencieusement obsolète bloquer ce script en mode CSP enforce."""
    r = QwebRegistry()
    r.register_dir(COMPONENTS_DIR)
    html = r.render("xweb.shell", {"content": "", "nav_tree": [], "app_name": "x", "page_title": "x", "user": None})

    script_text = re.search(r"<script>(.*?)</script>", html, re.DOTALL).group(1)
    digest = hashlib.sha256(script_text.encode("utf-8")).digest()
    real_hash = "sha256-" + base64.b64encode(digest).decode()

    assert real_hash == XWEB_THEME_SCRIPT_HASH, (
        f"XWEB_THEME_SCRIPT_HASH est périmé — régénérer avec {real_hash!r} "
        "après avoir modifié le <script> anti-flash de xweb/components/shell.xml"
    )
    assert "&#39;" not in script_text  # le bug qui a motivé ce test au départ
