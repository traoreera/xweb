// site/templates/directives.dsl — référence des directives QWeb du moteur
// xweb (xweb/engine/), une directive par page. Tout en xdsl.

import { doc_header, page_nav, index_card, code_sample, gotcha } from "site"

component site.directives_index {
    div { class: ["max-w-4xl", "mx-auto", "py-6"]
        doc_header {
            section: "Directives QWeb"
            section_path: "/directives"
            title: "Directives QWeb"
            subtitle: "Le langage du moteur lui-même : XML valide + attributs t-*."
        }
        p { class: ["mb-5", "opacity-70"]
            "Un fichier .xml sans aucune directive est déjà un template QWeb valide. Les directives ci-dessous sont ce que xdsl produit en sortie — les connaître aide à lire le XML compilé."
        }
        input {
            type: "search"
            placeholder: "Filtrer…"
            class: ["input", "input-bordered", "w-full", "max-w-sm", "mb-5"]
            data-filter-input: "1"
        }
        div { class: ["grid", "grid-cols-1", "md:grid-cols-2", "gap-3"]
            index_card { path: "/directives/t-name"; label: "t-name"; summary: "Le nom qualifié du template — la clé du registre." }
            index_card { path: "/directives/t-if"; label: "t-if / t-elif / t-else"; summary: "Branchement conditionnel sur un nœud entier." }
            index_card { path: "/directives/t-foreach"; label: "t-foreach / t-as"; summary: "Répétition, avec les variables _index/_size/_first/_last." }
            index_card { path: "/directives/t-esc"; label: "t-esc / t-out"; summary: "Sortie échappée par défaut, brute seulement si Markup." }
            index_card { path: "/directives/t-att"; label: "t-att-* / t-attf-*"; summary: "Attribut calculé, ou attribut formaté avec interpolation." }
            index_card { path: "/directives/t-call"; label: "t-call"; summary: "Inclure un autre template — le seul mécanisme de composition." }
            index_card { path: "/directives/t-set"; label: "t-set / t-value"; summary: "Variable locale au sous-arbre qui suit." }
            index_card { path: "/directives/filters"; label: "Filtres | nom"; summary: "Les 16 filtres du set fermé, non extensible par un plugin." }
            index_card { path: "/directives/t-inherit"; label: "t-inherit / xpath"; summary: "Héritage non-destructif : extension ou primary." }
            index_card { path: "/directives/passthrough"; label: "hx-* et _"; summary: "Ce que le compilateur ne touche PAS, et pourquoi." }
        }
    }
}

component site.directives_t_name {
    div { class: ["max-w-3xl", "mx-auto", "py-6"]
        doc_header { section: "Directives QWeb"; section_path: "/directives"; title: "t-name"
            subtitle: "Le nom qualifié du template — clé du registre, cible d'un t-call ou d'un t-inherit." }
        code_sample { lang: "xml"
            '
<template t-name="xweb.button">…</template>
'
        }
        p { "Convention : package_id.nom, calquée sur module.template d'Odoo. xweb.button pour un composant du cœur, crm_app.contacts_list pour une page de plugin." }
        gotcha { title: "Un registre global, non namespacé par page"
            span { "QwebRegistry est UN registre process-global : deux plugins qui nomment tous les deux leur template « index » se marchent dessus. Toujours qualifier." }
        }
        page_nav { next_path: "/directives/t-if"; next_label: "t-if / t-elif / t-else" }
    }
}

component site.directives_t_if {
    div { class: ["max-w-3xl", "mx-auto", "py-6"]
        doc_header { section: "Directives QWeb"; section_path: "/directives"; title: "t-if / t-elif / t-else"
            subtitle: "Le nœud PORTEUR disparaît entièrement si la condition est fausse." }
        code_sample { lang: "xml"
            '
<t t-if="href">
    <a t-att-href="href"><t t-esc="slot"/></a>
</t>
<t t-else="1">
    <button><t t-esc="slot"/></button>
</t>
'
        }
        gotcha { title: "Un nom ABSENT du contexte n'est pas simplement « faux »"
            span {
                "_eval attrape NameError sur toute l'expression et retombe sur None. Donc t-if=\"not entries\" "
                "sur un entries absent ne s'affiche PAS non plus : l'échec sur le nom invalide l'expression entière "
                "avant que not s'applique. Avec entries=[] (présent mais vide), not [] vaut bien True. "
                "Un t-call qui oublie de repasser une prop tombe régulièrement dans ce cas."
            }
        }
        page_nav { prev_path: "/directives/t-name"; prev_label: "t-name"; next_path: "/directives/t-foreach"; next_label: "t-foreach / t-as" }
    }
}

component site.directives_t_foreach {
    div { class: ["max-w-3xl", "mx-auto", "py-6"]
        doc_header { section: "Directives QWeb"; section_path: "/directives"; title: "t-foreach / t-as"
            subtitle: "Répète le nœud porteur une fois par élément." }
        code_sample { lang: "xml"
            '
<li t-foreach="items" t-as="item">
    <span t-esc="item.label"/>
    <span t-if="item_last">— dernier</span>
</li>
'
        }
        p { "t-as nomme la variable de boucle. QWeb expose automatiquement item_index, item_size, item_first et item_last." }
        gotcha { title: "Pas de len() dans une expression"
            span { "Les expressions n'ont AUCUN builtin Python. Pour un compte, passez-le pré-calculé depuis la vue, ou utilisez le filtre | length." }
        }
        page_nav { prev_path: "/directives/t-if"; prev_label: "t-if / t-elif / t-else"; next_path: "/directives/t-esc"; next_label: "t-esc / t-out" }
    }
}

component site.directives_t_esc {
    div { class: ["max-w-3xl", "mx-auto", "py-6"]
        doc_header { section: "Directives QWeb"; section_path: "/directives"; title: "t-esc / t-out"
            subtitle: "La frontière de sécurité du moteur." }
        div { class: ["overflow-x-auto", "my-4"]
            table { class: ["table"]
                thead { tr { th { "Directive" } th { "Comportement" } th { "Quand" } } }
                tbody {
                    tr { td { code { "t-esc" } } td { "TOUJOURS échappé" } td { "Défaut pour tout contenu utilisateur" } }
                    tr { td { code { "t-out" } } td { "Brut si Markup, échappé sinon" } td { "Sortie d'un composant de confiance" } }
                }
            }
        }
        gotcha { title: "t-out sur une valeur utilisateur"
            span { "Ne jamais t-out une valeur venant directement d'un input. La règle tient même en cas d'erreur : une str Python ordinaire reste échappée, seul un markupsafe.Markup sort brut." }
        }
        page_nav { prev_path: "/directives/t-foreach"; prev_label: "t-foreach / t-as"; next_path: "/directives/t-att"; next_label: "t-att-* / t-attf-*" }
    }
}

component site.directives_t_att {
    div { class: ["max-w-3xl", "mx-auto", "py-6"]
        doc_header { section: "Directives QWeb"; section_path: "/directives"; title: "t-att-* / t-attf-*"
            subtitle: "Attribut dont la valeur est calculée, ou formatée." }
        code_sample { lang: "xml"
            '
<a t-att-href="url"
   t-attf-class="btn btn-{{variant}} {{extra_class}}">…</a>
'
        }
        p { "t-att-nom : la valeur entière est une expression Python. t-attf-nom : une chaîne littérale avec des {{expr}} interpolées." }
        gotcha { title: "t-attf ne s'applique PAS aux props d'un t-call"
            span { "Sur un t-call, un attribut simple (non t-att-) est une chaîne LITTÉRALE, jamais interpolée. Pour une valeur calculée, il faut t-att-nom=\"expression\"." }
        }
        page_nav { prev_path: "/directives/t-esc"; prev_label: "t-esc / t-out"; next_path: "/directives/t-call"; next_label: "t-call" }
    }
}

component site.directives_t_call {
    div { class: ["max-w-3xl", "mx-auto", "py-6"]
        doc_header { section: "Directives QWeb"; section_path: "/directives"; title: "t-call"
            subtitle: "Le SEUL mécanisme d'inclusion — pas de syntaxe séparée pour « les composants »." }
        code_sample { lang: "xml"
            '
<t t-call="xweb.card">
    <t t-set="title">Contacts récents</t>
    <t t-call="xweb.button" variant="primary">Nouveau</t>
</t>
'
        }
        code_sample { lang: "xml"; caption: "Raccourci équivalent, désucré au PARSE"
            '
<xweb:card>
    <xweb:button variant="primary">Nouveau</xweb:button>
</xweb:card>
'
        }
        gotcha { title: "t-call ISOLE le contexte"
            span {
                "La cible ne voit QUE les props qu'on lui passe explicitement. Un composant générique qui a besoin de "
                "_, locale ou account_path doit les recevoir en props — sinon le nom est absent côté cible, "
                "et l'expression entière retombe sur None (voir t-if)."
            }
        }
        page_nav { prev_path: "/directives/t-att"; prev_label: "t-att-* / t-attf-*"; next_path: "/directives/t-set"; next_label: "t-set / t-value" }
    }
}

component site.directives_t_set {
    div { class: ["max-w-3xl", "mx-auto", "py-6"]
        doc_header { section: "Directives QWeb"; section_path: "/directives"; title: "t-set / t-value"
            subtitle: "Variable locale, portée au sous-arbre qui suit." }
        code_sample { lang: "xml"
            '
<t t-set="size_class" t-value="\'btn-sm\' if compact else \'btn-md\'"/>
<t t-set="titre">Contenu capturé comme valeur</t>
'
        }
        p { "Avec t-value : une expression. Sans, le CONTENU du nœud devient la valeur. t-default sert de repli quand la prop n'est pas passée — c'est ainsi que chaque composant xweb déclare ses props." }
        page_nav { prev_path: "/directives/t-call"; prev_label: "t-call"; next_path: "/directives/filters"; next_label: "Filtres | nom" }
    }
}

component site.directives_filters {
    div { class: ["max-w-3xl", "mx-auto", "py-6"]
        doc_header { section: "Directives QWeb"; section_path: "/directives"; title: "Filtres | nom[:arg]"
            subtitle: "Un set FERMÉ de transformations de valeur, chaînables." }
        code_sample { lang: "xml"
            '
<t t-esc="price | money"/>
<t t-esc="created_at | since"/>
<t t-esc="items | length"/>
<t t-esc="names | join:\',\'"/>
'
        }
        div { class: ["overflow-x-auto", "my-4"]
            table { class: ["table", "table-sm", "table-zebra"]
                thead { tr { th { "Filtre" } th { "Rôle" } } }
                tbody {
                    tr { td { code { "since" } } td { "Durée relative — « il y a 3 h »" } }
                    tr { td { code { "date / datetime / time" } } td { "Compaction date/heure" } }
                    tr { td { code { "money" } } td { "Montant français — 1 234,50 €" } }
                    tr { td { code { "number / percent" } } td { "Nombre / pourcentage français" } }
                    tr { td { code { "upper / lower / title / capitalize" } } td { "Casse" } }
                    tr { td { code { "truncate:n" } } td { "Troncature propre (défaut 80)" } }
                    tr { td { code { "slug" } } td { "Slug ASCII" } }
                    tr { td { code { "length / count" } } td { "len() — le builtin est absent" } }
                    tr { td { code { "first / last" } } td { "Premier / dernier élément" } }
                    tr { td { code { "join:sep" } } td { "Joint un itérable" } }
                    tr { td { code { "default:x" } } td { "Repli si vide (None/\"\"/[]/{}/0)" } }
                    tr { td { code { "default_if_empty:x" } } td { "Repli si None ou \"\" seulement" } }
                    tr { td { code { "yesno" } } td { "Oui / Non / —" } }
                    tr { td { code { "urlencode" } } td { "Encodage URL" } }
                }
            }
        }
        gotcha { title: "Aucun plugin ne peut ajouter un filtre"
            span {
                "C'est délibéré : rien d'exécutable ne vient d'un plugin dans le moteur de rendu. Un filtre ne produit "
                "jamais de Markup — le résultat repasse toujours par escape() au t-esc, la frontière de sécurité reste intacte. "
                "Un | suivi d'un nom inconnu n'est pas découpé : a | b reste un OU binaire Python, pas un crash."
            }
        }
        page_nav { prev_path: "/directives/t-set"; prev_label: "t-set / t-value"; next_path: "/directives/t-inherit"; next_label: "t-inherit / xpath" }
    }
}

component site.directives_t_inherit {
    div { class: ["max-w-3xl", "mx-auto", "py-6"]
        doc_header { section: "Directives QWeb"; section_path: "/directives"; title: "t-inherit / xpath"
            subtitle: "La raison d'être de xweb : étendre sans forker." }
        code_sample { lang: "xml"
            '
<template t-name="crm_app.button_badge"
          t-inherit="xweb.button"
          t-inherit-mode="extension">
    <xpath expr="//button" position="inside">
        <span class="badge badge-accent">CRM</span>
    </xpath>
</template>
'
        }
        div { class: ["grid", "grid-cols-1", "md:grid-cols-2", "gap-4", "my-4"]
            div { class: ["card", "bg-base-200", "p-4"]
                div { class: ["font-bold", "mb-1"]  "extension (défaut)" }
                div { class: ["text-sm"]  "Patche la cible EN PLACE. Tous les appelants de xweb.button voient le patch, même ceux qui ignorent l'existence du plugin." }
            }
            div { class: ["card", "bg-base-200", "p-4"]
                div { class: ["font-bold", "mb-1"]  "primary" }
                div { class: ["text-sm"]  "Duplique la cible sous le t-name DU PATCH. Copie figée de l'arbre déjà résolu, pas un lien vivant. La cible reste intacte." }
            }
        }
        gotcha { title: "Un conflit ne lève JAMAIS d'exception"
            span {
                "Deux patches replace sur le même expr = conflit réel : le moins prioritaire est ignoré pour ce nœud, "
                "avec un warning nommant les deux plugins. Jamais une exception — un désaccord entre deux plugins "
                "sans rapport ne doit pas faire planter toutes les pages qui utilisent le composant partagé. "
                "Les conflits sortent au BOOT (check_all()), pas à la première page qui les déclenche par hasard."
            }
        }
        page_nav { prev_path: "/directives/filters"; prev_label: "Filtres | nom"; next_path: "/directives/passthrough"; next_label: "hx-* et _" }
    }
}

component site.directives_passthrough {
    div { class: ["max-w-3xl", "mx-auto", "py-6"]
        doc_header { section: "Directives QWeb"; section_path: "/directives"; title: "hx-* et _ (hyperscript)"
            subtitle: "Ce que le compilateur traverse SANS interpréter." }
        p { "Du point de vue de xweb, ce sont des attributs HTML ordinaires : seul le navigateur les lit. Aucun échappement spécial requis, les deux sont XML-safe par construction." }
        code_sample { lang: "xml"
            '
<button hx-post="/app/crm/contacts"
        hx-target="#list"
        hx-swap="beforeend"
        _="on click add .loading to me"
        class="btn btn-primary">Ajouter</button>
'
        }
        gotcha { title: "hx-on : deux fausses pistes vérifiées contre le vrai code"
            span {
                "hx-on:click=\"…\" (avec deux-points) fait carrément REJETER le fichier par lxml — "
                "« Namespace prefix hx-on is not defined », TemplateSyntaxError au boot. "
                "Et hx-on=\"click: …\" (l'ancienne forme) a été RETIRÉ dans htmx 2.0 : silencieusement inerte. "
                "Seul hx-on-click=\"…\" (tiret) fonctionne — mais il exécute du JS arbitraire via new Function(). "
                "Dans cette pile, le comportement client passe par _hyperscript, pas par hx-on-*."
            }
        }
        page_nav { prev_path: "/directives/t-inherit"; prev_label: "t-inherit / xpath" }
    }
}
