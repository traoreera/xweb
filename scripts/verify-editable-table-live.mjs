// xweb.editable_table sur la vraie page "/" d'un vrai serveur en cours —
// htmx.min.js et _hyperscript.min.js exécutés pour de vrai (jsdom,
// resources:"usable"), même patron que verify-demo-page.mjs. Cible
// précisément ce que jsdom+manual-events ne peut pas prouver seul : est-ce
// qu'un <td>/<tr> RE-RENDU PAR LE SERVEUR ET SWAPPÉ PAR HTMX reste
// interactif (_hyperscript traite-t-il vraiment le nouveau contenu, ou
// seulement ce qui existait au chargement initial) ?
//
// Nécessite le serveur démarré. Usage : node scripts/verify-editable-table-live.mjs [base_url]

import { JSDOM } from "jsdom";
import assert from "node:assert/strict";

const BASE = process.argv[2] || "http://127.0.0.1:8000";

async function tick(ms = 200) {
  await new Promise((r) => setTimeout(r, ms));
}

console.log(`Chargement de ${BASE}/ (resources réseau réelles)…`);

const pageHtml = await (await fetch(`${BASE}/`)).text();
const patched = pageHtml
  .replace(
    "<head>",
    `<head><script>
    XPathExpression.prototype.evaluate = ((orig) => function (ctx, type, result) {
      return orig.call(this, ctx, type ?? 0, result ?? null);
    })(XPathExpression.prototype.evaluate);
    window.CSS = { escape: (s) => String(s) };
    Element.prototype.scrollIntoView = function () {};
  </script>`
  )
  .replace(/<link rel="stylesheet"[^>]*>/, "");

const dom = new JSDOM(patched, {
  url: `${BASE}/`,
  runScripts: "dangerously",
  resources: "usable",
  pretendToBeVisual: true,
});
const { window } = dom;
const { document } = window;

await tick(400);
assert.ok(window.htmx, "htmx ne s'est pas chargé");
assert.ok(window._hyperscript, "_hyperscript ne s'est pas chargé");
console.log("ok   — htmx et _hyperscript exécutés sur la vraie page /");

// Intercepte le corps RÉEL envoyé par htmx (XHR, pas fetch) — la seule
// façon fiable de prouver qu'un champ précis (ex. "value=") part vraiment
// dans la requête. Deux bugs réels trouvés exactement comme ça, invisibles
// autrement : (1) le <tr> ancêtre (glisser-déposer) porte son propre
// hx-vals="js:{order: JSON.stringify(event.detail.order)}" — htmx évalue
// les hx-vals de TOUS les ancêtres pour une requête, pas seulement celui
// de l'élément déclencheur ; sur un "change" (pas "table:reordered"),
// event.detail est undefined -> .order plantait TOUTE la construction de
// la requête. Corrigé en gardant l'expression contre un event.detail
// absent. (2) l'input texte n'a jamais porté de name= : sans lui, htmx
// n'a RIEN à inclure automatiquement sous "value" — la requête partait
// avec column= mais sans value= du tout, donc la cellule se vidait au
// lieu de se sauvegarder. Corrigé en posant value: event.target.value
// explicitement dans hx-vals (même geste déjà utilisé côté case à cocher).
const capturedBodies = [];
const OrigXHR = window.XMLHttpRequest;
const origSend = OrigXHR.prototype.send;
OrigXHR.prototype.send = function (body) {
  capturedBodies.push(String(body ?? ""));
  return origSend.call(this, body);
};

// tbody, pas juste .editable-table : les en-têtes de colonne portent
// aussi .cell-display depuis qu'ils sont renommables (même mécanique),
// et viennent AVANT le tbody en ordre document — un querySelector non
// scopé attraperait l'en-tête, pas une vraie cellule de ligne (trouvé en
// écrivant cette même vérification : la requête capturée portait
// "label=..." au lieu de "value=", signe qu'on éditait l'en-tête).
const cellSpan = document.querySelector(".editable-table tbody .cell-display");
assert.ok(cellSpan, "aucune cellule texte éditable trouvée sur / — le catalogue de composants doit être présent");

cellSpan.click();
await tick();
const input = cellSpan.nextElementSibling;
assert.notEqual(input.style.display, "none", "le clic initial doit bien afficher l'input (comportement déjà vérifié en jsdom pur)");

input.value = "Valeur modifiée par verify-editable-table-live";
input.dispatchEvent(new window.KeyboardEvent("keyup", { key: "Enter", bubbles: true }));
await tick(500); // vrai aller-retour réseau (PATCH /demo/table/cell/...)

const lastBody = capturedBodies.at(-1) ?? "";
assert.match(lastBody, /value=/, `le corps de la requête doit contenir "value=" — reçu : ${JSON.stringify(lastBody)}`);
console.log("ok   — la requête PATCH réelle porte bien value= (pas seulement column=) —", lastBody);

const cellAfter = document.querySelector(".editable-table tbody .cell-display");
assert.ok(cellAfter, "le <td> doit toujours contenir un .cell-display après le swap htmx");
assert.equal(cellAfter.textContent.trim(), "Valeur modifiée par verify-editable-table-live", "le swap doit refléter la vraie valeur sauvegardée côté serveur");
console.log("ok   — édition réelle : PATCH réseau réel, cellule remplacée avec la nouvelle valeur");

// Le test qui compte vraiment : le <td> swappé est un NOUVEAU noeud DOM
// (outerHTML), avec un NOUVEAU _="..." — _hyperscript l'a-t-il traité ?
cellAfter.click();
await tick();
const inputAfter = cellAfter.nextElementSibling;
const displayAfterClick = inputAfter.style.display;
if (displayAfterClick === "none") {
  console.error("FAIL — après le swap htmx, cliquer la cellule NE rouvre PAS le mode édition : _hyperscript n'a pas traité le contenu swappé.");
  process.exitCode = 1;
} else {
  console.log("ok   — la cellule swappée par htmx reste interactive : un second clic rouvre bien le mode édition");
}

// --- "Nouvelle ligne" : atterrit-elle dans LE BON <tbody> ? ---
// Bug réel trouvé avec ce script : la landing page affiche aussi
// xweb.table dans le catalogue (un second <tbody>, avant le nôtre dans le
// document) — hx-target="tbody" (bare, sans id) ciblait TOUJOURS le
// premier <tbody> de la page entière, jamais celui de xweb.editable_table.
// Le serveur créait bien la ligne (persistée), mais le swap l'insérait
// dans le mauvais tableau — invisible en curl/jsdom pur, seulement
// détectable avec un vrai htmx contre une vraie page à plusieurs <table>.
// Corrigé avec id= (comme xweb.kanban/modal/drawer), voir
// xweb/components/editable_table.xml.
const tbodies = [...document.querySelectorAll("tbody")];
assert.ok(tbodies.length >= 2, "cette page doit avoir au moins 2 <tbody> (xweb.table + xweb.editable_table) pour que ce test ait un sens");
const editableTbody = document.querySelector(".editable-table tbody");
const otherTbody = tbodies.find((t) => t !== editableTbody);
const rowsBefore = { editable: editableTbody.querySelectorAll("tr").length, other: otherTbody.querySelectorAll("tr").length };

const addRowBtn = [...document.querySelectorAll(".editable-table button")].find((b) => b.textContent.includes("Nouvelle ligne"));
assert.ok(addRowBtn, "bouton 'Nouvelle ligne' introuvable");
addRowBtn.click();
await tick(600); // vrai POST réseau /demo/table/row

const rowsAfter = { editable: editableTbody.querySelectorAll("tr").length, other: otherTbody.querySelectorAll("tr").length };
assert.equal(rowsAfter.editable, rowsBefore.editable + 1, "la nouvelle ligne doit apparaître dans LE tbody de xweb.editable_table");
assert.equal(rowsAfter.other, rowsBefore.other, "l'autre <tbody> (xweb.table) ne doit jamais être touché");
console.log("ok   — 'Nouvelle ligne' cible le bon <tbody> (id scopé par instance), même avec plusieurs tables sur la page");

window.close();
if (process.exitCode !== 1) {
  console.log("\nToutes les vérifications passent sur la vraie page /.");
}
