/**
 * xweb.LiveChannel — connexion SSE OU WebSocket à un flux de messages par
 * "channels", écrit à la main (comme storage.js / le script de
 * notifications.xml, CLAUDE.md#realtime) : EventSource/WebSocket + parsing
 * JSON + dispatch est au-delà de ce qui est idiomatique en _hyperscript,
 * même exception déjà faite ailleurs dans ce dépôt.
 *
 * Ne gère QUE le côté client. Le serveur reste à écrire séparément — ce
 * module attend un contrat précis des deux côtés (voir "Contrat serveur"
 * plus bas), volontairement le même quel que soit le transport pour que
 * le code appelant (ex. pousser un xweb.chat_bubble dans le fil) n'ait
 * jamais à savoir si c'est du SSE ou du WS en dessous.
 *
 * Contrat serveur
 * ----------------
 * SSE : `event: <channel>\ndata: <json>\n\n` par message (convention
 *   xpulse documentée dans CLAUDE.md/XWEB_KNOWLEDGE.md) — un `event:`
 *   absent est traité comme le channel spécial "message". Souscription
 *   par `?channels=a,b,c` sur l'URL.
 * WS : chaque frame est un objet JSON `{"channel": "...", "data": ...}`.
 *   Souscription par le même `?channels=a,b,c` sur l'URL du handshake
 *   (une query string sur une URL ws(s):// est valide, RFC 6455) — pas de
 *   message de souscription séparé à envoyer après connexion, pour
 *   garder EXACTEMENT le même contrat de souscription que le SSE.
 *
 * Usage
 * -----
 *   const chan = new XwebLiveChannel({
 *     url: "/stream",              // relative ou absolue
 *     channels: ["chat", "notif"], // -> ?channels=chat,notif
 *     transport: "auto",           // "sse" | "ws" | "auto" (déduit de l'URL : ws(s): -> ws, sinon sse)
 *     connectTimeoutMs: 10000,     // optionnel, défaut 10s — voir "Timeout de connexion" plus bas
 *     onMessage(channel, data) { ... },
 *     onOpen() { ... },            // optionnel
 *     onError(err) { ... },        // optionnel — ne ferme jamais tout seul, cette classe gère elle-même
 *                                  //  la reconnexion (backoff exponentiel, plafonné à 10s) pour les DEUX
 *                                  //  transports — SSE ne s'appuie plus seulement sur son propre
 *                                  //  mécanisme natif (voir "Timeout de connexion")
 *   });
 *   chan.close();                  // arrête toute reconnexion, ferme la connexion
 *
 * Timeout de connexion
 * ---------------------
 * `EventSource`/`WebSocket` n'exposent ni l'un ni l'autre de délai
 * explicite pour "jamais arrivé à l'état ouvert" — sur un réseau qui
 * laisse la connexion pendre sans jamais répondre (proxy qui avale la
 * réponse, IP qui timeout au niveau TCP après une très longue durée
 * dépendante de l'OS/du navigateur, pas de `onerror` ni `onclose` avant
 * ça), rien ne se passe pendant potentiellement des dizaines de secondes.
 * `connectTimeoutMs` force la main : si `onOpen` n'a pas été atteint dans
 * ce délai depuis le DÉBUT de la tentative, la connexion en cours est
 * fermée et une reconnexion est planifiée (même backoff que pour une
 * fermeture normale) — vérifié en jsdom contre une IP non routable
 * (`10.255.255.1`, ne répond jamais), `scripts/verify-live-channel.mjs`.
 *
 * Défensif par construction : un message qui n'est pas du JSON valide, ou
 * un callback utilisateur (`onMessage`/`onOpen`/`onError`) qui lève, ne
 * casse jamais la connexion — logué en `console.error`, la classe continue
 * de fonctionner (même posture que xweb/static/storage.js).
 *
 * Sécurité — ce que CE fichier ne peut PAS garantir tout seul
 * -------------------------------------------------------------
 * Ce module est un simple client — il n'authentifie rien, n'autorise
 * rien, et ne protège pas la page appelante contre du contenu hostile.
 * Trois responsabilités restent entièrement côté SERVEUR (voir
 * scripts/live_channel_test_server.py pour une implémentation vérifiée
 * du point 2) :
 *   1. Authentifier la connexion — un same-origin `new EventSource(url)`/
 *      `new WebSocket(url)` envoie déjà le cookie de session automatique-
 *      ment (même principe que xpulse, CLAUDE.md#realtime) : RIEN à
 *      ajouter ici pour ça, mais le serveur doit quand même vérifier ce
 *      cookie — une connexion reçue ne veut pas dire "utilisateur
 *      légitime", juste "un cookie a été présenté".
 *   2. Autoriser chaque channel demandé pour CET utilisateur — ne jamais
 *      traiter `?channels=...` comme une autorisation, seulement comme
 *      une préférence de souscription à filtrer côté serveur.
 *   3. (WS uniquement, pas SSE) Vérifier l'en-tête `Origin` du handshake
 *      contre une allowlist explicite — sans ça, N'IMPORTE QUEL autre
 *      site peut ouvrir un `new WebSocket("wss://ton-site/ws")` depuis sa
 *      propre page et recevoir les mêmes messages que l'utilisateur
 *      légitime (Cross-Site WebSocket Hijacking) : contrairement à
 *      `fetch`/`EventSource`, le navigateur envoie quand même les cookies
 *      sur un WS cross-origin, rien dans le protocole ne l'empêche —
 *      c'est au serveur de refuser la poignée de main. SSE n'a pas ce
 *      problème (`fetch`/`EventSource` cross-origin sont bloqués par le
 *      Same-Origin Policy sauf CORS explicite — ne JAMAIS ajouter de CORS
 *      permissif sur un endpoint SSE authentifié, ça annulerait cette
 *      protection).
 *
 * Ce que le code APPELANT doit faire, lui :
 *   - Ne jamais injecter `data` reçu via `onMessage` dans le DOM avec
 *     `innerHTML` sans échapper — un channel compromis (ou un serveur mal
 *     autorisé, point 2 ci-dessus) devient alors un vecteur XSS classique.
 *     `textContent`, ou un fragment déjà rendu/échappé côté serveur QWeb
 *     (`t-esc`), jamais du HTML brut assemblé en JS depuis `data`.
 */
(function (global) {
  "use strict";

  function buildUrl(url, channels) {
    if (!channels || channels.length === 0) return url;
    const sep = url.includes("?") ? "&" : "?";
    return url + sep + "channels=" + encodeURIComponent(channels.join(","));
  }

  function detectTransport(url, explicit) {
    if (explicit && explicit !== "auto") return explicit;
    return /^wss?:\/\//i.test(url) ? "ws" : "sse";
  }

  function safeCall(fn, ...args) {
    if (typeof fn !== "function") return;
    try {
      fn(...args);
    } catch (err) {
      console.error("[XwebLiveChannel] callback a levé :", err);
    }
  }

  class XwebLiveChannel {
    constructor(opts) {
      if (!opts || !opts.url) {
        throw new Error("XwebLiveChannel: 'url' est requis");
      }
      this._baseUrl = opts.url;
      this._channels = opts.channels || [];
      this._transport = detectTransport(opts.url, opts.transport);
      this._onMessage = opts.onMessage;
      this._onOpen = opts.onOpen;
      this._onError = opts.onError;
      this._closed = false;
      this._source = null;
      this._reconnectDelay = 500; // ms — départ du backoff (partagé par les deux transports)
      this._reconnectTimer = null;
      this._connectTimeoutMs = opts.connectTimeoutMs || 10000;
      this._connectTimeoutTimer = null;

      if (this._transport === "ws") {
        this._connectWs();
      } else {
        this._connectSse();
      }
    }

    /** Ferme définitivement — plus aucune reconnexion après ça. */
    close() {
      this._closed = true;
      this._clearConnectTimeout();
      if (this._reconnectTimer) {
        clearTimeout(this._reconnectTimer);
        this._reconnectTimer = null;
      }
      if (this._source) {
        try {
          this._source.close();
        } catch (_) {
          /* déjà fermé, sans conséquence */
        }
        this._source = null;
      }
    }

    _clearConnectTimeout() {
      if (this._connectTimeoutTimer) {
        clearTimeout(this._connectTimeoutTimer);
        this._connectTimeoutTimer = null;
      }
    }

    /** Arme le timeout de connexion pour la tentative en cours — `onTimeout`
     * doit fermer la connexion pendante (jamais rien de plus, le
     * `onclose`/appel manuel à `_scheduleReconnect` fait le reste). */
    _armConnectTimeout(onTimeout) {
      this._clearConnectTimeout();
      this._connectTimeoutTimer = setTimeout(() => {
        this._connectTimeoutTimer = null;
        onTimeout();
      }, this._connectTimeoutMs);
    }

    /** Planifie une reconnexion après le délai de backoff courant, puis le
     * double (plafonné à 10s) — factorisé, utilisé par les DEUX transports
     * (un timeout de connexion ou une fermeture normale y mènent pareil). */
    _scheduleReconnect(connectFn) {
      if (this._closed) return;
      this._reconnectTimer = setTimeout(() => {
        this._reconnectTimer = null;
        connectFn();
      }, this._reconnectDelay);
      this._reconnectDelay = Math.min(this._reconnectDelay * 2, 10000);
    }

    _dispatch(channel, rawData) {
      let data = rawData;
      try {
        data = JSON.parse(rawData);
      } catch (_) {
        // Pas du JSON valide — transmis tel quel plutôt que d'avaler le
        // message en silence (l'appelant décide si c'est une erreur).
      }
      safeCall(this._onMessage, channel || "message", data);
    }

    // --- SSE ---------------------------------------------------------

    _connectSse() {
      if (this._closed) return;
      const url = buildUrl(this._baseUrl, this._channels);
      const source = new EventSource(url);
      this._source = source;

      this._armConnectTimeout(() => {
        // Jamais atteint onopen dans le délai — EventSource ne redéclenche
        // rien tout seul sur un close() manuel (pas de onclose, contrairement
        // à WS), donc c'est à nous de programmer la reconnexion ici.
        try {
          source.close();
        } catch (_) {
          /* déjà fermé, sans conséquence */
        }
        this._scheduleReconnect(() => this._connectSse());
      });

      source.onopen = () => {
        this._clearConnectTimeout();
        this._reconnectDelay = 500; // connexion réussie -> on repart de zéro au prochain accroc
        safeCall(this._onOpen);
      };
      source.onerror = (err) => safeCall(this._onError, err); // EventSource se reconnecte tout seul sur une VRAIE erreur — le timeout ci-dessus couvre le cas "ni erreur ni ouverture"

      // "message" = event sans nom explicite côté serveur.
      source.addEventListener("message", (ev) => this._dispatch("message", ev.data));
      for (const channel of this._channels) {
        source.addEventListener(channel, (ev) => this._dispatch(channel, ev.data));
      }
    }

    // --- WebSocket -----------------------------------------------------

    _connectWs() {
      if (this._closed) return;
      const url = buildUrl(this._baseUrl, this._channels);
      const ws = new WebSocket(url);
      this._source = ws;

      this._armConnectTimeout(() => {
        // Fermer un WS encore CONNECTING déclenche bien onclose (vérifié
        // contre une IP non routable) — la reconnexion se programme donc
        // depuis ws.onclose ci-dessous, jamais ici directement.
        try {
          ws.close();
        } catch (_) {
          /* déjà fermé, sans conséquence */
        }
      });

      ws.onopen = () => {
        this._clearConnectTimeout();
        this._reconnectDelay = 500; // connexion réussie -> on repart de zéro au prochain accroc
        safeCall(this._onOpen);
      };

      ws.onmessage = (ev) => {
        let envelope;
        try {
          envelope = JSON.parse(ev.data);
        } catch (_) {
          this._dispatch("message", ev.data); // pas l'enveloppe {channel, data} attendue, transmis brut
          return;
        }
        if (envelope && typeof envelope === "object" && "channel" in envelope) {
          safeCall(this._onMessage, envelope.channel, envelope.data);
        } else {
          safeCall(this._onMessage, "message", envelope);
        }
      };

      ws.onerror = (err) => safeCall(this._onError, err);

      ws.onclose = () => {
        this._clearConnectTimeout();
        this._scheduleReconnect(() => this._connectWs());
      };
    }
  }

  global.XwebLiveChannel = XwebLiveChannel;
})(typeof window !== "undefined" ? window : globalThis);
