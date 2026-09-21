// site/templates/shell_patch.dsl — le site ajoute SES assets au <head> commun
// sans toucher au fichier de xweb.
//
// C'est la démonstration la plus directe de la raison d'être de xweb :
// xweb.shell_head est un composant vendorisé (il appartient au paquet xweb,
// la prochaine mise à jour l'écraserait si on l'éditait). Un patch t-inherit
// mode "extension" l'étend EN PLACE, pour tout appelant, sans fork —
// exactement ce qu'un plugin tiers ferait.
//
// Cible : le <link> vers app.css. xweb.shell_head n'a PAS d'élément <head>
// englobant (ses enfants SONT le contenu du head, insérés par xweb.shell),
// donc un xpath "//head" ne matcherait rien — on s'accroche à un nœud qui
// existe vraiment, et on insère juste après.

patch xweb.shell_head {
    xpath "//link[@rel='stylesheet']" {
        after: link { rel: "stylesheet"; href: "/site-static/site.css" }
    }
    xpath "//script[@src='/xweb-static/storage.js']" {
        after: script { src: "/site-static/site.js"; defer: "defer" }
    }
}
