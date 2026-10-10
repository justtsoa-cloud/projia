"""Tours détachés : la génération continue quand le client part."""

from __future__ import annotations

import asyncio
from typing import Any

from tontolo.agent.turns import TurnManager


async def slow_events(n: int = 5, delay: float = 0.02) -> Any:
    for i in range(n):
        await asyncio.sleep(delay)
        yield {"type": "delta", "content": str(i)}
    yield {"type": "done"}


async def test_follower_leaving_does_not_cancel() -> None:
    mgr = TurnManager()
    turn = mgr.start("c1", slow_events())
    seen = []
    async for ev in turn.follow():
        seen.append(ev)
        if len(seen) == 2:
            break                      # le client quitte l'écran en pleine génération
    assert not turn.done
    await turn.task  # type: ignore[misc]
    assert turn.done and turn.events[-1]["type"] == "done"
    # Un nouveau client se rattache : rejeu complet depuis le début.
    replay = [ev async for ev in turn.follow()]
    assert [e["type"] for e in replay] == ["delta"] * 5 + ["done"]


async def test_attach_while_running_gets_replay_then_live() -> None:
    mgr = TurnManager()
    mgr.start("c1", slow_events(6, 0.03))
    await asyncio.sleep(0.07)
    got = [ev async for ev in mgr.get("c1").follow()]  # type: ignore[union-attr]
    assert len(got) == 7 and got[0]["content"] == "0"


async def test_single_active_turn_and_stop() -> None:
    mgr = TurnManager()
    first = mgr.start("c1", slow_events(50, 0.05))
    assert mgr.start("c1", slow_events()) is first          # pas de second tour parallèle
    assert await mgr.stop("c1") is True
    assert first.done and first.events[-1]["type"] == "stopped"
    assert await mgr.stop("c1") is False


async def test_error_inside_turn_is_reported() -> None:
    async def boom() -> Any:
        yield {"type": "delta", "content": "a"}
        raise RuntimeError("panne")

    mgr = TurnManager()
    turn = mgr.start("c1", boom())
    events = [ev async for ev in turn.follow()]
    assert events[-1]["type"] == "error" and "RuntimeError" in events[-1]["message"]
