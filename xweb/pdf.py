"""PDF — génération de documents PDF via le même moteur QWeb que le rendu
HTML (docs/pdf.md, docs/spec-v1.md §5).

Un export PDF suit le même schéma en deux temps que `render_xweb_template`
(`xweb/mount.py`) : le template "de contenu" est rendu une première fois,
son HTML est injecté dans `ctx["content"]`, puis le LAYOUT PDF
(`xweb.pdf_document`, `xweb/components/pdf.xml`) est rendu à son tour — sauf que
le layout PDF est un document HTML minimal avec sa propre feuille de style
inline, jamais `xweb.shell_head` : WeasyPrint ne supporte ni les couleurs
`oklch()`/`color-mix()` ni `@layer` (Tailwind v4) — réutiliser `app.css`
produirait une page blanche silencieuse plutôt qu'une erreur visible.

`render_pdf()` ne dépend de `weasyprint` qu'à l'appel, jamais à l'import de
ce module : un déploiement sans le paquet installé continue de servir le
reste de l'application, seule la route qui exporte un PDF répond via
`PdfUnavailable` (fallback gracieux, même philosophie que le reste de
xweb — voir `xweb/i18n.py`).
"""

from __future__ import annotations

from typing import Any

PDF_LAYOUT = "xweb.pdf_document"


class PdfUnavailable(RuntimeError):
    """weasyprint n'est pas installé (`uv add weasyprint`) — levée à
    l'appel de `render_pdf()`, jamais à l'import de ce module."""


def render_pdf(
    engine: Any,
    template: str,
    ctx: dict[str, Any] | None = None,
    *,
    layout: str | None = PDF_LAYOUT,
    base_url: str | None = None,
) -> bytes:
    """Rend `template` avec `engine.render()` — le même `QwebRegistry` que
    toute page HTML de l'application ("même moteur", docs/spec-v1.md §5) —
    puis convertit le HTML obtenu en PDF via WeasyPrint.

    `layout` enveloppe le contenu dans `xweb.pdf_document` (en-tête titre +
    style imprimable) ; passer `layout=None` pour convertir `template` tel
    quel, sans enveloppe, quand il s'agit déjà d'un document `<html>`
    complet."""
    try:
        from weasyprint import HTML
    except ImportError as exc:
        raise PdfUnavailable("weasyprint n'est pas installé — `uv add weasyprint`.") from exc

    ctx_dict = dict(ctx or {})
    body = engine.render(template, ctx_dict)
    if layout:
        ctx_dict["content"] = body
        html = engine.render(layout, ctx_dict)
    else:
        html = body
    return HTML(string=html, base_url=base_url).write_pdf()
