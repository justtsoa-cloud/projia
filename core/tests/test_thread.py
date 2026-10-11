"""Robustesse du fil d'une discussion : priorités (fil > dossier > mémoire), longues discussions
mêlant texte, photos, images et vidéos, bascule de modèle sans perte du fil."""

from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tontolo.agent.loop import KEEP_IMAGES, compact_images
from tontolo.catalog.service import CatalogService
from tontolo.config import Settings
from tontolo.memory import MemoryService
from tontolo.providers.fake import FakeProvider
from tontolo.providers.registry import ProviderRegistry
from tontolo.server.app import create_app
from tontolo.storage.db import Database

IMG = {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}}


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


def _chat(client: TestClient, payload: dict[str, Any]) -> list[dict[str, Any]]:
    with client.stream("POST", "/tontolo/chat", json=payload) as s:
        return [json.loads(x[5:]) for x in s.iter_lines() if x.startswith("data:")]


async def test_memory_recall_skips_unrelated_and_same_discussion(
        db: Database, settings: Settings) -> None:
    mem = MemoryService(settings, db)
    await db.add_memory("L'utilisateur prépare l'exercice 8 sur la transformée de Laplace",
                        "fact", "autre-discussion")
    await db.add_memory("L'utilisateur est en terminale scientifique", "fact", "ici")
    await db.add_memory("Toujours répondre en français", "instruction", None)
    got = [m["text"] for m in await mem.recall("dessine un chat roux", exclude_source="ici")]
    assert got == ["Toujours répondre en français"]  # rien d'autre n'a de rapport
    got = [m["text"] for m in await mem.recall("terminale", exclude_source="ici")]
    assert all("terminale" not in t for t in got)  # tiré de CETTE discussion : déjà dans le fil


def test_only_recent_photos_are_sent_as_images() -> None:
    msgs = [{"role": "user", "content": [{"type": "text", "text": f"photo {i}"}, IMG]}
            for i in range(5)]
    out = compact_images(msgs)
    sent = [i for i, m in enumerate(out) if any(p.get("type") == "image_url"
                                                for p in m["content"])]
    assert sent == [3, 4] and KEEP_IMAGES == 2
    assert "photo envoyée plus tôt" in json.dumps(out[0], ensure_ascii=False)


def test_long_mixed_discussion_keeps_its_thread(client: TestClient, fake: FakeProvider) -> None:
    core = client.app.state.core  # type: ignore[attr-defined]
    first = _chat(client, {"content": "Commençons : je révise les probabilités"})
    cid = next(e["id"] for e in first if e["type"] == "conversation")

    async def build() -> None:
        for i in range(20):
            content: Any = ([{"type": "text", "text": f"exercice {i}"}, IMG] if i % 4 == 0
                            else f"question {i} sur les probabilités")
            await core.db.add_message(cid, {"role": "user", "content": content})
            await core.db.add_message(cid, {"role": "assistant", "content": f"réponse {i}"})
        await core.db.set_folder(cid, "Maths")
        other = await core.db.create_conversation("Statistiques")
        await core.db.set_folder(other, "Maths")
        await core.db.set_summary(other, "Moyenne et variance vues ensemble.", 2)
        await core.chat._summarize_thread(cid)

    client.portal.call(build)  # type: ignore[attr-defined]
    summary, covered = client.portal.call(core.db.get_summary, cid)  # type: ignore[attr-defined]
    assert summary and covered > 0  # le début du fil est résumé et enregistré

    _chat(client, {"conversation_id": cid, "content": "et la loi binomiale ?"})
    sent = fake.last_messages
    system = sent[0]["content"]
    assert "Priorités du contexte" in system
    text = json.dumps(sent, ensure_ascii=False)
    assert "Résumé du début de CETTE discussion" in text
    assert "Moyenne et variance" not in text  # aucun contexte provenant du dossier
    assert text.count("image_url") <= 2  # seules les photos récentes sont envoyées
    assert sent[-1]["role"] == "user" and sent[-1]["content"] == "et la loi binomiale ?"


async def test_summary_cannot_return_after_edit_or_delete(db: Database) -> None:
    cid = await db.create_conversation("Fil")
    await db.add_message(cid, {"role": "user", "content": "ancien sujet"})
    revision = await db.conversation_revision(cid)
    await db.edit_message(cid, 1, {"role": "user", "content": "nouveau sujet"})
    await db.set_summary(cid, "Résumé de l'ancien sujet", 1, revision)
    assert await db.get_summary(cid) == (None, 0)
    revision = await db.conversation_revision(cid)
    await db.delete_conversation(cid)
    await db.set_summary(cid, "Résumé du fil supprimé", 1, revision)
    assert await db.get_summary(cid) == (None, 0)


def test_folder_context_only_when_shared(client: TestClient, fake: FakeProvider) -> None:
    core = client.app.state.core  # type: ignore[attr-defined]
    first = _chat(client, {"content": "Bonjour, révisons les statistiques"})
    cid = next(e["id"] for e in first if e["type"] == "conversation")

    async def setup() -> None:
        await core.db.set_folder(cid, "Maths")
        other = await core.db.create_conversation("Variance")
        await core.db.set_folder(other, "Maths")
        await core.db.set_summary(other, "Moyenne et variance vues ensemble.", 2)

    client.portal.call(setup)  # type: ignore[attr-defined]
    _chat(client, {"conversation_id": cid, "content": "et l'écart type ?"})
    assert "Moyenne et variance" not in json.dumps(fake.last_messages, ensure_ascii=False)
    assert client.put("/tontolo/folders/share", json={"folder": "Maths", "share": True}).json()
    folders = client.get("/tontolo/folders").json()
    assert any(f["folder"] == "Maths" and f["shared"] for f in folders)
    _chat(client, {"conversation_id": cid, "content": "et la médiane ?"})
    text = json.dumps(fake.last_messages, ensure_ascii=False)
    assert "dossier partagé « Maths »" in text and "Moyenne et variance" in text
    assert fake.last_messages[-1]["content"] == "et la médiane ?"  # le fil reste au plus près
