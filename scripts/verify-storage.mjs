// Fait tourner xweb/static/storage.js pour de vrai dans un DOM (jsdom) —
// namespace, aller-retour JSON, dégradation défensive quand localStorage
// lève (navigation privée), lecture d'une valeur chaîne brute posée AVANT
// l'adoption de cette classe. Même patron que verify-hyperscript.mjs.
//
// Usage : npm install && node scripts/verify-storage.mjs

import { JSDOM } from "jsdom";
import { readFileSync } from "fs";
import assert from "node:assert/strict";

const SRC_PATH = new URL("../xweb/static/storage.js", import.meta.url);
const source = readFileSync(SRC_PATH, "utf-8");

function newDom() {
  const dom = new JSDOM("<!doctype html><html><body></body></html>", {
    runScripts: "dangerously",
    url: "http://localhost/",
  });
  dom.window.eval(source);
  return dom;
}

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

await check("namespace : xweb:theme sous la clé réelle localStorage", () => {
  const { window } = newDom();
  window.XwebStorage.set("theme", "dark");
  assert.equal(window.localStorage.getItem("xweb:theme"), '"dark"');
});

await check("aller-retour JSON : objets/tableaux/booléens intacts", () => {
  // JSON.stringify plutôt que assert.deepEqual : l'objet lu vient du
  // realm jsdom (autre Object.prototype que le process Node), assert/strict
  // (deepStrictEqual) le rejetterait malgré une structure identique.
  const { window } = newDom();
  window.XwebStorage.set("prefs", { collapsed: true, cols: ["a", "b"], n: 3 });
  assert.equal(
    JSON.stringify(window.XwebStorage.get("prefs")),
    JSON.stringify({ collapsed: true, cols: ["a", "b"], n: 3 }),
  );
});

await check("get() sur une clé absente rend le fallback, jamais une exception", () => {
  const { window } = newDom();
  assert.equal(window.XwebStorage.get("absent", "défaut"), "défaut");
  assert.equal(window.XwebStorage.get("absent"), null);
});

await check("has()/remove()", () => {
  const { window } = newDom();
  assert.equal(window.XwebStorage.has("x"), false);
  window.XwebStorage.set("x", 1);
  assert.equal(window.XwebStorage.has("x"), true);
  window.XwebStorage.remove("x");
  assert.equal(window.XwebStorage.has("x"), false);
});

await check("valeur chaîne brute préexistante (posée avant cette classe) reste lisible", () => {
  const { window } = newDom();
  window.localStorage.setItem("xweb:theme", "dark"); // pas du JSON — comme le script anti-flash le pose
  assert.equal(window.XwebStorage.get("theme"), "dark");
});

await check("localStorage qui lève (navigation privée) dégrade sans exception", () => {
  const { window } = newDom();
  const boom = () => {
    throw new DOMException("QuotaExceededError");
  };
  Object.defineProperty(window, "localStorage", {
    value: { getItem: boom, setItem: boom, removeItem: boom },
  });
  assert.equal(window.XwebStorage.get("theme", "clair"), "clair");
  assert.equal(window.XwebStorage.set("theme", "dark"), false);
  assert.equal(window.XwebStorage.remove("theme"), false);
  assert.equal(window.XwebStorage.has("theme"), false);
});

await check("deux instances, deux namespaces, aucune collision de clé", () => {
  const { window } = newDom();
  const a = new window.XwebStorageClass("plugin_a");
  const b = new window.XwebStorageClass("plugin_b");
  a.set("filtre", "actifs");
  b.set("filtre", "archivés");
  assert.equal(a.get("filtre"), "actifs");
  assert.equal(b.get("filtre"), "archivés");
});

console.log(failures === 0 ? "\nTout est vert." : `\n${failures} échec(s).`);
process.exit(failures === 0 ? 0 : 1);
