"""Serveur de test MINIMAL pour vérifier xweb/static/live_channel.js — SSE
et WS, chacun sur un endpoint dédié, chacun émettant deux messages connus
sur des channels connus puis se taisant. Ce n'est PAS un système de
channels/pubsub réel (pas de fan-out multi-abonné, pas de Redis) — juste
de quoi prouver que le contrat client/serveur documenté en tête de
live_channel.js (event:<channel>\\ndata:<json> pour SSE, {"channel","data"}
par frame pour WS, souscription ?channels=a,b) est bien celui que le
client sait consommer.

Usage :
    uv run uvicorn scripts.live_channel_test_server:app --port 8931

SÉCURITÉ — ce que ce fichier fait, et NE fait PAS
--------------------------------------------------
Ce serveur de test ne vérifie AUCUNE authentification et n'autorise AUCUN
channel — n'importe qui peut se connecter et demander n'importe quel
channel. C'est acceptable pour un harnais de vérification jetable, PAS
pour un vrai serveur de channels. Un vrai serveur doit, dans cet ordre,
AVANT tout `accept()`/toute émission :
  1. Résoudre l'utilisateur depuis le cookie de session (`access_token`,
     déjà transmis automatiquement en same-origin — pas de jeton à passer
     à la main dans l'URL, voir CLAUDE.md#realtime pour xpulse, le même
     principe). Rejeter si absent/invalide.
  2. Vérifier que CET utilisateur a le droit de voir CHAQUE channel
     demandé — ne JAMAIS faire confiance à `?channels=...` comme une
     autorisation, c'est une simple préférence de souscription, filtrée
     côté serveur exactement comme l'liste `wanted` ci-dessous filtre déjà
     par CONTENU (mais pas par droit d'accès).
  3. (WS spécifiquement, PAS SSE) Vérifier l'en-tête `Origin` du handshake
     contre une allowlist explicite — voir `_check_origin` ci-dessous.
     C'est la SEULE protection contre le Cross-Site WebSocket Hijacking
     (CSWSH) : contrairement à `fetch`/`EventSource` (bloqués cross-origin
     par le Same-Origin Policy sauf CORS explicite), un `new
     WebSocket("wss://ton-site/ws")" lancé depuis N'IMPORTE QUEL AUTRE SITE
     réussit à se connecter ET envoie les cookies du visiteur — rien dans
     le protocole WS lui-même ne l'empêche. Implémenté ci-dessous pour de
     vrai (pas juste documenté) et vérifié dans verify-live-channel.mjs.

Ce fichier n'illustre le point 3 que parce qu'il est spécifique à WS et
directement démontrable sans dépendance externe. Les points 1 et 2 restent
à la charge du vrai serveur — aucune vérification d'auth n'a de sens sur
un harnais jetable sans système d'utilisateurs.
"""

from __future__ import annotations

import asyncio
import json

from fastapi import FastAPI, WebSocket
from fastapi.responses import StreamingResponse

app = FastAPI()

# Allowlist explicite, jamais déduite/devinée — même posture que
# OAUTH_WEB_REDIRECT_ORIGINS (plugins/auth) déjà documenté dans CLAUDE.md :
# aucune origine n'est "de confiance par défaut" sous prétexte qu'elle a
# l'air locale.
_ALLOWED_ORIGINS = {"http://127.0.0.1:8931", "http://localhost:8931", None}
# None : un client SANS en-tête Origin DU TOUT (curl, un script serveur-à-
# serveur, un client non-navigateur) n'est structurellement pas concerné
# par le CSWSH — l'attaque dépend justement du navigateur qui l'envoie
# automatiquement depuis la page malveillante. Un vrai serveur en
# production resserre ceci à la liste exacte des origines qui servent la
# page (jamais None) SI tout accès légitime passe forcément par un
# navigateur ; le laisser ici ne sert qu'à ne pas casser des clients de
# test non-navigateur pendant le développement.


def _origin_allowed(origin: str | None) -> bool:
    return origin in _ALLOWED_ORIGINS


@app.get("/stream")
async def sse_stream(channels: str = ""):
    wanted = [c for c in channels.split(",") if c]

    async def gen():
        payload = {"text": "bonjour"}
        if not wanted or "chat" in wanted:
            yield f"event: chat\ndata: {json.dumps(payload)}\n\n"
        await asyncio.sleep(0.05)
        if not wanted or "notif" in wanted:
            yield f"event: notif\ndata: {json.dumps({'count': 3})}\n\n"
        # Un event SANS nom explicite — doit atterrir sur le channel
        # spécial "message" côté client (voir live_channel.js).
        yield f"data: {json.dumps({'plain': True})}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.websocket("/ws")
async def ws_stream(websocket: WebSocket, channels: str = ""):
    # Vérification CSWSH — voir la docstring du module. AVANT accept(),
    # jamais après : accepter puis fermer laisserait quand même la
    # poignée de main WS réussir aux yeux du navigateur appelant.
    if not _origin_allowed(websocket.headers.get("origin")):
        await websocket.close(code=1008)  # 1008 = Policy Violation
        return
    await websocket.accept()
    wanted = [c for c in channels.split(",") if c]
    if not wanted or "chat" in wanted:
        await websocket.send_text(json.dumps({"channel": "chat", "data": {"text": "bonjour"}}))
    await asyncio.sleep(0.05)
    if not wanted or "notif" in wanted:
        await websocket.send_text(json.dumps({"channel": "notif", "data": {"count": 3}}))
    await asyncio.sleep(0.2)
    await websocket.close()
