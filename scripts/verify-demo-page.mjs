// Charge la vraie page /plugins/demo/ depuis un vrai serveur xcore+xweb en
// cours d'exécution (pas une page statique reconstruite ici), exécute
// htmx.min.js et _hyperscript.min.js pour de vrai dans jsdom (resources:
// "usable" -> les <script src> sont réellement téléchargés et lancés), et
// simule des clics comme un navigateur. Le bouton "ping" fait un vrai
// aller-retour réseau vers le serveur en cours — l'horodatage renvoyé ne
// peut pas être deviné à l'avance, donc son changement prouve que
// l'échange a vraiment eu lieu, pas juste que le JS s'est exécuté.
//
// Nécessite le serveur démarré (xcli manager start / uvicorn main:app).
// Usage : node scripts/verify-demo-page.mjs [http://127.0.0.1:8000]

import { JSDOM } from "jsdom";
import assert from "node:assert/strict";

const BASE = process.argv[2] || "http://127.0.0.1:8000";
const URL = `${BASE}/plugins/demo/?name=Ada`;

async function tick(ms = 150) {
  await new Promise((r) => setTimeout(r, ms));
}

console.log(`Chargement de ${URL} (resources réseau réelles)…`);

// htmx pré-compile une XPathExpression au chargement (pour repérer les
// attributs hx-on:*) puis l'appelle en `expr.evaluate(contextNode)` sans
// fournir `type`/`result` — les vrais navigateurs défaultent `type` à 0
// (ANY_TYPE), jsdom l'exige explicitement et lève avant que htmx ait
// attaché le moindre écouteur. Confirmé en lisant htmx.min.js : c'est
// XPathExpression.prototype.evaluate (via `(new XPathEvaluator).
// createExpression(...)`), pas document.evaluate — un premier patch sur
// document.evaluate n'avait aucun effet, cette version corrigée cible la
// bonne méthode. Vit uniquement dans ce script de test, jamais dans le
// vrai template — limite de jsdom, pas de htmx ni de xweb.
const pageHtml = await (await fetch(URL)).text();
const patched = pageHtml
  .replace(
    "<head>",
    `<head><script>
    // Pré-rempli AVANT le script anti-flash réel de shell.xml (qui suit
    // dans le document, après <title>) — prouve que le thème persiste
    // dès le premier rendu d'une page fraîche, pas seulement après un
    // clic dans la même session JS (docs/theming.md, bug trouvé : le
    // thème ne survivait à aucun rechargement complet avant ce correctif).
    localStorage.setItem('theme', 'dark');
    XPathExpression.prototype.evaluate = ((orig) => function (ctx, type, result) {
      return orig.call(this, ctx, type ?? 0, result ?? null);
    })(XPathExpression.prototype.evaluate);
    // htmx appelle CSS.escape() en phase de "settle" après un swap
    // hx-boost (repérage d'éléments par id) — jsdom n'implémente pas du
    // tout l'objet global CSS. Passthrough délibéré, pas un échappement
    // complet : nos ids (xweb-content, theme-btn…) sont tous alphanumériques
    // + tirets, aucun caractère à échapper — correct pour ce que ce script
    // exerce réellement, pas une réimplémentation générale de CSS.escape.
    window.CSS = { escape: (s) => String(s) };
    // htmx scrolle vers le haut après une navigation boostée — jsdom n'a
    // aucune mise en page/viewport, scrollIntoView() n'existe pas du
    // tout. No-op correct ici, pas un contournement : il n'y a rien à
    // scroller dans un environnement sans rendu visuel.
    Element.prototype.scrollIntoView = function () {};
  </script>`
  )
  // jsdom (resources: "usable") chargerait ET PARSERAIT ce <link>
  // automatiquement au rendu de la page — son moteur CSS ne comprend pas
  // la syntaxe Tailwind v4 (@layer/@property), ça ferait planter le
  // chargement avant le premier clic. app.css est vérifié séparément
  // plus bas par un fetch direct, sans passer par le CSSOM de jsdom.
  .replace(/<link rel="stylesheet"[^>]*>/, "");

const dom = new JSDOM(patched, {
  url: URL,
  runScripts: "dangerously",
  resources: "usable",
  pretendToBeVisual: true,
});
const { window } = dom;
const { document } = window;

// Laisse htmx.min.js / _hyperscript.min.js finir de charger et de
// s'attacher (htmx scanne le DOM sur DOMContentLoaded).
await tick(300);

assert.ok(window.htmx, "htmx ne s'est pas chargé/exécuté");
assert.ok(window._hyperscript, "_hyperscript ne s'est pas chargé/exécuté");
console.log("ok   — htmx et _hyperscript exécutés dans la page réelle");

// --- persistance du thème — dès le premier rendu, pas après un clic ---
assert.equal(
  document.documentElement.dataset.theme, "dark",
  "le script anti-flash de shell.xml doit lire localStorage AVANT tout rendu"
);
console.log("ok   — thème 'dark' pré-enregistré dans localStorage appliqué dès le chargement (script anti-flash)");

// --- bouton "Ping le serveur" — vrai aller-retour réseau htmx ---
const result = document.getElementById("result");
assert.equal(result.textContent.trim(), "(pas encore de réponse)");

document.getElementById("ping-btn").click();
await tick(500); // vraie requête réseau, pas un mock — laisse le temps

assert.match(result.textContent, /pong reçu du serveur — horodatage : \d+\.\d+/, "htmx n'a pas remplacé #result");
const firstTimestamp = result.textContent;
console.log("ok   — clic sur #ping-btn -> htmx a fait un vrai POST /plugins/demo/ping ->", firstTimestamp.trim());

document.getElementById("ping-btn").click();
await tick(500);
assert.notEqual(result.textContent, firstTimestamp, "un deuxième clic doit renvoyer un nouvel horodatage serveur");
console.log("ok   — deuxième clic -> nouvel horodatage, donc un vrai second aller-retour (pas un cache)");

// --- bouton "Basculer le thème" — _hyperscript pur client ---
// Part de 'dark' (pré-rempli plus haut), pas de 'light' — le point de
// départ prouve déjà la persistance, ce bloc prouve juste que le clic
// continue de fonctionner par-dessus.
const html = document.documentElement;
assert.equal(html.dataset.theme, "dark");
document.getElementById("theme-btn").click();
await tick(100);
assert.equal(html.getAttribute("data-theme"), "light");
console.log("ok   — clic sur #theme-btn -> data-theme bascule en 'light' (_hyperscript, sans round-trip serveur)");

document.getElementById("theme-btn").click();
await tick(100);
assert.equal(html.getAttribute("data-theme"), "dark");
console.log("ok   — deuxième clic -> retour à 'dark'");

// --- app.css (DaisyUI/Tailwind) ---
// jsdom ne peut PAS être utilisé ici pour vérifier un style calculé : son
// moteur CSS ne parse pas la syntaxe moderne que Tailwind v4 génère
// (@layer, @property, @supports imbriqués — "Could not parse CSS
// stylesheet", testé et confirmé, pas supposé). Vérification au niveau
// qui compte réellement : le fichier CSS généré contient-il de vraies
// règles pour les classes que les templates utilisent VRAIMENT — pas un
// fichier vide ou un daisyUI générique jamais branché sur nos sources.
const cssRes = await fetch(`${BASE}/xweb-static/app.css`);
assert.equal(cssRes.status, 200, "app.css doit être servi");
const css = await cssRes.text();
for (const cls of [".btn", ".btn-primary", ".btn-ghost", ".btn-circle", "data-theme"]) {
  assert.ok(css.includes(cls), `app.css ne contient pas ${cls} — le scan des templates .xml n'a rien trouvé`);
}
console.log(`ok   — app.css généré (${css.length} octets) contient les vraies classes DaisyUI utilisées par les templates`);

// --- hx-boost — navigation sans rechargement complet (shell.xml) ---
// Un marqueur posé dans ce contexte JS ne survit à AUCUN vrai rechargement
// de page (nouveau document = nouveau contexte, le marqueur redeviendrait
// undefined) — s'il est toujours là après le clic, c'est que htmx a
// intercepté le lien au lieu de laisser le navigateur naviguer pour de vrai.
window.__xwebMarker = "toujours là si pas de vrai rechargement";
const navLink = [...document.querySelectorAll("a")].find((a) => a.textContent.trim() === "Démo");
assert.ok(navLink, "le lien de nav 'Démo' doit être présent (enregistré par plugins/demo/src/main.py::on_load)");

navLink.click();
await tick(400); // vraie requête réseau htmx, laisse le temps

assert.equal(window.__xwebMarker, "toujours là si pas de vrai rechargement", "un vrai rechargement aurait détruit le contexte JS");
assert.ok(document.getElementById("xweb-content"), "#xweb-content doit toujours être là après le swap");
assert.ok(document.getElementById("theme-btn"), "le shell (bouton de thème) ne doit pas avoir été remplacé, seul #xweb-content");
console.log("ok   — clic sur le lien de nav : htmx a intercepté (hx-boost), aucun vrai rechargement de page");

// --- #xweb-sidebar reste synchronisé après une VRAIE navigation boostée ---
// Bug trouvé sur une capture d'écran réelle : hx-boost ne renvoie jamais
// la sidebar (seul #xweb-content est swappé), donc .menu-active restait
// figé sur la page du chargement complet. On repart de la page fraîche
// (Démo actif dès /plugins/demo/?name=Ada) et on clique "Composants" —
// contrairement au clic "Démo" ci-dessus (déjà la page courante), celui-ci
// change vraiment quelle page est active.
const sidebarLinkFor = (label) =>
  [...document.querySelectorAll("#xweb-sidebar a")].find((a) => a.textContent.trim() === label);

assert.ok(
  sidebarLinkFor("Démo")?.classList.contains("menu-active"),
  "avant tout clic : Démo doit être actif (page chargée au départ)"
);

const componentsLink = sidebarLinkFor("Composants");
assert.ok(componentsLink, "le lien de nav 'Composants' doit être présent");
componentsLink.click();
await tick(400); // vraie requête réseau htmx boostée

assert.ok(
  !sidebarLinkFor("Démo")?.classList.contains("menu-active"),
  "après avoir cliqué Composants, Démo ne doit plus être actif — c'était le bug"
);
assert.ok(
  sidebarLinkFor("Composants")?.classList.contains("menu-active"),
  "Composants doit être actif après la navigation boostée vers cette page"
);
console.log("ok   — la sidebar se resynchronise après une navigation boostée (Démo → Composants), plus figée sur la page de départ");

window.close();
console.log("\nToutes les vérifications passent sur la vraie page /plugins/demo/.");
