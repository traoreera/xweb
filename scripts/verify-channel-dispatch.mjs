// Vérifie `onmessage { dispatch: true }` (xdsl/compiler.py::_write_channel_bootstrap)
// pour de vrai : vrai DOM (jsdom), vrai xweb/static/live_channel.js, vrai
// xweb/static/_hyperscript.min.js, contre le vrai serveur de test SSE+WS
// (scripts/live_channel_test_server.py) — sur LES DEUX transports, pas
// juste un des deux. La preuve décisive : un `_: on ... from document`
// hyperscript ordinaire (déjà supporté ailleurs dans le DSL, aucune
// nouvelle grammaire) réagit à un message reçu par WebSocket ET à un
// message reçu par SSE, chacun sur son propre `channel { }`.
//
// Nécessite scripts/live_channel_test_server.py démarré séparément (même
// convention que verify-live-channel.mjs) :
//   uv run uvicorn scripts.live_channel_test_server:app --port 8931
// Prérequis : uv run python scripts/render_channel_dispatch_fixture.py
// Usage : npm run verify:channel-dispatch

import { JSDOM } from "jsdom";
import { readFileSync } from "node:fs";
import assert from "node:assert/strict";

const BASE = process.argv[2] || "http://127.0.0.1:8931";
const HERE = new URL(".", import.meta.url);
const html = readFileSync(new URL("../.verify-channel-dispatch.html", HERE), "utf-8");
const liveChannelSrc = readFileSync(new URL("../xweb/static/live_channel.js", HERE), "utf-8");
const hyperscriptSrc = readFileSync(new URL("../xweb/static/_hyperscript.min.js", HERE), "utf-8");

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

// EventSource — absent de Node/jsdom (même constat que
// scripts/verify-live-channel.mjs), polyfillé sur fetch (que jsdom N'A
// PAS sur son `window` par défaut, contrairement à Node global — d'où
// window.fetch réassigné explicitement ci-dessous).
class MinimalEventSource {
  constructor(url) {
    this.url = url;
    this._listeners = {};
    this._closed = false;
    this._start();
  }
  addEventListener(name, cb) {
    (this._listeners[name] ||= []).push(cb);
  }
  close() {
    this._closed = true;
  }
  async _start() {
    const res = await fetch(this.url);
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";
    while (!this._closed) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      let idx;
      while ((idx = buf.indexOf("\n\n")) !== -1) {
        const block = buf.slice(0, idx);
        buf = buf.slice(idx + 2);
        let eventName = "message",
          data = "";
        for (const line of block.split("\n")) {
          if (line.startsWith("event:")) eventName = line.slice(6).trim();
          else if (line.startsWith("data:")) data += line.slice(5).trim();
        }
        for (const cb of this._listeners[eventName] || []) cb({ data });
      }
    }
  }
}

const dom = new JSDOM(html.replace("http://127.0.0.1:8931", BASE).replace("ws://127.0.0.1:8931", BASE.replace("http", "ws")), {
  // "outside-only" (pas "dangerously") : le HTML embarque déjà les
  // <script> de bootstrap générés par xdsl — avec "dangerously" jsdom les
  // exécuterait immédiatement au PARSE du document, avant même que
  // hyperscript/live_channel.js ne soient chargés (window.XwebLiveChannel
  // pas encore défini). "outside-only" laisse le contrôle de l'ordre
  // d'exécution à ce script (même patron que verify-channel-dsl.mjs).
  runScripts: "outside-only",
  url: "http://localhost/",
});
const { window } = dom;
window.WebSocket = globalThis.WebSocket;
window.fetch = globalThis.fetch;
window.EventSource = MinimalEventSource;

// _hyperscript.min.js d'abord — puis processNode() EXPLICITE (le
// DOMContentLoaded auto-init de la lib s'est déjà produit avant que ce
// script ne reprenne la main, même patron que verify-hyperscript.mjs) pour
// qu'il attache réellement les attributs `_` présents dans le HTML avant
// que live_channel.js ne commence à dispatcher des CustomEvent.
window.eval(hyperscriptSrc);
window._hyperscript.processNode(window.document.body);
window.eval(liveChannelSrc);
for (const s of window.document.querySelectorAll("script")) {
  window.eval(s.textContent);
}

await new Promise((r) => setTimeout(r, 2000));

await check("SSE — dispatch: true + hyperscript réel (`on chat_sse:message from document`) met à jour le DOM", () => {
  const text = window.document.querySelector("#sse-log").textContent.trim();
  assert.equal(text, "bonjour", `#sse-log attendu "bonjour", eu ${JSON.stringify(text)}`);
});

await check("WS — dispatch: true + hyperscript réel (`on notif_ws:message from document`) met à jour le DOM", () => {
  const text = window.document.querySelector("#ws-log").textContent.trim();
  assert.equal(text, "3", `#ws-log attendu "3", eu ${JSON.stringify(text)}`);
});

// Les connexions WS/SSE (le vrai WebSocket natif, le polyfill EventSource
// sur fetch) n'ont pas de raison de se refermer d'elles-mêmes ici — sans
// process.exit() explicite, Node resterait accroché à ces sockets ouvertes.
if (failures > 0) {
  console.error(`\n${failures} vérification(s) en échec`);
  process.exit(1);
}
console.log("\ndispatch: true fonctionne avec du hyperscript réel, sur SSE ET WS.");
process.exit(0);
