// Vérifie que le bootstrap `<script>` généré par `channel`/`use_channel:`
// (xdsl/compiler.py::_write_channel_bootstrap) fait vraiment ce qu'il dit
// une fois exécuté dans un DOM réel — pas juste que le texte généré
// "a l'air bon" (voir la discipline de vérification établie cette session
// pour storage.js/live_channel.js/hyperscript : lire du code ne prouve
// rien, l'exécuter si).
//
// xweb/static/live_channel.js lui-même (réseau SSE/WS réel) est déjà
// couvert par verify-live-channel.mjs — ce script-ci teste la couche
// au-dessus : le JS que le COMPILATEUR xdsl génère et colle dans la page.
// XwebLiveChannel est donc mocké ici (on capture ses options et on
// déclenche onMessage nous-mêmes) plutôt que reconnecté à un vrai
// serveur — ce n'est pas son rôle dans CE test.
//
// Prérequis : uv run python scripts/render_channel_fixture.py (écrit
// .verify-channel-dsl.html depuis le VRAI pipeline xdsl -> QwebRegistry).
// Usage : npm run verify:channel-dsl

import { JSDOM } from "jsdom";
import { readFileSync } from "fs";
import assert from "node:assert/strict";

const HTML_PATH = new URL("../.verify-channel-dsl.html", import.meta.url);
const STORAGE_PATH = new URL("../xweb/static/storage.js", import.meta.url);
const VALIDATORS_PATH = new URL("../xweb/static/validators.js", import.meta.url);
const html = readFileSync(HTML_PATH, "utf-8");
const storageSrc = readFileSync(STORAGE_PATH, "utf-8");
const validatorsSrc = readFileSync(VALIDATORS_PATH, "utf-8");

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

  // Capture la construction de XwebLiveChannel plutôt que de réutiliser le
  // vrai fichier (déjà couvert par verify-live-channel.mjs) — ce qu'on
  // vérifie ICI, c'est ce que le bootstrap généré par xdsl lui PASSE, et
  // ce qu'il fait de onMessage une fois qu'on le déclenche nous-mêmes.
  let capturedOpts = null;
  window.XwebLiveChannel = function (opts) {
    capturedOpts = opts;
    this.close = () => {};
  };

  // htmx.trigger — capturé plutôt que vendorisé, seul le passage de
  // paramètres du bootstrap généré nous intéresse ici.
  const htmxTriggerCalls = [];
  window.htmx = { trigger: (el, event, detail) => htmxTriggerCalls.push({ el, event, detail }) };

  window.eval(storageSrc);

  // Exécute le <script> inline du fragment (runScripts "outside-only" ne
  // le fait pas tout seul — on l'évalue explicitement, comme
  // verify-catalogue.mjs le fait pour d'autres fragments htmx).
  const scriptEl = window.document.querySelector("script");
  window.eval(scriptEl.textContent);

  return { window, capturedOpts: () => capturedOpts, htmxTriggerCalls };
}

await check("XwebLiveChannel est construit avec url/channels/transport/connectTimeoutMs corrects", () => {
  const { capturedOpts } = newDom();
  const opts = capturedOpts();
  assert.ok(opts, "XwebLiveChannel doit avoir été instancié");
  assert.equal(opts.url, "/stream");
  assert.equal(JSON.stringify(opts.channels), JSON.stringify(["chat", "notif"]));
  assert.equal(opts.transport, "sse");
  assert.equal(opts.connectTimeoutMs, 5000);
  assert.equal(typeof opts.onMessage, "function");
});

await check("onMessage — bind écrit le champ dans textContent de l'élément ciblé", () => {
  const { window, capturedOpts } = newDom();
  window.XwebValidate = () => ({ valid: true });
  capturedOpts().onMessage("chat", { count: 7 });
  assert.equal(window.document.querySelector("#counter").textContent, "7");
});

await check("onMessage — refresh déclenche htmx.trigger sur l'élément cible avec le bon nom d'event", () => {
  const { capturedOpts, htmxTriggerCalls } = newDom();
  const data = { count: 3 };
  capturedOpts().onMessage("chat", data);
  assert.equal(htmxTriggerCalls.length, 1);
  assert.equal(htmxTriggerCalls[0].el.id, "contacts-table");
  assert.equal(htmxTriggerCalls[0].event, "contacts:changed");
  assert.equal(JSON.stringify(htmxTriggerCalls[0].detail), JSON.stringify(data));
});

await check("onMessage — persist écrit la donnée dans XwebStorage sous la bonne clé", () => {
  const { window, capturedOpts } = newDom();
  capturedOpts().onMessage("chat", { count: 9 });
  assert.equal(
    JSON.stringify(window.XwebStorage.get("last_contact")),
    JSON.stringify({ count: 9 }),
  );
});

await check("onMessage — sans window.XwebValidate défini, bind/refresh/persist s'exécutent quand même (garde optionnelle)", () => {
  const { window, capturedOpts, htmxTriggerCalls } = newDom();
  assert.equal(window.XwebValidate, undefined, "précondition : XwebValidate absent de ce DOM");
  capturedOpts().onMessage("chat", { count: 1 });
  assert.equal(window.document.querySelector("#counter").textContent, "1");
  assert.equal(htmxTriggerCalls.length, 1);
});

await check("onMessage — XwebValidate présent et invalide bloque bind/refresh/persist", () => {
  const { window, capturedOpts, htmxTriggerCalls } = newDom();
  window.XwebValidate = () => ({ valid: false, errors: { count: ["invalide"] } });
  const before = window.document.querySelector("#counter").textContent;
  capturedOpts().onMessage("chat", { count: 999 });
  assert.equal(window.document.querySelector("#counter").textContent, before, "bind ne doit PAS s'exécuter");
  assert.equal(htmxTriggerCalls.length, 0, "refresh ne doit PAS s'exécuter");
  assert.equal(window.XwebStorage.get("last_contact"), null, "persist ne doit PAS s'exécuter");
});

await check("onMessage — XwebValidate présent et valide laisse passer bind/refresh/persist", () => {
  const { window, capturedOpts, htmxTriggerCalls } = newDom();
  window.XwebValidate = (schema, data) => {
    assert.equal(schema, "contact_form");
    return { valid: true };
  };
  capturedOpts().onMessage("chat", { count: 42 });
  assert.equal(window.document.querySelector("#counter").textContent, "42");
  assert.equal(htmxTriggerCalls.length, 1);
});

await check("bout-en-bout avec le VRAI xweb/static/validators.js (pas un mock) : schéma exporté par le compilateur, count @min(0)", () => {
  const { window, capturedOpts, htmxTriggerCalls } = newDom();
  // Le bootstrap généré a déjà posé window.XWEB_SCHEMAS.contact_form ({
  // count: [["min", [0]]] }) avant même qu'on charge validators.js —
  // c'est exactement l'ordre réel dans la page (compiler écrit XWEB_SCHEMAS
  // inline dans le <script> du bootstrap, avant tout <script src=".../validators.js">
  // n'a besoin de s'exécuter).
  assert.ok(window.XWEB_SCHEMAS && window.XWEB_SCHEMAS.contact_form, "le bootstrap doit avoir exporté le schéma");
  window.eval(validatorsSrc);

  const before = window.document.querySelector("#counter").textContent;
  capturedOpts().onMessage("chat", { count: -1 }); // viole @min(0)
  assert.equal(window.document.querySelector("#counter").textContent, before, "bind ne doit pas s'appliquer");
  assert.equal(htmxTriggerCalls.length, 0, "refresh ne doit pas se déclencher");

  capturedOpts().onMessage("chat", { count: 5 }); // valide
  assert.equal(window.document.querySelector("#counter").textContent, "5");
  assert.equal(htmxTriggerCalls.length, 1);
});

if (failures > 0) {
  console.error(`\n${failures} vérification(s) en échec`);
  process.exit(1);
}
console.log("\nToutes les vérifications channel/use_channel (xdsl) passent.");
