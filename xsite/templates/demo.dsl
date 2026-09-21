// site/templates/demo.dsl — la démo interactive : htmx, _hyperscript et un
// channel SSE qui tourne pour de vrai contre le backend de ce site.
//
// C'est ici que le DSL est exercé à fond : endpoint/use:, channel/use_channel:,
// hyperscript inline, et des fragments re-rendus côté serveur.

import { doc_header, code_sample, gotcha } from "site"
import { badge, card, toast } from "xweb"

// --- Déclarations réseau, en xdsl ------------------------------------------

// Flux SSE servi par site/backend/routes.py — un tick par seconde, avec le
// compteur de ticks et l'heure serveur.
channel site_clock {
    url: "/demo/sse"
    channels: ["clock"]
    transport: "sse"
    connect_timeout_ms: 5000
    onmessage {
        bind: { "#sse-time": "time"; "#sse-ticks": "ticks" }
        dispatch: true
        event: "clock:tick"
    }
}

component site.demo_page {
    div { class: ["max-w-4xl", "mx-auto", "py-6", "flex", "flex-col", "gap-8"]

        doc_header {
            section: "Démo"
            section_path: "/demo"
            title: "Démo interactive"
            subtitle: "Tout ce qui suit tourne réellement : vraies requêtes, vrai flux SSE, vrai hyperscript."
        }

        // ---------------------------------------------------------------
        // 1. hyperscript pur — zéro réseau
        // ---------------------------------------------------------------
        card { title: "1. _hyperscript — comportement pur client"
            div { class: ["flex", "flex-col", "gap-3"]
                div { class: ["flex", "items-center", "gap-3", "flex-wrap"]
                    button {
                        class: ["btn", "btn-primary", "btn-sm"]
                        _ { on click
                                increment #hs-count's textContent
                                then add .animate-pulse to #hs-count
                                then wait 300ms
                                then remove .animate-pulse from #hs-count
                        }
                        "Incrémenter"
                    }
                    button {
                        class: ["btn", "btn-ghost", "btn-sm"]
                        _ { on click set #hs-count's textContent to '0' }
                        "Remettre à zéro"
                    }
                    span { id: "hs-count"; class: ["badge", "badge-lg", "badge-primary"]  "0" }
                }
                code_sample { lang: "xdsl"; caption: "Le code exact de ce bouton"
                    '
button {
    class: ["btn", "btn-primary", "btn-sm"]
    _ { on click
            increment #hs-count\'s textContent
            then add .animate-pulse to #hs-count
            then wait 300ms
            then remove .animate-pulse from #hs-count
    }
    "Incrémenter"
}
'
                }
            }
        }

        // ---------------------------------------------------------------
        // 2. htmx — fragment re-rendu par le SERVEUR
        // ---------------------------------------------------------------
        card { title: "2. htmx — le serveur renvoie du HTML, pas du JSON"
            div { class: ["flex", "flex-col", "gap-3"]
                div {
                    id: "htmx-counter"
                    class: ["flex", "items-center", "gap-3", "flex-wrap"]
                    hx-get: "/demo/counter"
                    hx-target: "#htmx-counter"
                    hx-swap: "innerHTML"
                    hx-trigger: "load"
                    span { class: ["loading", "loading-spinner", "loading-sm"] }
                    span { class: ["text-sm", "opacity-60"]  "Chargement du fragment…" }
                }
                p { class: ["text-sm", "opacity-70"]
                    "Le bouton POSTe vers /demo/counter ; la route incrémente un compteur en mémoire et "
                    "re-rend le MÊME fragment xdsl (site.demo_counter). Aucun JSON, aucun templating client."
                }
                gotcha { title: "hx-target explicite, toujours"
                    span {
                        "Ce bloc pose hx-target=\"#htmx-counter\" sur lui-même. Sans ça, il hériterait le "
                        "hx-target=\"#xweb-content\" du shell et remplacerait la page entière à chaque clic."
                    }
                }
            }
        }

        // ---------------------------------------------------------------
        // 3. channel SSE — flux serveur poussé vers le DOM
        // ---------------------------------------------------------------
        card { title: "3. channel — flux SSE poussé par le serveur"
            div {
                use_channel: site_clock
                class: ["flex", "flex-col", "gap-3"]

                div { class: ["flex", "items-center", "gap-4", "flex-wrap"]
                    div { class: ["stat", "bg-base-200", "rounded-box", "px-4", "py-2"]
                        div { class: ["stat-title", "text-xs"]  "Heure serveur" }
                        div { id: "sse-time"; class: ["stat-value", "text-lg", "font-mono"]  "—" }
                    }
                    div { class: ["stat", "bg-base-200", "rounded-box", "px-4", "py-2"]
                        div { class: ["stat-title", "text-xs"]  "Ticks reçus" }
                        div { id: "sse-ticks"; class: ["stat-value", "text-lg"]  "0" }
                    }
                    span {
                        id: "sse-pulse"
                        class: ["badge", "badge-ghost"]
                        _ { on clock:tick from document
                                add .badge-success
                                then wait 400ms
                                then remove .badge-success
                        }
                        "en attente…"
                    }
                }

                code_sample { lang: "xdsl"; caption: "La déclaration complète du flux"
                    '
channel site_clock {
    url: "/demo/sse"
    channels: ["clock"]
    transport: "sse"
    connect_timeout_ms: 5000
    onmessage {
        bind: { "#sse-time": "time"; "#sse-ticks": "ticks" }
        dispatch: true
        event: "clock:tick"
    }
}

div { use_channel: site_clock
    span { id: "sse-time"  "—" }
}
'
                }

                p { class: ["text-sm", "opacity-70"]
                    "bind: écrit les champs du message en textContent (jamais innerHTML — une donnée temps réel "
                    "n'est jamais du HTML de confiance). dispatch: true émet en plus un CustomEvent DOM, "
                    "que le badge ci-dessus écoute en _hyperscript ordinaire."
                }
            }
        }

        // ---------------------------------------------------------------
        // 4. Les composants du catalogue, assemblés
        // ---------------------------------------------------------------
        card { title: "4. Des composants du catalogue, composés"
            div { class: ["flex", "flex-col", "gap-4"]
                div { class: ["flex", "items-center", "gap-2", "flex-wrap"]
                    badge { color: "primary"  "primary" }
                    badge { color: "secondary"  "secondary" }
                    badge { color: "success"  "success" }
                    badge { color: "warning"  "warning" }
                    badge { color: "error"  "error" }
                }
                code_sample { lang: "xdsl"
                    '
badge { color: "primary"  "primary" }
badge { color: "success"  "success" }
'
                }
                p { class: ["text-sm", "opacity-70"]
                    "Ces badges sont de vrais t-call vers xweb.badge, rendus côté serveur — la même mécanique "
                    "que n'importe quelle page du catalogue."
                }
            }
        }
    }
}

// Fragment re-rendu par la route htmx — un composant xdsl à part entière,
// appelé aussi bien au chargement initial qu'après chaque clic.
component site.demo_counter {
    span { class: ["text-sm", "opacity-70"]  "Compteur serveur :" }
    span { class: ["badge", "badge-lg", "badge-secondary"]  count }
    button {
        class: ["btn", "btn-secondary", "btn-sm"]
        hx-post: "/demo/counter"
        hx-target: "#htmx-counter"
        hx-swap: "innerHTML"
        "+1 côté serveur"
    }
    button {
        class: ["btn", "btn-ghost", "btn-sm"]
        hx-post: "/demo/counter/reset"
        hx-target: "#htmx-counter"
        hx-swap: "innerHTML"
        "Reset"
    }
    span { class: ["text-xs", "opacity-50"]  "rendu à " last_render }
}
