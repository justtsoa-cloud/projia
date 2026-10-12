"""Notes 👍 / 👎 : récompense ou pénalité bornée du modèle, réponse 👎 jamais réutilisée,
« autre modèle », notes collectives filtrées."""

from __future__ import annotations

from typing import Any

from tontolo.agent.loop import ChatService
from tontolo.config import Settings
from tontolo.providers.fake import FakeProvider
from tontolo.router.engine import Router
from tontolo.storage.db import Database


async def _ask(chat: ChatService, text: str) -> list[dict[str, Any]]:
    return [ev async for ev in chat.send(None, text, use_tools=False)]


def _done(events: list[dict[str, Any]]) -> dict[str, Any]:
    return next(e for e in events if e["type"] == "done")


async def test_rating_rewards_or_penalizes_within_bounds(
        settings: Settings, db: Database, router: Router) -> None:
    settings.task_planning = False
    chat = ChatService(settings, db, router)
    done = _done(await _ask(chat, "Qu'est-ce qu'un nombre premier ?"))
    model = done["model"]
    out = await chat.rate(done["uid"], -1, "inexact")
    assert out == {"model": model, "category": out["category"], "rating": -1}
    bad = router.reliability.feedback(model, out["category"])
    assert -0.18 <= bad < 0
    await chat.rate(done["uid"], 1)  # changer d'avis remplace la note
    assert router.reliability.feedback(model, out["category"]) > 0
    await chat.rate(done["uid"], 0)  # annuler
    assert router.reliability.feedback(model, out["category"]) == 0
    for _ in range(50):  # même beaucoup de 👎 restent bornés
        d = _done(await _ask(chat, "Combien de côtés a un hexagone ?"))
        await chat.rate(d["uid"], -1)
    assert router.reliability.feedback(d["model"], "chat") >= -0.18
    decision = await router.decide([{"role": "user", "content": "Bonjour"}])
    assert "feedback" in decision.chain[0].reason(decision.profile.category)


async def test_thumbs_down_answer_is_never_reused(
        settings: Settings, db: Database, router: Router) -> None:
    settings.task_planning = False
    chat = ChatService(settings, db, router)
    first = _done(await _ask(chat, "Qu'est-ce que la photosynthèse ?"))
    again = await _ask(chat, "Qu'est-ce que la photosynthèse ?")
    assert any(e["type"] == "cached" for e in again)
    await chat.rate(_done(again)["uid"], -1, "inexact")  # 👎 sur la réponse réutilisée
    third = await _ask(chat, "Qu'est-ce que la photosynthèse ?")
    assert not any(e["type"] == "cached" for e in third)
    assert first["uid"] != _done(third)["uid"]


async def test_retry_with_another_model(settings: Settings, db: Database, router: Router,
                                        fake: FakeProvider) -> None:
    settings.task_planning = False
    chat = ChatService(settings, db, router)
    events = await _ask(chat, "Raconte une blague courte")
    cid = next(e["id"] for e in events if e["type"] == "conversation")
    model = _done(events)["model"]
    again = [ev async for ev in chat.regenerate(cid, avoid=frozenset({model}))]
    assert _done(again)["model"] != model


def test_global_scores_need_enough_devices(router: Router) -> None:
    kept = router.set_global_scores([
        {"model": "fake:chatty", "category": "chat", "score": -0.8, "devices": 12},
        {"model": "fake:small", "category": "chat", "score": 0.9, "devices": 2},   # trop peu
        {"model": "fake:x", "category": "chat", "score": 7, "devices": 50},       # hors bornes
        {"oops": 1}, "texte",
    ])
    assert kept == 1
    assert router.reliability.feedback("fake:chatty", "chat") < 0
    assert router.reliability.feedback("fake:small", "chat") == 0
