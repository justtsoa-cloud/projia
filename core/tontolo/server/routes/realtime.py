"""WebSocket d'événements et terminal du bureau."""

from __future__ import annotations

import asyncio
import hmac
import json
import re
from typing import Any

from fastapi import FastAPI, WebSocket

from tontolo.security import (
    origin_allowed,
)
from tontolo.server.common import (
    LOOPBACK,
    TERM_MAX_MESSAGE,
    TERM_MESSAGES_PER_SECOND,
    WS_MAX_CLIENTS,
    Hub,
    RateLimiter,
    core_of,
)


def register(app: FastAPI, hub: Hub, ws_connects: RateLimiter) -> None:
    # --- WebSocket d'événements ------------------------------------------

    @app.websocket("/tontolo/ws")
    async def ws(websocket: WebSocket) -> None:
        core = core_of(websocket)
        token = core.settings.server.token
        if token and not hmac.compare_digest(websocket.query_params.get("token", ""), token):
            await websocket.close(code=4401)
            return
        if not origin_allowed(websocket.headers.get("origin")):
            await websocket.close(code=4403)
            return
        peer = websocket.client.host if websocket.client else "?"
        if len(hub.queues) >= WS_MAX_CLIENTS or not ws_connects.allow(f"ws:{peer}"):
            await websocket.close(code=4429)  # trop de connexions : débit limité
            return
        await websocket.accept()
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        hub.queues.add(q)
        try:
            while True:
                ev = await q.get()
                await websocket.send_text(json.dumps(ev, ensure_ascii=False, default=str))
        except Exception:
            pass
        finally:
            hub.queues.discard(q)

    # --- Terminal du bureau (une session par discussion) -----------------------------

    @app.websocket("/tontolo/terminal/{cid}/ws")
    async def terminal_ws(websocket: WebSocket, cid: str) -> None:
        """Affichage et saisie du terminal d'une discussion. Accès à un shell : application
        locale uniquement (aucune page web, aucun client distant)."""
        core = core_of(websocket)
        token = core.settings.server.token
        local = (websocket.client is not None and websocket.client.host in ("127.0.0.1", "::1")
                 and core.settings.server.host in LOOPBACK)
        # Un shell : jeton OBLIGATOIRE (sans jeton, n'importe quel processus local pourrait
        # s'y connecter), application locale seulement, aucune origine web.
        if (core.chat.terminals is None or not local or not token
                or websocket.headers.get("origin")
                or not re.fullmatch(r"[\w-]{1,64}", cid)
                or not hmac.compare_digest(websocket.query_params.get("token", ""), token)):
            await websocket.close(code=4403)
            return
        if not ws_connects.allow(f"term:{cid}"):
            await websocket.close(code=4429)
            return
        await websocket.accept()
        session = core.chat.terminals.get(cid, core.chat.terminal_cwd())
        typed = RateLimiter(TERM_MESSAGES_PER_SECOND, 1.0)
        q: asyncio.Queue[bytes] = asyncio.Queue()
        session.listeners.add(q)

        async def pump() -> None:
            await websocket.send_bytes(bytes(session.buffer))
            while True:
                await websocket.send_bytes(await q.get())

        sender = asyncio.create_task(pump())
        try:
            while True:
                raw = await websocket.receive_text()
                if len(raw) > TERM_MAX_MESSAGE or not typed.allow("in"):
                    await websocket.close(code=1009 if len(raw) > TERM_MAX_MESSAGE else 4429)
                    break
                msg = json.loads(raw)
                if not isinstance(msg, dict):
                    continue
                if isinstance(msg.get("input"), str):
                    session.write(msg["input"].encode())
                if isinstance(msg.get("resize"), list) and len(msg["resize"]) == 2:
                    session.resize(int(msg["resize"][0]), int(msg["resize"][1]))
                if msg.get("restart"):
                    session.close()
                    session.listeners.discard(q)
                    session = core.chat.terminals.get(cid, core.chat.terminal_cwd())
                    session.listeners.add(q)
                    await websocket.send_bytes(bytes(session.buffer))
        except Exception:
            pass
        finally:
            sender.cancel()
            session.listeners.discard(q)
