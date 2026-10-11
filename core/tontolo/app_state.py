"""Assemblage des services du cœur (utilisé par le serveur et la CLI)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from tontolo import http
from tontolo.agent.loop import ChatService
from tontolo.agent.mcp_client import McpManager
from tontolo.agent.turns import TurnManager
from tontolo.catalog.service import CatalogService
from tontolo.config import Settings, load_settings
from tontolo.creator.service import CreatorService
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
    turns: TurnManager = field(default_factory=TurnManager)

    @property
    def creator(self) -> CreatorService:
        """Créations de fichiers (langue suivie en direct depuis les réglages)."""
        return CreatorService(self.db, self.router, self.media.dir, self.settings.language,
                              self.settings.team_review)

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
        for cid in list(self.turns.turns):
            await self.turns.stop(cid)
        await self.mcp.close()
        if self.chat.browser_cdp is not None:
            await self.chat.browser_cdp.close()
        await self.db.close()
        await http.aclose()
