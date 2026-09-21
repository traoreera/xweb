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

**Remis à zéro depuis la dernière version de ce fichier** : `main.py`, `templates/` (landing, catalogue, export PDF) **n'existent plus du tout** — vérifié par `find . -maxdepth 1`, pas une supposition. Ce que la section précédente de ce fichier décrivait (landing page montée par `main.py`, `templates/components_showcase.xml`, démo `editable_table` persistée via `landing_data.py`) a disparu entre-temps. `plugins/` et `extensions/` restent **vides**, comme avant.

Ce qui existe réellement à la racine aujourd'hui :
- **`xdsl/`** — un DSL déclaratif QML-like, transpileur vers du XML QWeb standard, **implémenté** (pas juste designé) — voir §17, nouvelle section dédiée. `docs/dsl-design.md` porte encore un bandeau "phase de conception" en tête : **périmé**, à ignorer, le parser/compiler/validators existent et sont testés.
- **`contacts_demo.dsl` + `contacts_demo_app.py`** — une démo CRUD complète et fonctionnelle (formulaire dans un `xweb.popover`, table qui se rafraîchit par événement htmx, **plus un `channel` SSE temps réel** : compteur live via `bind:` et rafraîchissement de la table via `refresh:`, déclenchés par une vraie route `GET /sse/contacts` qui diffuse à chaque création/suppression — y compris depuis un autre onglet), **autonome** : son propre FastAPI, sa propre route `/`, sans passer par `xcore.boot()`/`main.py`/le système de plugins. Sert de référence vivante pour les patterns `endpoint`/`use:` **et** `channel`/`use_channel:` de §17. Vérifiée bout en bout contre le vrai serveur par `npm run verify:contacts-channel` (jsdom + vrai htmx + vrai `live_channel.js` ; la preuve décisive est un contact créé par un POST **hors** de la page, qui y apparaît quand même). `uv run uvicorn contacts_demo_app:app --reload` pour la lancer — **`--reload` ne watch que les `.py`, pas `contacts_demo.dsl`**, redémarrer à la main après un changement du `.dsl`.
- **`catalogue.dsl`/`catalogue.html`/`catalogue.xdsl.json`** (non trackés git) — sortie de `scripts/catalogue.py`, un catalogue de tous les composants `xweb.*` rendus avec des props de démo, généré via le pipeline xdsl plutôt qu'à la main.
- **`scripts/dsl2html.py`** — pipeline `.dsl`/`.xdsl.json` → XML → aperçu HTML statique (pas un serveur, contrairement à `contacts_demo_app.py`).
- **`docs_site_app.py` + `docs_site.dsl` + `docs_site_data.py`** — LE site de démo/référence à héberger réellement (`uv run uvicorn docs_site_app:app --reload`), pas un HTML statique généré : une vraie app FastAPI+QwebRegistry (même posture que `contacts_demo_app.py`), pages écrites **en xdsl** (`docs_site.dsl` : `overview_page`/`index_page`/`text_detail_page`/`component_detail_page`, réutilisant de VRAIS composants `xweb.table`/`xweb.badge`/`xweb.collapse`/`xweb.breadcrumbs`, pas du HTML/CSS écrit à la main), navigation réelle via `xweb.shell`/`NavRegistry` (5 entrées de nav, `hx-boost` natif — aucun `hx-get`/`hx-target` manuel sur les liens). Chaque composant `xweb.*` (~69) a sa propre route `/components/{short}` avec : docstring réelle, démo **réellement rendue** (vrai `QwebRegistry`), props réellement extraites de leur `<t t-set="..." t-default="...">`, **usage xdsl ET usage QWeb (`t-call`)** — les deux formes d'appel, générées depuis le même jeu de props de démo (`scripts/catalogue.py::DEMO`), avec la distinction RÉELLE entre les deux (un attribut littéral sur un `t-call` est toujours une chaîne, un bool/nombre a besoin de `t-att-x="expr"` — docs/language.md#t-call) et source QWeb brute. `docs_site_data.py` réutilise `scripts/generate_docs_site.py` (import direct, `scripts/` comme namespace package) pour le contenu prose (syntaxe xdsl/directives QWeb/guides), pas redupliqué une 2e fois.

  **Bug réel du PARSER xdsl trouvé et corrigé en construisant ce site** (`xdsl/parser.py::_read_expression`) : un item de liste qui est un littéral dict — `items: [{"label": "Accueil", "path": "/"}]`, la forme attendue par `xweb.breadcrumbs`/`xweb.table` déclarée INLINE dans un `.dsl` plutôt que passée depuis le contexte Python — **bouclait à l'infini**. `_read_expression` s'arrête inconditionnellement sur un `{` à profondeur 0 (`{` = début du corps d'un élément dans tous ses autres appels) et rend une chaîne vide SANS avancer le curseur ; `_parse_list` retestait alors éternellement le même token `{`, jamais `RBRACKET`. Corrigé par un paramètre `allow_top_level_brace` (n'affecte que le tout premier token de l'expression, jamais les appels existants). Testé avec un timeout dur (`signal.alarm`, pas de dépendance `pytest-timeout`) dans `xdsl/tests/test_parser.py::TestClassList::test_list_of_dict_literals_does_not_hang` — sans ce genre de garde-fou, une régression future ferait juste pendre `pytest` indéfiniment plutôt que d'échouer proprement. **La forme qui MARCHE pour un vrai littéral liste-de-dicts inline dans un `.dsl`** (celle qu'utilise `docs_site.dsl`) reste l'assignation locale déjà établie par `contacts_demo.dsl` (`table_columns = [...]` puis `table { columns: table_columns }`) — `_parse_list()` (la syntaxe `attr: [...]`) ne produit qu'une STRING jointe par des espaces (`t-attf-*`, pensée pour `class:`), jamais une vraie liste Python ; passer par une `Assignment` (`x = [...]`) produit un `t-set`/`t-value` avec un VRAI littéral Python, `t-att-x="x"` référençant une vraie liste au rendu.

  L'ancien générateur HTML statique (`scripts/generate_docs_site.py` → `docs-site.html`, non tracké git) reste utilisable pour un aperçu rapide hors-ligne (routage `location.hash`, aucun serveur requis) mais n'est plus le livrable principal — `docs_site_app.py` est LE site à héberger.

Dette connue, non résolue à ce jour :
- `integration.yaml` référence encore `plugins.directory: "./plugins"`, `namespaces.demo`/`namespaces.account` (chemins morts).
- Les docs (`docs/*.md`) n'ont pas été ré-auditées pour des exemples `plugins/demo`/`plugins/account` qui référencent du code aujourd'hui supprimé, au-delà de ce qui a été corrigé au fil des sessions successives.
- Rien dans `xdsl/` ne génère d'attributs HTML5 natifs (`required`, `type="email"`...) depuis un schéma `data`/`@decorateur` — v1, voir §17.

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
- **`t-copy`** — copie-modification **par rendu** (docs `docs/inheritance.md#xpatch`) : `<t t-copy="target">` prend une snapshot de l'arbre **déjà résolu** de la cible (`registry.get`, patches `extension`/`primary` comprises), applique ses propres enfants `<xpath expr position>` sur la **copie seulement** (`inherit.apply_patch_ops`, mêmes positions/vocabulaire — `parse_xpath_ops` est partagé avec `extract_patch`), rend la copie. La source n'est jamais modifiée, **rien n'est enregistré globalement** → deux pages peuvent composer un même template partagé différemment sans jamais créer de conflit `check_all()`. Props comme `t-call` (`t-att-*`/bruts, isolés), **pas de slot** ; enfant non-`<xpath>` → `TemplateError` (jamais de contenu perdu), cible inconnue → `TemplateError`. Testé dans `tests/test_compiler.py`.

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
- `xweb/urls.py` : testé, jamais utilisé en pratique dans ce projet.
- Aucun plugin réel n'existe — tout ce qui est câblé (permissions, RBAC, hot-reload de plugin) n'a jamais retourné vrai depuis la suppression de `plugins/`/`extensions/`. `main.py`/`templates/` (qui montaient une landing hors système de plugins) ont eux aussi disparu depuis — plus aucune page ne tourne actuellement en dehors de `contacts_demo_app.py`, qui est délibérément autonome (§2, §17).
- Docs (`docs/*.md`) pas ré-auditées de fond en comble pour des exemples `plugins/demo`/`plugins/account` obsolètes au-delà de ce qui a été corrigé au fil des sessions successives.
- `npm run verify:demo` cible `/plugins/demo/`, qui n'existe plus — actuellement cassé, pas un faux négatif à ignorer.
- `xdsl` : pas d'attributs HTML5 natifs générés depuis `data`/`@decorateur` (v1, §17) ; `endpoint.auth` est parsé mais n'a aucun effet à la compilation (`"cookie"` est un no-op délibéré — l'auth de ce projet est 100% cookies HttpOnly, rien à ajouter côté client ; toute autre valeur, ex. `"bearer"`, n'est simplement pas câblée).

---

## 17. `xdsl/` — DSL déclaratif QML-like, sucre syntaxique pour QWeb

**Implémenté**, pas juste designé — `docs/dsl-design.md` porte encore en tête "Statut : Phase de conception, pas encore implémenté" : **périmé**, à ignorer, tout ce qui suit a du code réel et des tests derrière (`xdsl/parser.py`, `xdsl/compiler.py`, `xdsl/serialize.py`, `xdsl/api.py`, `xdsl/validators.py`, `xdsl/tests/` — **non ramassé par `uv run pytest` seul**, `testpaths=["tests"]` dans `pyproject.toml`, lancer `uv run pytest xdsl/tests` séparément). N'est **pas** branché dans le chemin de service d'une vraie app xcore (`QwebRegistry.register_source`/`register_dir` détectent et transpilent un `.dsl` automatiquement — voir plus bas — mais aucun plugin réel n'existe pour en profiter, §16).

### Pipeline

```
.dsl (texte) ──Parser──▶ AST ──Compiler──▶ XML QWeb ──QwebRegistry──▶ rendu
.xdsl.json (capsule No-Code) ──ast_from_json──▶ AST ──Compiler──▶ (même XML)
```

`QwebRegistry.register_source()`/`register_dir()` (`xweb/engine/registry.py`) détectent un `.dsl` par **extension du filename OU par contenu** (`_is_dsl_source` : pas de `<` en tête après espaces/BOM) et transpilent avant d'enregistrer — un plugin dépose un `.dsl` là où un `.xml` allait, rien d'autre ne change. `register_dir` scanne `*.xml` **et** `*.dsl`.

### `data`/`@decorateur` — schéma de validation, PAS de rendu

```qml
data contact_form {
    name: string @required @min_length(3)
    email: string @required @email
    role: string @in(["admin", "editor"])
}
```

`@décorateur[(args)]` = une règle de `xdsl/validators.py::BUILTIN_VALIDATORS` (`required`, `min_length`, `max_length`, `min`, `max`, `email`, `pattern`, `in`) — champ sans `@required` = optionnel (`Required` est une règle comme une autre, pas un flag séparé). `data` n'émet **aucun XML** — c'est un schéma consommé côté **serveur**. **Chemin canonique depuis la décision « pas d'ORM → Pydantic source de vérité »** : `xdsl/pydantic_bridge.py::build_model()` compile le bloc `data` en VRAI `BaseModel` (`extract_models`), chaque `@décorateur` attaché comme `AfterValidator` réutilisant la MÊME classe Validator (jamais de contraintes Pydantic natives ré-implantées — pydantic ancrerait `pattern` en full-match vs préfixe du moteur, `ge` refuserait les non-nombres quand `MinValue` passe au travers), le `value_type` devient une annotation réellement APPLIQUÉE (l'ancien chemin ne typait jamais : `age: int @min(0)` + `"abc"` passait par un passthrough silencieux), `@required` → champ requis au modèle, message "missing" → « Ce champ est obligatoire », erreurs de type → « Type invalide — attendu : <type> ». `validate_model(model, payload)` est le drop-in de `validate_dict` (`{champ: [messages]}`, mêmes règles/messages français — les messages de règles multiples d'un champ sont agrégés en une entrée) ; `parse_form(form, models["nom"])` fonctionne tel quel. `extract_schemas`/`validate_dict` restent (vecteurs du miroir JS `validators.js`), toute nouvelle validation par `extract_models`. `channel { validate: ... }` exporte **aussi** `window.XWEB_SCHEMAS_JSON[nom]` = `model_json_schema()` du même modèle (à côté des listes de règles `XWEB_SCHEMAS`), réservé au futur rendu champ façon `t-field`/tout consommateur JSON Schema.

```python
from xdsl.api import extract_models, validate_model
models = extract_models(dsl_source)
contact = models["contact_form"].model_validate(payload)  # objet typé, prêt à persister
errors = validate_model(models["contact_form"], payload)  # {} si valide, drop-in validate_dict
```

**Composition et listes typées** (mêmes règles partout, client et serveur) : le `value_type` d'un champ accepte une RÉFÉRENCE à un autre `data` (`address: address` — objet imbriqué) ou `list[item]` (`phones: list[phone]`, `tags: list[string]` — item primitif OU référence). `split_value_type(value_type)` dans `xdsl/parser.py` est la classification unique partagée par tous les étages : `("primitive", type)` / `("ref", nom)` / `("list", item)` (`"list[primitif]"` et `"list[référence]"` portent exactement la même forme `list[...]` — c'est le split qui distingue). `extract_models` construit la MAP COMPLÈTE via `_ModelBuilder` récursif dans `pydantic_bridge` (mémoïsation ; **références circulaires refusées au build**, pas en RecursionError de validation — `data a { x: b }`/`data b { y: a }` → erreur « Référence circulaire entre schémas data : a -> b -> a »). Erreurs de sous-objet remontées au chemin doté (`address.city`), erreurs de liste à `phones.0.number` — le côté JS utilise `phones[0].number`, MÊME chemin, deux conventions d'index (arrondi dans `verify-validators.mjs::pyToJsKey`). Un composé n'a PAS de schéma plat : `extract_schemas`/`validate_dict` lèvent une ValueError explicite qui renvoie vers `extract_models`.
**Validation de RÉPONSE** (`api.validate_response(models, nom, payload, as_list=True)`) : `validate_model_list` valide un TABLEAU d'objets (`receive { list: true }`) — payload non-liste → `{"__root__": ["Doit être une liste valide."]}`, chaque item validé en `validate_model`, erreurs préfixées `0.name`. Bug de la 1re passe fige : `list[primitif]` doit être annoté `list[TYPE_MAP[item]]`, pas `TYPE_MAP[item]` (sinon `5` dans `list[int]` passe sans erreur de type).

**Piège réel, à ne pas refaire** : `data`/`@decorateurs` ne génère **aucun** attribut HTML5 natif (`required`, `type="email"`...) sur les `<input>` correspondants — v1, documenté, l'auteur DSL les écrit toujours à la main (voir `contacts_demo.dsl`). Sans route Python qui appelle `extract_schemas`/`validate_dict` explicitement, **rien ne valide nulle part**, ni client ni serveur — `data` est un outil DRY, pas un mécanisme d'application forcée.

### `endpoint`/`use:` — requête réseau déclarative, htmx natif

```qml
endpoint create_contact {
    method: POST
    url: "/api/contacts"
    send: contact_form
    receive { type: json  target: "#contacts-table"  event: "contacts:changed" }
    onloading { p { "Envoi..." } }
    onsuccess { toast { "Créé !" } }
    onerror { toast { "Erreur" } }
}
form { use: create_contact
    input { name: "name"; required: true }
}
```

**Décision d'architecture centrale** : QWeb n'a **aucun runtime navigateur** (`xweb/engine/` est server-only) — `receive`/`use:` ne rend **jamais** de JSON en HTML côté client, ça reviendrait à réécrire le moteur de rendu en JS. `receive.target`/`event` diffuse, au succès, un **CustomEvent DOM** (`document.querySelector(target).dispatchEvent(new CustomEvent(event_name))`) — c'est à l'élément CIBLE de s'auto-rafraîchir depuis le **serveur** via un vrai `hx-trigger="{event} from:body"` (même idiome que `calendar:select`→`xweb.datepicker`). (Attendu : les toutes premières versions compilaient `send {event} to {target}` en hyperscript ; remplacé par le dispatch CustomEvent dans le bloc js, `event` par défaut `{nom}:done`.) `onloading`/`onsuccess`/`onerror` sont du contenu DSL **statique**, précompilé une fois pour toutes (pas de liaison aux champs de la réponse JSON — `toast { "Créé !" }` fixe, jamais un gabarit rempli à l'exécution).

`use: nom` expanse, à la compilation (`Compiler._endpoint_attrs`/`_endpoint_hyperscript`/`_write_endpoint_scaffolding`), sur l'élément porteur (`form`/`button`, brut ou `t-call` vers `xweb.form`/`xweb.button` — ces deux-là ont dû apprendre à forwarder `hx_headers`/`hx_indicator` en plus de leur whitelist `hx_get`/`hx_post`/... déjà là) :
- `hx-{method}="{url}"`, `hx-headers` (JSON du dict `headers`), `hx-indicator="#{id}-indicator"` si `onloading` non vide.
- **`hx-swap="none"` automatique dès que `receive.kind == "json"`** — sans lui, htmx applique son défaut (remplacer l'innerHTML de l'élément DÉCLENCHEUR par le corps brut de la réponse), le texte JSON écraserait le formulaire lui-même. Bug réel trouvé en construisant une vraie démo, corrigé, testé.
- Un `_hyperscript` `on htmx:afterRequest` qui bascule la visibilité (`@hidden`) des blocs onsuccess/onerror précompilés (des `<div hidden="hidden">` siblings, id `{use_id}-onsuccess`/`-onerror`, `{ep.name}-{compteur}` — un compteur par usage, deux éléments peuvent réutiliser le même endpoint sans collision d'id).
- **`receive.schema` est CÂBLÉ (plus « documenté seulement »)** : au succès HTTP, la réponse JSON est validée via `window.XwebValidate(schema_name, JSON.parse(...), { list: true/false })` — une réponse structurée invalide passe par le chemin **onerror** (jamais onsuccess ni l'event de refresh), un corps non-JSON est traité comme invalide, jamais une exception ; `receive.list: true` = la réponse attendue est un TABLEAU. Ce CALLBACK ne remplace pas la validation serveur (le serveur reste la source de vérité, `validate_response`), c'est de l'UX (afficher l'erreur au client sans re-rendu). Le descripteur est exporté par le scaffolding : `<script>window.XWEB_SCHEMAS[nom] = …</script>` + la **FERMETURE TRANSITIVE** des `ref`/`list[ref]` (`_schema_closure`) — trouvé en vrai jsdom : un tableau valide dont `contact.address` pointe `address` échouait avec « schéma address absent » quand on n'exportait que le schéma racine ; même correction sur le bootstrap d'un `channel { validate: }` composé (fonction partagée). `receive.schema: nom_inconnu` → `CompileError` à la compilation (jamais une validation morte qui laisse tout passer).
- CSRF : sur un `<form>` brut + méthode mutante, injecte `<t t-call="xweb.csrf" t-att-token="csrf_token"/>` en premier enfant ; sur un `t-call="xweb.form"`, transmet plutôt la prop `token="csrf_token"` (xweb.form pose déjà son propre champ en interne — jamais les deux à la fois).
- `use: nom_inconnu` lève `xdsl.compiler.CompileError` à la compilation — jamais un élément inerte silencieux.

**Piège MAJEUR du hyperscript généré (découvert en jsdom, d'où la forme `js(event)`)**: le script est écrit multi-ligne pour la lisibilité du XML compilé, MAIS lxml normalise les `\n` des attributs XML en **espaces** au round-trip QwebRegistry — hyperscript reçoit TOUJOURS la forme APLATIE. La structure `if/else/end` d'hyperscript ne survit PAS à cet aplatissement (`Unexpected Token : else` — vérifié au vrai `_hyperscript.min.js`), seul un bloc `js(...) end` (JS verbatim, statements séparés par `;`) le tolère. `_endpoint_hyperscript` est donc **un seul js block** qui fait tout le routing (try/catch du `JSON.parse`, `XwebValidate`, bascule `hidden`, dispatch conditionnel) — jamais un if hyperscript, et `verify:endpoint-dsl` teste la forme RÉELLE aplatie (via `render_endpoint_fixture.py` + le vrai htmx/_hyperscript/validators.js en jsdom, événement `htmx:afterRequest` dispatché à la main), pas une copie propre. Un endpoint sans onsuccess/onerror/receive.target n'émet aucun `_` (rien à révéler ni diffuser).

**Piège réel, `headers: { "Content-Type": "application/json" }` ne fait PAS ce qu'on croit** : ça pose l'en-tête HTTP, ça ne change **pas** la sérialisation du corps — htmx encode toujours un `<form>` en `application/x-www-form-urlencoded` par défaut, quel que soit le Content-Type déclaré. Sans l'extension htmx `json-enc` (non vendorisée dans ce projet), une route qui appelle `request.json()` échoue silencieusement sur des octets form-encodés étiquetés JSON. `contacts_demo_app.py::create_contact` lit donc de vraies données de formulaire (`Form(...)`), pas un corps JSON — et `contacts_demo.dsl` omet délibérément ce header.

### `copy`/`patch` — trois bugs réels trouvés en enregistrant une vraie copie/patch pour la première fois

Les tests xdsl historiques ne comparaient que du **texte compilé**, jamais un vrai enregistrement/rendu via `QwebRegistry` — exactement le même angle mort qui avait déjà laissé passer le piège `ReceiveSpec.type`/discriminant JSON (voir plus bas). Trois bugs dormaient depuis le début :

1. **`patch` ne posait jamais de `t-name`** — le moteur QWeb exige `<template>` toujours nommé, même pour un patch extension (jamais résolu par nom, mais quand même requis par le parseur). `QwebRegistry.register_source` plantait (`<template> missing required t-name`) dès qu'on essayait d'enregistrer un vrai `patch`. Corrigé : nom synthétique auto-généré (`{package_id}.__patch{n}__`).
2. **`copy X as Y { contenu littéral }` compilait un XML valide, s'enregistrait sans erreur, et ne faisait STRICTEMENT RIEN au rendu.** `xweb/engine/inherit.py::extract_patch()` ne lit **que** les enfants `<xpath>` d'un `<template t-inherit-mode="primary">` — tout le reste du corps (l'exemple qui était dans `docs/dsl-design.md` lui-même, `div { class: "login-form" slot }`) est silencieusement ignoré, la cible ressort inchangée. **Corrigé structurellement** : `copy` n'accepte plus que des blocs `xpath` (même grammaire que `patch`), un corps littéral lève maintenant une `ParseError` explicite au parse plutôt que de compiler dans le vide.
3. **`xpath { attributes: { clé: "valeur" } }` générait `<a clé="valeur"/>`** — le moteur attend exclusivement `<attribute name="clé">valeur</attribute>` (`extract_patch` fait `xp.findall("attribute")`, un `<a .../>` lui est invisible). Encore un enregistrement sans erreur, sans le moindre effet. Corrigé ; la syntaxe DSL réelle est `attributes: a { clé: "valeur" }` (un élément dont chaque attribut devient un `<attribute>`) — le dict littéral `attributes: { clé: "valeur" }` documenté dans une version antérieure de `docs/dsl-design.md` **n'a jamais été implémenté**.

Une fois enregistrée, une copie est un template comme un autre — `patch` peut la cibler par son nom, sans distinction avec un template de base (`xdsl/tests/test_compiler.py::TestCopyEndToEnd`, vérifié bout en bout).

### `copy:` / `xpatch` — copie-modification INLINE (par rendu, pas enregistrée)

Une deuxième syntaxe, plus locale que `copy X as Y { xpath }` (qui enregistre un template `primary` global) : l'attribut **`copy: "target"`** posé sur un élément (le même token réservé `copy` doublant en nom d'attribut, comme `style:` — `TokenKind.COPY` accepté dans `_peek_is_attribute`/`_parse_attribute`, hors chemin mot-clé de `_parse_node`) + des blocs **`xpatch { expr: …; position: …; … }`** en enfants :

```dsl
component expeditions.page_head {
    head {
        copy: "xweb.shell_head"
        xpatch { expr: "//link[@rel='stylesheet']"; position: "after"
            link { rel: "stylesheet"; href: "/expeditions/site.css" }
        }
    }
}
```

Compile en `<head t-copy="xweb.shell_head"><xpath expr="…" position="after">…</xpath></head>`, rendu par `xweb/engine/compiler.py::_render_copy` — **snapshot de l'arbre résolu** de la cible, ops appliquées sur la copie seule, source intacte, rien enregistré globalement (deux pages peuvent composer `xweb.shell_head` différemment sans conflit `check_all()`, contrairement à un `patch ext`). Contraintes refusées à la compilation (CompileError, jamais silencieux) : cible non-littérale (pas d'expression — résolu par nom brut), enfant non-`xpatch`, `position:` inconnue, `expr:` manquante, `copy:` sur un élément void (pas de corps pour les ops). Tests : `xdsl/tests/test_compiler.py::TestInlineCopy` (texte compilé) + `TestInlineCopyEndToEnd` (vrai `QwebRegistry.render()`). **Piège parseur : l'accolade du corps doit COLLER au tag** (`xpatch { expr: … ; position: … }`) — la grammaire du DSL ne supporte pas d'accolade après les attributs (`xpatch expr: "…" position: "after" {` est une `ParseError` "Nœud inattendu: LBRACE").

### `channel`/`use_channel:` — bootstrap SSE/WS déclaratif, données live

```qml
data contact_form { count: int @min(0) }

channel contacts_feed {
    url: "/stream"
    channels: ["chat", "notif"]
    transport: "sse"
    connect_timeout_ms: 5000
    validate: "contact_form"
    persist: "last_contact"
    onmessage {
        bind: { "#counter": "count" }
        refresh: "#contacts-table"
        event: "contacts:changed"
    }
}
component p { div { use_channel: contacts_feed  span { id: "counter"  "0" } } }
```

Sucre déclaratif au-dessus de `xweb/static/live_channel.js` (SSE/WS unifiés) — `use_channel: nom` sur un élément (`Compiler._resolve_use_channel`, `Compiler._write_channel_bootstrap`) émet un `<script>` juste après lui qui construit `new XwebLiveChannel({url, channels, transport, connectTimeoutMs, onMessage})`. `onMessage`, dans l'ordre : (1) si `validate:` posé, bloque tout le reste si `window.XwebValidate(nom, data).valid` est faux ; (2) `bind:` écrit chaque champ en `textContent` (jamais `innerHTML`) ; (3) `refresh:` déclenche `htmx.trigger(cible, event, data)` — jamais un rendu JSON→HTML côté client, même décision d'architecture que `endpoint`/`receive` (aucun runtime QWeb dans le navigateur) ; (4) `persist:` écrit dans `xweb/static/storage.js`. `use_channel: nom_inconnu` et `validate: "schéma_inconnu"` lèvent tous deux `CompileError` à la compilation — jamais un abonnement ou un export de schéma silencieusement absent.

**`validate:` exporte le schéma `data` réel en JSON**, colocalisé dans le même `<script>` (`window.XWEB_SCHEMAS["nom"] = {champ: [[règle, [args]], ...]}`, même forme que `DataField.decorators`) — garanti disponible avant que `onMessage` ne puisse s'exécuter (assignation synchrone juste avant `new XwebLiveChannel`). `xweb/static/validators.js` (nouveau fichier) est un port JS du même ensemble fermé de règles que `xdsl/validators.py` (`required`/`min_length`/`max_length`/`min`/`max`/`email`/`pattern`/`in`, mêmes messages français) et expose `window.XwebValidate(nom, data) -> {valid, errors}` ; parité prouvée mécaniquement (pas relue) par `npm run verify:validators` — un script Python (`scripts/validators_fixture.py`) fait tourner les **vrais** validators Python sur un jeu de vecteurs et écrit les résultats attendus en JSON, qu'un script Node rejoue contre le **vrai** `validators.js`. **C'est de l'UX, jamais de la sécurité** : un client hostile contourne trivialement cette validation ; la seule qui compte reste `validate_dict()` côté serveur sur tout ce qui arrive par `endpoint`/`receive`.

La page doit charger `live_channel.js` (+ `storage.js` si `persist:`, + `validators.js` si `validate:`) elle-même — jamais injecté par le DSL, même contrat que `htmx.min.js`. Bout-en-bout (vrai XML compilé, vrai `QwebRegistry.render()`, vrai DOM jsdom exécutant le `<script>` généré, vrai `storage.js`/`validators.js`, jamais un mock d'`XwebValidate` sur la dernière vérification) : `npm run verify:channel-dsl` (`scripts/render_channel_fixture.py` + `scripts/verify-channel-dsl.mjs`). Couverture unitaire : `xdsl/tests/test_parser.py::TestParserChannel`, `xdsl/tests/test_compiler.py::TestChannel`/`TestChannelEndToEnd`, `xdsl/tests/test_serialize.py::test_channel_roundtrip` (même piège tuple/liste que `DataField.decorators` — `ChannelOnMessage.bindings` est un `list[tuple[str,str]]`, round-trippe en liste de listes via JSON, comparaison par recompilation plutôt qu'égalité stricte de dataclass, voir `test_data_and_endpoint_roundtrip`).

**`onmessage { dispatch: true }`** — la porte de sortie vers du hyperscript/JS arbitraire, SANS ouvrir `onmessage {}` lui-même à du code libre (grammaire toujours fermée : `bind`/`refresh`/`event`/`dispatch`, une clé inconnue lève `ParseError`, `_parse_channel_onmessage`). Diffuse, en plus de `bind:`/`refresh:`/`persist:`, un vrai `document.dispatchEvent(new CustomEvent(event_name, {detail:{channel,data}}))` — `event_name` est le MÊME champ `event:` (ou son défaut `"{channel}:message"`) que `refresh:` utilise déjà pour `htmx.trigger()`, un seul champ pour les deux mécanismes. N'importe quel élément récupère alors le message via l'attribut `_` **déjà supporté partout ailleurs dans le DSL** (`_: on {event} from document ...` ou `_ { ... }` en mode bloc si multi-ligne — le mode `_: ...` s'arrête au premier `\n`, piège trouvé en écrivant le fixture de vérification, voir `xdsl/parser.py::_read_hyperscript`) : `event.detail.channel`/`event.detail.data` sont directement lisibles, aucune nouvelle syntaxe. Fonctionne identiquement sur SSE et WS (même code `onMessage` généré des deux côtés) — vérifié bout-en-bout avec du VRAI `_hyperscript.min.js` (`window._hyperscript.processNode(document.body)` après chargement, un `<script>` embarqué dans le HTML testé exige `runScripts: "outside-only"` + eval contrôlé, jamais `"dangerously"`, sinon les bootstraps s'exécutent AVANT que la lib hyperscript ne soit chargée) contre un vrai serveur SSE+WS, sur deux `channel {}` séparés (un par transport) simultanément, par `npm run verify:channel-dispatch`. `contacts_demo.dsl` l'utilise pour un flash `.badge-primary` sur le compteur de contacts — vérifié contre le vrai serveur de démo (`npm run verify:contacts-channel`, poll plutôt que `sleep` fixe pour la disparition de la classe après le `wait 400ms`, la latence réseau réelle dépasse parfois une marge fixe optimiste).

### Autres pièges trouvés en construisant `xdsl`

- **`ReceiveSpec.type`/`DataField.type` écrasaient silencieusement le discriminant `"type"` du sérialiseur JSON** (`xdsl/serialize.py`, qui pose `{"type": <nom de la dataclass>, ...}` sur chaque nœud) — un champ dataclass qui se nomme aussi `type` gagne la clé à la sérialisation, cassant la désérialisation (`AttributeError: 'dict' object has no attribute 'target'`). Renommés `kind`/`value_type`. **Aucun futur champ de nœud xdsl ne doit s'appeler `type`.**
- **`@in(["a","b"])` échouait à parser** — `in` est un mot-clé réservé (`for x in list`), pas un `IDENT` ; `_parse_decorators` doit accepter explicitement `TokenKind.IN` en plus d'un `IDENT` pour le nom d'un décorateur.
- **`tr { ... }` (balise HTML `<tr>`) était injoignable** — `tr` est par ailleurs le mot-clé de traduction (`tr "texte"`). Désambiguïsé sur ce qui suit `tr` : `{` juste après → balise `<tr>`, sinon → directive de traduction (`_parse_node`, sur `TokenKind.TR`).
- **`|` (chaînage de filtre QWeb, `price | money`) était silencieusement avalé par le lexer** en dehors d'une interpolation `${...}` — `price | money` devenait `price money`, un `eval()` Python invalide, aucune erreur au parse. `TokenKind.PIPE` ajouté ; `_read_expression` reconnaît maintenant `expr | filtre[:arg]` (un seul argument par filtre en expression nue — un filtre multi-arguments a besoin d'une virgule de premier niveau, ambiguë avec un séparateur d'item de `class:[...]`, écrire ce cas dans `${...}` à la place).
- **Injection hyperscript/JS via `${...}` dans `_`/`hx-vals`** — l'échappement HTML de l'attribut protège la frontière HTML, pas la grammaire imbriquée (hyperscript, ou JS pour `hx-vals: "js:..."`) : une valeur contenant un guillemet redevient un guillemet réel une fois décodée par le navigateur, cassant la chaîne et exécutant du code injecté. Deux nouveaux filtres QWeb (`xweb/engine/filters.py`, set fermé) protègent : `hs` (échappe pour un contexte hyperscript) et `js` (`json.dumps`, pour un contexte JS). `xdsl/compiler.py::_CODE_ATTR_FILTERS` les chaîne automatiquement sur toute interpolation dans `_`/`hx-vals` — l'auteur DSL n'a rien à faire.
- **`xweb-popover`/`xweb-popup`/`xweb-datepicker` (id par défaut littéral, fixe) faisaient collision entre plusieurs instances sans id explicite sur une même page** — `#id` résout toujours vers le PREMIER élément portant cet id dans le DOM, donc le 2ᵉ déclencheur agissait sur le panneau du 1ᵉʳ. Corrigé dans les trois composants : ciblage par relation DOM (`the next .popover-panel`) au lieu d'un id — `id` redevient un prop purement cosmétique (hook CSS/JS externe), plus jamais utilisé en interne pour le mécanisme ouverture/fermeture. Vérifié en jsdom contre le vrai `_hyperscript.min.js` (2 instances, clic sur la 2ᵉ, seul son propre panneau bouge).
- **`hx-target` est HÉRITÉ en htmx, et `xweb.shell` en pose un sur `<body>`** (`hx-target="#xweb-content"`, pour `hx-boost`). Un élément qui fait sa propre requête htmx SANS poser son propre `hx-target` hérite silencieusement celui-là — `#contacts-table` (`hx-trigger="load"`, sans `hx-target` à lui) remplaçait TOUT `#xweb-content` (formulaire compris) par le seul contenu de `/contacts/table`, dès le premier chargement de la page. Vérifié en rejouant `htmx.min.js` réel en jsdom (`XPathExpression.evaluate` patché — htmx en a besoin en interne, jsdom exige un type de résultat explicite que htmx ne fournit pas toujours). **Tout élément qui fait sa propre requête htmx dans une page sous `xweb.shell` doit poser son propre `hx-target` explicite**, même en auto-référence (`hx-target="#mon-propre-id"`), sinon il hérite silencieusement `#xweb-content`.
- **Une route custom hors `render_xweb_template`/`mount_xweb_page` doit répliquer à la main le contrat `HX-Request`** — `xweb.shell` boost la navigation interne (clic sur un lien nav → `GET` en AJAX avec `HX-Request: true`). Une route qui ignore cet en-tête et renvoie toujours la page complète (comme `contacts_demo_app.py::index` avant correction) fait injecter par htmx un `<html>` entier dans `#xweb-content` — DOM cassé, le formulaire "disparaît" alors qu'il est bien présent dans le HTML renvoyé. Contrat à répliquer : `HX-Request: true` → répondre `<title>...</title>` + fragment seul, jamais le document complet (`xweb/mount.py::render_xweb_template` le fait déjà pour toute page qui passe par lui ; une route qui construit sa propre réponse hors de ce chemin doit le faire elle-même).

### `<xweb:nom>` — sucre syntaxique pour `t-call`, PAS xdsl

Différent de `xdsl` : c'est un raccourci XML **natif au moteur QWeb** (`xweb/engine/parser.py`), désucré au parse, avant que le compilateur/registre/héritage ne voient quoi que ce soit. `<xweb:button variant="primary">…</xweb:button>` ⇒ `<t t-call="xweb.button" variant="primary">…</t>` (sans point → `xweb.<nom>` ; avec point → n'importe quelle cible du registre). Les deux syntaxes coexistent dans un même fichier. Un nom invalide ou une cible absente du registre est une `TemplateSyntaxError`/`TemplateError` au parse/enregistrement, jamais un silence (`tests/test_xweb_shorthand.py`).

### Discipline de vérification spécifique à xdsl

Les bugs `copy`/`t-name` ci-dessus n'ont été trouvés qu'en poussant un test au-delà de "le texte compilé contient la bonne sous-chaîne" jusqu'à "`QwebRegistry.register_source()` + `render()` réels" — même principe que §13, appliqué à xdsl lui-même. `xdsl/tests/test_compiler.py::TestCopyEndToEnd`/`TestDslToEngineEndToEnd` existent précisément pour ce palier. Pour tout ce qui touche `_`/hyperscript généré par xdsl (`use:`, `endpoint`), le palier 5 de §13 (jsdom + vrai `htmx.min.js`/`_hyperscript.min.js` contre un vrai serveur) reste le seul qui aurait attrapé le bug `hx-target` hérité — un test texte-seul sur le XML compilé ne peut structurellement pas le voir.

Palier supplémentaire pour du JS **dupliqué** entre deux langages (`xdsl/validators.py` ↔ `xweb/static/validators.js`, même règles réimplémentées à la main de chaque côté) : ni la lecture croisée ni un test unitaire par langage ne prouvent la parité — les deux peuvent diverger silencieusement sur un cas limite (troncature, coercition de type, message d'erreur). Le seul test qui le prouve fait tourner le moteur **source de vérité** (Python) sur un jeu de vecteurs, écrit les résultats en JSON, puis rejoue le **même** JSON contre le port (JS) et compare — `scripts/validators_fixture.py` + `scripts/verify-validators.mjs`. À refaire pour toute future logique dupliquée serveur/client de ce genre.

### `xsite/` — le site de présentation xweb+xdsl, TOUT écrit en xdsl, boot xcore RÉEL

`xsite/` (jamais `site/` — collision réelle avec le module **stdlib** Python `site`, confirmée à l'exécution : `uvicorn site.backend.main:app` échoue avec `No module named 'site.backend'; 'site' is not a package`, le stdlib gagne toujours la résolution) :

```
xsite/
├── integration.yaml   # xcore.boot() réel — services.extensions.xweb (module: XwebExtension), namespaces: {site: xsite/templates}
├── templates/*.dsl    # TOUTE la mise en page en xdsl — aucune chaîne HTML construite en Python
├── static/{site.css,site.js}   # le peu de CSS/JS propre au site, écrit à la main (0 dépendance, 0 CDN)
├── plugins/            # vide — ce site n'a besoin d'aucun plugin, ses pages sont montées directement sur `app`
└── backend/{main.py,routes.py,catalog.py}   # boot + routes + extraction du catalogue de composants
```

`xsite/backend/main.py` fait un **vrai** `Xcore(config_path=...).boot(app)` (pas un `QwebRegistry()` nu comme `contacts_demo_app.py`/`docs_site_app.py`, racine du dépôt, sessions précédentes) — `xcore.services.get("ext.xweb").engine` sert toutes les pages. Aucune base de données requise pour booter (confirmé : `services.databases` absent de `xsite/integration.yaml`, boot silencieux). `bind_hot_reload` câblé après boot, comme documenté dans CLAUDE.md.

**Le CSS/JS du site est injecté par un `patch` xdsl sur `xweb.shell_head`** (`xsite/templates/shell_patch.dsl`), jamais en éditant le composant vendorisé — la démonstration la plus directe de la raison d'être de xweb, appliquée au site qui la documente. `xweb.shell_head` n'a pas d'élément `<head>` englobant (ses enfants SONT le head, insérés par `xweb.shell`) : le xpath cible un nœud qui existe réellement (`//link[@rel='stylesheet']`) et insère `after:`, pas un `//head` qui ne matcherait rien.

**Chaque page de texte (syntaxe/directives/guides) est composée en xdsl** via des composants maison importés comme n'importe quel composant `xweb.*` (`import { doc_header, code_sample, gotcha } from "site"` — `site` est ici un nom de **namespace QWeb** dans `namespaces:`, sans aucun rapport avec le nom du dossier Python `xsite/` ni avec la collision stdlib). Seule la section **Composants** a son contenu construit côté Python (`xsite/backend/catalog.py`) — et ce n'est que des DONNÉES (docstring/props/rendu déjà fait/extraits de code), jamais du HTML : c'est `xsite/templates/components.dsl` qui en fait la mise en page, avec de vrais `xweb.table`/`xweb.badge`/`xweb.collapse`/`xweb.breadcrumbs`.

**Chaque composant a trois usages générés**, pas deux : xdsl, `t-call` QWeb, ET le raccourci `<xweb:nom>` — les trois produisent le même XML compilé (`xweb/engine/parser.py` désucre le raccourci au parse, avant que compilateur/registre/héritage ne voient quoi que ce soit).

**Vrai bug du COMPILATEUR xdsl trouvé en écrivant `xsite/templates/syntax.dsl`** (`xdsl/compiler.py`, la branche `_build_component_attrs` qui émet `t-att-{attr.name}="'...'"` pour une prop littérale de `t-call`) : c'était le **seul** chemin d'émission d'attribut de tout le compilateur qui n'appelait jamais `_esc()`. `card { title: "un <template> ici" }` produisait `t-att-title="'un <template> ici'"` — un `<` non échappé dans une valeur d'attribut XML, **XML invalide**. L'erreur ne se voyait qu'à l'**enregistrement** (`lxml.etree.XMLSyntaxError: Unescaped '<' not allowed in attributes values`), avec un numéro de ligne pointant le XML **compilé**, pas le `.dsl` source — un vrai piège à diagnostiquer sans le bon réflexe (tester au-delà de la compilation, jusqu'au vrai `QwebRegistry`, même discipline que les bugs `copy`/`t-name` plus haut). Corrigé par une nouvelle fonction `_esc_expr()` (échappe `&`/`<`/`>`/`"` mais PAS `'`, qui délimite le littéral Python lui-même — les échapper aussi aurait marché mais rendu toute la sortie compilée illisible). Testé dans `xdsl/tests/test_compiler.py::TestCallPropEscaping`, avec un test au palier `QwebRegistry.register_source()`+`render()` réel, pas seulement texte compilé.

Vérifié bout-en-bout contre un vrai serveur (`uv run uvicorn xsite.backend.main:app`) : 12+ routes à 200, patch `shell_head` actif (CSS/JS du site bien injectés), nav réelle à 6 sections, démo `xweb.popover` avec son vrai hyperscript (`then halt the event`), flux SSE `/demo/sse` qui pousse un vrai tick par seconde consommé par `channel site_clock` (`bind`/`dispatch` xdsl), compteur `/demo/counter` qui incrémente pour de vrai côté serveur à chaque POST htmx, contrat `HX-Request` respecté.

---

## Langue

Code, commentaires, docs de ce dépôt : **français**. Garder cette convention sur tout fichier existant édité.
