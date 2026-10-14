"""Serveur FastAPI : API compatible OpenAI (`/v1/*`), API native (`/tontolo/*`) et
WebSocket d'événements (bascules, nouveautés, jobs médias).

Le même serveur tourne embarqué dans l'application (127.0.0.1, mode local)
ou sur une machine Linux (mode client-serveur, jeton obligatoire).
"""

from __future__ import annotations

import hmac
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

from tontolo import __version__
from tontolo.app_state import Core
from tontolo.config import Settings, load_settings
from tontolo.providers.registry import ProviderRegistry
from tontolo.security import (
    LOOPBACK_NAMES,
    host_of,
    origin_allowed,
)
from tontolo.server.common import (
    LOOPBACK,
    WS_CONNECTS_PER_MINUTE,
    Hub,
    RateLimiter,
)
from tontolo.server.routes import ROUTERS


def create_app(
    settings: Settings | None = None, *, registry: ProviderRegistry | None = None,
    refresh: bool = True,
) -> FastAPI:
    hub = Hub()
    ws_connects = RateLimiter(WS_CONNECTS_PER_MINUTE, 60.0)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        started = time.monotonic()
        core = await Core.start(settings, registry=registry, refresh=refresh)
        # Durée du démarrage du cœur (catalogue compris) : mesurée pour docs/PERF.md.
        print(f"[tontolo] cœur prêt en {time.monotonic() - started:.2f}s", flush=True)
        app.state.core = core
        core.catalog.on_changes(lambda ch: hub.publish({"type": "catalog_changes",
                                                        "changes": ch}))
        core.media.on_event(hub.publish)
        yield
        await core.stop()

    # Schéma OpenAPI servi (jeton requis) ; pas de /docs ni /redoc : leurs pages chargent des
    # scripts depuis un CDN externe. Documentation lisible : docs/API.md (scripts/api_docs.py).
    app = FastAPI(title="Tontolo", version=__version__, lifespan=lifespan, docs_url=None,
                  redoc_url=None)
    app.state.hub = hub


    @app.middleware("http")
    async def auth(request: Request, call_next: Any) -> Response:
        core: Core | None = getattr(request.app.state, "core", None)
        token = core.settings.server.token if core else None
        # Anti-CSRF : une page web ne peut pas piloter le serveur local.
        if not origin_allowed(request.headers.get("origin")):
            return JSONResponse({"error": {"message": "Origine refusée"}}, status_code=403)
        # Anti-DNS rebinding : en écoute locale, seul un Host de boucle locale est accepté.
        bind = core.settings.server.host if core else "127.0.0.1"
        if bind in LOOPBACK and host_of(request.headers.get("host", "")) not in LOOPBACK_NAMES:
            return JSONResponse({"error": {"message": "Hôte refusé"}}, status_code=403)
        if token and request.url.path not in ("/health",):
            given = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
            if not hmac.compare_digest(given, token):
                return JSONResponse({"error": {"message": "Jeton invalide"}}, status_code=401)
        response: Response = await call_next(request)
        return response

    for router in ROUTERS:
        router.register(app, hub, ws_connects)

    return app


def run(host: str | None = None, port: int | None = None) -> None:
    import uvicorn

    settings = load_settings()
    host = host or settings.server.host
    port = port or settings.server.port
    if host not in LOOPBACK and not settings.server.token:
        raise SystemExit("Un jeton (server.token ou TONTOLO_TOKEN) est obligatoire pour "
                         "écouter hors de la boucle locale.")
    settings.server.host, settings.server.port = host, port
    uvicorn.run(create_app(settings), host=host, port=port, log_level="info")
