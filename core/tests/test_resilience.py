"""Pannes de stockage : base verrouillée, disque plein. Le serveur ne plante pas, répond par
une erreur lisible, et reprend dès que le problème disparaît."""

from __future__ import annotations

import errno
import json
import sqlite3
from typing import Any

import pytest
from fastapi.testclient import TestClient

from projia.catalog.service import CatalogService
from projia.config import Settings
from projia.providers.fake import FakeProvider
from projia.providers.registry import ProviderRegistry
from projia.server.app import create_app
from projia.storage.db import Database


@pytest.fixture
def client(settings: Settings, catalog_service: CatalogService, fake: FakeProvider,
           monkeypatch: pytest.MonkeyPatch) -> Any:
    async def fake_load(self: CatalogService) -> Any:
        self.catalog = catalog_service.catalog
        return self.catalog

    monkeypatch.setattr(CatalogService, "load", fake_load)
    app = create_app(settings, registry=ProviderRegistry(lambda p: fake), refresh=False)
    with TestClient(app, base_url="http://127.0.0.1", raise_server_exceptions=False) as c:
        yield c


def _chat(client: TestClient, text: str) -> tuple[int, list[dict[str, Any]]]:
    with client.stream("POST", "/projia/chat", json={"content": text}) as r:
        return r.status_code, [json.loads(x[5:]) for x in r.iter_lines() if x.startswith("data:")]


@pytest.mark.parametrize("failure", [
    sqlite3.OperationalError("database is locked"),
    OSError(errno.ENOSPC, "No space left on device"),
    sqlite3.OperationalError("database or disk is full"),
])
def test_storage_failure_never_kills_the_server(client: TestClient, monkeypatch: pytest.MonkeyPatch,
                                                failure: Exception) -> None:
    original = Database.add_message
    broken = True

    async def add_message(self: Database, *a: Any, **kw: Any) -> Any:
        if broken:
            raise failure
        return await original(self, *a, **kw)

    monkeypatch.setattr(Database, "add_message", add_message)
    status, events = _chat(client, "Bonjour")
    assert status in (200, 500, 503)
    if status == 200:  # flux ouvert : l'échec est annoncé, jamais un silence
        errors = [e for e in events if e["type"] == "error"]
        assert errors, events
        assert errors[0].get("code") in ("storage_full", "storage_busy"), errors
    assert client.get("/health").status_code == 200  # toujours vivant
    broken = False
    status, events = _chat(client, "Et maintenant ?")
    assert status == 200 and any(e["type"] == "done" for e in events)  # reprise sans redémarrage
