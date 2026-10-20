"""Course couverte : le premier qui parle gagne, le suivant n'est lancé que si besoin."""

from __future__ import annotations

import asyncio

import pytest

from projia.router.hedge import race_streams


def source(name: str, delay: float, n: int = 3, fail: bool = False, log: list | None = None):
    async def gen():
        try:
            await asyncio.sleep(delay)
            if fail:
                raise RuntimeError(f"{name} en panne")
            for i in range(n):
                yield {"from": name, "i": i}
        except asyncio.CancelledError:
            if log is not None:
                log.append(f"{name} annulé")
            raise
    return gen


async def collect(factories, hedge_after, failures=None):
    out = []
    async for idx, item in race_streams(factories, hedge_after,
                                        (lambda i, e: failures.append(i)) if failures is not None
                                        else None):
        out.append((idx, item["from"], item["i"]))
    return out


async def test_fast_primary_never_starts_the_backup() -> None:
    log: list[str] = []
    out = await collect([source("A", 0.01), source("B", 0.0, log=log)], hedge_after=1.0)
    assert [o[1] for o in out] == ["A", "A", "A"] and log == []


async def test_slow_primary_is_hedged_and_loser_cancelled() -> None:
    log: list[str] = []
    out = await collect([source("A", 2.0, log=log), source("B", 0.01)], hedge_after=0.1)
    assert {o[1] for o in out} == {"B"} and [o[0] for o in out] == [1, 1, 1]
    assert log == ["A annulé"]


async def test_primary_can_still_win_after_the_hedge() -> None:
    out = await collect([source("A", 0.25), source("B", 1.0)], hedge_after=0.1)
    assert {o[1] for o in out} == {"A"}


async def test_failure_starts_the_backup_at_once_and_is_reported() -> None:
    failures: list[int] = []
    out = await collect([source("A", 0.0, fail=True), source("B", 0.0)], hedge_after=5.0,
                        failures=failures)
    assert {o[1] for o in out} == {"B"} and failures == [0]


async def test_all_sources_failing_raises_the_primary_error() -> None:
    with pytest.raises(RuntimeError, match="A en panne"):
        await collect([source("A", 0.0, fail=True), source("B", 0.0, fail=True)], 0.05)
