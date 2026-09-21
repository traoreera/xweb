// site/templates/guides.dsl — guides thématiques : styling, hyperscript,
// htmx, architecture. Tout en xdsl.

import { doc_header, page_nav, index_card, code_sample, gotcha } from "site"

component site.guides_index {
    div { class: ["max-w-4xl", "mx-auto", "py-6"]
        doc_header {
            section: "Guides"
            section_path: "/guides"
            title: "Guides"
            subtitle: "Comment les morceaux s'assemblent, et les pièges réellement rencontrés."
        }
        div { class: ["grid", "grid-cols-1", "md:grid-cols-2", "gap-3"]
            index_card { path: "/guides/styling"; label: "Styling — DaisyUI / Tailwind"; summary: "data-theme, build vendorisé, et le piège du scanner de classes." }
            index_card { path: "/guides/hyperscript"; label: "Hyperscript"; summary: "Les patterns réels de ce dépôt, et le piège du bulling d'événement." }
            index_card { path: "/guides/htmx"; label: "htmx"; summary: "hx-boost, hx-target hérité, contrat HX-Request." }
            index_card { path: "/guides/architecture"; label: "Architecture"; summary: "xcore, xweb en extension, QwebRegistry, le chemin d'une requête." }
            index_card { path: "/guides/assets"; label: "Assets statiques"; summary: "Ce qui est vendorisé, ce qui est écrit à la main, et pourquoi." }
        }
    }
}

component site.guides_styling {
    div { class: ["max-w-3xl", "mx-auto", "py-6"]
        doc_header { section: "Guides"; section_path: "/guides"; title: "Styling — DaisyUI / Tailwind v4"
            subtitle: "Un attribut sur <html>, un CSS compilé et commité." }

        h2 { class: ["text-xl", "font-bold", "mt-4", "mb-2"]  "Le mécanisme de thème" }
        p { "DaisyUI théme via l'attribut data-theme sur <html> — pas une classe .dark. Chaque valeur sélectionne un jeu de variables CSS que les classes DaisyUI consomment déjà." }
        code_sample { lang: "html"
            '
<html data-theme="dark">
'
        }
        p { "La bascule est du _hyperscript côté client, sans aucun aller-retour serveur. Un petit script inline dans <head> lit localStorage AVANT le premier rendu — c'est la seule ligne de JS écrite à la main de tout le système de thème." }

        h2 { class: ["text-xl", "font-bold", "mt-6", "mb-2"]  "Le build" }
        code_sample { lang: "bash"
            '
npm install          # une fois
npm run build:css    # à chaque changement de classes
npm run watch:css    # pendant le développement
'
        }
        p { "assets/app.css est la SOURCE ; xweb/static/app.css est la sortie compilée, vendorisée et COMMITÉE — exactement comme htmx.min.js. Node est un outil de dev, jamais une dépendance d'exécution." }

        gotcha { title: "Une classe construite au RENDU n'existe pour personne"
            span {
                "Le scanner de contenu Tailwind v4 ne voit que le TEXTE SOURCE littéral des .xml — jamais le résultat "
                "d'une interpolation. t-attf-class=\"toggle toggle-{{color}}\" produit une classe qui n'apparaît "
                "littéralement nulle part dans le code source : elle n'est donc jamais générée dans app.css, et "
                "l'élément sort sans style. Si un composant DaisyUI a l'air non stylé malgré un build frais, "
                "vérifiez d'abord si sa classe est interpolée — la parade est un @source inline(...) explicite."
            }
        }
        page_nav { next_path: "/guides/hyperscript"; next_label: "Hyperscript" }
    }
}

component site.guides_hyperscript {
    div { class: ["max-w-3xl", "mx-auto", "py-6"]
        doc_header { section: "Guides"; section_path: "/guides"; title: "Hyperscript"
            subtitle: "Le comportement client de ce projet — jamais du JS inline." }

        code_sample { lang: "hyperscript"; caption: "Bascule de thème (xweb.theme_toggle)"
            '
on click
  if document.documentElement.dataset.theme is \'dark\'
    set document.documentElement.dataset.theme to \'light\'
  else
    set document.documentElement.dataset.theme to \'dark\'
  end
  then call localStorage.setItem(\'theme\', document.documentElement.dataset.theme)
'
        }

        gotcha { title: "Le piège du bulling d'événement (xweb.popover)"
            span {
                "Sans « then halt the event » sur le déclencheur, le MÊME clic qui ouvre le panneau est vu comme "
                "un clic « ailleurs » par le panneau lui-même (l'événement bulle jusqu'au document APRÈS l'ouverture) "
                "et le referme aussitôt. Testé : ça ne marche pas sans le halt."
            }
        }

        gotcha { title: "Cibler par relation DOM, jamais par id"
            span {
                "#id résout toujours vers le PREMIER élément portant cet id. Deux popovers sans id explicite sur la "
                "même page : cliquer le second ouvrait le panneau du premier. « the next .popover-panel » n'a besoin "
                "d'aucun id et marche pour un nombre quelconque d'instances."
            }
        }

        h2 { class: ["text-xl", "font-bold", "mt-6", "mb-2"]  "Essayer maintenant" }
        div { class: ["flex", "items-center", "gap-3", "flex-wrap"]
            button {
                class: ["btn", "btn-sm", "btn-outline"]
                _ { on click
                        increment #hs-counter's textContent
                }
                "Incrémenter"
            }
            span { class: ["badge", "badge-lg", "badge-primary"]  id: "hs-counter"  "0" }
            span { class: ["text-sm", "opacity-60"]  "— zéro requête réseau, tout est côté client." }
        }

        page_nav { prev_path: "/guides/styling"; prev_label: "Styling"; next_path: "/guides/htmx"; next_label: "htmx" }
    }
}

component site.guides_htmx {
    div { class: ["max-w-3xl", "mx-auto", "py-6"]
        doc_header { section: "Guides"; section_path: "/guides"; title: "htmx"
            subtitle: "Les requêtes, et les trois pièges qui coûtent le plus cher." }

        h2 { class: ["text-xl", "font-bold", "mt-4", "mb-2"]  "hx-boost sur le shell" }
        p { "xweb.shell pose hx-boost sur <body> : un clic sur un lien interne ne recharge pas la page, il remplace seulement #xweb-content. C'est pourquoi les liens de ce site sont de simples <a href> — aucun hx-get manuel." }

        gotcha { title: "hx-target est HÉRITÉ"
            span {
                "Le shell pose hx-target=\"#xweb-content\" sur <body>. Tout élément qui fait sa PROPRE requête sans "
                "poser le sien hérite silencieusement celui-là : un hx-trigger=\"load\" sans hx-target remplace alors "
                "TOUT le contenu de la page, formulaire compris, dès le premier chargement. Toujours poser un "
                "hx-target explicite, même en auto-référence."
            }
        }

        gotcha { title: "Une route custom doit répliquer le contrat HX-Request"
            span {
                "Une requête boostée arrive avec HX-Request: true et attend <title>…</title> + le FRAGMENT seul. "
                "Une route qui renvoie toujours la page complète fait injecter un <html> entier dans #xweb-content — "
                "DOM cassé, et le symptôme (« mon formulaire a disparu ») n'a aucun rapport apparent avec la cause. "
                "mount_xweb_page gère ce contrat pour vous."
            }
        }

        gotcha { title: "hx-swap=\"none\" sur toute réponse JSON"
            span {
                "Sans lui, htmx remplace l'innerHTML de l'élément déclencheur par le corps brut de la réponse : "
                "le texte JSON écrase le formulaire. xdsl le pose automatiquement dès que receive.type vaut json."
            }
        }

        page_nav { prev_path: "/guides/hyperscript"; prev_label: "Hyperscript"; next_path: "/guides/architecture"; next_label: "Architecture" }
    }
}

component site.guides_architecture {
    div { class: ["max-w-3xl", "mx-auto", "py-6"]
        doc_header { section: "Guides"; section_path: "/guides"; title: "Architecture"
            subtitle: "Comment ce site lui-même est monté." }

        h2 { class: ["text-xl", "font-bold", "mt-4", "mb-2"]  "xweb est une EXTENSION xcore, pas un plugin" }
        code_sample { lang: "yaml"; caption: "site/integration.yaml"
            '
services:
  extensions:
    xweb:
      module: xweb.engine.integration.xcore:XwebExtension
      config:
        namespaces:
          site: site/templates
'
        }
        p { "XwebExtension charge xweb/components/ tout seul (il est embarqué dans le paquet xweb), puis chaque dossier listé dans namespaces. register_dir scanne les .xml ET les .dsl — les templates de ce site sont des .dsl, rien d'autre à configurer." }

        h2 { class: ["text-xl", "font-bold", "mt-6", "mb-2"]  "Le chemin d'une requête" }
        code_sample { lang: "text"
            '
Navigateur ──HTTP──▶ FastAPI (xcore)
                       └── routeur du site
                             └── mount_xweb_page
                                   ├── résout l\'utilisateur (anonyme ici)
                                   ├── appelle la vue (dict de contexte)
                                   └── render_xweb_template
                                         ├── HX-Request ? → <title> + fragment
                                         └── sinon        → xweb.shell complet
'
        }

        h2 { class: ["text-xl", "font-bold", "mt-6", "mb-2"]  "Boot" }
        code_sample { lang: "python"
            '
xcore = Xcore(config_path="site/integration.yaml")
xcore.setup(app)
await xcore.boot(app)
bind_hot_reload(xcore, xcore.services.get("ext.xweb"))
'
        }
        p { "bind_hot_reload nettoie le registre (templates ET patches) plus les quatre registres de contribution quand un plugin est déchargé — un abonnement fait APRÈS le boot, parce qu'une extension est construite avec sa seule config, sans accès à l'event bus." }

        page_nav { prev_path: "/guides/htmx"; prev_label: "htmx"; next_path: "/guides/assets"; next_label: "Assets statiques" }
    }
}

component site.guides_assets {
    div { class: ["max-w-3xl", "mx-auto", "py-6"]
        doc_header { section: "Guides"; section_path: "/guides"; title: "Assets statiques"
            subtitle: "Vendorisé ou écrit à la main — jamais un CDN." }

        div { class: ["overflow-x-auto", "my-4"]
            table { class: ["table", "table-sm", "table-zebra"]
                thead { tr { th { "Fichier" } th { "Nature" } th { "Rôle" } } }
                tbody {
                    tr { td { code { "xweb/static/app.css" } } td { "Compilé, commité" } td { "Tailwind v4 + DaisyUI 5" } }
                    tr { td { code { "xweb/static/htmx.min.js" } } td { "Vendorisé" } td { "Requêtes déclaratives hx-*" } }
                    tr { td { code { "xweb/static/_hyperscript.min.js" } } td { "Vendorisé" } td { "Comportement DOM déclaratif" } }
                    tr { td { code { "xweb/static/live_channel.js" } } td { "Écrit à la main" } td { "SSE/WS unifiés par channels" } }
                    tr { td { code { "xweb/static/storage.js" } } td { "Écrit à la main" } td { "localStorage namespacé" } }
                    tr { td { code { "xweb/static/validators.js" } } td { "Écrit à la main" } td { "Port JS des règles de validation xdsl" } }
                    tr { td { code { "site/static/site.css" } } td { "Propre au site" } td { "Blocs de code, cartes d'index" } }
                    tr { td { code { "site/static/site.js" } } td { "Propre au site" } td { "Filtre d'index, coloration, trim des exemples" } }
                }
            }
        }
        p { "Aucune dépendance npm au runtime : ce qui vient de l'extérieur est vendorisé et commité, ce qui est petit est écrit à la main. Un déploiement sert des fichiers statiques, point." }

        page_nav { prev_path: "/guides/architecture"; prev_label: "Architecture" }
    }
}
