"""Hors ligne : on attend le retour de la connexion au lieu de défiler tous les modèles."""

from __future__ import annotations

from typing import Any

import pytest

from tontolo.agent.loop import ChatService
from tontolo.config import Settings
from tontolo.providers.base import ErrorKind, ProviderError
from tontolo.providers.fake import FakeProvider
from tontolo.router import engine
from tontolo.router.engine import Router
from tontolo.storage.db import Database


def net() -> ProviderError:
    return ProviderError("ConnectError", ErrorKind.NETWORK)


async def collect(gen: Any) -> list[dict[str, Any]]:
    return [ev async for ev in gen]


@pytest.fixture(autouse=True)
def fast(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(engine, "OFFLINE_STEP", 0.005)
    monkeypatch.setattr(engine, "OFFLINE_WAIT", 0.01)


async def test_offline_never_switches_models(
    router: Router, fake: FakeProvider, db: Database, settings: Settings
) -> None:
    async def down() -> bool:
        return False

    router.probe = down
    fake.fail("chatty", *[net()] * 5)
    chat = ChatService(settings, db, router)
    events = await collect(chat.send(None, "Bonjour", use_tools=False))
    assert not [e for e in events if e["type"] == "model_switched"]
    err = next(e for e in events if e["type"] == "error")
    assert err["offline"] and "connexion" in err["message"]
    assert len(fake.calls) == 1 and not router.quota.snapshot()  # aucun modèle pénalisé


async def test_connection_back_retries_same_model(
    router: Router, fake: FakeProvider, db: Database, settings: Settings
) -> None:
    state = {"up": False}

    async def probe() -> bool:
        ok = state["up"]
        state["up"] = True  # la connexion revient après le premier test
        return ok

    router.probe = probe
    fake.fail("chatty", net())
    chat = ChatService(settings, db, router)
    events = await collect(chat.send(None, "Bonjour", use_tools=False))
    assert any(e["type"] == "offline" for e in events)
    assert not [e for e in events if e["type"] == "model_switched"]
    assert next(e for e in events if e["type"] == "done")["model"] == "fake:chatty"


async def test_network_error_online_still_switches(
    router: Router, fake: FakeProvider, db: Database, settings: Settings
) -> None:
    fake.fail("chatty", net())
    chat = ChatService(settings, db, router)
    events = await collect(chat.send(None, "Bonjour", use_tools=False))
    assert [e for e in events if e["type"] == "model_switched"]
    assert next(e for e in events if e["type"] == "done")["model"] != "fake:chatty"
