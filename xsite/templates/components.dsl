// site/templates/components.dsl — catalogue des composants xweb.*.
//
// Seule section dont le CONTENU vient du backend : la liste des composants,
// leurs props réelles et leur rendu de démo sont extraits de
// xweb/components/*.xml à chaud (site/backend/catalog.py). La MISE EN PAGE
// reste ici, en xdsl, comme partout ailleurs.

import { doc_header, index_card, code_sample } from "site"
import { badge, table, collapse, breadcrumbs } from "xweb"

component site.components_index {
    div { class: ["max-w-5xl", "mx-auto", "py-6"]
        doc_header {
            section: "Composants"
            section_path: "/components"
            title: "Catalogue des composants"
            subtitle: "Chaque composant xweb.*, avec une démo réellement rendue par le moteur."
        }
        div { class: ["flex", "items-center", "gap-3", "mb-5", "flex-wrap"]
            input {
                type: "search"
                placeholder: "Filtrer les composants…"
                class: ["input", "input-bordered", "w-full", "max-w-sm"]
                data-filter-input: "1"
            }
            badge { color: "success"  ok_count }
            badge { color: "ghost"  "rendus par le vrai QwebRegistry" }
        }
        div { class: ["grid", "grid-cols-1", "sm:grid-cols-2", "lg:grid-cols-3", "gap-3"]
            for comp in components {
                index_card {
                    path: "/components/${comp['short']}"
                    label: comp["short"]
                    summary: comp["summary"]
                }
            }
        }
    }
}

component site.component_detail {
    crumbs = [{"label": "Composants", "path": "/components"}, {"label": short, "path": ""}]
    props_columns = [{"key": "prop", "label": "Prop"}, {"key": "default", "label": "Défaut"}]

    div { class: ["max-w-4xl", "mx-auto", "py-6", "flex", "flex-col", "gap-5"]

        div { class: ["flex", "flex-col", "gap-2"]
            breadcrumbs { items: crumbs }
            div { class: ["flex", "items-center", "gap-3", "flex-wrap"]
                h1 { class: ["text-3xl", "font-bold", "font-mono"]  name }
                badge { color: "${'success' if status == 'ok' else 'error'}"  status }
            }
            p { class: ["opacity-70"]  docstring }
        }

        div { class: ["flex", "flex-col", "gap-2"]
            h2 { class: ["text-xl", "font-bold"]  "Démo" }
            div { class: ["demo-frame", "border", "border-dashed", "border-base-300", "rounded-box", "p-8", "flex", "justify-center", "items-start", "bg-base-100"]
                raw rendered
            }
            p { class: ["text-xs", "opacity-60"]
                "Rendu à la requête par le même QwebRegistry que cette page — pas une image, pas un extrait figé."
            }
        }

        div { class: ["flex", "flex-col", "gap-2"]
            h2 { class: ["text-xl", "font-bold"]  "Props réelles" }
            p { class: ["text-sm", "opacity-70"]
                "Extraites des <t t-set=\"prop\" t-default=\"…\"/> du composant lui-même, jamais d'une liste tenue à la main."
            }
            table {
                columns: props_columns
                rows: props_rows
                zebra: true
                size: "sm"
                empty: "Aucune prop déclarée."
            }
        }

        div { class: ["flex", "flex-col", "gap-2"]
            h2 { class: ["text-xl", "font-bold"]  "Comment l'utiliser" }
            div { class: ["grid", "grid-cols-1", "lg:grid-cols-2", "gap-4"]
                code_sample { lang: "xdsl"; caption: "En xdsl"
                    xdsl_usage
                }
                code_sample { lang: "xml"; caption: "En QWeb (t-call)"
                    xweb_usage
                }
            }
            code_sample { lang: "xml"; caption: "En QWeb (raccourci <xweb:…>)"
                shorthand_usage
            }
        }

        collapse { title: "Source du composant"; variant: "arrow"
            pre { class: ["code-block"]
                code { data-lang: "xml"
                    source
                }
            }
        }
    }
}
