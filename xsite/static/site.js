/**
 * site/static/site.js — le JS propre à ce site, écrit à la main.
 *
 * Aucune dépendance, aucun CDN : même posture que le reste du JS de ce dépôt
 * (xweb/static/storage.js, live_channel.js, validators.js). Injecté dans le
 * <head> commun par site/templates/shell_patch.dsl.
 *
 * Trois rôles, tous purement cosmétiques — le site reste entièrement lisible
 * et navigable si ce fichier ne se charge pas :
 *   1. trim() des blocs de code (convention "newline en tête" des chaînes
 *      multi-lignes xdsl, voir site/templates/home.dsl) ;
 *   2. coloration syntaxique légère, jeu FERMÉ de mots-clés par langage ;
 *   3. filtre de recherche sur les cartes d'index.
 *
 * xweb.shell boost la navigation (hx-boost sur <body>) : le contenu de
 * #xweb-content est REMPLACÉ sans rechargement de page. Tout est donc
 * (ré)appliqué sur htmx:afterSettle en plus du chargement initial, et rendu
 * idempotent (marqueur data-site-done) pour ne jamais re-colorer du HTML
 * déjà colorisé — ce qui doublerait les <span> à chaque navigation.
 */
(function () {
  "use strict";

  // --- 1. Nettoyage des blocs de code -------------------------------------

  function trimCodeBlocks(root) {
    for (const code of root.querySelectorAll(".code-block code")) {
      if (code.dataset.siteTrimmed === "1") continue;
      code.textContent = code.textContent.replace(/^\n+/, "").replace(/\s+$/, "");
      code.dataset.siteTrimmed = "1";
    }
  }

  // --- 2. Coloration syntaxique -------------------------------------------
  // Jeu fermé, par langage — pas un vrai tokenizer : des expressions
  // régulières appliquées sur du texte DÉJÀ échappé par le moteur. On
  // travaille donc sur innerHTML (où `<` est déjà `&lt;`), ce qui garantit
  // qu'aucun contenu ne peut créer de balise : le seul HTML injecté ici est
  // celui de nos propres <span>.

  const RULES = {
    xdsl: [
      [/\b(component|import|from|if|elif|else|for|in|patch|copy|as|priority|slot|raw|tr|style|props|xpath|inside|replace|before|after|attributes|extension|primary|data|endpoint|channel|use|use_channel)\b/g, "tok-keyword"],
      [/@\w+/g, "tok-deco"],
      [/&#34;[^&]*?&#34;|&quot;[^&]*?&quot;|'[^']*?'/g, "tok-string"],
      [/\/\/[^\n]*/g, "tok-comment"],
    ],
    xml: [
      [/&lt;\/?[a-zA-Z][\w:.-]*/g, "tok-tag"],
      [/[a-zA-Z-]+(?==&#34;)|[a-zA-Z-]+(?==&quot;)/g, "tok-attr"],
      [/&#34;[^&]*?&#34;|&quot;[^&]*?&quot;/g, "tok-string"],
      [/&lt;!--[\s\S]*?--&gt;/g, "tok-comment"],
    ],
    python: [
      [/\b(def|class|import|from|return|if|else|elif|for|in|try|except|raise|with|as|None|True|False|await|async)\b/g, "tok-keyword"],
      [/&#34;[^&]*?&#34;|&quot;[^&]*?&quot;|'[^']*?'/g, "tok-string"],
      [/#[^\n]*/g, "tok-comment"],
    ],
    hyperscript: [
      [/\b(on|from|end|if|else|then|wait|put|into|add|remove|toggle|set|call|send|trigger|increment|decrement|me|my|it|event)\b/g, "tok-keyword"],
      [/'[^']*?'/g, "tok-string"],
    ],
    bash: [[/#[^\n]*/g, "tok-comment"]],
    yaml: [
      [/^\s*[\w.-]+(?=:)/gm, "tok-attr"],
      [/#[^\n]*/g, "tok-comment"],
    ],
    html: [
      [/&lt;\/?[a-zA-Z][\w:.-]*/g, "tok-tag"],
      [/&#34;[^&]*?&#34;|&quot;[^&]*?&quot;/g, "tok-string"],
    ],
  };

  function highlight(root) {
    for (const code of root.querySelectorAll(".code-block code[data-lang]")) {
      if (code.dataset.siteHighlighted === "1") continue;
      const rules = RULES[code.dataset.lang];
      code.dataset.siteHighlighted = "1"; // posé même sans règle : inutile de repasser
      if (!rules) continue;
      let html = code.innerHTML;
      for (const [re, cls] of rules) {
        html = html.replace(re, (m) => '<span class="' + cls + '">' + m + "</span>");
      }
      code.innerHTML = html;
    }
  }

  // --- 3. Filtre des cartes d'index ---------------------------------------
  // Délégation sur `document` : le champ de recherche vit DANS #xweb-content,
  // donc il disparaît à chaque navigation boostée. Un écouteur posé sur
  // l'input lui-même serait perdu au premier swap ; posé sur document, il
  // survit à tous.

  document.addEventListener("input", function (event) {
    const input = event.target;
    if (!input || !input.matches || !input.matches("[data-filter-input]")) return;
    const query = input.value.trim().toLowerCase();
    for (const card of document.querySelectorAll(".index-card")) {
      const key = (card.dataset.filterKey || card.textContent || "").toLowerCase();
      card.classList.toggle("is-filtered-out", query !== "" && !key.includes(query));
    }
  });

  // --- Application ---------------------------------------------------------

  function apply() {
    const root = document.getElementById("xweb-content") || document;
    trimCodeBlocks(root);
    highlight(root);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", apply);
  } else {
    apply();
  }

  // htmx remplace #xweb-content sur chaque navigation boostée — le nouveau
  // contenu n'est jamais passé par apply(), il faut le refaire à ce moment-là.
  document.body.addEventListener("htmx:afterSettle", apply);
})();
