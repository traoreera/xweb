"""En-têtes de sécurité de base pour l'app hôte.

Porté depuis xui/security.py — la mécanique du middleware ne change pas,
mais son contenu (CSP) doit être revérifié pour la pile xweb, pas
recopié tel quel :

  - xui accordait `'unsafe-eval'` à `script-src` parce qu'Alpine.js
    évalue des expressions via eval/new Function. La quasi-totalité des
    attributs `hx-*` n'a pas ce besoin (docs/language.md, `studio/xweb/assets/
    htmx.meta.yaml` — ce sont des requêtes serveur/déclencheurs/swaps,
    jamais du JS évalué depuis un attribut) — **sauf `hx-on-*`**
    (`hx-on-click="…"`, forme tiret ; la forme `hx-on:click` avec `:`
    ne parse même pas dans ce moteur, `etree.fromstring` la rejette comme
    préfixe de namespace XML non déclaré, testé directement contre lxml),
    qui appelle bien `new Function("event", …)` — vérifié en le faisant
    tourner pour de vrai contre `xweb/static/htmx.min.js` en jsdom. Aucun
    template de ce dépôt n'utilise `hx-on-*` aujourd'hui (grep vérifié),
    donc ça ne force rien ici, mais l'affirmation "htmx n'a pas ce besoin"
    était fausse pour cette famille précise d'attribut — voir
    `studio/xweb/assets/htmx.meta.yaml` (`forbidden_families`) pour pourquoi le
    Studio la refuse plutôt que de la lister comme un attribut hx-* de
    plus. `_hyperscript`, de son côté, interprète sa propre DSL au
    runtime et a probablement un besoin similaire à `'unsafe-eval'` —
    **non vérifié contre sa documentation**, à confirmer avant de retirer
    `'unsafe-eval'` d'ici.
  - Le hash SHA-256 du script inline anti-flash de thème est calculé
    (`XWEB_THEME_SCRIPT_HASH` ci-dessous) contre le texte réellement rendu
    de `xweb/components/shell.xml`, pas deviné depuis le source — un vrai bug
    de compilateur trouvé en le calculant : `escape()` transformait `'`
    en `&#39;` dans le `<script>`, qu'un navigateur exécute littéralement
    (SyntaxError) puisque `<script>`/`<style>` ne décodent jamais les
    entités HTML (corrigé dans `engine/compiler.py`, `_RAW_TEXT_TAGS`).
    `test_security.py::test_theme_script_hash_matches_the_real_rendered_shell`
    casse si le script change sans que ce hash soit régénéré. Le nom de la
    constante date d'avant que ce même script anti-flash ne porte AUSSI
    l'état replié/déplié de la sidebar (docs/shell.md) — un seul `<script>`
    inline dans `xweb.shell_head`, un seul hash à maintenir, jamais renommé
    depuis pour éviter de casser les imports existants sans bénéfice réel.

`report_only=True` reste le défaut prudent, comme dans xui : à l'app
hôte de décider quand passer en mode enforce (`report_only=False`).
"""

from __future__ import annotations

from typing import Sequence

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

# sha256 du texte exact du <script> anti-flash dans xweb/components/shell.xml
# (docs/theming.md#bascule-côté-client) — recalculer si ce script change,
# voir test_security.py pour la procédure et le garde-fou.
XWEB_THEME_SCRIPT_HASH = "sha256-sFZmuJND1Rv3DCIDxo/AdqToolUoyy6nf4XqE52s4G8="

DEFAULT_CSP = (
    "default-src 'self'; "
    f"script-src 'self' 'unsafe-eval' '{XWEB_THEME_SCRIPT_HASH}'; "  # voir docstring — _hyperscript non confirmé
    "style-src-elem 'self'; "
    "style-src-attr 'unsafe-inline'; "  # DaisyUI + t-attf-style dynamiques, même situation que xui
    "img-src 'self' data:; "
    "connect-src 'self'; "
    "object-src 'none'; "
    "frame-ancestors 'none'; "
    "base-uri 'self'"
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Ajoute les en-têtes de sécurité minimaux à chaque réponse.

    Args:
        report_only: mode Content-Security-Policy-Report-Only (surveille
            sans bloquer) — à passer False en production.
        exclude_paths: préfixes de chemins non couverts.
        csp: directive CSP (défaut DEFAULT_CSP).
    """

    def __init__(
        self,
        app,
        report_only: bool = True,
        exclude_paths: Sequence[str] = (),
        csp: str = DEFAULT_CSP,
    ) -> None:
        super().__init__(app)
        self._header = "Content-Security-Policy-Report-Only" if report_only else "Content-Security-Policy"
        self._csp = csp
        self._excluded = tuple(exclude_paths)

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        if any(request.url.path.startswith(p) for p in self._excluded):
            return response
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault(self._header, self._csp)
        return response
