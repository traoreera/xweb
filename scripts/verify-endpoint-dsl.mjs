// Vérifie la validation de RÉPONSE d'un `endpoint` (`receive { schema: ...
// list: true }`) en exécutant le VRAI hyperscript généré par le compilateur
// xdsl dans jsdom, avec le VRAI _hyperscript et le VRAI validators.js — pas
// juste "le texte généré a l'air bon".
//
// Couvre aussi le piège lxml : le HTML rendu par QwebRegistry contient
// l'attribut `_` APLATI (les \n des attributs XML sont normalisés en
// espaces), or le hyperscript if/else ne survit PAS à cet aplatissement
// (Unexpected Token : else) — seul le bloc `js(...) end` (contenu séparé
// par `;`) le tolère. Ce script prouve que la forme générée fonctionne
// vraiment sous sa forme RÉELLE (aplatie), pas une copie propre.
//
// TODO scaffold : pas de réseau — on dispache l'événement htmx:afterRequest
// nous-mêmes avec un detail.xhr réaliste (le hyperscript est l'unité testée,
// même niveau que verify-hyperscript.mjs ; verify-live-channel.mjs reste la
// référence des tests réseau réels).
//
// Prérequis : uv run python scripts/render_endpoint_fixture.py
// Usage : npm run verify:endpoint-dsl

import { JSDOM } from "jsdom";
import { readFileSync } from "fs";
import assert from "node:assert/strict";

const HERE = new URL(".", import.meta.url);
const HTML_PATH = new URL("../.verify-endpoint-dsl.html", HERE);
const htmxSrc = readFileSync(new URL("../xweb/static/htmx.min.js", HERE), "utf-8");
const hsSrc = readFileSync(new URL("../xweb/static/_hyperscript.min.js", HERE), "utf-8");
const validatorsSrc = readFileSync(new URL("../xweb/static/validators.js", HERE), "utf-8");
const html = readFileSync(HTML_PATH, "utf-8");

let failures = 0;

async function check(name, fn) {
  try {
    await fn();
    console.log(`ok   — ${name}`);
  } catch (e) {
    failures++;
    console.error(`FAIL — ${name}\n      ${e.message}`);
  }
}

function newDom() {
  const dom = new JSDOM(`<!doctype html><html><body>${html}</body></html>`, {
    runScripts: "outside-only",
    url: "http://localhost/",
  });
  const { window } = dom;
  // Mêmes patches que verify-live-channel.mjs/verify-catalogue.mjs — htmx
  // a besoin d'un window.CSS.escape, d'un scrollIntoView et du shim
  // XPathExpression.prototype.evaluate (sinon "You must provide an XPath
  // result type (0=any)").
  window.CSS = { escape: (s) => String(s) };
  window.Element.prototype.scrollIntoView = function () {};
  window.Node.prototype.scrollIntoView = function () {};
  const xpe = window.XPathExpression;
  if (xpe && xpe.prototype && typeof xpe.prototype.evaluate === "function") {
    const orig = xpe.prototype.evaluate;
    xpe.prototype.evaluate = function (ctx, type, result) {
      return orig.call(this, ctx, type ?? 0, result ?? null);
    };
  }
  window.eval(htmxSrc);
  window.eval(hsSrc);
  // Les <script> inline du fragment (export window.XWEB_SCHEMAS du
  // scaffolding d'endpoint) ne s'exécutent pas en "outside-only" — on les
  // évalue explicitement, dans l'ordre où le navigateur le ferait (même
  // patron que verify-channel-dsl.mjs). Ils exportent XWEB_SCHEMAS AVANT
  // que validators.js ne soit chargé — mais l'ordre n'importe pas ici,
  // XwebValidate lit window.XWEB_SCHEMAS paresseusement à chaque appel.
  for (const scriptEl of window.document.querySelectorAll("script")) {
    if (!scriptEl.src) window.eval(scriptEl.textContent);
  }
  window.eval(validatorsSrc);
  // htmx démarre son scanner sur le document.
  window.htmx.process(window.document.body);
  // _hyperscript n'initialise pas les attributs `_` pré-existants sur une
  // page chargée en "outside-only" — c'est le processNode explicite
  // documenté dans AGENTS.md.
  window._hyperscript.processNode(window.document.body);
  return dom;
}

function afterRequest(dom, successful, responseText) {
  const { window } = dom;
  const el = window.document.querySelector("button");
  const ev = new window.Event("htmx:afterRequest", { bubbles: true, cancelable: true });
  ev.detail = { successful, xhr: { responseText }, target: el, el, error: null };
  el.dispatchEvent(ev);
}

function visible(dom, sel) {
  const el = dom.window.document.querySelector(sel);
  return el && !el.hidden;
}

await check("le constructeur du DSL est exécutable tel quel (schema composé + list)", async () => {
  const dom = newDom();
  const { window } = dom;
  assert.ok(window.XWEB_SCHEMAS["contact"], "le schéma contact doit être exporté par le scaffolding");
  assert.ok(
    window.XWEB_SCHEMAS["contact"].address,
    "la composition (réf address) doit figurer dans le descripteur exporté",
  );
});

await check("réponse JSON valide (tableau d'objets composés) -> onsuccess, event diffusé, pas onerror", async () => {
  const dom = newDom();
  const { window } = dom;
  let fired = 0;
  window.document.querySelector("#rows").addEventListener("contacts:loaded", () => fired++);
  afterRequest(dom, true, JSON.stringify([
    { name: "Alice", address: { street: "1 rue", city: "Paris" } },
    { name: "Bob", address: { street: "2 av", city: "Lyon" } },
  ]));
  assert.equal(visible(dom, "#list_contacts-1-onsuccess"), true, "onsuccess doit être révélé");
  assert.equal(visible(dom, "#list_contacts-1-onerror"), false, "onerror doit rester caché");
  assert.equal(fired, 1, "contacts:loaded doit être diffusé vers #rows");
});

await check("réponse JSON INVALIDE (succès HTTP mais champ requis absent / nested cassé) -> onerror", async () => {
  const dom = newDom();
  const { window } = dom;
  let fired = 0;
  window.document.querySelector("#rows").addEventListener("contacts:loaded", () => fired++);
  afterRequest(dom, true, JSON.stringify([
    { name: "x", address: { street: "1 rue", city: "Paris" } },
    { address: { city: "sans rue requise" } },
  ]));
  assert.equal(visible(dom, "#list_contacts-1-onsuccess"), false, "onsuccess ne doit PAS être révélé");
  assert.equal(visible(dom, "#list_contacts-1-onerror"), true, "onerror doit être révélé");
  assert.equal(fired, 0, "l'event de refresh ne doit PAS être diffusé");
});

await check("corps non-JSON -> invalide (jamais une exception), onerror", async () => {
  const dom = newDom();
  const { window } = dom;
  let fired = 0;
  window.document.querySelector("#rows").addEventListener("contacts:loaded", () => fired++);
  afterRequest(dom, true, "<html>erreur du serveur en HTML</html>");
  assert.equal(visible(dom, "#list_contacts-1-onerror"), true, "onerror doit être révélé");
  assert.equal(fired, 0);
});

await check("réponse pas un tableau malgré list:true -> invalide (__root__)", async () => {
  const dom = newDom();
  const { window } = dom;
  let fired = 0;
  window.document.querySelector("#rows").addEventListener("contacts:loaded", () => fired++);
  afterRequest(dom, true, JSON.stringify({ name: "pas une liste" }));
  assert.equal(visible(dom, "#list_contacts-1-onerror"), true, "onerror doit être révélé");
  assert.equal(fired, 0);
});

await check("échec HTTP (successful:false) -> onerror, pas d'event", async () => {
  const dom = newDom();
  const { window } = dom;
  let fired = 0;
  window.document.querySelector("#rows").addEventListener("contacts:loaded", () => fired++);
  afterRequest(dom, false, "500 Internal Server Error");
  assert.equal(visible(dom, "#list_contacts-1-onerror"), true);
  assert.equal(visible(dom, "#list_contacts-1-onsuccess"), false);
  assert.equal(fired, 0);
});

if (failures > 0) {
  console.error(`\n${failures} vérification(s) en échec`);
  process.exit(1);
}
console.log("\nToutes les vérifications endpoint-dsl (validation de réponse) passent.");