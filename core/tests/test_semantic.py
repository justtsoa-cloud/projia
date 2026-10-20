"""Mémoire sémantique unifiée : souvenirs et réponses déjà données dans un même index local."""

from __future__ import annotations

from typing import Any

from projia import semantic
from projia.agent.loop import ChatService
from projia.config import Settings
from projia.providers.fake import FakeProvider
from projia.router.engine import Router
from projia.storage.db import Database


def test_similarity_across_wording_and_accents() -> None:
    q = "Qu'est-ce que la photosynthèse ?"
    assert semantic.similarity(q, "explique-moi la photosynthese") > semantic.REUSE
    assert semantic.similarity(q, "Explique la relativité") < 0.3
    assert semantic.similarity("What is photosynthesis?", q) > semantic.RELATED  # voisine


def test_only_timeless_impersonal_standalone_questions_are_reused() -> None:
    ok = ["Qu'est-ce que la photosynthèse ?", "Capitale de Madagascar ?",
          "Inona no renivohitr'i Madagasikara?", "Explain photosynthesis"]
    no = ["Quel temps fait-il aujourd'hui ?", "Et pour le Japon, c'est pareil ?",
          "Corrige mon CV", "Quelles sont les dernières nouvelles ?", "Can I learn Python fast?",
          "Explique-le encore", "ok"]
    assert all(semantic.reusable_question(t) for t in ok)
    assert not any(semantic.reusable_question(t) for t in no)
    assert not semantic.same_numbers("Combien font 2 + 3 ?", "Combien font 2 + 4 ?")
    assert not semantic.same_wording("Explain photosynthesis", "Explique la photosynthèse")


async def _send(chat: ChatService, text: str, cid: str | None = None) -> list[dict[str, Any]]:
    return [ev async for ev in chat.send(cid, text, use_tools=False)]


async def test_same_question_is_answered_from_the_cache(
        settings: Settings, db: Database, router: Router, fake: FakeProvider) -> None:
    settings.task_planning = False
    chat = ChatService(settings, db, router)
    first = await _send(chat, "Qu'est-ce que la photosynthèse ?")
    assert not any(e["type"] == "cached" for e in first)
    calls = len(fake.calls)
    again = await _send(chat, "Explique-moi la photosynthese")
    assert any(e["type"] == "cached" for e in again)
    done = next(e for e in again if e["type"] == "done")
    assert done["cached"] and done["message"]["content"] == next(
        e for e in first if e["type"] == "done")["message"]["content"]
    assert len(fake.calls) == calls  # aucun appel de modèle
    cid = next(e["id"] for e in again if e["type"] == "conversation")
    # Régénérer ne passe jamais par le cache, et l'oublie pour cette discussion.
    regen = [ev async for ev in chat.regenerate(cid)]
    assert not any(e["type"] == "cached" for e in regen) and len(fake.calls) > calls


async def test_never_cached_for_time_numbers_or_settings(
        settings: Settings, db: Database, router: Router, fake: FakeProvider) -> None:
    settings.task_planning = False
    chat = ChatService(settings, db, router)
    await _send(chat, "Quel temps fait-il aujourd'hui à Tana ?")
    assert not any(e["type"] == "cached"
                   for e in await _send(chat, "Quel temps fait-il aujourd'hui à Tana ?"))
    await _send(chat, "Combien font 12 fois 7 ?")
    assert not any(e["type"] == "cached" for e in await _send(chat, "Combien font 12 fois 8 ?"))
    settings.answer_cache = False
    await _send(chat, "Définis la photosynthèse")
    assert not any(e["type"] == "cached" for e in await _send(chat, "Définis la photosynthèse"))


async def test_close_question_gets_the_old_answer_as_context(
        settings: Settings, db: Database, router: Router, fake: FakeProvider) -> None:
    settings.task_planning = False
    chat = ChatService(settings, db, router)
    await _send(chat, "Explique le cycle de l'eau pour des enfants de dix ans")
    events = await _send(chat, "Explique le cycle de l'eau simplement aux enfants")
    assert not any(e["type"] == "cached" for e in events)  # voisine, pas identique
    system = " ".join(str(m.get("content")) for m in fake.last_messages
                      if m.get("role") == "system")
    assert "Réponse déjà donnée" in system


async def test_deleting_a_conversation_forgets_its_answers(
        settings: Settings, db: Database, router: Router) -> None:
    settings.task_planning = False
    chat = ChatService(settings, db, router)
    first = await _send(chat, "Qu'est-ce qu'un nombre premier ?")
    cid = next(e["id"] for e in first if e["type"] == "conversation")
    assert await db.count_answers() == 1
    await db.delete_conversation(cid)
    chat.answers.invalidate()
    assert await db.count_answers() == 0
    assert not any(e["type"] == "cached"
                   for e in await _send(chat, "Qu'est-ce qu'un nombre premier ?"))


async def test_memory_recall_by_meaning_not_only_identical_words(
        db: Database, settings: Settings) -> None:
    from projia.memory import MemoryService

    mem = MemoryService(settings, db)
    await mem.remember("L'utilisateur enseigne les mathématiques", kind="explicit")
    await mem.remember("L'utilisateur aime le football", kind="explicit")
    got = [m["text"] for m in await mem.recall("prépare un cours de mathematique")]
    assert got and "mathématiques" in got[0]  # accent et pluriel différents
    assert not any("football" in t for t in got)

