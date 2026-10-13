"""Navigateur intégré (pont avec l'application)."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request

from tontolo.server.common import (
    Hub,
    RateLimiter,
    _local_only,
    core_of,
)


def register(app: FastAPI, hub: Hub, ws_connects: RateLimiter) -> None:
    # --- Navigateur intégré -------------------------------------------------------

    @app.get("/tontolo/browser")
    async def browser_status(request: Request) -> dict[str, Any]:
        chat = core_of(request).chat
        cdp = chat.browser_cdp
        return {"desktop": cdp is not None, "executable": cdp.executable if cdp else None,
                "tabs": len(cdp.tabs) if cdp else 0, "panel": chat.browser_bridge.available}

    @app.get("/tontolo/browser/next")
    async def browser_next(request: Request, wait: float = 25) -> dict[str, Any]:
        """Tablette : prochaine commande à exécuter dans le panneau WebView (attente longue)."""
        core = core_of(request)
        _local_only(request, core)
        cmd = await core.chat.browser_bridge.next(max(0.0, min(wait, 25.0)))
        return {"command": cmd}

    @app.post("/tontolo/browser/result")
    async def browser_result(request: Request) -> dict[str, bool]:
        core = core_of(request)
        _local_only(request, core)
        body = await request.json()
        data = body.get("data") if isinstance(body.get("data"), dict) else {}
        return {"ok": core.chat.browser_bridge.result(str(body.get("id") or ""), data)}
