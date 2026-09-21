// site/templates/syntax.dsl — référence de la syntaxe xdsl, une construction
// par page. Prose ET exemples écrits en xdsl : aucune chaîne HTML côté Python.

import { doc_header, page_nav, index_card, code_sample, gotcha } from "site"

component site.syntax_index {
    div { class: ["max-w-4xl", "mx-auto", "py-6"]
        doc_header {
            section: "Syntaxe xdsl"
            section_path: "/syntax"
            title: "Syntaxe xdsl"
            subtitle: "Chaque construction du langage, avec son équivalent QWeb compilé."
        }
        input {
            type: "search"
            placeholder: "Filtrer…"
            class: ["input", "input-bordered", "w-full", "max-w-sm", "mb-5"]
            data-filter-input: "1"
        }
        div { class: ["grid", "grid-cols-1", "md:grid-cols-2", "gap-3"]
            index_card { path: "/syntax/component"; label: "component"; summary: "Déclarer un composant : props, style, imports, contenu." }
            index_card { path: "/syntax/control-flow"; label: "if / elif / else / for"; summary: "Structures de contrôle, compilées en t-if/t-foreach." }
            index_card { path: "/syntax/class-style"; label: "class: et style:"; summary: "Liste de classes et dict de styles, avec interpolation ${...}." }
            index_card { path: "/syntax/text"; label: "Texte, raw, tr"; summary: "Texte littéral, sortie brute, et traduction i18n." }
            index_card { path: "/syntax/hyperscript"; label: "Attribut _ (hyperscript)"; summary: "Mode ligne et mode bloc, et pourquoi ça change tout." }
            index_card { path: "/syntax/data"; label: "data + @décorateurs"; summary: "Schéma de validation, ensemble fermé de règles." }
            index_card { path: "/syntax/endpoint"; label: "endpoint + use:"; summary: "Requête réseau déclarative, expansée en hx-*." }
            index_card { path: "/syntax/channel"; label: "channel + use_channel:"; summary: "SSE/WebSocket déclaratif, bind/refresh/dispatch." }
            index_card { path: "/syntax/inherit"; label: "copy / patch / xpath"; summary: "Héritage non-destructif d'un composant qu'on ne possède pas." }
            index_card { path: "/syntax/filters"; label: "Filtres et @include"; summary: "Chaînage | et directive de layout de fichier." }
        }
    }
}

component site.syntax_component {
    div { class: ["max-w-3xl", "mx-auto", "py-6"]
        doc_header { section: "Syntaxe xdsl"; section_path: "/syntax"; title: "component"
            subtitle: "L'unité de base : un composant xdsl compile vers un <template t-name=\"...\"> QWeb." }

        p { "Un fichier .dsl contient un ou plusieurs composants. Le nom peut être qualifié (site.home) — il devient le t-name du template, la clé du registre." }

        code_sample { lang: "xdsl"; caption: "xdsl"
            '
component contacts_page {
    import { button } from "xweb"

    props: {
        title: "Contacts"
    }

    style: ".title { font-weight: bold; }"

    div { class: ["p-4"]
        h1 { title }
        button { variant: "primary"  "Ajouter" }
    }
}
'
        }

        code_sample { lang: "xml"; caption: "QWeb compilé"
            '
<template t-name="contacts_page">
    <t t-set="title" t-default="\'Contacts\'"/>
    <style>.title { font-weight: bold; }</style>
    <div class="p-4">
        <h1><t t-esc="title"/></h1>
        <t t-call="xweb.button" t-att-variant="\'primary\'">Ajouter</t>
    </div>
</template>
'
        }

        h2 { class: ["text-xl", "font-bold", "mt-6", "mb-2"]  "props:" }
        p { "Déclare les valeurs par défaut des props que le composant accepte. Chaque entrée DOIT avoir une valeur par défaut, et seulement une valeur scalaire (chaîne, nombre, true/false)." }

        gotcha { title: "Pas de liste ni de dict en valeur par défaut"
            span {
                "props: { items: [] } lève une ParseError — _parse_default_value n'accepte que string/number/bool/ident. "
                "Pour une prop de type liste, ne la déclarez pas dans props: : référencez-la directement, "
                "le contexte de rendu la fournira (c'est ce que fait ce site pour le catalogue des composants)."
            }
        }

        page_nav { next_path: "/syntax/control-flow"; next_label: "if / elif / else / for" }
    }
}

component site.syntax_control_flow {
    div { class: ["max-w-3xl", "mx-auto", "py-6"]
        doc_header { section: "Syntaxe xdsl"; section_path: "/syntax"; title: "if / elif / else / for"
            subtitle: "Compilés en t-if / t-elif / t-else / t-foreach." }

        code_sample { lang: "xdsl"; caption: "xdsl"
            '
if (count > 0) {
    span { count }
} elif (count == 0) {
    span { "vide" }
} else {
    span { "négatif ?!" }
}

for contact in contacts {
    div { class: "card"
        span { contact["name"] }
    }
}
'
        }

        code_sample { lang: "xml"; caption: "QWeb compilé"
            '
<t t-if="count > 0"><span><t t-esc="count"/></span></t>
<t t-elif="count == 0"><span>vide</span></t>
<t t-else="1"><span>négatif ?!</span></t>

<t t-foreach="contacts" t-as="contact">
    <div class="card"><span><t t-esc="contact[\'name\']"/></span></div>
</t>
'
        }

        p { class: ["mt-4"]
            "Dans une boucle, QWeb expose automatiquement contact_index, contact_size, contact_first et contact_last."
        }

        gotcha { title: "Un nom absent du contexte n'est pas « faux »"
            span {
                "_eval attrape NameError et retombe sur None. Donc if (not entries) sur un entries ABSENT du contexte "
                "ne s'affiche pas non plus : l'échec sur le nom invalide TOUTE l'expression avant que not s'applique. "
                "Avec entries=[] (présent, vide), ça marche normalement."
            }
        }

        page_nav { prev_path: "/syntax/component"; prev_label: "component"; next_path: "/syntax/class-style"; next_label: "class: et style:" }
    }
}

component site.syntax_class_style {
    div { class: ["max-w-3xl", "mx-auto", "py-6"]
        doc_header { section: "Syntaxe xdsl"; section_path: "/syntax"; title: "class: et style:"
            subtitle: "Liste de classes, dict de styles, et interpolation ${...}." }

        code_sample { lang: "xdsl"; caption: "xdsl"
            '
div {
    class: ["btn", "btn-primary", "${size}-gap", live_class]
    style: { color: "${\'crimson\' if urgent else \'inherit\'}"; padding: "2rem" }
}
'
        }

        code_sample { lang: "xml"; caption: "QWeb compilé"
            '
<div t-attf-class="btn btn-primary {{size}}-gap {{live_class}}"
     t-attf-style="color: {{\'crimson\' if urgent else \'inherit\'}}; padding: 2rem;"/>
'
        }

        p { class: ["mt-4"]
            "Une entrée de la liste peut être une chaîne littérale, une chaîne interpolée, ou une expression nue (un nom du contexte)."
        }

        gotcha { title: "La syntaxe [ ... ] ne produit JAMAIS une vraie liste"
            span {
                "attr: [...] est pensé pour class: — le compilateur joint les items par un espace dans un t-attf-*, "
                "c'est une CHAÎNE. Pour passer une vraie liste Python à un composant (les items d'un breadcrumbs, "
                "les columns d'une table), il faut une assignation locale : crumbs = [{\"label\": \"A\", \"path\": \"/\"}] "
                "puis breadcrumbs { items: crumbs } — qui compile en t-set/t-value avec un vrai littéral Python."
            }
        }

        page_nav { prev_path: "/syntax/control-flow"; prev_label: "if / elif / else / for"; next_path: "/syntax/text"; next_label: "Texte, raw, tr" }
    }
}

component site.syntax_text {
    div { class: ["max-w-3xl", "mx-auto", "py-6"]
        doc_header { section: "Syntaxe xdsl"; section_path: "/syntax"; title: "Texte, raw, tr"
            subtitle: "Trois façons de sortir du contenu, trois niveaux d'échappement." }

        code_sample { lang: "xdsl"; caption: "xdsl"
            '
p { "Texte littéral, échappé." }
p { user_name }
p { raw trusted_html }
p { tr "Se connecter" }
'
        }

        code_sample { lang: "xml"; caption: "QWeb compilé"
            '
<p>Texte littéral, échappé.</p>
<p><t t-esc="user_name"/></p>
<p><t t-out="trusted_html"/></p>
<p><t t-tr="1">Se connecter</t></p>
'
        }

        div { class: ["overflow-x-auto", "my-4"]
            table { class: ["table", "table-sm"]
                thead { tr { th { "Écriture" } th { "Compile vers" } th { "Échappement" } } }
                tbody {
                    tr { td { code { "\"texte\"" } } td { code { "texte brut" } } td { "Échappé à la compilation" } }
                    tr { td { code { "expr" } } td { code { "t-esc" } } td { "Toujours échappé au rendu" } }
                    tr { td { code { "raw expr" } } td { code { "t-out" } } td { "Brut SI la valeur est Markup, échappé sinon" } }
                    tr { td { code { "tr \"texte\"" } } td { code { "t-tr" } } td { "Traduit puis échappé" } }
                }
            }
        }

        gotcha { title: "raw n'est pas un laissez-passer"
            span {
                "t-out ne sort du HTML brut que si la valeur est un markupsafe.Markup. Une chaîne Python ordinaire "
                "est quand même échappée — la frontière de sécurité tient même si on se trompe de directive."
            }
        }

        page_nav { prev_path: "/syntax/class-style"; prev_label: "class: et style:"; next_path: "/syntax/hyperscript"; next_label: "Attribut _ (hyperscript)" }
    }
}

component site.syntax_hyperscript {
    div { class: ["max-w-3xl", "mx-auto", "py-6"]
        doc_header { section: "Syntaxe xdsl"; section_path: "/syntax"; title: "Attribut _ (hyperscript)"
            subtitle: "Le comportement client déclaratif, capturé brut par le lexer." }

        p { "Le lexer capture le script hyperscript en UN token, sans le tokeniser comme du xdsl — sinon des mots comme on, click ou wait entreraient en collision avec la grammaire." }

        code_sample { lang: "xdsl"; caption: "Mode ligne — s'arrête au premier saut de ligne"
            '
button { _ : on click toggle .hidden on #modal }
'
        }

        code_sample { lang: "xdsl"; caption: "Mode bloc — newlines préservées"
            '
div {
    _ {
        on load
            wait 2s
            transition opacity to 0
        on click
            remove me
    }
}
'
        }

        gotcha { title: "Le mode ligne s'arrête au premier \\n"
            span {
                "Un script multi-ligne écrit avec _ : ... ne capture que la PREMIÈRE ligne ; le reste est reparsé "
                "comme du xdsl et provoque une erreur incompréhensible. Dès qu'il y a plus d'une ligne, mode bloc _ { ... }."
            }
        }

        h2 { class: ["text-xl", "font-bold", "mt-6", "mb-2"]  "Démo vivante" }
        p { class: ["text-sm", "opacity-70", "mb-3"]  "Ce bouton est rendu par ce template, son comportement est du vrai _hyperscript exécuté par le navigateur :" }
        div { class: ["flex", "items-center", "gap-3"]
            button {
                class: ["btn", "btn-primary", "btn-sm"]
                _ { on click
                        toggle .hidden on #hs-demo-target
                        then toggle between .btn-primary and .btn-success on me
                }
                "Basculer"
            }
            span { id: "hs-demo-target"; class: ["badge", "badge-lg"]  "Me voici !" }
        }

        page_nav { prev_path: "/syntax/text"; prev_label: "Texte, raw, tr"; next_path: "/syntax/data"; next_label: "data + @décorateurs" }
    }
}

component site.syntax_data {
    div { class: ["max-w-3xl", "mx-auto", "py-6"]
        doc_header { section: "Syntaxe xdsl"; section_path: "/syntax"; title: "data + @décorateurs"
            subtitle: "Un schéma de validation déclaré une fois, utilisé côté serveur ET côté client." }

        code_sample { lang: "xdsl"; caption: "xdsl"
            '
data contact_form {
    name: string @required @min_length(3)
    email: string @required @email
    age: int @min(0) @max(120)
    role: string @in(["admin", "editor"])
}
'
        }

        p { "L'ensemble des règles est FERMÉ (xdsl/validators.py::BUILTIN_VALIDATORS) : required, min_length, max_length, min, max, email, pattern, in. Un décorateur hors de cette liste lève une erreur à la compilation, jamais une faute de frappe silencieuse." }

        code_sample { lang: "python"; caption: "Côté serveur — les MÊMES règles"
            '
from xdsl.api import extract_schemas
from xdsl.validators import validate_dict

schemas = extract_schemas(open("contacts.dsl").read())
errors = validate_dict(payload, schemas["contact_form"])
# {} si valide, sinon {"name": ["Minimum 3 caractères"], ...}
'
        }

        gotcha { title: "data n'émet AUCUN XML et ne valide rien tout seul"
            span {
                "Aucun attribut HTML5 (required, type=\"email\") n'est généré sur les <input> correspondants — "
                "à écrire à la main. Et sans une route Python qui appelle extract_schemas/validate_dict, "
                "rien ne valide nulle part. C'est un outil DRY, pas un mécanisme d'application forcée."
            }
        }

        page_nav { prev_path: "/syntax/hyperscript"; prev_label: "Attribut _ (hyperscript)"; next_path: "/syntax/endpoint"; next_label: "endpoint + use:" }
    }
}

component site.syntax_endpoint {
    div { class: ["max-w-3xl", "mx-auto", "py-6"]
        doc_header { section: "Syntaxe xdsl"; section_path: "/syntax"; title: "endpoint + use:"
            subtitle: "Une requête HTTP décrite une fois, attachée à un élément." }

        code_sample { lang: "xdsl"; caption: "xdsl"
            '
endpoint create_contact {
    method: POST
    url: "/api/contacts"
    send: contact_form
    receive {
        type: json
        target: "#contacts-table"
        event: "contacts:changed"
    }
    onloading { p { "Envoi…" } }
    onsuccess { toast { variant: "success"  "Créé !" } }
    onerror { toast { variant: "error"  "Erreur" } }
}

form { use: create_contact
    input { name: "name"; required: true }
    button { type: "submit"  "Ajouter" }
}
'
        }

        p { "use: expanse à la compilation en hx-{method}, hx-headers, hx-indicator, hx-swap et un bloc _hyperscript qui bascule la visibilité des blocs onsuccess/onerror précompilés." }

        gotcha { title: "Jamais de JSON re-templaté côté client"
            span {
                "QWeb n'a aucun runtime navigateur. receive.target/event ne rend PAS la réponse JSON : "
                "il diffuse un événement, et c'est à l'élément cible d'aller rechercher son HTML à jour "
                "auprès du serveur via son propre hx-trigger. Le « rendu » reste un aller-retour serveur."
            }
        }

        gotcha { title: "hx-swap=\"none\" est automatique sur un endpoint JSON"
            span {
                "Sans lui, htmx remplacerait l'innerHTML de l'élément déclencheur par le corps brut de la réponse — "
                "le texte JSON écraserait le formulaire lui-même. Le compilateur le pose dès que receive.type vaut json."
            }
        }

        page_nav { prev_path: "/syntax/data"; prev_label: "data + @décorateurs"; next_path: "/syntax/channel"; next_label: "channel + use_channel:" }
    }
}

component site.syntax_channel {
    div { class: ["max-w-3xl", "mx-auto", "py-6"]
        doc_header { section: "Syntaxe xdsl"; section_path: "/syntax"; title: "channel + use_channel:"
            subtitle: "SSE ou WebSocket déclaratif, au-dessus de xweb/static/live_channel.js." }

        code_sample { lang: "xdsl"; caption: "xdsl"
            '
data contact_form { count: int @min(0) }

channel contacts_feed {
    url: "/sse/contacts"
    channels: ["contacts"]
    transport: "sse"
    connect_timeout_ms: 5000
    validate: "contact_form"
    persist: "last_contact"
    onmessage {
        bind: { "#counter": "count" }
        refresh: "#contacts-table"
        dispatch: true
        event: "contacts:changed"
    }
}

div { use_channel: contacts_feed
    span { id: "counter"  "0" }
}
'
        }

        div { class: ["overflow-x-auto", "my-4"]
            table { class: ["table", "table-sm"]
                thead { tr { th { "Clé de onmessage" } th { "Effet" } } }
                tbody {
                    tr { td { code { "bind" } } td { "Écrit un champ du message en textContent (jamais innerHTML)" } }
                    tr { td { code { "refresh" } } td { "htmx.trigger() sur la cible — elle recharge son HTML du serveur" } }
                    tr { td { code { "dispatch" } } td { "CustomEvent DOM réel — la porte de sortie vers du hyperscript" } }
                    tr { td { code { "event" } } td { "Nom d'événement partagé par refresh et dispatch" } }
                }
            }
        }

        p { "La grammaire de onmessage est FERMÉE : ces quatre clés, rien d'autre. Pour du comportement arbitraire, dispatch: true émet un CustomEvent que n'importe quel _hyperscript peut écouter — sans ouvrir onmessage à du code libre." }

        code_sample { lang: "xdsl"; caption: "Réagir au dispatch, en hyperscript ordinaire"
            '
span {
    _ { on contacts:changed from document
            put event.detail.data.count into me
    }
}
'
        }

        p { class: ["text-sm", "opacity-70"]
            "WS et SSE fonctionnent simultanément : deux blocs channel distincts, deux instances XwebLiveChannel indépendantes. "
            "En WS, l'enveloppe attendue est {\"channel\": \"nom\", \"data\": {...}} ; le client ne filtre pas, c'est au serveur d'honorer ?channels=."
        }

        page_nav { prev_path: "/syntax/endpoint"; prev_label: "endpoint + use:"; next_path: "/syntax/inherit"; next_label: "copy / patch / xpath" }
    }
}

component site.syntax_inherit {
    div { class: ["max-w-3xl", "mx-auto", "py-6"]
        doc_header { section: "Syntaxe xdsl"; section_path: "/syntax"; title: "copy / patch / xpath"
            subtitle: "Étendre un composant qu'on ne possède pas, sans le forker. La raison d'être de xweb." }

        code_sample { lang: "xdsl"; caption: "patch — modifie le template partagé EN PLACE"
            '
patch xweb.button {
    xpath "//button" { inside: span { class: "badge badge-accent"  "CRM" } }
}
'
        }

        code_sample { lang: "xdsl"; caption: "copy — duplique sous un nouveau nom, la source reste intacte"
            '
copy xweb.button as crm.fancy_button {
    xpath "//button" { attributes: a { data-fancy: "1" } }
}
'
        }

        div { class: ["overflow-x-auto", "my-4"]
            table { class: ["table", "table-sm"]
                thead { tr { th { "position" } th { "Effet sur le nœud ciblé" } } }
                tbody {
                    tr { td { code { "before" } } td { "Insère juste avant" } }
                    tr { td { code { "after" } } td { "Insère juste après" } }
                    tr { td { code { "inside" } } td { "Insère en dernier enfant" } }
                    tr { td { code { "replace" } } td { "Remplace entièrement" } }
                    tr { td { code { "attributes" } } td { "Ajoute/modifie des attributs" } }
                }
            }
        }

        gotcha { title: "copy et patch n'acceptent QUE des blocs xpath"
            span {
                "Un corps littéral (copy X as Y { div { ... } }) lève une ParseError. Ce n'est pas une limite du DSL : "
                "le moteur QWeb lui-même ne lit jamais qu'un <xpath> dans un template t-inherit — un contenu littéral "
                "y serait silencieusement ignoré au rendu, ce qui est bien pire qu'une erreur."
            }
        }

        gotcha { title: "attributes prend un élément, pas un dict"
            span {
                "La forme correcte est attributes: a { clé: \"valeur\" } — chaque attribut de cet élément devient un "
                "<attribute name=\"clé\">valeur</attribute>, la seule forme que extract_patch lit réellement."
            }
        }

        page_nav { prev_path: "/syntax/channel"; prev_label: "channel + use_channel:"; next_path: "/syntax/filters"; next_label: "Filtres et @include" }
    }
}

component site.syntax_filters {
    div { class: ["max-w-3xl", "mx-auto", "py-6"]
        doc_header { section: "Syntaxe xdsl"; section_path: "/syntax"; title: "Filtres et @include"
            subtitle: "Formatage de valeur, et directive de layout de fichier." }

        code_sample { lang: "xdsl"; caption: "Filtres — même set fermé que QWeb"
            '
span { price | money }
span { created_at | since }
span { items | length }
span { names | join:"," }
'
        }

        p { "Un seul argument par filtre en expression nue : une virgule de premier niveau serait ambiguë avec un séparateur d'item de class: [...]. Pour un cas multi-arguments, écrire le filtre dans une interpolation ${...}." }

        code_sample { lang: "xdsl"; caption: "@include — layout de fichier"
            '
@include "xweb.shell"

component ma_page {
    div { "Contenu" }
}
'
        }

        p { "Directive de tête de fichier, une seule fois : elle indique dans quel layout envelopper le rendu (utilisée par scripts/dsl2html.py pour un aperçu autonome). En production, c'est mount_xweb_page qui décide du shell." }

        page_nav { prev_path: "/syntax/inherit"; prev_label: "copy / patch / xpath" }
    }
}
