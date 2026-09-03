"""Email — génération HTML via le même moteur QWeb (docs/email.md,
docs/spec-v1.md §5). Symétrique de `xweb/pdf.py::render_pdf()` : même
schéma en deux temps (rendre le contenu, l'injecter dans un layout dédié),
mêmes raisons de garder le layout indépendant d'`app.css`.

Ce module ne SAIT PAS envoyer d'email — seulement en produire le HTML. Le
transport reste le contrat `ext.email` déjà utilisé ailleurs dans ce projet
(`extensions/email.py::ConsoleEmailExtension` en dev — `async def
send(to, subject, body, is_html)` / `def queue(...)`), jamais réinventé ici.

`plugins/auth` a son propre système d'email HTML (Jinja2,
`plugins/auth/src/services/email/base.py`, `data/templates/*.html`) —
plugin séparé, auto-contenu, avec ses propres templates déjà en
production dans ce projet. Ce module ne le remplace pas (le retoucher
serait un vrai changement de plugin, pas une extension de xweb) — il
comble le point que spec-v1.md §5 visait réellement : que QWeb, le moteur
de xweb, PUISSE aussi produire un email, pour tout code qui passe par
xweb (n'importe quel plugin qui utilise déjà QwebRegistry pour ses pages),
pas seulement du HTML/PDF. Exemple concret : `plugins/demo` (docs/email.md).
"""

from __future__ import annotations

from typing import Any

EMAIL_LAYOUT = "xweb.email_layout"


def render_email(
    engine: Any,
    template: str,
    ctx: dict[str, Any] | None = None,
    *,
    layout: str | None = EMAIL_LAYOUT,
) -> str:
    """Rend `template` avec `engine.render()` — le même `QwebRegistry` que
    toute page HTML de l'application ("même moteur", docs/spec-v1.md §5) —
    puis l'enveloppe dans `xweb.email_layout` : une mise en page à base de
    `<table>`, CSS entièrement inline (`components/email.xml`). Aucun
    `<style>`/`app.css` — de nombreux clients mail (Outlook en tête)
    suppriment les balises `<style>` ou n'appliquent pas Flexbox/Grid ; un
    tableau + attributs `style="..."` inline est le seul dénominateur
    commun qui tienne à peu près partout, exactement pour la même raison
    que `xweb.pdf_document` n'utilise jamais `app.css` (WeasyPrint ne
    comprend pas `oklch()`/`@layer` — voir `xweb/pdf.py`).

    `layout=None` traite `template` comme un document `<html>` déjà
    complet, sans enveloppe — même paramètre, même sens que dans
    `xweb/pdf.py::render_pdf()`.

    Retourne du HTML, jamais n'envoie quoi que ce soit — voir la docstring
    du module pour le contrat de transport (`ext.email`)."""
    ctx_dict = dict(ctx or {})
    body = engine.render(template, ctx_dict)
    if layout:
        ctx_dict["content"] = body
        return engine.render(layout, ctx_dict)
    return body
