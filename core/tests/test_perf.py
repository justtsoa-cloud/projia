"""Garde-fou de performance (joué en CI) : versions réduites des bancs de bench/, seuils
LARGES (machines de CI variables) pour attraper une régression nette, pas une fluctuation."""

from __future__ import annotations

import asyncio
import time

from bench.harness import core, drain
from tontolo.providers.base import ErrorKind, ProviderError


async def test_concurrent_turns_stay_fast_and_consistent() -> None:
    async with core() as (c, fake, _home):
        for mid in ("coder-pro", "chatty"):
            for _ in range(5):
                fake.fail(mid, ProviderError("quota", ErrorKind.RATE_LIMIT, status=429,
                                             retry_after=1))
        users, turns = 30, 3
        cids = [await c.db.create_conversation(f"P{i}") for i in range(users)]
        started = time.perf_counter()

        async def user(i: int) -> None:
            for k in range(turns):
                evs = await drain(c.chat.send(cids[i], f"Question {k}"))
                assert any(e["type"] == "done" for e in evs), evs[-3:]

        await asyncio.gather(*[user(i) for i in range(users)])
        elapsed = time.perf_counter() - started
        assert elapsed < 20, f"{users * turns} tours en {elapsed:.1f} s"
        for cid in cids:
            roles = [m["role"] for m in await c.db.get_messages(cid)]
            assert roles == ["user", "assistant"] * turns


async def test_turn_on_a_long_thread_stays_fast() -> None:
    async with core() as (c, _fake, _home):
        cid = await c.db.create_conversation("Long fil")
        for i in range(1500):
            await c.db.add_message(cid, {"role": "user" if i % 2 == 0 else "assistant",
                                         "content": f"message numéro {i} " * 20})
        started = time.perf_counter()
        evs = await drain(c.chat.send(cid, "Et maintenant ?"))
        elapsed = time.perf_counter() - started
        assert any(e["type"] == "done" for e in evs)
        assert elapsed < 5, f"un tour sur 1500 messages en {elapsed:.2f} s"
        started = time.perf_counter()
        window = await c.db.get_window(cid, 120)
        assert len(window) <= 120 and time.perf_counter() - started < 0.5
