# PDF — export de documents via le même moteur QWeb

Statut : **implémenté**. Voir [spec-v1.md §5](spec-v1.md) — l'autre des
deux points explicitement listés "hors scope v1", avec [i18n](i18n.md).

## Principe

Spec-v1.md §5 posait l'exigence sous la forme « génération PDF via le même
moteur » — c'est-à-dire réutiliser `QwebRegistry.render()` pour produire
le HTML, pas un moteur de template séparé. `xweb/pdf.py::render_pdf()`
fait exactement ça, en deux temps, symétrique de
`render_xweb_template()` ([`xweb/mount.py`](../xweb/mount.py)) :

```python
body = engine.render(template, ctx)          # ex. account.audit_pdf
ctx["content"] = body
html = engine.render("xweb.pdf_document", ctx)  # layout imprimable
pdf_bytes = HTML(string=html).write_pdf()       # WeasyPrint
```

La conversion HTML → PDF elle-même est déléguée à
[WeasyPrint](https://weasyprint.org/) (`weasyprint>=69.0`,
`pyproject.toml`), choisi plutôt que Chromium/Playwright parce que les
bibliothèques système Pango/Cairo dont il dépend étaient déjà présentes
dans cet environnement — pas de navigateur headless à provisionner.

## Pourquoi un layout séparé de `xweb.shell_head`

WeasyPrint implémente CSS 2.1 + une bonne partie de CSS3, mais **pas**
`oklch()`/`color-mix()` ni `@layer` — tous les deux utilisés par
`app.css` (Tailwind v4 + DaisyUI 5, voir [theming.md](theming.md)).
Brancher un export PDF sur `app.css` produirait une page blanche, sans la
moindre erreur au moment du rendu (les règles CSS non comprises sont
silencieusement ignorées — comportement CSS standard, pas un bug
WeasyPrint).

`xweb.pdf_document` ([`xweb/components/pdf.xml`](../xweb/components/pdf.xml)) est
donc un layout indépendant : couleurs hex plates, pas de dark mode (un
document imprimé n'a pas de thème), typographie et bordures suffisantes
pour un tableau lisible. Il porte :

- un en-tête (`page_title`, `app_name`, `generated_at`) ;
- une règle `@page` (format A4, marges, pied de page `counter(page) /
  counter(pages)` — pagination automatique, une fonctionnalité WeasyPrint
  que ni `app.css` ni un navigateur normal n'a besoin de fournir) ;
- `<t t-out="content"/>` pour le contenu, injecté par `render_pdf()`
  exactement comme `xweb.shell`/`xweb.shell_minimal` le font pour une page
  HTML normale.

`generated_at` est **déjà formaté en Python** avant d'entrer dans le
contexte de rendu (`_fmt_dt(datetime.now(timezone.utc).isoformat())` côté
vue) — aucune fonction `datetime`/`strftime` n'est disponible dans une
expression de template (`eval(expr, {"__builtins__": {}}, ctx)`,
[CLAUDE.md](../CLAUDE.md)).

## `render_pdf(engine, template, ctx, *, layout=..., base_url=...)`

- `layout` (défaut `xweb.pdf_document`) enveloppe `template` dans le
  layout PDF ; `layout=None` traite `template` comme un document `<html>`
  déjà complet, sans enveloppe.
- `base_url` — passé tel quel à `weasyprint.HTML(string=..., base_url=...)`,
  utile si un futur export référence des assets relatifs (images, polices).
  Aucun export actuel n'en a besoin (CSS entièrement inline).
- N'importe `weasyprint` qu'à l'appel, jamais à l'import du module : un
  déploiement sans le paquet installé continue de servir le reste de
  l'application. `PdfUnavailable` (sous-classe de `RuntimeError`) est
  levée à la place d'une `ImportError` brute — même politique de
  dégradation gracieuse que le reste de xweb (voir
  [`xweb/i18n.py`](../xweb/i18n.py)).

## Exemple concret : export du journal d'audit

`GET /plugins/account/audit/export.pdf`
([`plugins/account/src/routes.py`](../plugins/account/src/routes.py)) —
bouton « Exporter en PDF » sur la page Audit
([`plugins/account/templates/audit.xml`](../plugins/account/templates/audit.xml)),
visible seulement quand la liste n'est pas vide.

Contrairement à `mount_xweb_page` (qui enveloppe systématiquement dans un
layout **HTML** + `<head>` `app.css`), cette route est une fonction FastAPI
manuelle : la réponse est un fichier binaire (`Content-Type:
application/pdf`, `Content-Disposition: attachment`), pas une page.
Réutilise la même logique de vue que la page HTML
(`audit_ctx(request, user)`, `plugins/account/src/routes.py`) — les deux
partagent exactement les mêmes données, seul le template de sortie diffère
(`account.audit` pour le HTML, `account.audit_pdf` pour le contenu inséré
dans le PDF, [`plugins/account/templates/audit_pdf.xml`](../plugins/account/templates/audit_pdf.xml)) :

- même contrôle de permission que la page HTML (`audit:read` ou
  `admin:*`, via `ctx.has_role()` — pas `require_role()`/
  `XwebPermissionDenied`, cette route n'est pas montée par
  `mount_xweb_page` donc rien n'intercepte l'exception ; un simple `if not
  ctx.has_role(...): return Response(status_code=403)` suffit) ;
  anonyme → redirection login (même `login_redirect()` que le reste du
  pont) ;
- une erreur API dynamique pendant la récupération des entrées (`exc.detail`)
  ne peut pas être encodée dans `?m=<clé>` (clés fixes uniquement, voir
  l'en-tête du module `routes.py`) — la route redirige simplement vers
  `/audit`, qui refait son propre appel et affiche son propre flash
  d'erreur ;
- `PdfUnavailable` (weasyprint non installé) redirige vers `/audit` avec
  `?m=pdf_unavailable`.

## Étendre à un autre écran

Le motif est générique, pas spécifique à l'audit :

1. écrire un template de contenu minimal (pas de shell, pas de classes
   DaisyUI — voir `account.audit_pdf` pour le style attendu : tables HTML
   nues, classes `.pdf-mono`/`.pdf-empty` déjà fournies par
   `xweb.pdf_document`) ;
2. une route qui réutilise la même fonction de vue que la page HTML
   correspondante, appelle `render_pdf(engine, "mon_plugin.mon_export_pdf",
   ctx)`, et renvoie un `Response(content=pdf_bytes,
   media_type="application/pdf", headers={"Content-Disposition": ...})` ;
3. un bouton `hx-boost="false"` (téléchargement de fichier, pas une
   navigation htmx) sur la page HTML source.

## Tests

- [`tests/test_pdf.py`](../tests/test_pdf.py) — `render_pdf()` en
  isolation, contre le vrai paquet `weasyprint` (jamais mocké, même
  politique que `npm run verify:hyperscript`/`verify:demo` : vérifier pour
  de vrai) : produit de vrais octets `%PDF-`, applique bien le layout par
  défaut (le PDF varie avec `page_title`, que `test.pdf_content` seul
  n'utilise jamais — preuve que le wrapping a eu lieu, une comparaison de
  sous-chaîne étant impossible sur un flux PDF compressé FlateDecode),
  `layout=None` traite le template comme document complet, dégrade en
  `PdfUnavailable` si l'import échoue.
- [`tests/test_account_extended.py`](../tests/test_account_extended.py) —
  `/plugins/account/audit/export.pdf` : vrai PDF renvoyé avec les bons
  en-têtes pour un propriétaire de tenant, 403 pour un membre sans
  `audit:read`, redirection login pour un visiteur anonyme.

## Voir aussi

[i18n.md](i18n.md) — l'autre point listé "hors scope v1" dans
[spec-v1.md §5](spec-v1.md), traité dans la même vague de travail.
