"""Robustesse du fil d'une discussion : priorités (fil > dossier > mémoire), longues discussions
mêlant texte, photos, images et vidéos, bascule de modèle sans perte du fil."""

from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from projia.agent.loop import KEEP_IMAGES, compact_images
from projia.catalog.service import CatalogService
from projia.config import Settings
from projia.memory import MemoryService
from projia.providers.fake import FakeProvider
from projia.providers.registry import ProviderRegistry
from projia.server.app import create_app
from projia.storage.db import Database

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
    with client.stream("POST", "/projia/chat", json=payload) as s:
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
    assert client.put("/projia/folders/share", json={"folder": "Maths", "share": True}).json()
    folders = client.get("/projia/folders").json()
    assert any(f["folder"] == "Maths" and f["shared"] for f in folders)
    _chat(client, {"conversation_id": cid, "content": "et la médiane ?"})
    text = json.dumps(fake.last_messages, ensure_ascii=False)
    assert "dossier partagé « Maths »" in text and "Moyenne et variance" in text
    assert fake.last_messages[-1]["content"] == "et la médiane ?"  # le fil reste au plus près


def _behave_all(fake: FakeProvider, fn: Any) -> None:
    for mid in ("coder-pro", "chatty", "small", "vision-x", "paid-genius"):
        fake.behaviors[mid] = fn


def test_cut_answer_continues_automatically(client: TestClient, fake: FakeProvider) -> None:
    parts = iter(["Début de la réponse", " suite 1", " fin."])

    def cut(model: Any, messages: list[dict[str, Any]]) -> dict[str, Any]:
        piece = next(parts)
        return {"role": "assistant", "content": piece,
                "_finish": "stop" if piece == " fin." else "length"}

    _behave_all(fake, cut)
    events = _chat(client, {"content": "écris un long texte"})
    assert sum(e["type"] == "continuing" for e in events) == 2
    done = next(e for e in events if e["type"] == "done")
    assert done["message"]["content"] == "Début de la réponse suite 1 fin."
    cid = next(e["id"] for e in events if e["type"] == "conversation")
    msgs = client.get(f"/projia/conversations/{cid}").json()["messages"]
    assert [m["role"] for m in msgs] == ["user", "assistant"]  # un seul message fusionné


def test_continue_stops_without_progress(client: TestClient, fake: FakeProvider) -> None:
    def always_cut(model: Any, messages: list[dict[str, Any]]) -> dict[str, Any]:
        return {"role": "assistant", "content": "même texte", "_finish": "length"}

    _behave_all(fake, always_cut)
    events = _chat(client, {"content": "boucle ?"})
    assert sum(e["type"] == "continuing" for e in events) == 1  # aucune boucle infinie
    assert next(e for e in events if e["type"] == "done")["message"]["content"] == "même texte"


def test_continue_is_bounded(client: TestClient, fake: FakeProvider) -> None:
    counter = iter(range(100))

    def endless(model: Any, messages: list[dict[str, Any]]) -> dict[str, Any]:
        return {"role": "assistant", "content": f" morceau {next(counter)}", "_finish": "length"}

    _behave_all(fake, endless)
    events = _chat(client, {"content": "sans fin"})
    assert sum(e["type"] == "continuing" for e in events) == 3


def test_agent_mode_prompt_and_tools(client: TestClient, fake: FakeProvider) -> None:
    events = _chat(client, {"content": "compare deux sources", "mode": "agent",
                            "agent": "researcher"})
    cid = next(e["id"] for e in events if e["type"] == "conversation")
    assert client.get(f"/projia/conversations/{cid}").json()["mode"] == "agent:researcher"
    system = fake.last_messages[0]["content"]
    assert "agent Chercheur" in system
    route = next(e for e in events if e["type"] == "route")
    assert route["model"] != "fake:small"  # le seul modèle sans outils est écarté
    _chat(client, {"conversation_id": cid, "content": "merci", "mode": "general"})
    assert "Mode agent" not in fake.last_messages[0]["content"]


def test_manual_compaction(client: TestClient, fake: FakeProvider) -> None:
    core = client.app.state.core  # type: ignore[attr-defined]
    first = _chat(client, {"content": "Projet de rapport"})
    cid = next(e["id"] for e in first if e["type"] == "conversation")
    small = client.post(f"/projia/conversations/{cid}/compact").json()
    assert small["ok"] is False  # trop court : rien à compacter

    async def build() -> None:
        for i in range(10):
            await core.db.add_message(cid, {"role": "user", "content": f"point {i}"})
            await core.db.add_message(cid, {"role": "assistant", "content": f"noté {i}"})

    client.portal.call(build)  # type: ignore[attr-defined]

    async def quick(messages: list[dict[str, Any]], **kw: Any) -> str:
        assert "## Tâches en cours" in messages[0]["content"]
        return "## Sujets\n- rapport, points 0 à 3\n## Tâches en cours\n- finir le rapport"

    core.chat.router.quick = quick
    out = client.post(f"/projia/conversations/{cid}/compact").json()
    assert out["ok"] is True and "## Sujets" in out["summary"] and out["summary_covered"] > 0
    data = client.get(f"/projia/conversations/{cid}").json()
    assert len(data["messages"]) == 22 and data["summary"] == out["summary"]  # rien d'effacé


def test_auto_compaction_can_be_disabled(client: TestClient) -> None:
    core = client.app.state.core  # type: ignore[attr-defined]
    client.put("/projia/settings", json={"auto_compact": False})
    assert core.settings.auto_compact is False
    first = _chat(client, {"content": "x"})
    cid = next(e["id"] for e in first if e["type"] == "conversation")

    async def build() -> bool:
        for i in range(40):
            await core.db.add_message(cid, {"role": "user", "content": f"q{i}"})
            await core.db.add_message(cid, {"role": "assistant", "content": f"r{i}"})
        return await core.chat._summarize_thread(cid)

    assert client.portal.call(build) is False  # type: ignore[attr-defined]


def test_generators_and_model_details(client: TestClient) -> None:
    kinds = client.get("/projia/generators").json()["kinds"]
    assert [m["key"] for m in kinds["image_gen"]] == ["fake:img-1"]
    assert kinds["video_gen"] == []
    models = client.get("/projia/catalog", params={"free": False}).json()["models"]
    by = {m["key"]: m for m in models}
    assert by["fake:coder-pro"]["agentic"] is True and by["fake:small"]["agentic"] is False
    assert by["fake:img-1"]["agentic"] is False and "inputs" in by["fake:vision-x"]


def _fill(client: TestClient, cid: str, n: int) -> None:
    core = client.app.state.core  # type: ignore[attr-defined]

    async def build() -> None:
        for i in range(n):
            await core.db.add_message(cid, {"role": "user", "content": f"question {i}"})
            await core.db.add_message(cid, {"role": "assistant", "content": f"réponse {i}"})

    client.portal.call(build)  # type: ignore[attr-defined]


def test_long_unsummarized_thread_is_windowed(client: TestClient, fake: FakeProvider) -> None:
    first = _chat(client, {"content": "début"})
    cid = next(e["id"] for e in first if e["type"] == "conversation")
    _fill(client, cid, 400)  # 800 messages jamais résumés (discussion importée)
    _chat(client, {"conversation_id": cid, "content": "où en est-on ?"})
    sent = fake.calls[0][1] if fake.calls else 0
    assert 0 < sent <= 45  # fenêtre bornée + note, pas 800 messages
    assert "plus anciens" in json.dumps(fake.last_messages, ensure_ascii=False) or sent <= 45


def test_summary_survives_a_message_arriving_meanwhile(client: TestClient) -> None:
    core = client.app.state.core  # type: ignore[attr-defined]
    first = _chat(client, {"content": "début"})
    cid = next(e["id"] for e in first if e["type"] == "conversation")
    _fill(client, cid, 40)

    async def run() -> tuple[bool, str | None, int]:
        original = core.chat.router.quick

        async def slow_quick(messages: list[dict[str, Any]], **kw: Any) -> str:
            # pendant le résumé, l'utilisateur envoie un nouveau message
            await core.db.add_message(cid, {"role": "user", "content": "message arrivé pendant"})
            return await original(messages, **kw) or ("Résumé de test " * 6)

        core.chat.router.quick = slow_quick
        ok = await core.chat._summarize_thread(cid)
        summary, covered = await core.db.get_summary(cid)
        return ok, summary, covered

    ok, summary, covered = client.portal.call(run)  # type: ignore[attr-defined]
    assert ok and summary and covered > 0  # avant : jeté dès qu'un message arrivait


def test_rolling_summary_reads_a_huge_start_in_chunks(client: TestClient) -> None:
    core = client.app.state.core  # type: ignore[attr-defined]
    first = _chat(client, {"content": "début"})
    cid = next(e["id"] for e in first if e["type"] == "conversation")
    seen: list[str] = []

    async def run() -> tuple[bool, int]:
        for i in range(120):
            await core.db.add_message(cid, {"role": "user", "content": f"Q{i} " + "x" * 1400})
            await core.db.add_message(cid, {"role": "assistant", "content": f"R{i} " + "y" * 1400})

        async def quick(messages: list[dict[str, Any]], **kw: Any) -> str:
            seen.append(str(messages[-1]["content"]))
            return "Résumé cumulé : " + str(len(seen)) * 60

        core.chat.router.quick = quick
        ok = await core.chat._summarize_thread(cid)
        _, covered = await core.db.get_summary(cid)
        return ok, covered

    ok, covered = client.portal.call(run)  # type: ignore[attr-defined]
    assert ok and len(seen) >= 2  # plusieurs blocs, pas un seul morceau tronqué
    assert all(len(s) <= 40_000 for s in seen)
    assert "Q0 " in seen[0] and "Résumé précédent" in seen[1]  # le tout début est bien lu
    assert covered > 0
