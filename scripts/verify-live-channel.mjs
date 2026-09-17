// Vérifie xweb/static/live_channel.js (SSE + WS) pour de vrai — un vrai
// serveur, de vrais WebSocket/EventSource, pas une lecture du code. Ni
// Node ni jsdom n'ont EventSource nativement (vérifié en construisant ce
// script) : un shim minimal mais conforme au protocole (event:/data:
// framing, dispatch par nom d'event, "message" par défaut) pilote le VRAI
// live_channel.js sans le modifier — WebSocket, lui, est natif à Node 24+,
// aucun shim nécessaire pour ce chemin.
//
// Nécessite scripts/live_channel_test_server.py démarré séparément (même
// convention que verify-demo-page.mjs — ce script ne spawn pas le
// serveur) :
//   uv run uvicorn scripts.live_channel_test_server:app --port 8931
// Usage : node scripts/verify-live-channel.mjs [http://127.0.0.1:8931]

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const BASE = process.argv[2] || "http://127.0.0.1:8931";
const HERE = dirname(fileURLToPath(import.meta.url));
const LIVE_CHANNEL_JS = readFileSync(join(HERE, "..", "xweb", "static", "live_channel.js"), "utf-8");

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

class MinimalEventSource {
  constructor(url) {
    this.url = url;
    this._listeners = {};
    this.onopen = null;
    this.onerror = null;
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
    try {
      const res = await fetch(this.url);
      if (this.onopen) this.onopen();
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buf = "";
      while (!this._closed) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        let idx;
        while ((idx = buf.indexOf("\n\n")) !== -1) {
          this._dispatch(buf.slice(0, idx));
          buf = buf.slice(idx + 2);
        }
      }
    } catch (err) {
      if (this.onerror) this.onerror(err);
    }
  }
  _dispatch(block) {
    let eventName = "message";
    let data = "";
    for (const line of block.split("\n")) {
      if (line.startsWith("event:")) eventName = line.slice(6).trim();
      else if (line.startsWith("data:")) data += line.slice(5).trim();
    }
    for (const cb of this._listeners[eventName] || []) cb({ data });
  }
}
globalThis.EventSource = MinimalEventSource;

// eslint-disable-next-line no-eval — charge le vrai fichier, pas une copie retapée.
eval(LIVE_CHANNEL_JS);
const XwebLiveChannel = globalThis.XwebLiveChannel;

await check("SSE — channels nommés + event sans nom (\"message\") tous reçus", async () => {
  const received = [];
  const chan = new XwebLiveChannel({
    url: `${BASE}/stream`,
    channels: ["chat", "notif"],
    transport: "sse",
    onMessage: (channel, data) => received.push([channel, data]),
  });
  await new Promise((r) => setTimeout(r, 800));
  chan.close();

  const byChannel = Object.fromEntries(received);
  assert.deepEqual(byChannel.chat, { text: "bonjour" }, "channel 'chat'");
  assert.deepEqual(byChannel.notif, { count: 3 }, "channel 'notif'");
  assert.deepEqual(byChannel.message, { plain: true }, "event sans nom -> channel 'message'");
});

await check("SSE — souscription à un seul channel n'en reçoit qu'un", async () => {
  const received = [];
  const chan = new XwebLiveChannel({
    url: `${BASE}/stream`,
    channels: ["chat"],
    transport: "sse",
    onMessage: (channel, data) => received.push([channel, data]),
  });
  await new Promise((r) => setTimeout(r, 800));
  chan.close();

  const channels = received.map((r) => r[0]);
  assert.ok(channels.includes("chat"), "'chat' doit être reçu");
  assert.ok(!channels.includes("notif"), "'notif' ne doit PAS être reçu (jamais souscrit)");
});

await check("WS — enveloppe {channel, data} correctement dispatchée", async () => {
  const received = [];
  await new Promise((resolve, reject) => {
    const chan = new XwebLiveChannel({
      url: `${BASE.replace("http", "ws")}/ws`,
      channels: ["chat", "notif"],
      transport: "ws",
      onMessage: (channel, data) => {
        received.push([channel, data]);
        if (received.length === 2) {
          chan.close(); // avant le close() serveur -> pas de reconnexion parasite dans CE check
          resolve();
        }
      },
      onError: reject,
    });
    setTimeout(() => reject(new Error("timeout — pas reçu 2 messages en 2s")), 2000);
  });

  const byChannel = Object.fromEntries(received);
  assert.deepEqual(byChannel.chat, { text: "bonjour" });
  assert.deepEqual(byChannel.notif, { count: 3 });
});

await check("WS — reconnexion automatique après une fermeture inattendue", async () => {
  let openCount = 0;
  const received = [];
  await new Promise((resolve, reject) => {
    const chan = new XwebLiveChannel({
      url: `${BASE.replace("http", "ws")}/ws`,
      channels: ["chat"],
      transport: "ws",
      onOpen: () => {
        openCount++;
      },
      onMessage: (channel, data) => {
        received.push([channel, data]);
        // Le serveur de test ferme lui-même après ses deux messages —
        // laisser faire (pas de chan.close() ici) pour observer une
        // vraie reconnexion, puis vérifier une 2e vague de messages.
        if (openCount >= 2 && received.length >= 2) {
          chan.close();
          resolve();
        }
      },
    });
    setTimeout(() => reject(new Error("timeout — pas reconnecté en 3s")), 3000);
  });
  assert.ok(openCount >= 2, `au moins 2 connexions attendues, eu ${openCount}`);
});

// ---------------------------------------------------------------------
// connectTimeoutMs — connexion qui ne répond JAMAIS (ni onopen, ni erreur,
// ni close), le cas que ni EventSource ni WebSocket ne bornent tout seuls.
// 10.255.255.1 est une IP non routable (bloc réservé TEST-NET-3, RFC 5737)
// — aucune machine n'y répond jamais, la connexion pend sans jamais
// déclencher d'événement tant que l'OS ne timeout pas de lui-même (bien
// plus long que connectTimeoutMs ici). On compte les tentatives de
// connexion réelles en enveloppant temporairement le constructeur global.
// ---------------------------------------------------------------------

const UNROUTABLE = "10.255.255.1";

await check("WS — connectTimeoutMs force une reconnexion sur une IP qui ne répond jamais", async () => {
  const RealWebSocket = globalThis.WebSocket;
  let attempts = 0;
  globalThis.WebSocket = function (url) {
    attempts++;
    return new RealWebSocket(url);
  };
  try {
    const chan = new XwebLiveChannel({
      url: `ws://${UNROUTABLE}:9999/`,
      transport: "ws",
      connectTimeoutMs: 300,
    });
    await new Promise((r) => setTimeout(r, 1200)); // largement 2-3 cycles de connectTimeoutMs
    chan.close();
    assert.ok(attempts >= 2, `au moins 2 tentatives de connexion attendues, eu ${attempts}`);
  } finally {
    globalThis.WebSocket = RealWebSocket;
  }
});

await check("SSE — connectTimeoutMs force une reconnexion sur une IP qui ne répond jamais", async () => {
  const RealEventSource = globalThis.EventSource;
  let attempts = 0;
  globalThis.EventSource = function (url) {
    attempts++;
    return new RealEventSource(url);
  };
  try {
    const chan = new XwebLiveChannel({
      url: `http://${UNROUTABLE}:9999/stream`,
      transport: "sse",
      connectTimeoutMs: 300,
    });
    await new Promise((r) => setTimeout(r, 1200));
    chan.close();
    assert.ok(attempts >= 2, `au moins 2 tentatives de connexion attendues, eu ${attempts}`);
  } finally {
    globalThis.EventSource = RealEventSource;
  }
});

// ---------------------------------------------------------------------
// Sécurité — Cross-Site WebSocket Hijacking (CSWSH). Contrairement à
// fetch/EventSource (bloqués cross-origin par le Same-Origin Policy sauf
// CORS explicite), un navigateur envoie quand même les cookies sur un
// new WebSocket("wss://cible/ws") lancé depuis N'IMPORTE QUELLE origine —
// la seule protection est que le SERVEUR vérifie l'en-tête Origin du
// handshake. Le WebSocket natif du navigateur (et celui de Node) ne
// permettent pas de fixer Origin à la main (c'est justement tout l'intérêt
// de l'en-tête — non falsifiable depuis JS) : ce check parle donc
// directement le protocole HTTP d'upgrade en TCP brut pour simuler ce
// qu'un navigateur enverrait réellement depuis chaque origine.
// ---------------------------------------------------------------------

async function attemptWsHandshake(origin) {
  const net = await import("node:net");
  const crypto = await import("node:crypto");
  const host = new URL(BASE).hostname;
  const port = Number(new URL(BASE).port);
  return new Promise((resolve) => {
    const socket = net.connect(port, host, () => {
      const key = crypto.randomBytes(16).toString("base64");
      let req =
        `GET /ws HTTP/1.1\r\nHost: ${host}:${port}\r\nUpgrade: websocket\r\n` +
        `Connection: Upgrade\r\nSec-WebSocket-Key: ${key}\r\nSec-WebSocket-Version: 13\r\n`;
      if (origin !== undefined) req += `Origin: ${origin}\r\n`;
      socket.write(req + "\r\n");
    });
    socket.on("data", (chunk) => {
      resolve(chunk.toString().split("\r\n")[0]);
      socket.destroy();
    });
    socket.on("error", () => resolve("CONNECTION ERROR"));
    setTimeout(() => {
      resolve("TIMEOUT");
      socket.destroy();
    }, 1500);
  });
}

await check("WS — une origine hostile est rejetée AVANT toute donnée (CSWSH)", async () => {
  const status = await attemptWsHandshake("https://evil.example");
  assert.match(status, /403/, `attendu 403 Forbidden, eu: ${status}`);
});

await check("WS — l'origine légitime du serveur de test passe toujours", async () => {
  const status = await attemptWsHandshake(BASE); // origine = celle listée dans _ALLOWED_ORIGINS du serveur de test
  assert.match(status, /101/, `attendu 101 Switching Protocols, eu: ${status}`);
});

if (failures > 0) {
  console.error(`\n${failures} vérification(s) en échec`);
  process.exit(1);
}
console.log("\nToutes les vérifications live_channel.js passent.");
