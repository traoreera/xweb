// site/templates/layout.dsl — briques de mise en page réutilisées par toutes
// les pages du site. Écrit en xdsl, appelé en xdsl : c'est la démonstration
// que la composition de composants marche aussi pour des composants MAISON,
// pas seulement pour le catalogue xweb.*.
//
// Le shell (sidebar, topbar, hx-boost) vient de xweb.shell, posé par
// mount_xweb_page côté backend — ces composants-ci ne s'occupent que du
// contenu de #xweb-content.

import { breadcrumbs } from "xweb"

// En-tête commun : fil d'Ariane + titre + sous-titre optionnel.
component site.doc_header {
    props: {
        section: ""
        section_path: ""
        title: ""
        subtitle: ""
    }
    crumbs = [{"label": section, "path": section_path}, {"label": title, "path": ""}]
    div { class: ["flex", "flex-col", "gap-2", "mb-6"]
        breadcrumbs { items: crumbs }
        h1 { class: ["text-3xl", "font-bold"]  title }
        if (subtitle) {
            p { class: ["opacity-70"]  subtitle }
        }
    }
}

// Pied de page : précédent / suivant, pour parcourir une section une page
// à la fois. Un lien vide n'affiche rien (t-if sur le chemin).
component site.page_nav {
    props: {
        prev_path: ""
        prev_label: ""
        next_path: ""
        next_label: ""
    }
    div { class: ["flex", "justify-between", "items-center", "gap-4", "mt-10", "pt-4", "border-t", "border-base-300"]
        if (prev_path) {
            a { href: prev_path; class: ["btn", "btn-ghost", "btn-sm"]
                "« "
                prev_label
            }
        } else {
            span {}
        }
        if (next_path) {
            a { href: next_path; class: ["btn", "btn-ghost", "btn-sm"]
                next_label
                " »"
            }
        } else {
            span {}
        }
    }
}

// Carte d'entrée d'index : un lien vers une page, avec résumé.
component site.index_card {
    props: {
        path: ""
        label: ""
        summary: ""
    }
    a {
        href: path
        data-filter-key: label
        class: ["index-card", "card", "bg-base-100", "border", "border-base-300", "p-4", "flex", "flex-col", "gap-1", "hover:border-primary", "transition-colors"]
        div { class: ["font-semibold"]  label }
        div { class: ["text-sm", "opacity-70"]  summary }
    }
}

// Bloc d'exemple de code avec son libellé de langage. Le contenu est passé
// en slot (une chaîne multi-ligne xdsl) — voir la convention "newline en
// tête" documentée dans home.dsl.
component site.code_sample {
    props: {
        lang: "xdsl"
        caption: ""
    }
    div { class: ["flex", "flex-col", "gap-1", "my-3"]
        if (caption) {
            div { class: ["text-xs", "uppercase", "tracking-wide", "opacity-60", "font-semibold"]  caption }
        }
        pre { class: ["code-block"]
            code { data-lang: lang
                slot
            }
        }
    }
}

// Encadré "piège réel" — utilisé partout où ce dépôt documente un bug
// réellement rencontré plutôt qu'une bonne pratique théorique.
component site.gotcha {
    props: { title: "Piège réel" }
    div { class: ["alert", "alert-warning", "flex", "flex-col", "items-start", "gap-1", "my-3", "text-sm"]
        div { class: ["font-bold"]  title }
        div { slot }
    }
}
