"""Un modèle muet, interrompu ou qui plante ne fait jamais perdre la réponse : bascule."""

from __future__ import annotations

import pytest

from tontolo.providers.fake import FakeProvider
from tontolo.router import engine
from tontolo.router.engine import Router


async def _run(router: Router, text: str = "bonjour") -> list[dict]:
    return [ev async for ev in router.run([{"role": "user", "content": text}])]


async def test_unexpected_exception_falls_back(router: Router, fake: FakeProvider) -> None:
    for mid in ("coder-pro", "chatty", "vision-x"):
        fake.crash[mid] = KeyError("choices")  # JSON inattendu d'un fournisseur
    events = await _run(router)
    done = [e for e in events if e["type"] == "done"]
    assert done and done[0]["model"] not in ("fake:coder-pro", "fake:chatty", "fake:vision-x")
    assert any(e["type"] == "model_switched" for e in events)


async def test_silent_model_times_out_then_falls_back(router: Router, fake: FakeProvider,
                                                      monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(engine, "FIRST_TOKEN_TIMEOUT", 0.2)
    for mid in ("coder-pro", "chatty"):
        fake.hang.add(mid)
    events = await _run(router)
    assert any(e["type"] == "done" for e in events)
    assert any(e["type"] == "model_switched" for e in events)  # le muet a été abandonné


async def test_stalled_stream_is_reset_and_replaced(router: Router, fake: FakeProvider,
                                                    monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(engine, "STALL_TIMEOUT", 0.2)
    for mid in ("coder-pro", "chatty", "vision-x"):
        fake.stall_mid.add(mid)
    events = await _run(router)
    kinds = [e["type"] for e in events]
    assert "stream_reset" in kinds and kinds[-1] == "done"
    text = "".join(str(e.get("content") or "") for e in events if e["type"] == "delta")
    assert events[-1]["message"]["content"]  # une réponse complète est livrée
    assert text  # des mots ont été diffusés


async def test_everything_hangs_ends_with_an_error_not_a_hang(
        router: Router, fake: FakeProvider, monkeypatch: pytest.MonkeyPatch) -> None:
    import asyncio

    monkeypatch.setattr(engine, "FIRST_TOKEN_TIMEOUT", 0.05)
    monkeypatch.setattr(engine, "MAX_ATTEMPTS", 3)
    monkeypatch.setattr(engine, "SHORT_WAIT", 0.05)
    fake.hang.update({"coder-pro", "chatty", "small", "vision-x", "paid-genius"})
    events = await asyncio.wait_for(_run(router), 20)
    assert events[-1]["type"] == "error"


async def test_time_wasted_on_silent_models_is_capped(
        router: Router, fake: FakeProvider, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(engine, "FIRST_TOKEN_TIMEOUT", 0.15)
    monkeypatch.setattr(engine, "MAX_WASTED", 0.3)
    monkeypatch.setattr(engine, "SHORT_WAIT", 0.05)
    fake.hang.update({"coder-pro", "chatty", "small", "vision-x", "paid-genius"})
    events = await _run(router)
    assert events[-1]["type"] == "error"
    switched = [e for e in events if e["type"] == "model_switched"]
    assert len(switched) <= 3  # 0,15 s par essai : arrêt après ~0,3 s perdue, pas 8 essais
