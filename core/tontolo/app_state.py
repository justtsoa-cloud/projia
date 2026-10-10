"""Assemblage des services du cœur (utilisé par le serveur et la CLI)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from tontolo import http
from tontolo.agent.loop import ChatService
from tontolo.agent.mcp_client import McpManager
from tontolo.catalog.service import CatalogService
from tontolo.config import Settings, load_settings
from tontolo.media.service import MediaService
from tontolo.providers.registry import ProviderRegistry
from tontolo.router.engine import Router
from tontolo.storage.db import Database


@dataclass
class Core:
    settings: Settings
    db: Database
    catalog: CatalogService
    router: Router
    chat: ChatService
    media: MediaService
    mcp: McpManager
    events: list[Any] = field(default_factory=list)

    @classmethod
    async def start(
        cls, settings: Settings | None = None, *, registry: ProviderRegistry | None = None,
        refresh: bool = True,
    ) -> Core:
        settings = settings or load_settings()
        db = await Database(settings.data_dir / "tontolo.db").open()
        catalog = CatalogService(settings, db)
        await catalog.load()
        router = Router(settings, catalog, db, registry=registry)
        await router.startup()
        mcp = McpManager(settings.data_dir / "mcp_servers.yaml")
        chat = ChatService(settings, db, router, mcp)
        media = MediaService(settings, db, router)
        core = cls(settings, db, catalog, router, chat, media, mcp)
        if refresh:
            catalog.refresh_in_background()
        return core

    async def stop(self) -> None:
        await self.mcp.close()
        await self.db.close()
        await http.aclose()
