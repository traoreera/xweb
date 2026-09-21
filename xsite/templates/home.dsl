// site/templates/home.dsl — page d'accueil du site de présentation xweb+xdsl.
//
// TOUT est écrit en xdsl : la prose, les exemples de code, la mise en page.
// Aucune chaîne HTML construite en Python — le backend ne fournit que des
// DONNÉES (catalogue des composants), jamais du markup.
//
// Convention des blocs de code dans tout ce dossier : la chaîne commence par
// un saut de ligne (`code { '` puis retour à la ligne) pour que TOUTES les
// lignes de l'exemple soient à la colonne 0 dans le rendu — sinon le
// compilateur indente la première ligne (son indentation de template) et pas
// les suivantes. site/static/site.js fait ensuite un trim() de sécurité.

import { card, badge } from "xweb"

component site.home {
    div { class: ["max-w-4xl", "mx-auto", "flex", "flex-col", "gap-8", "py-6"]

        div { class: ["flex", "flex-col", "gap-3"]
            div { class: ["flex", "items-center", "gap-3", "flex-wrap"]
                h1 { class: ["text-4xl", "font-bold"]  "xweb + xdsl" }
                badge { color: "primary"  "server-only" }
                badge { color: "ghost"  "zéro runtime JS de template" }
            }
            p { class: ["text-lg", "opacity-80"]
                "Un moteur de rendu QWeb (XML + directives t-*) et un SDK de plugin pour xcore, "
                "plus un DSL déclaratif QML-like qui se transpile vers ce même QWeb. "
                "Ce site est lui-même écrit intégralement en xdsl et servi par xcore."
            }
        }

        div { class: ["grid", "grid-cols-1", "md:grid-cols-3", "gap-4"]
            a { href: "/syntax"; class: ["card", "bg-base-100", "border", "border-base-300", "p-5", "hover:border-primary", "transition-colors", "flex", "flex-col", "gap-2"]
                div { class: ["text-lg", "font-semibold"]  "Syntaxe xdsl" }
                div { class: ["text-sm", "opacity-70"]
                    "component, data, endpoint, channel, copy/patch, hyperscript, filtres — une page par construction, avec son équivalent QWeb compilé."
                }
            }
            a { href: "/directives"; class: ["card", "bg-base-100", "border", "border-base-300", "p-5", "hover:border-primary", "transition-colors", "flex", "flex-col", "gap-2"]
                div { class: ["text-lg", "font-semibold"]  "Directives QWeb" }
                div { class: ["text-sm", "opacity-70"]
                    "t-name, t-if, t-foreach, t-esc/t-out, t-att, t-call, t-set, t-inherit, et les 16 filtres du set fermé."
                }
            }
            a { href: "/components"; class: ["card", "bg-base-100", "border", "border-base-300", "p-5", "hover:border-primary", "transition-colors", "flex", "flex-col", "gap-2"]
                div { class: ["text-lg", "font-semibold"]  "Composants" }
                div { class: ["text-sm", "opacity-70"]
                    "Le catalogue xweb.* complet : démo réellement rendue, props réelles, usage en xdsl ET en QWeb."
                }
            }
        }

        div { class: ["flex", "flex-col", "gap-3"]
            h2 { class: ["text-2xl", "font-bold"]  "Le pipeline" }
            pre { class: ["code-block", "diagram"]
                code { '
.dsl (texte)  ──Parser──▶  AST  ──Compiler──▶  XML QWeb  ──QwebRegistry──▶  HTML
      │                                              │
      └── xdsl/parser.py                             └── xweb/engine/ (t-*, t-inherit,
          xdsl/compiler.py                                filtres, i18n)

Navigateur : htmx (requêtes) + _hyperscript (comportement DOM) + DaisyUI (style)
             — AUCUN moteur de template côté client.
' }
            }
            p { class: ["text-sm", "opacity-70"]
                "Le moteur QWeb ignore complètement que xdsl existe : "
                "QwebRegistry.register_dir() détecte un .dsl (par extension OU par contenu) et le transpile "
                "avant enregistrement. Un plugin dépose un .dsl là où un .xml allait, rien d'autre ne change."
            }
        }

        div { class: ["flex", "flex-col", "gap-3"]
            h2 { class: ["text-2xl", "font-bold"]  "Le même composant, trois écritures" }
            div { class: ["grid", "grid-cols-1", "lg:grid-cols-3", "gap-4"]

                card { title: "1. xdsl"
                    pre { class: ["code-block"]
                        code { '
button {
    variant: "primary"
    size: "sm"
    "Ajouter"
}
' }
                    }
                }

                card { title: "2. QWeb (t-call)"
                    pre { class: ["code-block"]
                        code { '
<t t-call="xweb.button"
   variant="primary"
   size="sm">
    Ajouter
</t>
' }
                    }
                }

                card { title: "3. QWeb (raccourci)"
                    pre { class: ["code-block"]
                        code { '
<xweb:button
    variant="primary"
    size="sm">
    Ajouter
</xweb:button>
' }
                    }
                }
            }
            p { class: ["text-sm", "opacity-70"]
                "Les trois produisent exactement le même HTML. Le raccourci <xweb:nom> est désucré au PARSE "
                "(xweb/engine/parser.py), avant que le compilateur, le registre ou l'héritage ne voient quoi que ce soit."
            }
        }

        div { class: ["flex", "flex-col", "gap-3"]
            h2 { class: ["text-2xl", "font-bold"]  "Ce site, concrètement" }
            div { class: ["grid", "grid-cols-1", "md:grid-cols-2", "gap-4"]
                card { title: "Ce qui est en xdsl"
                    ul { class: ["list-disc", "pl-5", "text-sm", "flex", "flex-col", "gap-1"]
                        li { "Toutes les pages (site/templates/*.dsl) — prose, exemples, mise en page." }
                        li { "La navigation par liens, boostée par hx-boost du shell." }
                        li { "Les comportements client, en _hyperscript inline." }
                    }
                }
                card { title: "Ce qui reste en Python"
                    ul { class: ["list-disc", "pl-5", "text-sm", "flex", "flex-col", "gap-1"]
                        li { "Le boot xcore + xweb monté en extension (integration.yaml)." }
                        li { "Les routes (mount_xweb_page) et les DONNÉES du catalogue." }
                        li { "L'extraction des props réelles depuis xweb/components/*.xml." }
                    }
                }
            }
        }

        div { class: ["alert", "alert-info", "text-sm"]
            span {
                "Chaque page de démo ci-dessous est rendue par le VRAI moteur, pas une capture : "
                "le composant que vous voyez est exécuté à la requête, avec le même QwebRegistry que le reste du site."
            }
        }
    }
}
