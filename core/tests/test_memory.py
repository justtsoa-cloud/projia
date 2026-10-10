"""Mémoire à long terme : capture, rappel, secrets refusés, compactage automatique."""

from __future__ import annotations

import json
from typing import Any

from tontolo.agent.loop import ChatService
from tontolo.config import Settings
from tontolo.memory import MemoryService, explicit_memory, similarity
from tontolo.router.engine import Router
from tontolo.storage.db import Database


def test_explicit_capture() -> None:
    assert explicit_memory("Souviens-toi que je préfère le tutoiement") == \
        "je préfère le tutoiement"
    assert explicit_memory("Remember that I teach maths") == "I teach maths"
    assert explicit_memory("Tadidio fa mpampianatra aho") == "mpampianatra aho"
    assert explicit_memory("Quel temps fait-il ?") is None


async def test_remember_merge_and_secrets(db: Database, settings: Settings) -> None:
    mem = MemoryService(settings, db)
    assert await mem.remember("L'utilisateur préfère les réponses courtes")
    assert await mem.remember("L'utilisateur préfère les réponses très courtes")  # fusion
    assert not await mem.remember("Ma clé est sk-or-v1-abcdefghijklmnop")
    assert not await mem.remember("Mon mot de passe est hunter2")
    items = await db.list_memories()
    assert len(items) == 1 and "très courtes" in items[0]["text"]


async def test_recall_relevance_and_budget(db: Database, settings: Settings) -> None:
    settings.memory_budget_chars = 80
    mem = MemoryService(settings, db)
    await mem.remember("L'utilisateur enseigne les mathématiques au lycée")
    await mem.remember("L'utilisateur habite à Antananarivo")
    await mem.remember("Le projet Tontolo utilise Flutter et Python")
    got = await mem.recall("Prépare un exercice de mathématiques")
    assert got and "mathématiques" in got[0]["text"]
    assert sum(len(m["text"]) for m in got) <= 80


async def test_auto_compaction_with_model(db: Database, settings: Settings) -> None:
    settings.memory_max_items = 10

    async def quick(messages: list[dict[str, Any]]) -> str:
        return json.dumps({"memories": ["Résumé A", "Résumé B", "Résumé C"]})

    mem = MemoryService(settings, db, quick)
    for i in range(11):
        await db.add_memory(f"souvenir numéro {i} sujet{i} différent{i * 7}")
    await mem.maybe_compact()
    assert [m["text"] for m in await db.list_memories()] == ["Résumé A", "Résumé B", "Résumé C"]


async def test_auto_compaction_without_model(db: Database, settings: Settings) -> None:
    settings.memory_max_items = 10
    mem = MemoryService(settings, db, None)
    for i in range(15):
        await db.add_memory(f"élément{i} unique{i * 13} thème{i * 31}")
    assert await mem.maybe_compact() == 5
    assert similarity("a b c chat chien", "chien chat") == 1.0


async def test_chat_uses_memory_and_instructions(router: Router, db: Database,
                                                  settings: Settings, fake: Any) -> None:
    settings.custom_instructions = "Réponds toujours en vers."
    chat = ChatService(settings, db, router)
    events = [e async for e in chat.send(None, "Souviens-toi que j'adore la géométrie",
                                         use_tools=False)]
    assert any(e["type"] == "memory_saved" for e in events)
    seen: list[list[dict[str, Any]]] = []
    fake.behaviors["chatty"] = lambda m, msgs: seen.append(msgs) or {
        "role": "assistant", "content": "ok"}
    _ = [e async for e in chat.send(None, "Parle-moi de géométrie", use_tools=False)]
    system = "\n".join(m["content"] for m in seen[-1] if m["role"] == "system")
    assert "géométrie" in system and "en vers" in system


async def test_regenerate_and_edit(router: Router, db: Database, settings: Settings) -> None:
    chat = ChatService(settings, db, router)
    events = [e async for e in chat.send(None, "Bonjour", use_tools=False)]
    cid = next(e["id"] for e in events if e["type"] == "conversation")
    _ = [e async for e in chat.regenerate(cid, model="fake:coder-pro")]
    msgs = await db.get_messages(cid)
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    assert msgs[1]["_meta"]["model"] == "fake:coder-pro"
    _ = [e async for e in chat.edit_and_resend(cid, 1, "Salut")]
    msgs = await db.get_messages(cid)
    assert msgs[0]["content"] == "Salut" and msgs[1]["content"].endswith("Salut")
