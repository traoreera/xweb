# xweb — Documentation

!!! tip "Vous voulez juste UTILISER xweb/xcore ?"
    Cette page et le reste de `docs/*.md` expliquent *pourquoi* le système est construit comme il l'est. Pour des exemples précis et copiables — construire une page, un composant, une contribution de nav — allez directement au [**Guide**](guide/index.md).

> **Statut de ce corpus** : xweb existe en code, réellement — ces documents ont commencé comme la spécification à partir de laquelle l'implémenter, écrits avec la même confiance que s'ils décrivaient un système livré ; depuis, le système livré a rattrapé la spec (moteur, shell, theming, sécurité, auth, i18n, PDF, email, contexte multi-tenant, `t-inherit-mode="primary"` — tout ce que ce document listait comme "à faire" ou "hors scope" est fait, voir [Questions ouvertes](#questions-ouvertes) et `spec-v1.md` §5). Ce qui n'a pas encore de doc dédiée reste écrit au présent normatif par habitude — vérifier `docs/*.md` individuellement pour un statut précis plutôt que de faire confiance à ce paragraphe seul.
>
> Issu de trois documents de conception successifs (*Patch Points* → *QWeb for XCore* → *xweb Blueprint*), basés sur une lecture directe de `traoreera/xcore`, `NiCE-DEV226/xui` et `traoreera/microframe` au 2 septembre 2026.

## Sommaire

| Document | Contenu |
|---|---|
| [`guide/`](guide/index.md) | **Guide d'utilisation** — comment faire, avec des exemples précis (page perso, composants, nav, filtres, pattern d'appel à un plugin JSON) |
| [`spec-v1.md`](spec-v1.md) | Principes fondateurs, contrat avec le kernel xcore, architecture globale |
| [`language.md`](language.md) | Référence des directives `t-*` du moteur de templates |
| [`inheritance.md`](inheritance.md) | `t-inherit` / XPath — extension non-destructive entre plugins |
| [`shell.md`](shell.md) | Layout persistant façon Obsidian, registres de contribution |
| [`theming.md`](theming.md) | DaisyUI, `data-theme`, mode sombre |
| [`components.md`](components.md) | Catalogue des composants et état de migration |
| [`i18n.md`](i18n.md) | Traduction des templates (`t-tr`/`_()`, catalogues, résolution de locale) |
| [`pdf.md`](pdf.md) | Export PDF via le même moteur QWeb (`xweb/pdf.py`) |
| [`email.md`](email.md) | Génération HTML d'email via le même moteur QWeb (`xweb/email.py`) |
| [`integration-xcore.md`](integration-xcore.md) | Câblage `ext.xweb`, permissions, cache |
| [`plugins.md`](plugins.md) | Guide auteur de plugin |
| [`studio.md`](studio.md) | Éditeur visuel de templates QWeb (UI builder pur, spec v2 — rien d'implémenté) |
| [`migration-guide.md`](migration-guide.md) | Checklist de parité et procédure de bascule |
| [`cli.md`](cli.md) | Commandes `xweb` en ligne de commande |

## Ce qu'est xweb en une phrase

Un moteur de rendu QWeb (parseur XML, compilateur de directives, héritage par XPath) et le rôle que jouait xui pour xcore, fusionnés dans un seul dépôt neuf — construit pour qu'un plugin puisse étendre une page ou un composant d'un autre plugin sans le forker, ce qu'aucun des deux dépôts existants ne permet aujourd'hui.

## Pile technique

| Rôle | Choix | Remplace |
|---|---|---|
| Templates | QWeb (XML + directives `t-*`) | Jinja2 / django-cotton-ui |
| Interactivité serveur | htmx | — (n'existait pas) |
| Interactivité client pure | `_hyperscript` | Alpine.js |
| CSS / composants visuels | DaisyUI (plugin Tailwind) | cotton-ui |
| Parseur | `lxml.etree` | — |

## Conventions de nommage — tranchées

- **`t-name`** : `<package_id>.<nom>` (style Odoo) — voir [`language.md`](language.md#t-name). Validé en pratique, plus une question ouverte.
- **Nom du dépôt** : `xweb` — utilisé partout dans le code réel (package, imports, docs), pas juste une proposition.
- **`plugin_prefix`** : pas une convention xweb — un vrai réglage de déploiement, `app.plugin_prefix` dans `integration.yaml` (défaut xcore réel : `/plugin`, singulier ; ce projet l'a fait varier entre `/plugins` et `/app` selon les périodes). Jamais un littéral codé en dur nulle part dans le code — `xweb.paths.plugin_prefix()` est la seule source de vérité, voir [`integration-xcore.md`](integration-xcore.md).

## JS et CSS — vendorisés et vérifiés

`htmx.min.js` (2.0.10, 0BSD) et `_hyperscript.min.js` (0.9.93, BSD-2-Clause) vivent dans `xweb/static/` (voir `NOTICE.md` à côté). Tous les extraits `_hyperscript` des docs tournent pour de vrai contre le fichier réel dans un DOM jsdom — `npm run verify:hyperscript`. `xweb/static/app.css` est compilé depuis `assets/app.css` (Tailwind v4 + DaisyUI 5, `npm run build:css`) puis vendorisé/commité comme le JS — Node reste un outil de dev, jamais une dépendance d'exécution.

**Vérifié bout-en-bout sur une vraie page servie par un vrai xcore** (pas des vérifications isolées) : `npm run verify:demo` (`scripts/verify-demo-page.mjs`) charge `/plugins/demo/` depuis le serveur en cours, exécute htmx/`_hyperscript` réels, clique sur les boutons, vérifie un vrai aller-retour réseau (`hx-post`, horodatage serveur qui change à chaque clic) et que `app.css` contient les vraies classes utilisées.

**Deux limites de jsdom trouvées et documentées en vérifiant** (pas des bugs xweb) — htmx utilise `document.evaluate`/`XPathExpression` d'une façon que jsdom refuse par défaut (corrigé par un patch local au script de test) ; le moteur CSS de jsdom ne parse pas la syntaxe Tailwind v4 (`@layer`/`@property`) donc `app.css` est vérifié par son contenu généré, pas par un style calculé. Détails dans [`theming.md`](theming.md#build).

## Shell — implémenté et vérifié en vrai

`xweb/contrib.py` (`NavRegistry`/`RibbonRegistry`/`CommandRegistry`/`StatusBarRegistry`, généralisés depuis `xui/nav.py`) et `xweb/components/shell.xml` sont câblés dans `xweb/mount.py` — chaque page est enveloppée par défaut (`use_shell=False` pour y échapper, ex. un écran de login). Vérifié sur le squelette : la nav du shell affiche réellement l'entrée que `plugins/demo/src/main.py::on_load()` enregistre.

**Une vraie correction d'architecture trouvée en câblant le hot-reload** — `spec-v1.md` affirmait qu'`ext.xweb` pouvait s'abonner à `plugin.*.unloaded` lui-même dans son `init()` ; en l'implémentant, `ExtensionLoader._load()` s'est révélé ne passer que `config` aux extensions, jamais l'`EventBus`. Le vrai point de câblage est `bind_hot_reload(xcore, ext)`, appelé depuis `main.py` après `xcore.boot(app)` — voir `spec-v1.md` §3 pour le détail, testé contre le vrai `EventBus` xcore.

## Thème — persiste réellement entre les pages

`shell.xml` avait `data-theme="light"` en dur — le bouton `_hyperscript` écrivait bien dans `localStorage` au clic, mais rien ne le relisait au chargement suivant. Corrigé avec le script anti-flash déjà documenté dans `theming.md` mais jamais câblé pour de vrai.

**Un vrai bug de compilateur trouvé en calculant le hash CSP de ce script**, pas en l'écrivant : `escape()` transformait `'` en `&#39;` à l'intérieur du `<script>` — un navigateur ne décode jamais les entités HTML dans `<script>`/`<style>` (raw text elements), ce qui aurait exécuté `&#39;` littéralement et levé une `SyntaxError`. Corrigé dans `engine/compiler.py` (`_RAW_TEXT_TAGS`), avec un test qui aurait attrapé exactement ce bug. `XWEB_THEME_SCRIPT_HASH` (`xweb/security.py`) est maintenant réintégré dans la CSP — le TODO qui y trainait depuis Phase 3 est refermé — avec un test qui casse si le script change sans régénérer le hash.

Vérifié en conditions réelles : `localStorage` pré-rempli avant le tout premier rendu d'une page fraîche (pas juste après un clic dans la même session), le thème choisi s'applique immédiatement — `scripts/verify-demo-page.mjs`.

## Sécurité — construite, puis réellement branchée

`CSRFMiddleware`/`SecurityHeadersMiddleware` (Phase 3) et `xcore.setup(app)` (TraceContextMiddleware/TenantMiddleware) étaient testés mais jamais ajoutés à l'app réelle du squelette — trouvé en faisant le point sur ce qu'il restait, pas repéré à la construction. Corrigé dans `main.py`, vérifié en direct : en-têtes CSP présents, mutation avec cookie de session + mauvais token rejetée (403), sans cookie acceptée normalement. Détail dans [`integration-xcore.md`](integration-xcore.md#securite-cablee-dans-mainpy-pas-juste-construite).

## Questions ouvertes

La liste complète vit dans le document de conception (*xweb Blueprint*, §10) et n'est pas dupliquée ici pour éviter qu'elle diverge en deux endroits. Les deux dernières questions listées ici (vrai backend d'auth, signature de plugin) sont désormais résolues — vérifié en relisant ce document plutôt que supposé toujours vrai :

- ~~Vrai backend d'auth pour tester le chemin RBAC~~ — `plugins/auth` (docs/auth.md) est un backend d'auth complet et réel (multi-tenant, RBAC, MFA, OAuth), enregistré comme le vrai `AuthBackend` de xcore dans son propre `on_load()`. `AnonymousAuthBackend` n'est plus utilisé ; voir le commentaire en tête de `main.py` pour pourquoi il ne doit jamais servir de filet de repli silencieux.
- ~~Comment signer les plugins si `strict_trusted` repasse à `true`~~ — `xcli plugin security sign` existe bien dans le paquet installé (vérifié : `uv run xcli plugin security sign --help` répond), contrairement à ce que cette note affirmait.

*Résolues depuis la dernière mise à jour : le hook de hot-reload xcore, les conventions de nommage, le conflit XPath, la syntaxe `_hyperscript`, le mode de build CSS (Node en dev, vendorisé en prod), le backend d'auth réel, la signature de plugin, et — hors de cette liste, dans spec-v1.md §5 — i18n, PDF, email et le contexte multi-tenant intégré au rendu.*
