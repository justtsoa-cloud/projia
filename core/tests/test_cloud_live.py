"""Synchronisation des créations (≤ 1 Mo) et suivi en direct des tâches en cours."""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tontolo.catalog.service import CatalogService
from tontolo.config import Settings
from tontolo.providers.fake import FakeProvider
from tontolo.providers.registry import ProviderRegistry
from tontolo.server.app import create_app


@pytest.fixture
def client(settings: Settings, catalog_service: CatalogService, fake: FakeProvider,
           monkeypatch: pytest.MonkeyPatch) -> Any:
    async def fake_load(self: CatalogService) -> Any:
        self.catalog = catalog_service.catalog
        return self.catalog

    monkeypatch.setattr(CatalogService, "load", fake_load)
    app = create_app(settings, registry=ProviderRegistry(lambda p: fake), refresh=False)
    with TestClient(app, base_url="http://127.0.0.1") as c:
        yield c


def test_creations_roundtrip(client: TestClient, tmp_path: Path) -> None:
    core = client.app.state.core  # type: ignore[attr-defined]
    small, big = tmp_path / "a.png", tmp_path / "b.png"
    small.write_bytes(b"\x89PNG" + b"0" * 100)
    big.write_bytes(b"0" * 1_000_001)

    async def setup() -> None:
        for jid, path in (("a"*32, small), ("b"*32, big)):
            await core.db.upsert_job({"id": jid, "kind": "image_gen", "status": "done",
                                      "prompt": "un chat", "params": {"mime": "image/png"},
                                      "result_path": str(path), "conversation_id": "c1"})

    client.portal.call(setup)  # type: ignore[attr-defined]
    out = client.get("/tontolo/cloud/creations").json()
    assert [c["id"] for c in out["creations"]] == ["a"*32]  # la lourde reste sur l'appareil
    assert out["until"] > 0
    assert client.get("/tontolo/cloud/creations", params={"since": out["until"]}).json()[
        "creations"] == []
    item = dict(out["creations"][0], id="c"*32)
    assert client.post("/tontolo/cloud/creations", json={"creations": [item]}).json() == {
        "applied": 1}
    assert client.post("/tontolo/cloud/creations", json={"creations": [item]}).json() == {
        "applied": 0}  # jamais en double
    job = client.get("/tontolo/media/" + "c" * 32).json()
    assert job["status"] == "done"
    assert client.get("/tontolo/media/" + "c" * 32 + "/file").content == small.read_bytes()
    bad = dict(item, id="../evil")
    assert client.post("/tontolo/cloud/creations", json={"creations": [bad]}).json() == {
        "applied": 0}
    huge = dict(item, id="d"*32, data_b64=base64.b64encode(b"0" * 1_000_001).decode())
    assert client.post("/tontolo/cloud/creations", json={"creations": [huge]}).json() == {
        "applied": 0}


async def test_turn_progress_and_activity() -> None:
    import asyncio

    from tontolo.agent.turns import TurnManager

    gate = asyncio.Event()

    async def events() -> Any:
        yield {"type": "step", "step": "doc_writing"}
        yield {"type": "delta", "content": "Il était "}
        yield {"type": "delta", "content": "une fois"}
        await gate.wait()

    turns = TurnManager()
    turn = turns.start("c1", events())
    await asyncio.sleep(0.01)
    assert [t.conversation_id for t in turns.running()] == ["c1"]
    p = turn.progress()
    assert p["partial"] == "Il était une fois" and p["step"] == "doc_writing"
    gate.set()
    await asyncio.sleep(0.01)
    assert turns.running() == []


def test_activity_endpoint(client: TestClient) -> None:
    out = client.get("/tontolo/activity").json()
    assert out["tasks"] == [] and out["at"] > 0


async def test_waiting_for_the_user() -> None:
    import asyncio

    from tontolo.agent.turns import TurnManager

    async def asks() -> Any:
        yield {"type": "delta", "content": "Quelle matière ?"}
        yield {"type": "done", "message": {"role": "assistant", "content": "Quelle matière ?"}}

    async def confirm() -> Any:
        yield {"type": "tool_confirmation", "calls": []}

    async def plain() -> Any:
        yield {"type": "done", "message": {"role": "assistant", "content": "Voilà."}}

    turns = TurnManager()
    for cid, gen in (("q", asks()), ("t", confirm()), ("p", plain())):
        turns.start(cid, gen)
    await asyncio.sleep(0.05)
    assert turns.waiting == {"q": "question", "t": "tool"}
    turns.start("q", plain())  # l'utilisateur répond : plus d'attente
    await asyncio.sleep(0.05)
    assert "q" not in turns.waiting


def test_conversation_list_has_dots(client: TestClient) -> None:
    core = client.app.state.core  # type: ignore[attr-defined]

    async def setup() -> str:
        cid = await core.db.create_conversation("Exercice")
        core.turns.waiting[cid] = "question"
        return cid

    cid = client.portal.call(setup)  # type: ignore[attr-defined]
    row = next(c for c in client.get("/tontolo/conversations").json() if c["id"] == cid)
    assert row["running"] is False and row["waiting"] == "question"
    act = client.get("/tontolo/activity").json()
    assert act["waiting"] == [{"conversation_id": cid, "reason": "question",
                               "title": "Exercice"}]
