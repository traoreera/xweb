#!/usr/bin/env python3
"""Site de démo et d'aide à la syntaxe — xweb + xdsl, un élément à la fois.

Génère UNE page HTML statique (docs-site.html à la racine, non trackée git,
même convention que catalogue.html) navigée comme un vrai site de référence :
une barre latérale groupée (Démarrer / Syntaxe xdsl / Directives QWeb /
Composants / Guides) liste CHAQUE construction xdsl, CHAQUE directive QWeb,
CHAQUE composant xweb.* individuellement — cliquer un élément affiche
UNIQUEMENT sa page (doc + exemple, et pour un composant une démo RÉELLEMENT
rendue via QwebRegistry + le vrai app.css), avec Précédent/Suivant pour un
parcours séquentiel. Jamais une longue page à scroller d'un bloc.

Le routage est côté client (location.hash) : un seul fichier HTML statique,
pas de serveur requis — cohérent avec scripts/catalogue.py/scripts/dsl2html.py
déjà dans ce dépôt.

Usage:
    uv run scripts/generate_docs_site.py
    uv run scripts/generate_docs_site.py --out /tmp/docs-site.html
"""

from __future__ import annotations

import argparse
import html as html_mod
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from lxml import etree

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

from catalogue import BASE_CTX, DEMO, EXCLUDE, SLOT_MAP, component_docs, render_one  # noqa: E402
from xweb.engine.registry import QwebRegistry  # noqa: E402

COMPONENTS_DIR = ROOT / "xweb" / "components"


@dataclass
class Page:
    id: str
    group: str
    title: str
    body: str  # HTML déjà assemblé (titre exclu — ajouté par le template de page)


# =============================================================================
# Extraction — props réelles déclarées par chaque composant (même convention
# que design/scripts/generate_components_catalog.py : <t t-set="x"
# t-default="y"/> en enfants directs du <template>, avant tout autre
# contenu).
# =============================================================================


def _extract_props(template_el: etree._Element) -> list[tuple[str, str]]:
    props: list[tuple[str, str]] = []
    for child in template_el:
        if not isinstance(child.tag, str):
            continue  # commentaire XML
        if etree.QName(child).localname != "t":
            break
        t_set, t_default = child.get("t-set"), child.get("t-default")
        if t_set is None or t_default is None:
            break
        props.append((t_set, t_default))
    return props


def _raw_xml_source(template_el: etree._Element) -> str:
    return etree.tostring(template_el, pretty_print=True, encoding="unicode").strip()


def _py_default_to_xdsl(value: object) -> str | None:
    """Convertit une valeur Python (du dict DEMO) en littéral xdsl plausible
    pour le snippet d'usage — scalaires seulement, un dict/liste imbriqué
    complexe (columns/rows d'un tableau...) retombe sur None (signalé à
    l'appelant) plutôt que de deviner une syntaxe fausse."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return f'"{value.replace(chr(34), chr(92) + chr(34))}"'
    return None


def _xdsl_usage_snippet(short: str) -> str:
    demo = DEMO.get(short, {})
    lines = [f"{short} {{"]
    complex_keys = []
    for key, value in demo.items():
        xdsl_val = _py_default_to_xdsl(value)
        if xdsl_val is None:
            complex_keys.append(key)
            continue
        lines.append(f"    {key}: {xdsl_val}")
    slot = SLOT_MAP.get(short)
    if slot:
        lines.append(f'    "{slot}"')
    lines.append("}")
    snippet = "\n".join(lines)
    if complex_keys:
        snippet += (
            f"\n// certaines props ({', '.join(complex_keys)}) sont des structures imbriquées"
            f" — voir xweb/components/{short}.xml pour leur forme exacte."
        )
    return snippet


def code(text: str, lang: str = "") -> str:
    return f'<pre class="code-block" data-lang="{lang}"><code>{html_mod.escape(text)}</code></pre>'


# =============================================================================
# Pages — Vue d'ensemble
# =============================================================================


def overview_page() -> Page:
    diagram = """
.dsl (texte)  ──Parser──▶  AST  ──Compiler──▶  XML QWeb  ──QwebRegistry──▶  HTML
      │                                              │
      └── xdsl/parser.py                             └── xweb/engine/ (t-*, t-inherit,
          xdsl/compiler.py                                filtres, i18n)

Navigateur : htmx (requêtes) + _hyperscript (comportement DOM) + DaisyUI/Tailwind (style)
             — AUCUN moteur de template côté client, jamais de JSON re-templaté en JS.
""".strip()
    body = f"""
    <p>
      <strong>xweb</strong> est un moteur de rendu QWeb (XML + directives <code>t-*</code>) et un
      SDK de plugin pour <strong>xcore</strong> — server-only, sans runtime navigateur, l'inverse
      d'un framework JS. <strong>xdsl</strong> est un sucre syntaxique QML-like au-dessus : un
      fichier <code>.dsl</code> se transpile en XML QWeb standard avant d'atteindre le moteur —
      le moteur lui-même ignore que xdsl existe.
    </p>
    <pre class="ascii-diagram">{html_mod.escape(diagram)}</pre>
    <p>
      Trois façons de produire un template : écrire le XML QWeb à la main (<code>xweb/components/*.xml</code>),
      écrire du <code>.dsl</code> (compilé automatiquement par <code>QwebRegistry.register_dir</code>/<code>register_source</code>),
      ou composer par héritage non-destructif (<code>t-inherit</code>/<code>copy</code>/<code>patch</code>) sans forker.
    </p>
    <p>
      Utilisez la barre latérale à gauche pour naviguer <strong>un élément à la fois</strong> — chaque
      construction xdsl, chaque directive QWeb et chaque composant a sa propre page (doc + exemple, et
      pour un composant, une démo réellement rendue). Précédent/Suivant en bas de page pour un parcours
      séquentiel ; le champ de recherche filtre la liste.
    </p>
    """
    return Page("overview", "Démarrer", "Vue d'ensemble", body)


# =============================================================================
# Pages — Syntaxe xdsl (une construction = une page)
# =============================================================================


def xdsl_syntax_pages() -> list[Page]:
    items: list[tuple[str, str, str]] = []  # (id, title, body)

    items.append((
        "xdsl-component",
        "component — déclaration",
        "<p>Un composant xdsl compile vers un <code>&lt;template t-name=\"...\"&gt;</code> QWeb.</p>"
        + code(
            'component contacts_page {\n'
            '    import { button } from "xweb"\n\n'
            '    props: {\n'
            '        title: "Contacts"\n'
            '    }\n\n'
            '    style: ".title { font-weight: bold; }"\n\n'
            '    div { class: ["p-4"]\n'
            '        h1 { title }\n'
            '        button { variant: "primary"  "Ajouter" }\n'
            '    }\n'
            "}",
            "xdsl",
        ),
    ))
    items.append((
        "xdsl-control-flow",
        "Structures de contrôle — if/elif/else, for",
        code(
            'if (count > 0) {\n'
            '    span { count }\n'
            '} elif (count == 0) {\n'
            '    span { "vide" }\n'
            '} else {\n'
            '    span { "négatif ?!" }\n'
            '}\n\n'
            'for contact in contacts {\n'
            '    div { class: "card"\n'
            '        span { contact.name }\n'
            '    }\n'
            "}",
            "xdsl",
        ),
    ))
    items.append((
        "xdsl-class-style",
        "class: / style: — liste et dict avec interpolation",
        "<p><code>class:</code> accepte une liste (jointe par un espace) ; <code>style:</code> un dict inline. "
        "Les deux acceptent l'interpolation <code>${...}</code>.</p>"
        + code(
            'div {\n'
            '    class: ["btn", "btn-primary", "${size}-gap"]\n'
            '    style: { color: "${\'a\' if is_urgent else \'b\'}"; padding: "2rem" }\n'
            "}",
            "xdsl",
        ),
    ))
    items.append((
        "xdsl-hyperscript-attr",
        "Attribut hyperscript brut — _: ... / _{ ... }",
        "<p>Deux modes : <strong>ligne</strong> (<code>_: ...</code>, s'arrête au premier saut de ligne ou à la "
        "<code>}</code> de l'élément) et <strong>bloc</strong> (<code>_{ ... }</code>, newlines préservées — "
        "nécessaire dès que le script tient sur plusieurs lignes).</p>"
        + code(
            'button {\n'
            '    _ : on click toggle .hidden on #modal\n'
            "}\n\n"
            'div {\n'
            '    _ {\n'
            '        on load\n'
            '            wait 2s\n'
            '            transition opacity to 0\n'
            '        on click\n'
            '            remove me\n'
            '    }\n'
            "}",
            "xdsl",
        ),
    ))
    items.append((
        "xdsl-data",
        "data — schéma de validation (@decorateurs)",
        "<p>Ensemble <strong>fermé</strong> de décorateurs (<code>xdsl/validators.py::BUILTIN_VALIDATORS</code>) : "
        "<code>@required</code>, <code>@min_length(n)</code>, <code>@max_length(n)</code>, <code>@min(n)</code>, "
        "<code>@max(n)</code>, <code>@email</code>, <code>@pattern(regex)</code>, <code>@in([...])</code>. "
        "N'émet <strong>aucun XML</strong> — consommé côté serveur via <code>xdsl.api.extract_schemas()</code> + "
        "<code>xdsl.validators.validate_dict()</code>, et côté client par <code>validate:</code> d'un <code>channel</code>. "
        "<strong>Ne génère pas</strong> d'attributs HTML5 natifs (<code>required</code>, <code>type=\"email\"</code>) "
        "— à écrire à la main sur chaque champ (v1, limite connue).</p>"
        + code(
            'data contact_form {\n'
            '    name: string @required @min_length(3)\n'
            '    email: string @required @email\n'
            '    role: string @in(["admin", "editor"])\n'
            "}",
            "xdsl",
        ),
    ))
    items.append((
        "xdsl-endpoint",
        "endpoint / use: — requête réseau déclarative",
        "<p>Décrit une requête HTTP une fois, l'attache à un élément avec <code>use: nom</code> — expansé en "
        "<code>hx-*</code>/<code>_hyperscript</code> à la compilation. <strong>Aucun rendu JSON→HTML côté client</strong> "
        "(QWeb est server-only) : <code>receive.target</code>/<code>event</code> diffuse un événement, c'est à la "
        "cible de se rafraîchir depuis le <em>serveur</em> via <code>hx-trigger</code>. "
        "<code>use: nom_inconnu</code> lève <code>CompileError</code> à la compilation.</p>"
        + code(
            'endpoint create_contact {\n'
            '    method: POST\n'
            '    url: "/api/contacts"\n'
            '    send: contact_form\n'
            '    receive { type: json  target: "#contacts-table"  event: "contacts:changed" }\n'
            '    onsuccess { toast { variant: "success"  "Créé !" } }\n'
            '    onerror { toast { variant: "error"  "Erreur" } }\n'
            "}\n\n"
            'form { use: create_contact\n'
            '    input { name: "name"; required: true }\n'
            "}",
            "xdsl",
        ),
    ))
    items.append((
        "xdsl-channel",
        "channel / use_channel: — SSE/WS déclaratif",
        "<p>Sucre au-dessus de <code>xweb/static/live_channel.js</code>. <code>onmessage {}</code> reste une "
        "grammaire <strong>fermée</strong> : <code>bind</code> (textContent, jamais innerHTML), <code>refresh</code> "
        "(htmx.trigger, jamais un rendu JSON→HTML), <code>dispatch: true</code> (CustomEvent DOM — la porte de "
        "sortie vers du hyperscript arbitraire, sans ouvrir <code>onmessage{}</code> lui-même), <code>event</code> "
        "(nom partagé par refresh/dispatch). <code>validate:</code> référence un schéma <code>data</code> exporté "
        "en JSON pour <code>xweb/static/validators.js</code> — de l'UX, jamais un remplacement de la validation "
        "serveur.</p>"
        + code(
            'data contact_form { count: int @min(0) }\n\n'
            'channel contacts_feed {\n'
            '    url: "/sse/contacts"\n'
            '    channels: ["contacts"]\n'
            '    transport: "sse"\n'
            '    connect_timeout_ms: 5000\n'
            '    validate: "contact_form"\n'
            '    onmessage {\n'
            '        bind: { "#counter": "count" }\n'
            '        refresh: "#contacts-table"\n'
            '        dispatch: true\n'
            '        event: "contacts:changed"\n'
            '    }\n'
            "}\n\n"
            'div { use_channel: contacts_feed\n'
            '    span { id: "counter"  "0" }\n'
            '    span {\n'
            '        _ { on contacts:changed from document add .badge-primary wait 400ms remove .badge-primary }\n'
            '    }\n'
            "}",
            "xdsl",
        ),
    ))
    items.append((
        "xdsl-inherit",
        "copy ... as ... / patch — héritage non-destructif",
        "<p><code>patch CIBLE { }</code> (<code>t-inherit-mode=\"extension\"</code>) modifie le template partagé "
        "EN PLACE. <code>copy SOURCE as ALIAS { }</code> (<code>t-inherit-mode=\"primary\"</code>) duplique sous un "
        "nouveau nom, la source reste intacte. <strong>Les deux n'acceptent QUE des blocs <code>xpath</code></strong> "
        "— un corps littéral lève <code>ParseError</code> à l'analyse.</p>"
        + code(
            'copy xweb.button as demo.fancy_button {\n'
            '    xpath "//button" { attributes: a { data-fancy: "1" } }\n'
            "}\n\n"
            'patch xweb.form {\n'
            '    xpath "//button" { inside: span { class: "helper"  "note" } }\n'
            "}",
            "xdsl",
        ),
    ))
    items.append((
        "xdsl-filters",
        "Filtres — expression | filtre",
        "<p>Même ensemble fermé que QWeb (<code>xweb/engine/filters.py</code>) — un seul argument par filtre "
        "en interpolation nue.</p>"
        + code('span { price | money }\n// -> t-esc="price | money" -> "1 234,50 €"', "xdsl"),
    ))
    items.append((
        "xdsl-include",
        "@include — layout de fichier",
        "<p>Directive de tête de fichier (une fois) — enveloppe la sortie dans <code>xweb.shell</code> plutôt "
        "qu'un fragment nu.</p>"
        + code('@include "xweb.shell"', "xdsl"),
    ))

    return [Page(pid, "Syntaxe xdsl", title, body) for pid, title, body in items]


# =============================================================================
# Pages — Directives QWeb (une directive = une page)
# =============================================================================


def qweb_directive_pages() -> list[Page]:
    items: list[tuple[str, str, str]] = []

    items.append(("qweb-t-name", "t-name", code('<template t-name="xweb.button">…</template>', "xml")
        + "<p>Nom qualifié du template — clé du registre. Convention <code>&lt;package_id&gt;.&lt;nom&gt;</code>.</p>"))
    items.append(("qweb-t-if", "t-if / t-elif / t-else",
        code('<t t-if="href"><a t-att-href="href">…</a></t>\n<t t-else="1"><button>…</button></t>', "xml")
        + "<p><strong>Piège réel</strong> : <code>_eval</code> attrape <code>NameError</code> et retombe sur "
          "<code>None</code> — <code>t-if=\"not entries\"</code> sur un <code>entries</code> ABSENT du contexte "
          "ne s'affiche pas non plus (l'échec invalide toute l'expression avant que <code>not</code> s'applique), "
          "alors que <code>entries=[]</code> (présent, vide) fonctionne normalement.</p>"))
    items.append(("qweb-t-foreach", "t-foreach / t-as",
        code('<li t-foreach="items" t-as="item">\n    <span t-esc="item.label"/>\n    <span t-if="item_last">— dernier</span>\n</li>', "xml")))
    items.append(("qweb-t-esc", "t-esc / t-out",
        "<p><code>t-esc</code> — toujours échappé, défaut pour tout contenu utilisateur. <code>t-out</code> — "
        "brut si <code>Markup</code> déjà sûr, échappé sinon. Ne jamais <code>t-out</code> une valeur venant "
        "directement d'un input utilisateur.</p>"))
    items.append(("qweb-t-att", "t-att-* / t-attf-*",
        code('<a t-att-href="url" t-attf-class="btn btn-{{variant}} {{extra_class}}">…</a>', "xml")))
    items.append(("qweb-t-call", "t-call",
        code('<t t-call="xweb.card">\n    <t t-set="title">Contacts récents</t>\n    <t t-call="xweb.button" variant="primary">Nouveau</t>\n</t>', "xml")))
    items.append(("qweb-t-set", "t-set / t-value",
        code('<t t-set="size_class" t-value="\'btn-sm\' if compact else \'btn-md\'"/>', "xml")))

    filters_rows = [
        ("since", "durée relative", "created_at | since → « il y a 3 h »"),
        ("date / datetime", "compaction date/heure", "created_at | date"),
        ("time", "heure seule", "created_at | time"),
        ("money", "montant français", "1234.5 | money → « 1 234,50 € »"),
        ("number", "nombre français", "1234.56 | number"),
        ("percent", "pourcentage", "0.125 | percent → « 12,5 % »"),
        ("upper/lower/title/capitalize", "casse", "s | upper"),
        ("truncate[:n]", "troncature (…, défaut 80)", "s | truncate:120"),
        ("slug", "slug ASCII", '"Ça va ?" | slug → « ca-va »'),
        ("length / count", "len() — builtin absent", "items | length"),
        ("first / last", "premier / dernier élément", "items | first"),
        ("join[:sep]", "joint un itérable", "names | join:','"),
        ("default[:fallback]", "repli si vide", "x | default:'N/A'"),
        ("default_if_empty[:fallback]", "repli si None/'' seulement", "x | default_if_empty:'—'"),
        ("yesno", "Oui/Non/—", "flag | yesno"),
        ("urlencode", "encodage URL", "q | urlencode"),
    ]
    filters_table = (
        '<table class="ref-table"><thead><tr><th>Filtre</th><th>Rôle</th><th>Exemple</th></tr></thead><tbody>'
        + "".join(
            f"<tr><td><code>{html_mod.escape(a)}</code></td><td>{html_mod.escape(b)}</td><td><code>{html_mod.escape(c)}</code></td></tr>"
            for a, b, c in filters_rows
        )
        + "</tbody></table>"
    )
    items.append((
        "qweb-filters",
        "Filtres | nom[:args] — ensemble FERMÉ",
        "<p>Aucun plugin ne peut déclarer/surcharger un filtre. Jamais de <code>Markup</code> produit — repasse "
        "toujours par <code>escape()</code> au <code>t-esc</code>.</p>" + filters_table,
    ))
    items.append((
        "qweb-inherit",
        "t-inherit / xpath — héritage non-destructif",
        "<p><code>t-inherit-mode=\"extension\"</code> (défaut) patche EN PLACE, partagé par tout appelant. "
        "<code>\"primary\"</code> duplique sous le <code>t-name</code> du patch (copie figée de l'arbre déjà "
        "résolu) — la source reste intacte. Conflit réel seulement si deux patches ciblent le même "
        "<code>expr</code> avec <code>position=\"replace\"</code> (résolu par priorité, warning au boot, jamais "
        "une exception). <code>position</code> : <code>before</code>/<code>after</code>/<code>inside</code>/"
        "<code>replace</code>/<code>attributes</code>.</p>"
        + code(
            '<template t-name="crm_app.button_badge" t-inherit="xweb.button" t-inherit-mode="extension">\n'
            '    <xpath expr="//button" position="inside">\n'
            '        <span class="badge badge-accent">CRM</span>\n'
            "    </xpath>\n"
            "</template>",
            "xml",
        ),
    ))
    items.append((
        "qweb-hx-hyperscript",
        "hx-* et _hyperscript — pas des directives QWeb",
        "<p>Traversent le compilateur SANS interprétation, XML-safe par construction. <strong>Piège réel, "
        "vérifié contre le vrai code</strong> : <code>hx-on:click=\"…\"</code> fait planter le parseur XML "
        "(<code>Namespace prefix hx-on ... is not defined</code>) ; <code>hx-on=\"click: …\"</code> a été "
        "RETIRÉ dans htmx 2.0 (silencieusement inerte, testé contre le vrai <code>htmx.min.js</code> 2.0.10). "
        "<code>hx-on-click=\"…\"</code> (tiret, fonctionne) exécute du JS arbitraire via <code>new Function()</code> "
        "— hors whitelist. <code>_hyperscript</code> reste le choix attendu pour tout comportement client.</p>"
        + code('<button hx-post="/plugins/crm_app/contacts" hx-target="#list" hx-swap="beforeend" class="btn btn-primary">Ajouter</button>', "xml"),
    ))

    return [Page(pid, "Directives QWeb", title, body) for pid, title, body in items]


# =============================================================================
# Pages — Guides thématiques (5 pages)
# =============================================================================


def guide_pages() -> list[Page]:
    items: list[tuple[str, str, str]] = []

    items.append(("guide-styling", "Styling — DaisyUI / Tailwind v4",
        "<h4>Le mécanisme de thème</h4>"
        "<p>DaisyUI théme via l'attribut <code>data-theme</code> sur <code>&lt;html&gt;</code> — pas une classe "
        "<code>.dark</code>. Bascule côté client en <code>_hyperscript</code>, aucun round-trip serveur ; un script "
        "anti-flash inline dans <code>&lt;head&gt;</code> lit <code>localStorage.theme</code> et pose "
        "<code>data-theme</code> AVANT le premier rendu.</p>"
        + code('<html data-theme="dark">', "html")
        + "<h4>Build — vendorisé, jamais une dépendance runtime</h4>"
        "<p><code>assets/app.css</code> (source) compile vers <code>xweb/static/app.css</code> via "
        "<code>npm run build:css</code> — puis COMMIS, comme <code>htmx.min.js</code>.</p>"
        + code("npm install\nnpm run build:css   # à chaque changement de classes\nnpm run watch:css", "bash")
        + "<h4>Piège réel — classes générées au RENDU sont invisibles au scanner Tailwind</h4>"
        "<p>Le scanner de contenu Tailwind v4 ne voit que le TEXTE SOURCE littéral des <code>.xml</code> — "
        "jamais le résultat d'une interpolation runtime. <code>t-attf-class=\"toggle toggle-{{color}}\"</code> "
        "produit une classe invisible au scanner → jamais générée. A touché plusieurs composants jusqu'à l'ajout "
        "d'un <code>@source inline(...)</code> explicite.</p>"))

    items.append(("guide-hyperscript", "Patterns hyperscript réels de ce dépôt",
        "<h4>Bascule de thème</h4>"
        + code(
            '_="on click\n'
            "     if document.documentElement.dataset.theme is 'dark' set document.documentElement.dataset.theme to 'light'\n"
            "     else set document.documentElement.dataset.theme to 'dark'\n"
            "   end\n"
            "   then call localStorage.setItem('theme', document.documentElement.dataset.theme)\"",
            "hyperscript",
        )
        + "<h4>Popover — piège du bulling d'événement</h4>"
        "<p><strong>Trouvé en l'écrivant</strong> : sans <code>then halt the event</code> sur le déclencheur, le "
        "MÊME clic qui ouvre le popover est vu comme « elsewhere » par le panneau lui-même et le referme aussitôt. "
        "Ciblage par relation DOM (<code>the next .popover-panel</code>), jamais par id — <code>#id</code> résout "
        "toujours vers le PREMIER élément portant cet id.</p>"
        + "<h4>Écouter un CustomEvent diffusé par un channel xdsl</h4>"
        + code(
            '_ {\n'
            "    on contacts:changed from document\n"
            "        if event.detail.channel is 'contacts'\n"
            "            put event.detail.data.count into me\n"
            "        end\n"
            "}",
            "hyperscript",
        )))

    items.append(("guide-htmx", "Intégration htmx",
        "<h4>hx-boost + hx-target hérité — piège réel</h4>"
        "<p><code>xweb.shell</code> pose <code>hx-target=\"#xweb-content\"</code> sur <code>&lt;body&gt;</code>. "
        "<strong>hx-target est HÉRITÉ</strong> par tout élément qui fait sa PROPRE requête sans poser le sien — "
        "un <code>hx-trigger=\"load\"</code> sans <code>hx-target</code> remplace alors TOUT "
        "<code>#xweb-content</code>.</p>"
        + code('<div id="contacts-table" hx-get="/contacts/table" hx-trigger="load" hx-target="#contacts-table" hx-swap="innerHTML">…</div>', "xml")
        + "<h4>hx-swap=\"none\" — requis sur tout endpoint JSON</h4>"
        "<p>Sans lui, htmx remplace l'innerHTML de l'élément DÉCLENCHEUR par le corps brut de la réponse — le "
        "texte JSON écraserait le formulaire. xdsl l'ajoute automatiquement.</p>"
        "<h4>Contrat HX-Request</h4>"
        "<p>Une route custom qui ignore <code>HX-Request: true</code> fait injecter un <code>&lt;html&gt;</code> "
        "ENTIER dans <code>#xweb-content</code> — DOM cassé. Contrat : boosté → "
        "<code>&lt;title&gt;+fragment</code> seul.</p>"))

    items.append(("guide-python", "Architecture Python",
        "<h4>QwebRegistry</h4>"
        + code("registry = QwebRegistry()\nregistry.register_dir(ROOT / 'xweb' / 'components', source_plugin='xweb-core')\nregistry.check_all()\nhtml = registry.render('xweb.button', {{'label': 'Go'}})", "python")
        + "<h4>Pipeline xdsl</h4>"
        + code("from xdsl.api import extract_schemas\nfrom xdsl.validators import validate_dict\n\nschemas = extract_schemas(open('contacts.dsl').read())\nerrors = validate_dict(request_json, schemas['contact_form'])", "python")
        + "<h4>_eval — pas de builtins Python</h4>"
        "<p><code>eval(expr, {{\"__builtins__\": {{}}}}, ctx)</code> — <code>len()</code>/<code>str()</code> "
        "lèvent <code>NameError</code>, retombent sur <code>None</code>, jamais une erreur bruyante.</p>"))

    items.append(("guide-assets", "Assets statiques vendorisés",
        '<table class="ref-table"><thead><tr><th>Fichier</th><th>Rôle</th></tr></thead><tbody>'
        + "".join(
            f"<tr><td><code>{a}</code></td><td>{b}</td></tr>"
            for a, b in [
                ("xweb/static/app.css", "Tailwind v4 + DaisyUI 5 COMPILÉ — commis, jamais généré en prod."),
                ("xweb/static/htmx.min.js", "htmx 2.0.x vendorisé."),
                ("xweb/static/_hyperscript.min.js", "_hyperscript vendorisé."),
                ("xweb/static/live_channel.js", "SSE/WS unifiés, hand-written."),
                ("xweb/static/storage.js", "Wrapper localStorage namespacé, hand-written."),
                ("xweb/static/validators.js", "Port JS des règles de validation xdsl, hand-written."),
            ]
        )
        + "</tbody></table>"))

    return [Page(pid, "Guides", title, body) for pid, title, body in items]


# =============================================================================
# Pages — Composants (un composant = une page, avec démo LIVE)
# =============================================================================


def component_pages(registry: QwebRegistry) -> tuple[list[Page], dict[str, int]]:
    names = sorted(t for t in registry._templates if t.startswith("xweb.") and t not in EXCLUDE)
    stats = {"ok": 0, "err": 0}
    pages: list[Page] = []

    xml_index: dict[str, etree._Element] = {}
    for xml_file in sorted(COMPONENTS_DIR.glob("*.xml")):
        raw = xml_file.read_text(encoding="utf-8")
        wrapped = raw if raw.strip().startswith("<templates>") else f"<templates>\n{raw}\n</templates>"
        try:
            root = etree.fromstring(wrapped.encode("utf-8"))
        except etree.XMLSyntaxError:
            continue
        for t in root.findall(".//template"):
            n = t.get("t-name")
            if n:
                xml_index[n] = t

    for name in names:
        short = name.split(".", 1)[-1]
        try:
            rendered = render_one(registry, name)
            badge = "ok"
            stats["ok"] += 1
        except Exception as exc:
            rendered = f'<div class="text-error text-sm">{html_mod.escape(str(exc).splitlines()[0][:200])}</div>'
            badge = "err"
            stats["err"] += 1

        docstring = component_docs(name)
        el = xml_index.get(name)
        props = _extract_props(el) if el is not None else []
        props_table = (
            '<table class="ref-table props-table"><thead><tr><th>Prop</th><th>Défaut</th></tr></thead><tbody>'
            + "".join(f"<tr><td><code>{html_mod.escape(p)}</code></td><td><code>{html_mod.escape(d)}</code></td></tr>" for p, d in props)
            + "</tbody></table>"
            if props
            else '<p class="muted">Aucune prop déclarée.</p>'
        )
        xdsl_snippet = _xdsl_usage_snippet(short)
        raw_xml = _raw_xml_source(el) if el is not None else ""

        body = f"""
        <div class="component-header">
          <code class="component-name">{html_mod.escape(name)}</code>
          <span class="badge badge-{'success' if badge == 'ok' else 'error'} badge-sm">{badge}</span>
        </div>
        <p class="component-doc">{html_mod.escape(docstring) or '<em>Pas de docstring en tête de fichier.</em>'}</p>
        <h4>Démo</h4>
        <div class="component-preview">{rendered}</div>
        <h4>Props réelles ({len(props)})</h4>
        {props_table}
        <h4>Usage xdsl</h4>
        {code(xdsl_snippet, "xdsl")}
        <h4>Source QWeb brute</h4>
        {code(raw_xml, "xml")}
        """
        pages.append(Page(f"component-{short}", "Composants", short, body))

    return pages, stats


# =============================================================================
# Assemblage de la page — sidebar groupée, une page visible à la fois
# =============================================================================

PAGE_CSS = """
:root { --sidebar-w: 280px; }
body.docs-body { display: flex; min-height: 100vh; margin: 0; }
.docs-sidebar {
  width: var(--sidebar-w); flex-shrink: 0; position: sticky; top: 0; height: 100vh;
  overflow-y: auto; border-right: 1px solid rgba(0,0,0,0.12);
  padding: 1rem 0.75rem; background: rgba(0,0,0,0.02);
}
.docs-sidebar h1 { font-size: 1rem; font-weight: 700; margin: 0 0 0.75rem 0.25rem; }
.docs-sidebar .sidebar-group { margin-top: 1rem; }
.docs-sidebar .sidebar-group:first-of-type { margin-top: 0; }
.docs-sidebar .sidebar-group-title {
  font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.04em; opacity: 0.55;
  padding: 0.25rem 0.5rem; font-weight: 700;
}
.docs-sidebar nav a {
  display: block; padding: 0.3rem 0.5rem; border-radius: 0.375rem; font-size: 0.85rem;
  color: inherit; text-decoration: none; opacity: 0.85; cursor: pointer;
}
.docs-sidebar nav a:hover { background: rgba(0,0,0,0.06); opacity: 1; }
.docs-sidebar nav a.active { background: rgba(59,130,246,0.15); opacity: 1; font-weight: 600; }
.docs-main { flex: 1; min-width: 0; padding: 1.5rem 2.5rem 3rem; max-width: 900px; }
.doc-page { display: none; }
.doc-page.active { display: block; }
.doc-page-header { margin-bottom: 1.25rem; border-bottom: 2px solid rgba(0,0,0,0.08); padding-bottom: 0.75rem; }
.doc-page-group { font-size: 0.75rem; text-transform: uppercase; opacity: 0.55; letter-spacing: 0.04em; }
.doc-page-title { font-size: 1.6rem; font-weight: 700; margin: 0.15rem 0 0 0; }
.doc-page h4 { font-size: 1rem; font-weight: 700; margin: 1.25rem 0 0.4rem; }
.code-block { background: #1e1e2e; color: #cdd6f4; padding: 0.75rem 1rem; border-radius: 0.375rem; overflow-x: auto; font-size: 0.82rem; line-height: 1.5; }
.ascii-diagram { background: rgba(0,0,0,0.04); padding: 1rem; border-radius: 0.5rem; font-size: 0.78rem; overflow-x: auto; }
.ref-table { width: 100%; border-collapse: collapse; margin-top: 0.5rem; font-size: 0.85rem; }
.ref-table th, .ref-table td { text-align: left; padding: 0.35rem 0.6rem; border-bottom: 1px solid rgba(0,0,0,0.08); }
.component-header { display: flex; align-items: center; gap: 0.5rem; }
.component-name { font-size: 1.1rem; font-weight: 700; }
.component-doc { opacity: 0.75; font-size: 0.9rem; }
.component-preview { border: 1px dashed rgba(0,0,0,0.18); border-radius: 0.5rem; padding: 1.25rem; display: flex; justify-content: center; background: rgba(0,0,0,0.015); margin: 0.5rem 0 1rem; }
.muted { opacity: 0.6; font-style: italic; }
.page-nav { display: flex; justify-content: space-between; margin-top: 2.5rem; padding-top: 1rem; border-top: 1px solid rgba(0,0,0,0.1); }
.page-nav a { text-decoration: none; color: inherit; font-size: 0.85rem; padding: 0.5rem 0.9rem; border: 1px solid rgba(0,0,0,0.15); border-radius: 0.4rem; }
.page-nav a:hover { background: rgba(0,0,0,0.05); }
.page-nav .spacer { flex: 1; }
#sidebar-search { width: 100%; margin-bottom: 0.75rem; padding: 0.4rem 0.6rem; border-radius: 0.375rem; border: 1px solid rgba(0,0,0,0.2); font-size: 0.85rem; }
@media (max-width: 900px) {
  body.docs-body { flex-direction: column; }
  .docs-sidebar { position: static; width: 100%; height: auto; }
  .docs-main { padding: 1rem 1.25rem 2rem; }
}
"""

PAGE_JS = """
const PAGE_IDS = window.__PAGE_IDS__;

function showPage(id) {
  if (!PAGE_IDS.includes(id)) id = PAGE_IDS[0];
  for (const el of document.querySelectorAll('.doc-page')) el.classList.toggle('active', el.id === 'page-' + id);
  for (const a of document.querySelectorAll('.docs-sidebar nav a')) a.classList.toggle('active', a.dataset.pageId === id);
  const idx = PAGE_IDS.indexOf(id);
  const prevEl = document.getElementById('nav-prev');
  const nextEl = document.getElementById('nav-next');
  if (idx > 0) { prevEl.href = '#' + PAGE_IDS[idx - 1]; prevEl.hidden = false; } else { prevEl.hidden = true; }
  if (idx < PAGE_IDS.length - 1) { nextEl.href = '#' + PAGE_IDS[idx + 1]; nextEl.hidden = false; } else { nextEl.hidden = true; }
  document.querySelector('.docs-main').scrollTo(0, 0);
  const activeLink = document.querySelector('.docs-sidebar nav a.active');
  if (activeLink) activeLink.scrollIntoView({ block: 'nearest' });
}

window.addEventListener('hashchange', () => showPage(location.hash.slice(1)));
showPage(location.hash.slice(1) || PAGE_IDS[0]);

document.getElementById('sidebar-search').addEventListener('input', function () {
  const q = this.value.toLowerCase();
  for (const a of document.querySelectorAll('.docs-sidebar nav a')) {
    a.hidden = q && !a.textContent.toLowerCase().includes(q);
  }
  for (const g of document.querySelectorAll('.sidebar-group')) {
    const visible = g.querySelectorAll('a:not([hidden])').length > 0;
    g.hidden = !visible;
  }
});

// Surlignage syntaxique léger, sans dépendance externe (pas de CDN — même
// posture "vendorisé ou écrit à la main" que le reste du JS de ce dépôt) —
// un jeu FERMÉ de mots-clés par langage, pas un vrai tokenizer.
(function highlight() {
  const RULES = {
    xdsl: [
      [/\\b(component|import|from|if|elif|else|for|in|patch|copy|as|priority|slot|raw|tr|style|props|xpath|inside|replace|before|after|attributes|extension|primary|data|endpoint|channel|use|use_channel)\\b/g, 'hl-kw'],
      [/@\\w+/g, 'hl-deco'],
      [/\\/\\/.*/g, 'hl-comment'],
    ],
    xml: [[/(&lt;\\/?[a-zA-Z][\\w:.-]*)/g, 'hl-tag']],
    python: [[/\\b(def|class|import|from|return|if|else|elif|for|in|try|except|raise|with|as|None|True|False)\\b/g, 'hl-kw']],
    hyperscript: [[/\\b(on|from|end|if|else|wait|put|into|add|remove|toggle|set|then|halt|the|event|call|send|trigger|me|my)\\b/g, 'hl-kw']],
  };
  for (const block of document.querySelectorAll('.code-block')) {
    const rules = RULES[block.dataset.lang];
    if (!rules) continue;
    const codeEl = block.querySelector('code');
    let out = codeEl.innerHTML;
    for (const [re, cls] of rules) out = out.replace(re, (m) => '<span class="' + cls + '">' + m + '</span>');
    codeEl.innerHTML = out;
  }
})();
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "docs-site.html")
    parser.add_argument("--css", type=Path, default=None)
    args = parser.parse_args()

    registry = QwebRegistry()
    registry.register_dir(COMPONENTS_DIR, source_plugin="xweb-core")

    syntax_pages = xdsl_syntax_pages()
    directive_pages = qweb_directive_pages()
    comp_pages, stats = component_pages(registry)
    guides = guide_pages()
    all_pages: list[Page] = [overview_page(), *syntax_pages, *directive_pages, *comp_pages, *guides]

    css = args.css or Path(os.path.relpath(ROOT / "xweb" / "static" / "app.css", args.out.parent))
    css = css.as_posix()

    # Sidebar groupée dans l'ORDRE d'apparition des groupes (pas un tri
    # alphabétique — Démarrer doit rester en tête).
    groups: dict[str, list[Page]] = {}
    for p in all_pages:
        groups.setdefault(p.group, []).append(p)

    sidebar_html = []
    for group, pages_in_group in groups.items():
        links = "".join(
            f'<a href="#{p.id}" data-page-id="{p.id}">{html_mod.escape(p.title)}</a>' for p in pages_in_group
        )
        sidebar_html.append(f'<div class="sidebar-group"><div class="sidebar-group-title">{html_mod.escape(group)}</div><nav>{links}</nav></div>')

    pages_html = []
    for p in all_pages:
        pages_html.append(f"""
        <section class="doc-page" id="page-{p.id}">
          <header class="doc-page-header">
            <div class="doc-page-group">{html_mod.escape(p.group)}</div>
            <h2 class="doc-page-title">{html_mod.escape(p.title)}</h2>
          </header>
          {p.body}
        </section>
        """)

    page_ids_js = "[" + ",".join(f'"{p.id}"' for p in all_pages) + "]"

    page = f"""<!doctype html>
<html data-theme="light">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>xweb / xdsl — démo &amp; référence de syntaxe</title>
<link rel="stylesheet" href="{css}"/>
<style>{PAGE_CSS}</style>
</head>
<body class="docs-body min-h-screen bg-base-100 text-base-content">
<aside class="docs-sidebar">
  <h1>xweb + xdsl</h1>
  <input id="sidebar-search" type="search" placeholder="Filtrer…"/>
  {"".join(sidebar_html)}
</aside>
<main class="docs-main">
{"".join(pages_html)}
<div class="page-nav">
  <a id="nav-prev" href="#">&laquo; Précédent</a>
  <span class="spacer"></span>
  <a id="nav-next" href="#">Suivant &raquo;</a>
</div>
</main>
<script>window.__PAGE_IDS__ = {page_ids_js};</script>
<script>{PAGE_JS}</script>
</body>
</html>"""

    args.out.write_text(page, encoding="utf-8")
    print(
        f"écrit : {args.out} ({len(all_pages)} pages : "
        f"1 vue d'ensemble, {len(syntax_pages)} syntaxe xdsl, {len(directive_pages)} directives QWeb, "
        f"{len(comp_pages)} composants ({stats['ok']} ok, {stats['err']} err), {len(guides)} guides — "
        f"{len(page)} octets)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
