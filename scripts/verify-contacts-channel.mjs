// Vérifie le `channel contacts_feed` de contacts_demo.dsl contre le VRAI
// serveur en cours : vrai live_channel.js, vrai htmx.min.js, vrai
// _hyperscript.min.js (chargé et auto-initialisé comme dans un vrai
// navigateur — page réelle via resources:"usable", pas de processNode()
// manuel nécessaire ici, contrairement à verify-channel-dispatch.mjs), vraie
// route SSE. La preuve décisive : on crée un contact par un POST DIRECT
// (hors de la page jsdom — comme le ferait un AUTRE onglet), et on vérifie
// que la page se met à jour toute seule (bind:/refresh:/dispatch:).
// Impossible à simuler par hasard.
//
// Nécessite le serveur de démo démarré séparément (même convention que
// verify-demo-page.mjs — ce script ne le lance pas) :
//   uv run uvicorn contacts_demo_app:app --port 8933
// Usage : npm run verify:contacts-channel
//         node scripts/verify-contacts-channel.mjs [http://127.0.0.1:8933]

import { JSDOM } from "jsdom";
import assert from "node:assert/strict";

const BASE = process.argv[2] || "http://127.0.0.1:8933";

async function tick(ms = 300) {
  await new Promise((r) => setTimeout(r, ms));
}

const pageHtml = await (await fetch(BASE + "/")).text();

// Polyfill EventSource — absent de jsdom ET de Node (confirmé en écrivant
// scripts/verify-live-channel.mjs). Implémenté ici sur XMLHttpRequest, que
// jsdom fournit vraiment, pour rester DANS le realm de la page : le vrai
// live_channel.js doit trouver EventSource sur son propre window.
const POLYFILL = `<script>
window.EventSource = function (url) {
  var self = this;
  self._listeners = {};
  self._opened = false;
  self.addEventListener = function (name, cb) {
    (self._listeners[name] = self._listeners[name] || []).push(cb);
  };
  self.close = function () { try { xhr.abort(); } catch (e) {} };
  function dispatch(block) {
    var eventName = "message", data = "";
    block.split("\\n").forEach(function (line) {
      if (line.indexOf(":") === 0) return; // commentaire / keep-alive
      if (line.indexOf("event:") === 0) eventName = line.slice(6).trim();
      else if (line.indexOf("data:") === 0) data += line.slice(5).trim();
    });
    (self._listeners[eventName] || []).forEach(function (cb) { cb({ data: data }); });
  }
  var xhr = new XMLHttpRequest();
  var offset = 0, pending = "";
  xhr.open("GET", url, true);
  xhr.onprogress = function () {
    if (!self._opened) { self._opened = true; if (self.onopen) self.onopen(); }
    var text = xhr.responseText;
    pending += text.slice(offset);
    offset = text.length;
    var idx;
    while ((idx = pending.indexOf("\\n\\n")) !== -1) {
      dispatch(pending.slice(0, idx));
      pending = pending.slice(idx + 2);
    }
  };
  xhr.onerror = function () { if (self.onerror) self.onerror(new Error("xhr")); };
  xhr.send();
};
XPathExpression.prototype.evaluate = ((orig) => function (ctx, type, result) {
  return orig.call(this, ctx, type ?? 0, result ?? null);
})(XPathExpression.prototype.evaluate);
window.CSS = { escape: (s) => String(s) };
Element.prototype.scrollIntoView = function () {};
</script>`;

const patched = pageHtml
  .replace("<head>", "<head>" + POLYFILL)
  .replace(/<link rel="stylesheet"[^>]*>/, ""); // CSSOM jsdom ne digère pas Tailwind v4

const dom = new JSDOM(patched, {
  url: BASE + "/",
  runScripts: "dangerously",
  resources: "usable",
  pretendToBeVisual: true,
});
const { window } = dom;

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

// Laisse htmx + live_channel.js se charger (resources réseau réelles) et le
// flux SSE s'établir.
await tick(2500);

const countEl = () => window.document.querySelector("#contacts-count");
const tableText = () => window.document.querySelector("#contacts-table").textContent;

await check("live_channel.js est bien chargé et instancié par le bootstrap généré", () => {
  assert.equal(typeof window.XwebLiveChannel, "function", "XwebLiveChannel absent du window de la page");
});

await check("état initial poussé par le serveur dès la connexion SSE (bind: #contacts-count)", () => {
  const shown = countEl().textContent.trim();
  assert.match(shown, /^\d+$/, `compteur non numérique: ${JSON.stringify(shown)}`);
});

const initialCount = Number(countEl().textContent.trim());
console.log(`     (compteur initial lu depuis le serveur : ${initialCount})`);

// --- La preuve : une création faite AILLEURS que dans cette page ---------
const marker = "Zaphod-" + Date.now();
await fetch(BASE + "/api/contacts", {
  method: "POST",
  headers: { "Content-Type": "application/x-www-form-urlencoded" },
  body: new URLSearchParams({ name: marker, email: "zaphod@example.com" }),
});
await tick(1500);

await check("bind: — le compteur s'incrémente sans que la page ait rien soumis", () => {
  const now = Number(countEl().textContent.trim());
  assert.equal(now, initialCount + 1, `attendu ${initialCount + 1}, eu ${now}`);
});

await check("refresh: — la table s'est rechargée depuis le serveur (htmx.trigger -> from:body)", () => {
  assert.ok(
    tableText().includes(marker),
    `le contact créé ailleurs (${marker}) devrait apparaître dans #contacts-table après rafraîchissement`,
  );
});

// --- dispatch: true — le flash hyperscript sur #contacts-count -----------
// `_ { on contacts:changed from document add .badge-primary wait 400ms
// remove .badge-primary }` — transitoire, donc il faut l'attraper DANS la
// fenêtre des 400ms, contrairement aux checks bind:/refresh: ci-dessus qui
// lisent un état stable. Nouvelle création pour ne pas dépendre du timing
// déjà écoulé par les checks précédents.
const marker2 = "Marvin-" + Date.now();
await fetch(BASE + "/api/contacts", {
  method: "POST",
  headers: { "Content-Type": "application/x-www-form-urlencoded" },
  body: new URLSearchParams({ name: marker2, email: "marvin@example.com" }),
});
await tick(150); // avant les 400ms de `wait` — la classe doit être présente ICI

await check("dispatch: true — hyperscript réel ajoute .badge-primary sur le CustomEvent contacts:changed", () => {
  assert.ok(
    countEl().classList.contains("badge-primary"),
    "la classe .badge-primary devrait être posée pendant la fenêtre de flash (0-400ms après contacts:changed)",
  );
});

await check("dispatch: true — hyperscript réel retire .badge-primary après le wait 400ms", async () => {
  // Poll plutôt qu'un sleep fixe : la latence réseau du POST + SSE + settle
  // htmx sur cette machine peut repousser le déclenchement réel du handler
  // hyperscript au-delà d'une marge fixe optimiste — seule l'absence
  // persistante après une fenêtre large est un vrai échec.
  const deadline = Date.now() + 2000;
  while (Date.now() < deadline && countEl().classList.contains("badge-primary")) {
    await tick(100);
  }
  assert.ok(
    !countEl().classList.contains("badge-primary"),
    "la classe .badge-primary devrait avoir disparu après le wait 400ms du hyperscript",
  );
});

dom.window.close();
if (failures > 0) {
  console.error(`\n${failures} vérification(s) en échec`);
  process.exit(1);
}
console.log("\nLe channel de contacts_demo.dsl fonctionne contre le vrai serveur.");
