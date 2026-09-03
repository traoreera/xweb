# XWEB_KNOWLEDGE.md — référence complète, pour validation par un LLM

Fichier unique, exhaustif, pensé pour être chargé comme contexte par un LLM qui doit **valider** du code touchant `xweb`/ce projet — pas un tutoriel, pas de pédagogie progressive : tout ce qu'il y a à savoir, à plat, organisé pour être cherché plutôt que lu linéairement. `AGENTS.md` reste la version compacte ("ce que tu devinerais mal") ; `CLAUDE.md`/`docs/*.md` restent la source pour le *pourquoi* détaillé et l'historique de conception. Ici : le *quoi*, en entier, avec les pièges réels trouvés en le construisant.

Tout ce qui est affirmé ici a été vérifié contre le code réel ou par exécution réelle (pytest, curl, jsdom+vrai htmx/`_hyperscript` contre un vrai serveur) au moins une fois pendant la construction de ce projet — pas déduit par lecture seule.

---

## 1. Ce qu'est xweb, en une phrase

Un moteur de rendu QWeb (parseur XML via `lxml`, compilateur de directives `t-*`, héritage non-destructif par XPath) et un SDK de plugin pour **xcore** (paquet installé `xcoreruntime`, importé `xcore`) — joue le rôle que jouait un dépôt `xui` séparé, plus l'héritage non-destructif (`t-inherit`/XPath) qu'aucun des deux ancêtres ne permettait. `xweb` est un SDK **niveau plugin uniquement** — rien dans le paquet `xcore` installé n'est informé de son existence.

Pile technique :

| Rôle | Choix | Remplace |
|---|---|---|
| Templates | QWeb (XML + `t-*`) | Jinja2 / django-cotton-ui |
| Interactivité serveur | htmx | — |
| Interactivité client pure | `_hyperscript` | Alpine.js |
| CSS / composants visuels | DaisyUI (plugin Tailwind v4) | cotton-ui |
| Parseur | `lxml.etree` | — |

JS/CSS vendorisés dans `xweb/static/` : `htmx.min.js` (2.0.10, 0BSD), `_hyperscript.min.js` (0.9.93, BSD-2-Clause), `app.css` (compilé depuis `assets/app.css`, Tailwind v4 + DaisyUI 5). Node est un outil de **dev uniquement**, jamais une dépendance d'exécution — le JS/CSS committé est ce qui tourne en prod.

---

## 2. État réel du projet, aujourd'hui — pas une supposition

`plugins/` et `extensions/` sont **vides** (supprimés en cours de projet, remise à zéro délibérée). Ce qui existait avant et pourrait revenir : `plugins/auth` (backend JSON pur, multi-tenant/RBAC/MFA/OAuth), `plugins/account` (pont HTML devant lui), `plugins/demo`, `plugins/XPulses` (SSE), `extensions/pubsub`, `extensions/googleService`, `extensions/email.py` (`ConsoleEmailExtension`). **Ne jamais supposer qu'un de ces plugins existe sans vérifier `ls plugins/`.**

Ce qui tourne réellement aujourd'hui :
- La **landing page** (`/`, `templates/landing.xml`), montée directement par `main.py` (hors système de plugins — voir §8).
- Le **catalogue de composants** (`templates/components_showcase.xml`, appelé par `t-call` depuis `site.landing`) — ~46 composants `xweb.*` rendus en vrai sur la même page.
- Une **démo persistée** de `xweb.editable_table` (`landing_data.py` — état de module, pas une base de données — + routes `/demo/table/*` dans `main.py`).
- Un **export PDF** du catalogue (`GET /components.pdf`, `templates/components_pdf.xml`).

Dette connue, non résolue à ce jour :
- `integration.yaml` référence encore `plugins.directory: "./plugins"`, `namespaces.demo`/`namespaces.account` (chemins morts).
- `main.py` a une variable `page = PageRoute(path="/", ...)` (import de `xweb.urls`) jamais branchée sur `mount_xweb_pages` — la landing tourne sur un appel direct à `render_xweb_template`, pas sur ce module.
- Les docs (`docs/*.md`) n'ont pas été ré-auditées pour des exemples `plugins/demo`/`plugins/account` qui référencent du code aujourd'hui supprimé, au-delà de ce qui a été corrigé au fil de cette session.

---

## 3. Architecture — chemin de requête et intégration xcore

```
Navigateur --HTTP--> app FastAPI (xcore)
                        ├── routeur système (kernel)
                        ├── routeur par plugin (get_router())
                        │     ├── mode=xweb   -> pages server-rendues (QwebRegistry)
                        │     ├── mode=spa    -> StaticFiles + fallback index.html
                        │     └── mode=hybrid -> mix explicite
                        └── PluginSupervisor.call() -> pipeline de middlewares -> plugin.handle()
```

Pas de dispatcher générique : un appel htmx (`hx-post="/plugins/x/y"`) est une route ordinaire déclarée par ce plugin, qui passe par le pipeline complet (CSRF, en-têtes de sécurité, rate limit, permissions) comme n'importe quelle requête HTTP.

**`xweb` s'intègre comme une *extension* xcore, pas un plugin.** `XwebExtension` (`xweb/engine/integration/xcore.py`) est un `BaseService`, sous `services.extensions.xweb` dans `integration.yaml`. Une extension est construite avec **seulement `config`**, jamais l'`EventBus`/`KernelContext` du kernel — `ext.xweb` ne peut donc pas s'abonner lui-même à `plugin.*.unloaded` depuis son propre `init()`. Le vrai câblage du hot-reload se fait après le boot, côté app :

```python
await xcore.boot(app)
bind_hot_reload(xcore, xcore.services.get("ext.xweb"))   # main.py, après boot()
```

`bind_hot_reload` nettoie `QwebRegistry` (templates de base *et* patches taggées avec le `source_plugin` d'un plugin déchargé) + les quatre registres de contribution (`nav`/`ribbon`/`commands`/`status_bar`), sur les événements `plugin.*.unloaded`.

**Aucun plugin ne peut servir `/` lui-même.** `xcore.boot()` re-préfixe systématiquement chaque routeur de plugin sous `/plugins/<nom>/` (`xcore/__init__.py::boot()`, vérifié dans le paquet installé) — impossible d'opter pour autre chose en réglant son propre préfixe de routeur. D'où la landing page montée directement sur `app` dans `lifespan()`, juste après `bind_hot_reload` : un `APIRouter()` nu, jamais collecté par `PluginSupervisor`, donc jamais re-préfixé. Suivre ce même patron (routeur propre, monté post-boot, layout propre) pour toute autre page qui n'appartient à aucun plugin précis.

**Ordre des middlewares dans `main.py`.** Starlette refuse d'ajouter un middleware une fois l'app démarrée — `xcore.setup(app)` (enregistre `TraceContextMiddleware`/`TenantMiddleware`), `mount_builtin_assets(app)`, `SecurityHeadersMiddleware` et `CSRFMiddleware` doivent tous être ajoutés **au niveau module**, avant que `lifespan()` tourne — jamais dans le context manager de lifespan.

**`xweb.paths.plugin_prefix()` — source de vérité unique.** `app.plugin_prefix` dans `integration.yaml` décide où xcore monte réellement chaque plugin (`xcore/__init__.py::boot()`, `f"{prefix}/{plugin_name}"`) — un vrai réglage par déploiement (ce projet l'a fait varier entre `/plugins` et `/app`), pas une constante. `xweb.paths.plugin_prefix()` appelle `xcore.configurations.loader.ConfigLoader.load()` (classe **publique**, la même que `Xcore.boot()` utilise en interne), mis en cache (`lru_cache`, la valeur ne change pas sans redémarrage complet). Tout chemin absolu auto-référentiel du projet en dérive : `path=` des cookies, appels HTTP internes entre plugins, défauts SDK de `xweb/mount.py` (`DEFAULT_LOGIN_PATH`...), `CSRFMiddleware(protected_paths=...)` de `main.py`. `_base_render_context` (`xweb/mount.py`) injecte la valeur résolue comme `plugin_prefix` dans le contexte de **chaque** page.

---

## 4. Le langage de template QWeb — référence complète des directives

XML, `t-*`, parsé via `lxml.etree`.

- **`t-name`** : `<package_id>.<nom>` (style Odoo) — `xweb.button` pour un composant du cœur, `crm_app.contacts_list` pour une page de plugin. `QwebRegistry` est **un seul registre process-global, non namespacé par page** — toujours qualifier, un nom non qualifié entre en collision entre plugins par design.
- **`t-esc`** (échappé) : défaut pour tout ce qui vient d'un formulaire/API/utilisateur.
- **`t-out`** (brut) : seulement pour une valeur déjà connue sûre (sortie d'un autre composant xweb rendu, jamais une chaîne construite à la main).
- **`t-if`/`t-elif`/`t-else="1"`** — la valeur de `t-else` n'a aucun sens, seule la présence de l'attribut compte (convention du moteur, pas une expression évaluée).
  - **Piège** : `not <nom absent du contexte>` évalue à `None` (falsy), **jamais** `True` — l'expression entière échoue (`NameError`) avant que `not` s'applique, et `_eval` la récupère comme `None`. Un `t-call` qui oublie de forwarder une prop (`t-att-entries="entries"` manquant) rend silencieusement vide plutôt que de planter.
- **`t-foreach`/`t-as`** — pas de `t-foreach="range(...)"` : `range` n'est pas dans les builtins autorisés, construire la liste côté vue Python.
- **`t-att-*`** — la valeur est une **expression** Python (`t-att-href="account_path + 'security'"`).
- **`t-attf-*`** — interpolation `{{...}}` dans une chaîne littérale (`t-attf-href="{{account_path}}security"`).
  - Les deux échappent **toujours** — jamais de `Markup` possible sur un attribut, contrairement à `t-out`.
  - `hx-*` et `_` (`_hyperscript`) sont des attributs **normaux** aux yeux du compilateur — `t-att-hx-post="url"` ou `hx-post="/x/y"` en dur, les deux marchent, jamais traités spécialement.
- **`t-call` + props + `slot`** — **contexte isolé** : la cible ne voit *que* les props explicitement données, jamais le reste du contexte de l'appelant.
  - Prop littérale (`title="Statut"`) → chaîne fixe, jamais évaluée.
  - Prop calculée (`t-att-title="page_title"`) → expression Python, évaluée dans le contexte de l'**appelant**.
  - Contenu entre les balises `t-call` → disponible côté cible comme `slot` (`t-out="slot"` typiquement).
  - Sur un `t-call`, un attribut plain (pas `t-att-`) est une **chaîne littérale** — `t-attf-*` ne s'applique **pas** aux props d'un `t-call` (`xweb/engine/compiler.py::_render_call`).
- **`t-set`/`t-default`/`t-value`** :
  - `t-default` ne pose la variable **que si la clé est absente du contexte** — pattern "prop avec défaut" pour un composant.
  - `t-value` l'écrase **toujours**, inconditionnellement.
  - **Piège réel, trouvé cette session** : si un `t-call` transmet une prop dont l'expression échoue côté *appelant* (nom absent → `None`), la clé **existe** côté cible avec la valeur `None` — `t-default` ne la rattrape **pas** (elle ne joue que si la clé est *absente*, pas si elle vaut `None`). Pour une prop qui doit survivre "jamais transmise" **et** "transmise à `None`", utiliser `<t t-set="x" t-value="x or repli"/>`, jamais `t-default` seul.
- **Filtres `| nom[:args]`** — ensemble **fermé** (`xweb/engine/filters.py`) : `price | money`, `created_at | since`, `names | join:','`, `maybe | default:'—'`, etc. Aucun plugin ne peut enregistrer/écraser un filtre (même posture "rien d'exécutable ne vient d'un plugin" que le reste du moteur). Un filtre ne produit **jamais** de `Markup` — le résultat repasse par `escape()` à `t-esc`. `_eval` résout un nom absent en `None` **avant** de passer aux filtres, sans court-circuiter la chaîne — un nom manquant `|` `default:'N/A'` doit rendre `'N/A'`, pas vide (sinon le seul cas d'usage réel de `default`/`yesno` serait cassé).
- **`t-tr="1"`** — traduction du texte **statique littéral** d'un élément (`<h1 t-tr="1">Organisation</h1>`).
- **`_('texte')`** — valeur **composée** à traduire à l'exécution (`_('Bonjour ' + name)`) ; `_` est injecté dans le contexte de rendu par `xweb/mount.py`, jamais importé par le compilateur lui-même. Un composant générique `xweb.*` n'appelle **jamais** `_()` en interne — l'appelant traduit avant de passer la prop, et doit forwarder `_`/`locale`/`locales` explicitement à travers tout `t-call` (isolation de contexte).
- **`_RAW_TEXT_TAGS`** (`engine/compiler.py`) — à l'intérieur de `<script>`/`<style>`, les entités HTML ne sont **jamais** échappées (un navigateur ne les décode pas dans ces balises). Un vrai bug de compilateur a existé ici (`escape()` transformait `'` en `&#39;` dans un `<script>` inline, exécuté littéralement par le navigateur → `SyntaxError`) — corrigé, testé, ne pas y toucher sans relire ce test en premier.

---

## 5. Le compilateur — `_eval`, échappement, sécurité XSS

`_eval(expr, ctx)` (`xweb/engine/compiler.py`) : `eval(expr, {"__builtins__": {}}, ctx)`, **aucun builtin Python disponible** — `len()`, `str()`, `sorted()` lèvent `NameError`. Ce `NameError` est capturé **pour l'expression entière**, jamais partiellement — d'où le piège `not <undefined>` → `None` documenté plus haut. Toute autre exception (`ZeroDivisionError`, `AttributeError` sur un objet réellement présent, etc.) remonte telle quelle en `TemplateError`, jamais avalée.

**Posture XSS** — audité explicitement cette session, tout le dépôt : seulement **2 sites de construction `Markup(...)`** dans tout le code (les deux dans `xweb/engine/compiler.py`, tous les deux sûrs par construction, à partir de contenu déjà échappé). `t-esc` échappe toujours. `t-out` échappe sauf si la valeur est déjà un `Markup` de confiance. `t-att-*`/`t-attf-*` échappent **toujours, sans exception, aucun contournement**. Aucun fichier `routes.py` du dépôt n'importe `Markup`.

---

## 6. `QwebRegistry` — enregistrement, résolution, hot-reload

- `register_source(source, filename, source_plugin)` — parse et enregistre chaque `<template>` déclaré. Retourne la liste des `t-name` trouvés.
- `register_file(path, source_plugin)` / `register_dir(directory, source_plugin)` — `register_dir` est un no-op silencieux si le dossier n'existe pas encore (même posture défensive que xui : un plugin sans dossier de templates propre n'est pas une erreur).
- **Un `t-name` déjà pris n'est jamais une exception.** `register_source` logue un `logger.warning("... re-registered ... shadows the previous definition")` et le **nouveau** template écrase silencieusement l'ancien dans `self._templates`. Une collision entre deux fichiers du même dossier (ou entre un composant cœur et un template projet) ne casse jamais le boot — elle fait juste disparaître un composant sans autre signe qu'un log. `tests/test_component_registry.py` garde ce risque sous contrôle (assert zéro warning + compte de templates enregistrés == compte de `t-name` déclarés dans les sources, via un vrai parse lxml).
- `check_all()` — résout **chaque** template de base/`primary` immédiatement (au lieu d'attendre le premier `render()` qui le touche). Un conflit XPath (`position="replace"` par deux patches sur le même nœud) ne lève **jamais** — juste un warning qui nomme les deux plugins. Appelé depuis `XwebExtension.init()`, donc les conflits atterrissent dans le log de boot, pas des heures plus tard sur la page d'un visiteur.
- `unregister_plugin(plugin_name)` — retire à la fois les templates de base d'un plugin **et** ses patches contre les templates d'un tiers. Appelé depuis l'abonnement `plugin.*.unloaded` (voir `bind_hot_reload`), jamais par le plugin lui-même.
- `__len__` (`len(registry)`) — compte les templates de base enregistrés, pas les patches (qui vivent dans un dict séparé, keyé par la cible).

**Héritage `t-inherit` — les deux modes sont implémentés** :
- `t-inherit-mode="extension"` (défaut) — patche l'arbre **partagé** de la cible en place ; tout appelant de la cible voit le patch.
- `t-inherit-mode="primary"` — duplique l'arbre déjà résolu de la cible sous le `t-name` **propre** du patch : une copie figée (pas un lien vivant), composable avec d'autres patches `extension` une fois résolue, chaînable (un `primary` peut lui-même cibler un autre `primary`).
- `position` : `before`/`after`/`inside`/`replace`/`attributes`.
- Plusieurs patches sur la même cible se résolvent par `priority` (int, défaut 0, le plus bas d'abord), puis ordre d'enregistrement — **jamais** l'ordre d'import.
- Conflit réel : deux patches, même `expr`, `position="replace"` — le moins prioritaire est abandonné pour ce nœud, warning nommant les deux plugins. Opérations non conflictuelles sur le même nœud (`inside`+`inside`, `inside`+`attributes`) s'appliquent toutes les deux.

---

## 7. La couche de montage — `xweb/mount.py`, `XwebContext`

- **`mount_xweb_page(router, plugin_ctx, engine, *, path, template, view, ...)`** — monte UNE page server-rendue, toujours GET(+HEAD). Résout l'utilisateur courant via `resolve_user_or_anonymous(request)` (`xweb/context.py`) **avant** d'appeler `view` — c'est ce qui exige un `AuthBackend` xcore réel enregistré, même pour une page qui n'utilise jamais `ctx.user` (voir §2, la landing page évite ce coût en passant par `render_xweb_template` directement plutôt que `mount_xweb_page`). `view(ctx)` reçoit un `XwebContext` déjà résolu, retourne soit un `dict` de contexte de rendu, soit un `XwebRedirect` (`ctx.redirect(path, code=303)`).
  - `ctx.require_user()` — lève `XwebLoginRequired` (redirection login) si anonyme.
  - `ctx.require_role(*roles)` — lève `XwebPermissionDenied` (page 403, `xweb.error_page`, dans le shell) si le rôle manque.
  - Ces deux exceptions sont interceptées par `mount_xweb_page`, jamais laissées remonter telles quelles.
- **`render_xweb_template(engine, template, plugin_ctx, request, user, extra=None, ...)`** — la fonction que `mount_xweb_page` appelle en interne, utilisable **seule**, sans résolution d'utilisateur (`user=None` explicite) — utile pour une page qui n'a structurellement besoin d'aucun utilisateur (la landing page) ou pour ré-afficher la même page après une erreur de validation POST avec le même contexte.
- **`resolve_user_or_anonymous(request)`** (`xweb/context.py`) — distingue "anonyme" (401 → `None`, visiteur légitime) d'une vraie panne du backend d'auth (toute autre `HTTPException`, notamment 503 "Auth backend non disponible", remonte telle quelle). Ne jamais élargir en `except Exception` généralisé.
- **`XwebContext`** — `plugin_ctx`, `request`, `user` (`AuthPayload | None`). `is_authenticated`, `has_role(*roles)`, `require_user()`, `require_role(*roles)`, `redirect(path, code)`, `csrf_token` (lit `ext.xweb.csrf_token`, `""` hors xcore, jamais une exception), `call_plugin(plugin, action, payload)` (délègue à `plugin_ctx.caller` — voir §14 sur l'IPC).
- **htmx / boost / redirection** — navigation via `hx-boost` sur `<body>` (clic interne = swap uniquement `#xweb-content`). `render_xweb_template` regarde l'en-tête `HX-Request` pour décider page complète vs fragment (`<title>…</title>` + contenu). Un lien qui **quitte** le shell (login, logout — tout ce qui pose des cookies ou vise un autre layout) doit porter `hx-boost="false"`, sinon htmx swappe la réponse dans `#xweb-content` au lieu de naviguer. `redirect_response()` (`xweb/mount.py`) répond `HX-Redirect` au lieu d'un 303 brut si la requête vient de htmx — une requête boostée vers une page protégée obtient une vraie navigation navigateur vers le login, pas le *fragment* login inséré dans la page courante.

---

## 8. Shell & registres de contribution

`xweb/contrib.py` — quatre singletons, généralisés depuis `xui/nav.py` : `nav`/`ribbon`/`commands`/`status_bar`, instances de `NavRegistry`/`RibbonRegistry`/`CommandRegistry`/`StatusBarRegistry` (toutes dérivées de `ContributionRegistry`). Un plugin s'enregistre typiquement dans `on_load()` via `Contribution(id=..., plugin=..., label=..., path=..., permission=...)`. Le nettoyage à l'unload est **centralisé** dans `ext.xweb` (via `bind_hot_reload`) — un auteur de plugin n'a **rien** à faire lui-même pour ça, ne jamais désenregistrer dans `on_unload()`.

`xweb.shell` (`xweb/components/shell.xml`) — layout complet : ruban, nav latérale, barre du haut avec menu de compte, contenu, barre d'état, palette de commandes Ctrl+K. `xweb.shell_minimal` (`xweb/components/layout.xml`) — pour les écrans d'auth (le même `<head>`/CSS/thème, sans la nav). `xweb.marketing_layout` — pleine largeur, sans chrome applicatif ni carte étroite, utilisé par la landing page. `use_shell=False` sur `mount_xweb_page` saute les deux, pour une route htmx brute qui rend un fragment.

Une entrée de nav invisible tant qu'une seule locale existe (`xweb.locale_switcher`, `xweb/mount.py::_resolve_translator` replie sur `["fr"]` sans catalogue configuré). Pas de badge live par entrée de nav possible aujourd'hui — `NavRegistry` est un singleton partagé résolu **une fois** à l'enregistrement, pas par requête.

---

## 9. Theming

DaisyUI pilotée par `data-theme` sur `<html>` (pas une classe `.dark`). Bascule client = `_hyperscript` qui écrit dans `localStorage` (chaîne brute `'theme'`/`'sidebar'`, **pas** `xweb/static/storage.js`, voir §13) ; un script anti-flash inline dans `<head>` (`xweb.shell_head`, `xweb/components/layout.xml`) relit `localStorage` **avant** le premier rendu — seul JS écrit à la main dans tout le système de thème.

Ce script est épinglé par hash dans la CSP (`XWEB_THEME_SCRIPT_HASH`, `xweb/security.py`), recalculé contre le texte **réellement rendu**, pas deviné — un test casse s'il change sans régénérer le hash. Doit rester le **premier `<script>` inline** du document ; un `<script src=...>` externe peut le précéder sans violer cette contrainte (seuls les scripts inline comptent).

`assets/app.css` = source Tailwind/DaisyUI ; `xweb/static/app.css` = sortie **compilée, vendorisée, committée**. Recompiler (`npm run build:css`) après **tout** changement de classe utilisée dans `xweb/components/**/*.xml` ou `templates/**/*.xml`, **y compris un tout nouveau fichier composant** — rien ne rescane automatiquement, même avec `--reload` actif. Un composant "pas stylé du tout" dans un vrai navigateur malgré des vérifications curl/jsdom qui passent est, de très loin, le plus souvent ce problème — comparer les mtimes de `xweb/static/app.css` et du fichier composant en cause avant de chercher ailleurs.

**Piège d'interpolation confirmé plusieurs fois** : le scanner de Tailwind v4 ne voit que le **texte source littéral** des fichiers `.xml` — jamais le résultat d'une interpolation runtime. Un composant qui construit une classe DaisyUI dynamiquement (`t-attf-class="toggle toggle-{{color}}"`, ou `'text-' + color` côté Python) produit une classe absente de `app.css`, même après une recompilation fraîche, car la chaîne littérale `toggle-primary` n'apparaît nulle part dans le source. Un `@source inline("...")` en tête de `assets/app.css` force-génère le produit complet couleur × taille pour chaque composant qui compose une classe ainsi (`toggle`/`select`/`textarea`/`range`/`spinner`, et le générique `{btn,badge,alert,...}-{primary,...,error}` qui couvre désormais `badge-success` etc. utilisés par `xweb.editable_table`). Vérifier ce safelist avant d'assumer autre chose.

---

## 10. i18n — `xweb/i18n.py`

Le français est la langue **source** de tout le projet — un catalogue mappe le texte source français lui-même à sa traduction (`{"Se connecter": "Log in"}`, convention gettext — `msgid` = le texte lui-même), jamais un système de clés abstraites séparées. `Catalog` charge `<locales_dir>/<code>.json` par code de `locales` (le français n'a besoin d'aucun fichier, `_()` y est l'identité). Un fichier de catalogue manquant/invalide dégrade en catalogue vide (warning), jamais un échec de boot.

`_` (le traducteur) réalise **toujours** un repli silencieux vers le texte source si la locale n'a pas d'entrée, ou si la locale demandée n'a pas de catalogue du tout — jamais de `KeyError`.

Résolution de locale (`resolve_locale`) : `?lang=` explicite > cookie `xweb_locale` (posé par `xweb.locale_switcher`) > `Accept-Language` du navigateur > français source. Ne retourne jamais un code absent de `catalog.available`.

Config : `locales`/`locales_dir` sous `services.extensions.xweb.config` dans `integration.yaml` — un changement de ce bloc n'est **pas** repris par `--reload` (qui ne watch que les `.py`), nécessite un redémarrage manuel.

---

## 11. Composants — `xweb/components/`

~46 fichiers, tous `xweb.*`, catalogue vivant sur `templates/components_showcase.xml` (rendu sur `/`). Migration complète depuis `xui/components/` (django-cotton-ui, 50 fichiers d'origine, quelques-uns renommés/fusionnés en route — voir `docs/components.md` pour la table de correspondance complète des noms xui → xweb).

### Conventions communes
- Feuilles avant composites (un composant sans `t-call` interne se migre/écrit avant ceux qui en dépendent).
- Classes DaisyUI directement, jamais de dictionnaire `variants`/`size_classes` recréé à la main.
- `t-esc` par défaut pour tout texte utilisateur (`label`, `title`) ; `t-out` seulement pour un `slot` qui contient du HTML de confiance déjà rendu par un autre composant xweb.
- Zéro JS quand le natif HTML suffit : `<details>`/`<summary>` (`collapse`, `accordion`), `<dialog>` (`modal`), une checkbox cachée (`drawer`) — `_hyperscript` seulement pour ce que le natif ne couvre pas (glisser-déposer, filtrage local, logique conditionnelle d'ouverture/fermeture comme `popover`).
- `id` explicite en prop (défaut `"xweb-<nom>"`) sur tout composant qui a besoin d'être ciblé sans ambiguïté (`kanban`, `modal`+`modal_trigger`, `drawer`+`drawer_toggle`, `popover`, `combobox`, `datepicker`, `editable_table`) — **nécessaire dès qu'une page peut contenir plus d'une instance**, voir le piège htmx `hx-target` au §13.

### Catalogue par catégorie (non exhaustif ligne à ligne — voir `docs/components.md` pour le détail par fichier)
- **Conteneurs** : `card`, `field`, `description`, `error`, `label`.
- **Boutons/actions** : `button` (gère `href` → `<a>` ou `<button>`), `badge`, `spinner`, `progress`.
- **Formulaire** : `form` (pose le CSRF automatiquement), `input`, `password`, `textarea`, `checkbox`, `radio`, `toggle` (ex-`switch`), `range`, `select` (fusion de `select`/`select_native`/`select_option`, prop `options`), `combobox` (filtrage `_hyperscript`, valeur lue via `data-value`, jamais interpolée en dur), `datepicker`/`calendar` (grille calculée côté Python, `xweb/calendar.py::month_grid()` — aucun builtin date en expression QWeb).
- **Avatar/identité** : `avatar`, `avatar_group`, `breadcrumbs` (fusion avec `breadcrumb_item`, prop `items`).
- **Disclosure** : `accordion` (fusion avec `accordion_item`, `<details>` groupés par attribut `name` natif), `collapse`, `tabs` (fusion avec `tab`, prop `items`), `table` (prop `columns`/`rows`, slot pour un `<tbody>` sur mesure).
- **Overlays** : `dropdown` (slot `<li><a>`), `menu` (prop `items`, base de la nav/palette), `modal`+`modal_trigger` (`<dialog>` natif), `drawer`+`drawer_toggle` (checkbox cachée), `popover`+`tooltip` (`popover` = contenu riche clic + `_hyperscript`, piège : sans `then halt the event` sur le déclencheur, le clic d'ouverture est vu comme "elsewhere" par le panneau et le referme aussitôt), `toast`+`toasts_oob` (swap hors-bande htmx).
- **Système** : `alert` (fermeture `_hyperscript`, `remove closest .alert`), `icon` (SVG inline Heroicons v2 + logos de marque type Google/GitHub/Discord/Microsoft en `fill="currentColor"`, aucune police d'icônes — CSP `default-src 'self'`), `kbd`, `empty`, `divider`.
- **Avancé** : `kanban` (glisser-déposer HTML5 natif — voir détail ci-dessous), `editable_table` (grille éditable façon Notion — détail complet ci-dessous).
- **PDF/Email** (layouts, pas des composants de page) : `xweb.pdf_document`, `xweb.email_layout`+`xweb.email_button` — voir §12.

### `xweb.kanban` — détail
Props : `columns` (`[{id, title, cards: [{id, title, subtitle?}]}]`, `card['id']` doit être **unique sur toute la page**), `move_url` (falsy désactive la persistance — `t-att-hx-post="move_url or None"` n'émet pas l'attribut). Mécanique : `put draggedCard at end of me` (**pas** `move ... to end of ...` — absent du build vendorisé de `_hyperscript`, testé et confirmé planter le parseur). `put` déplace vraiment le nœud DOM existant, pas un clone. `send kanban:moved(card_id:…, column_id:…) to draggedCard` pose les valeurs sur `event.detail`, lues par `hx-vals="js:{...event.detail...}"` au déclenchement ; `hx-swap="none"` (l'état visuel est déjà correct via `put`, l'appel `hx-post` part en parallèle juste pour persister).

### `xweb.editable_table` — détail complet (le composant le plus élaboré du dépôt, cinq bugs réels trouvés en le construisant)
Props : `id` (défaut `"xweb-editable-table"`, DOIT être unique s'il y a plusieurs instances), `columns` (`[{key, label, type, options?}]`, `type` ∈ `"text"`/`"select"`/`"checkbox"`, `"select"` exige `options: [{value, label, color?}]`), `rows` (`[{id, <col.key>: valeur, ...}]`, `id` unique page-wide), `save_url`, `add_row_url`, `delete_row_url`, `reorder_url`, `add_column_url`, `rename_column_url`, `extra_class`. Toutes les URLs falsy désactivent le contrôle correspondant (même convention `x or None` que `xweb.kanban`).

Comportement : cellule texte = span (affichage) + input (édition, `style="display:none"` initial) basculés par `_hyperscript` au clic ; Entrée ou perte de focus sauvegarde (`hx-trigger="change, keyup[key=='Enter']"`) ; cellule select = badge coloré cliquable ouvrant un menu DaisyUI (idiome `combobox` : valeur lue via `data-value`) ; case à cocher = sauvegarde immédiate au `change`, pas de mode édition séparé ; réordonnancement = glisser-déposer natif, dépose **avant ou après** la ligne survolée selon `event.clientY` vs le milieu de sa `getBoundingClientRect()` (contrairement à `xweb.kanban` qui dépose toujours en fin de colonne) ; ajout de colonne = toujours type texte en v1 (pas d'éditeur d'options pour "select", volontairement hors scope) ; en-têtes renommables par le même mécanisme clic-pour-éditer que les cellules texte.

**Les cinq bugs, dans l'ordre où ils ont été trouvés** (chacun invisible au niveau de vérification précédent — voir §13 pour la discipline générale) :
1. `hide`/`show` de `_hyperscript` togglent `style.display` **inline**, jamais une classe CSS — une classe Tailwind `hidden` posée à côté n'est jamais retirée par ces commandes. Corrigé en posant `style="display:none"` plutôt qu'une classe pour l'état initial.
2. Les opérateurs de comparaison/arithmétique de cette version vendorisée sont les **symboles** (`<`, `+`), pas les mots anglais (`less than`, `plus` — absents du parseur, `Expected 'end' but found ')'`).
3. `hx-target="tbody"` (nu, sans id) cible le **premier** `<tbody>` de toute la page — sur la landing page, qui affiche aussi `xweb.table` juste au-dessus dans le catalogue (donc deux `<tbody>`), la ligne ajoutée atterrissait dans le mauvais tableau. Le serveur créait bien la ligne (persistée correctement) ; seul le swap client visait le mauvais endroit. Corrigé avec un `id` par instance, `hx-target="#{{id}}-tbody"`.
4. **htmx évalue `hx-vals` de TOUS les ancêtres de l'élément qui déclenche une requête, pas seulement le sien.** Le `<tr>` (glisser-déposer) porte son propre `hx-vals="js:{order: JSON.stringify(event.detail.order)}"` ; en éditant une cellule à l'intérieur (événement `change`, pas `table:reordered`), `event.detail` vaut `undefined`, `.order` fait planter TOUTE la construction de la requête de l'enfant — la cellule ne se sauvegardait jamais. Corrigé en gardant l'expression contre un `event.detail` absent : `(event.detail || {}).order || []`.
5. **Un `<input>`/`<select>` sans `name=` ne fait remonter AUCUNE valeur automatiquement dans une requête htmx**, quel que soit le déclencheur. La cellule texte/select n'avait jamais posé `name=` (délibéré — le nom du champ POST se décide via `hx-vals`, pas `name=`), donc la requête partait avec `column=` mais sans `value=` du tout : la cellule se vidait au lieu de sauvegarder la nouvelle valeur. Seule la case à cocher y échappait (elle posait déjà `value: event.target.checked` explicitement). Corrigé en posant `value: event.target.value` explicitement dans `hx-vals`, même geste que la case à cocher.

Ces deux derniers bugs n'ont été trouvés **qu'en inspectant le corps réel de la requête XHR** (`XMLHttpRequest.prototype.send` intercepté) contre un vrai serveur — invisibles en curl, invisibles en jsdom+`_hyperscript` isolé.

---

## 12. Export PDF et Email — même moteur QWeb

**PDF** (`xweb/pdf.py::render_pdf(engine, template, ctx, *, layout="xweb.pdf_document", base_url=None)`) — même schéma en deux temps que `render_xweb_template` : `template` est rendu une première fois, son HTML injecté dans `ctx["content"]`, puis `layout` est rendu à son tour, puis converti en PDF via WeasyPrint (`weasyprint>=69.0`). `xweb.pdf_document` (`xweb/components/pdf.xml`) est **délibérément indépendant** de `xweb.shell_head`/`app.css` — WeasyPrint ne supporte ni `oklch()`/`color-mix()` ni `@layer` (Tailwind v4/DaisyUI), réutiliser `app.css` produirait une page blanche silencieuse plutôt qu'une erreur visible. Feuille de style inline, hex plates, `@page` pour la pagination. `render_pdf()` n'importe `weasyprint` qu'à l'appel (`PdfUnavailable` si absent), jamais à l'import du module — un déploiement sans le paquet continue de servir le reste de l'app, seule la route PDF dégrade en 503.

**Email** (`xweb/email.py::render_email(engine, template, ctx, *, layout="xweb.email_layout")`) — même patron exactement. `xweb.email_layout` (`xweb/components/email.xml`) est un `<table>` + `style="..."` inline partout, **aucune** classe DaisyUI ni `app.css` (beaucoup de clients mail suppriment `<style>`, n'implémentent pas Flexbox/Grid). `xweb.email_button` est le seul autre composant du module — un `<a>` stylé bouton (`<button>` n'est pas fiable en email). `render_email()` ne dépend d'aucun paquet externe, contrairement à `render_pdf()`. `render_email()` ne fait **que** produire du HTML, jamais l'envoyer — le transport reste le contrat `ext.email` (`async def send(to, subject, body, is_html)`).

---

## 13. Discipline de vérification — ce que chaque outil prouve vraiment

Le principe central de tout ce projet : **chaque niveau de vérification qu'on saute est un niveau où un vrai bug se cache.** Par ordre croissant de ce qu'il couvre réellement :

1. **`uv run pytest`** (`registry.render(...)`, Python pur) — prouve que le template *compile* et que la chaîne HTML produite est celle attendue. Ne prouve **rien** sur le CSS ou le JS (ni l'un ni l'autre n'est exécuté).
2. **`curl`/`TestClient`** contre un serveur qui tourne — prouve le *contrat HTTP* (routes, codes de statut, en-têtes). Toujours rien sur le CSS/JS.
3. **jsdom + le vrai `_hyperscript.min.js` vendorisé, HTML construit à la main** (`scripts/verify-hyperscript.mjs`) — prouve la *logique hyperscript* en isolation. Ne prouve pas l'intégration avec htmx ; un HTML retapé à la main peut silencieusement diverger du vrai template.
4. **jsdom + `_hyperscript.min.js` réel, HTML issu d'un vrai rendu QWeb** (fichier écrit par un script Python, lu par le script Node — `scripts/verify-editable-table.mjs`) — prouve que le VRAI template produit un comportement correct, pas une approximation retapée.
5. **jsdom + `htmx.min.js` **et** `_hyperscript.min.js` réels, chargés contre un VRAI serveur en cours d'exécution** (`resources: "usable"`, `runScripts: "dangerously"` — `scripts/verify-demo-page.mjs`, `scripts/verify-editable-table-live.mjs`) — le seul niveau qui attrape les bugs spécifiques à htmx. Deux bugs réels **uniquement** trouvés ici (détaillés au §11, `editable_table`, bugs 4 et 5).

Patch jsdom nécessaire pour ce niveau (voir le haut de `verify-demo-page.mjs` pour le détail exact) :
```js
XPathExpression.prototype.evaluate = ((orig) => function (ctx, type, result) {
  return orig.call(this, ctx, type ?? 0, result ?? null);
})(XPathExpression.prototype.evaluate);   // htmx précompile une XPathExpression ; jsdom exige type/result explicites, un vrai navigateur défaute à ANY_TYPE/null
window.CSS = { escape: (s) => String(s) };  // htmx appelle CSS.escape() en phase de settle après un swap hx-boost ; jsdom n'a pas l'objet CSS global
Element.prototype.scrollIntoView = function () {};  // htmx scrolle après une navigation boostée ; jsdom n'a pas de mise en page
```
Et retirer le `<link rel="stylesheet">` avant de charger la page (jsdom parserait/exécuterait le CSS moderne de Tailwind v4 et planterait sur `@layer`/`@property`) — vérifier `app.css` séparément, par un `fetch()` direct de son contenu, jamais via le CSSOM de jsdom.

**Pour du HTML pré-rendu (pas dynamiquement injecté) portant déjà des attributs `_="..."`**, `_hyperscript` ne s'auto-initialise pas de façon fiable dans un jsdom nu — appeler explicitement `dom.window._hyperscript.processNode(dom.window.document.body)` juste après `eval(hsSource)` pour tout un sous-arbre ; le patron `element.setAttribute("_", ...)` + `processNode(element)` de `verify-hyperscript.mjs` ne prouve que l'élément unique qu'il cible.

**Scoper précisément toute requête DOM dans un script de vérification.** Une page avec plus d'une instance d'un motif similaire (deux `<table>`, un en-tête de colonne et une cellule de ligne partageant la même classe `.cell-display` depuis que les en-têtes sont devenus renommables) fait qu'un `querySelector` non scopé attrape le mauvais élément et produit un succès ou un échec trompeur — ça a piégé les scripts de vérification eux-mêmes deux fois dans ce projet, pas seulement les templates.

**Corollaire htmx `hx-target`** : un sélecteur nu (`hx-target="tbody"`) cible le **premier** de toute la page, jamais "le plus proche" — sur une page à plusieurs instances du motif, ça vise silencieusement le mauvais élément pendant que la requête serveur réussit quand même (facile à rater : la ligne est vraiment créée, juste dans le mauvais tableau). Soit `closest <sélecteur>` (relatif à l'élément déclencheur — toujours sûr), soit, quand la cible n'est pas un ancêtre du déclencheur, un `id` de composant + `hx-target="#{{id}}-<partie>"` — même contrat que `kanban`/`modal`/`drawer`/`popover`/`combobox`/`datepicker`. Nécessaire dès qu'une page peut contenir plus d'une instance d'un composant, ce qui est toujours vrai d'une page catalogue.

**`--reload` ne watch que les `.py`.** Un changement dans un `.xml` ou dans `integration.yaml` ne déclenche **aucun** redémarrage — `QwebRegistry` charge les templates une seule fois au boot. Après un changement de template seul, `touch main.py` (ou éditer n'importe quel `.py`) pour forcer un vrai redémarrage avant de tester contre le serveur en direct. Une correction de template "qui ne prend pas effet" est presque toujours ça, pas un vrai bug.

**CSS qui périme silencieusement** — voir §9. `npm run build:css` après tout changement de classe, y compris un tout nouveau fichier composant.

---

## 14. Sécurité

- **CSRF** (`xweb/csrf.py::CSRFMiddleware`) — protège toute méthode mutante sous `protected_paths` quand la requête porte un cookie de session (jamais si elle porte un `Authorization: Bearer`). Câblé une seule fois au niveau app dans `main.py`, `protected_paths=(f"{plugin_prefix()}/",)` — dérivé de `plugin_prefix()`, jamais un `"/plugins/"` en dur (un oubli laisserait le middleware ne rien protéger du tout après un changement de préfixe, silencieusement, sans erreur au boot).
- **`SecurityHeadersMiddleware`** (`xweb/security.py`) — `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, CSP (`report_only=True` par défaut, prudent — à l'app hôte de passer en mode enforce). `XWEB_THEME_SCRIPT_HASH` y est intégré pour autoriser le script anti-flash inline (voir §9).
- **Posture XSS** — voir §5, section dédiée. Auditée explicitement, tout le dépôt, cette session.
- **Permissions fail-closed** — un `permissions:` vide/absent dans `plugin.yaml` bloque silencieusement tous les appels de ce plugin (`{"status":"error","code":"permission_denied"}`, jamais une exception bruyante).
- **Cookies stricts** (`xweb/cookies.py`, voir §15) — `HttpOnly` toujours actif, `Secure` suit le vrai schéma de la requête, préfixe `__Host-`/`__Secure-` automatique.

---

## 15. Modules SDK additionnels

### `xweb/cookies.py`
Pose stricte par défaut, dérogation explicite si besoin. `HttpOnly` toujours vrai — aucun paramètre pour le désactiver. `Secure` suit le schéma réel de la requête (jamais forcé — casserait silencieusement le dev `http://localhost`, un cas documenté et supporté). Préfixe `__Host-`/`__Secure-` (RFC 6265bis, garantie forcée par le navigateur lui-même) appliqué automatiquement dès que `Secure` est vrai — jamais sur HTTP simple, où un cookie préfixé serait tout simplement refusé par le navigateur au lieu d'être juste moins protégé. `SameSite="strict"` par défaut — `same_site="lax"` seulement pour un cookie qui doit explicitement survivre une navigation externe de haut niveau (jamais l'inverse). `PendingState` — codec JSON base64url pour un état intermédiaire multi-étapes, signature HMAC-SHA256 **optionnelle** (`secret=`) : absente par défaut (un payload qui ne porte que des secrets déjà opaques n'a rien à gagner d'une signature), à fournir dès qu'un champ non opaque est agi sans revalidation côté serveur.

### `xweb/forms.py`
`parse_form(form: FormData, model: type[ModelT], *, translate: bool = True) -> FormResult[ModelT]`. Traduit les erreurs Pydantic en français en matchant sur le **`type`** stable de l'erreur (`"missing"`, `"string_too_short"`, `"greater_than_equal"`...) et en interpolant depuis `ctx` (`{"min_length": 3}`) — **jamais** sur le texte anglais `msg`. Une bibliothèque (`pydantic-i18n`, PyPI, MIT) a été essayée puis abandonnée pour cette raison précise : son matching par regex sur le texte anglais confondait deux gabarits partageant un préfixe commun (`"Input should be greater than {}"` matchait partiellement à l'intérieur de `"Input should be greater than or equal to {}"`), produisant un message mi-traduit. `type`+`ctx` élimine à la fois ce bug (identifiants exacts, pas de chevauchement possible) et la fragilité déjà connue du pattern `_FR` (matching sur texte anglais brut d'une API externe, cassait silencieusement si l'upstream reformulait un message). Un `type` non couvert par `_FR_BY_TYPE` dégrade sur le texte anglais brut, jamais une exception. Limite connue : `EmailStr` délègue à `email-validator` (bibliothèque tierce), dont le texte anglais propre n'est traduit qu'en partie (le préfixe "Value error, " → "Erreur : ", pas le détail derrière).

### `xweb/urls.py`
Sucre syntaxique façon `django.urls` : `path(route, view, *, template, name=None)` construit un `PageRoute` sans rien monter ; `mount_xweb_pages(router, ctx, engine, urlpatterns, *, login_path=...)` monte chaque route via `mount_xweb_page` dans l'ordre de la liste, lève `ValueError` sur un `name` réutilisé pour un chemin différent ; `reverse(name)` résout un chemin déclaré, lève `KeyError` sur un nom inconnu. `_names` est un dict **process-wide** — chaque test doit utiliser un nom de route unique pour ne pas entrer en collision avec d'autres tests du même run. Testé (`tests/test_urls.py`), mais **pas encore branché en production** — la landing page continue d'utiliser `render_xweb_template` directement (voir §2, dette connue).

### `xweb/static/storage.js` (`XwebStorage`)
Wrapper client-side pour `localStorage`, écrit à la main (comme le reste du JS non-vendorisé de ce dépôt — script anti-flash, flux SSE). Namespace (`"xweb:"` par défaut, `new XwebStorageClass('mon_plugin')` pour un espace propre), JSON automatique (`get`/`set` (dé)sérialisent), défensif (`localStorage` peut lever en navigation privée ou storage désactivé — chaque méthode intercepte et dégrade, jamais d'exception qui casserait le script appelant). Ne jamais y stocker un secret — lisible par n'importe quel JS de la page (XSS y a un accès direct), contrairement à un cookie `HttpOnly`. **N'est PAS branché sur le thème/sidebar existants** — leur script anti-flash est épinglé par hash dans la CSP et lit du `localStorage` en **chaîne brute** (`'dark'`/`'light'`, pas de JSON) ; le faire passer par `get()`/`set()` changerait le format stocké (JSON-encodé, `"dark"` avec guillemets) sans changer l'autre moitié de la paire lecture/écriture — un vrai bug silencieux au chargement suivant. Cette classe est pour du code **neuf**, jamais une migration automatique de l'existant.

---

## 16. Ce qui reste ouvert (au moment où ce fichier a été écrit)

- `integration.yaml` : `plugins.directory`, `namespaces.demo`/`namespaces.account` pointent vers des dossiers supprimés.
- `main.py` : `page = PageRoute(...)` défini, jamais passé à `mount_xweb_pages` — code mort.
- `xweb/urls.py` : testé, jamais utilisé en pratique dans ce projet.
- Aucun plugin réel n'existe — tout ce qui est câblé (permissions, RBAC, hot-reload de plugin) n'a jamais retourné vrai depuis la suppression de `plugins/`/`extensions/`, seulement la landing page (hors système de plugins par construction).
- Docs (`docs/*.md`) pas ré-auditées de fond en comble pour des exemples `plugins/demo`/`plugins/account` obsolètes au-delà de ce qui a été corrigé au fil de cette session.
- `npm run verify:demo` cible `/plugins/demo/`, qui n'existe plus — actuellement cassé, pas un faux négatif à ignorer.

---

## Langue

Code, commentaires, docs de ce dépôt : **français**. Garder cette convention sur tout fichier existant édité.
