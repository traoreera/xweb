# Email — génération HTML via le même moteur QWeb

Statut : **implémenté**. Voir [spec-v1.md §5](spec-v1.md) — le troisième
des trois points listés "hors scope v1" (avec [i18n](i18n.md) et
[PDF](pdf.md)).

## Ce que ça couvre, et ce que ça ne couvre pas

spec-v1.md §5 posait l'exigence sous la forme « génération PDF/**email**
via le même moteur ». `xweb/email.py::render_email()` réalise exactement
ça pour ce que xweb contrôle directement — mais **`plugins/auth` a déjà
son propre système d'email HTML**, complet et en production dans ce
projet :

- Jinja2, pas QWeb (`plugins/auth/src/services/email/base.py::_render()`) ;
- templates dans `plugins/auth/data/templates/*.html` ;
- utilisé pour tous les emails réellement envoyés par le pont d'auth
  (inscription, réinitialisation de mot de passe, invitations —
  `plugins/auth/src/services/email/senders/`).

Ce module ne remplace **pas** ce système — `plugins/auth` est un plugin
séparé, auto-contenu, avec ses propres dépendances (voir "Python
dependency layout" dans [CLAUDE.md](../CLAUDE.md)) ; réécrire son moteur
d'email interne serait un vrai changement de plugin, pas une extension de
xweb. Ce que `xweb/email.py` apporte, c'est la **capacité** — pour
n'importe quel plugin qui utilise déjà `QwebRegistry` (donc n'importe quel
plugin `xweb`, `plugins/demo` et `plugins/account` compris) de produire un
email en HTML sans sortir du moteur qu'il utilise déjà pour ses pages, au
lieu d'avoir à apprendre/vendoriser un second moteur de template pour ça
seul.

## Principe

Même schéma en deux temps que [`xweb/pdf.py::render_pdf()`](pdf.md) :

```python
body = engine.render(template, ctx)              # ex. demo.welcome_email
ctx["content"] = body
html = engine.render("xweb.email_layout", ctx)    # layout email
# html est le corps à passer à ext.email.send(..., body=html, is_html=True)
```

`render_email()` ne fait **que** produire du HTML — il n'envoie jamais
rien lui-même. Le transport reste le contrat `ext.email` déjà établi
ailleurs dans ce projet (`extensions/email.py::ConsoleEmailExtension` en
dev — logue au lieu d'envoyer, aucun credential SMTP réel dans ce
squelette) : `async def send(to, subject, body, is_html) -> bool` /
`def queue(to, subject, body, is_html) -> bool`.

## Pourquoi un layout séparé de `xweb.shell_head`

Même raison que [`xweb.pdf_document`](pdf.md#pourquoi-un-layout-separe-de-xwebshell_head) :
`xweb.email_layout` ([`xweb/components/email.xml`](../xweb/components/email.xml))
n'utilise ni `app.css` ni la moindre classe DaisyUI. De nombreux clients
mail (Outlook en tête) suppriment les balises `<style>` et n'implémentent
Flexbox/Grid de façon fiable — un `<table>` + attributs `style="..."`
inline reste le seul dénominateur commun qui rende à peu près correctement
partout. Le layout porte :

- un en-tête (`app_name`) sur fond sombre ;
- une colonne centrale de 600px, fond blanc, coins arrondis ;
- `<t t-out="content"/>` pour le contenu, injecté par `render_email()` ;
- un pied de page (`app_name` répété).

[`xweb.email_button`](../xweb/components/email.xml) est le seul autre
composant du module — un `<a>` stylé en bouton (pas un `<button>`,
peu fiable en email), pour les appels à l'action (« Confirmer mon
compte », « Réinitialiser mon mot de passe »…).

## `render_email(engine, template, ctx, *, layout=...)`

- `layout` (défaut `xweb.email_layout`) enveloppe `template` ; `layout=None`
  traite `template` comme un document `<html>` déjà complet, sans
  enveloppe — même paramètre, même sens que dans `xweb/pdf.py::render_pdf()`.
- Ne dépend d'aucun paquet externe (contrairement à `render_pdf()` et
  `weasyprint`) — juste `QwebRegistry.render()`, déjà une dépendance de
  tout le reste de xweb.

## Exemple concret : email de bienvenue de `plugins/demo`

Bouton « Envoyer un email de démo » sur `/plugins/demo/`
([`plugins/demo/templates/index.xml`](../plugins/demo/templates/index.xml)) —
`POST /plugins/demo/email/send`
([`plugins/demo/src/main.py`](../plugins/demo/src/main.py)) :

```python
html = render_email(engine, "demo.welcome_email", {
    "page_title": "Bienvenue", "app_name": APP_NAME, "name": "Ada",
    "cta_url": "/plugins/demo/",
})
email_ext = self.get_service("ext.email")
sent = await email_ext.send(to="ada@example.com", subject="Bienvenue", body=html, is_html=True) if email_ext else False
```

`demo.welcome_email`
([`plugins/demo/templates/welcome_email.xml`](../plugins/demo/templates/welcome_email.xml))
est un template QWeb ordinaire — texte + un `t-call="xweb.email_button"` —
qui ne sait rien du layout email dans lequel il finira injecté.
`self.get_service("ext.email")` peut être `None` (extension pas
configurée) : la route dégrade sur un message d'erreur dans le fragment
htmx renvoyé, jamais un 500.

## Étendre à un autre écran

Même motif que pour le PDF :

1. écrire un template de contenu (texte + `xweb.email_button` au besoin,
   pas de classes DaisyUI — voir `demo.welcome_email` pour le style
   attendu) ;
2. appeler `render_email(engine, "mon_plugin.mon_email", ctx)` pour
   obtenir le HTML ;
3. le passer à `ext.email.send(...)`/`.queue(...)` comme n'importe quel
   autre corps d'email.

## Tests

- [`tests/test_email.py`](../tests/test_email.py) — `render_email()` en
  isolation (applique bien le layout par défaut, `layout=None` traite le
  template comme document complet, aucune classe/lien `app.css` ne fuit
  dans le layout email, `xweb.email_button` rend un `<a>` jamais un
  `<button>`) ; et `/plugins/demo/email/send` bout en bout, avec un
  **vrai** `ConsoleEmailExtension` (pas mocké) qui reçoit le HTML produit
  par le moteur QWeb — et dégrade proprement (200, pas 500) quand
  `ext.email` n'est pas disponible.

## Voir aussi

[pdf.md](pdf.md) et [i18n.md](i18n.md) — les deux autres points listés
"hors scope v1" dans [spec-v1.md §5](spec-v1.md).
