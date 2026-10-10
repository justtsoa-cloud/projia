"""Phase 4 : quotas, bascule sans perte d'historique, retour au meilleur modèle."""

from __future__ import annotations

import time
from typing import Any

import pytest

from tontolo.agent.loop import ChatService
from tontolo.config import PaidFallback, Settings
from tontolo.providers.base import ErrorKind, ProviderError, Scope
from tontolo.providers.fake import FakeProvider
from tontolo.router.engine import Router
from tontolo.router.quota import QuotaManager, next_utc_midnight
from tontolo.storage.db import Database


def r429(retry: float | None = 60, msg: str = "Rate limit exceeded") -> ProviderError:
    return ProviderError(msg, ErrorKind.RATE_LIMIT, status=429, retry_after=retry)


async def collect(gen: Any) -> list[dict[str, Any]]:
    return [ev async for ev in gen]


async def test_switch_on_429_keeps_history(
    router: Router, fake: FakeProvider, db: Database, settings: Settings
) -> None:
    chat = ChatService(settings, db, router)
    events = await collect(chat.send(None, "Bonjour", use_tools=False))
    cid = next(e["id"] for e in events if e["type"] == "conversation")
    assert next(e for e in events if e["type"] == "done")["model"] == "fake:chatty"

    fake.fail("chatty", r429(retry=120))
    events = await collect(chat.send(cid, "Et ensuite ?", use_tools=False))
    switched = [e for e in events if e["type"] == "model_switched"]
    assert switched and switched[0]["from"] == "fake:chatty"
    assert switched[0]["reason"] == "limite de débit atteinte"
    done = next(e for e in events if e["type"] == "done")
    assert done["model"] != "fake:chatty"

    history = await db.get_messages(cid)
    assert [m["role"] for m in history] == ["user", "assistant", "user", "assistant"]
    assert history[1]["_meta"]["model"] == "fake:chatty"
    assert history[3]["_meta"]["model"] == done["model"]
    # Le modèle de secours a bien reçu tout l'historique (system + 3 messages).
    assert fake.calls[-1][1] == 4


async def test_return_to_best_after_cooldown(
    router: Router, fake: FakeProvider, db: Database, settings: Settings
) -> None:
    chat = ChatService(settings, db, router)
    fake.fail("chatty", r429(retry=1))
    events = await collect(chat.send(None, "Bonjour", use_tools=False))
    cid = next(e["id"] for e in events if e["type"] == "conversation")
    assert next(e for e in events if e["type"] == "done")["model"] != "fake:chatty"

    # Pendant le refroidissement : pas de requête de test vers chatty.
    calls_before = [c for c in fake.calls if c[0] == "chatty"]
    events = await collect(chat.send(cid, "Encore", use_tools=False))
    assert [c for c in fake.calls if c[0] == "chatty"] == calls_before

    # Refroidissement terminé : retour automatique au meilleur modèle.
    for st in router.quota.states.values():
        st.until = time.time() - 1
    events = await collect(chat.send(cid, "Et maintenant ?", use_tools=False))
    assert any(e["type"] == "model_returned" for e in events)
    assert next(e for e in events if e["type"] == "done")["model"] == "fake:chatty"


async def test_return_to_preferred_not_top(
    router: Router, fake: FakeProvider, db: Database, settings: Settings
) -> None:
    await db.set_preference("global", "", "fake:vision-x")
    chat = ChatService(settings, db, router)
    fake.fail("vision-x", r429(retry=1))
    events = await collect(chat.send(None, "Bonjour", use_tools=False))
    cid = next(e["id"] for e in events if e["type"] == "conversation")
    assert next(e for e in events if e["type"] == "done")["model"] == "fake:chatty"
    for st in router.quota.states.values():
        st.until = time.time() - 1
    events = await collect(chat.send(cid, "Re", use_tools=False))
    assert next(e for e in events if e["type"] == "done")["model"] == "fake:vision-x"


async def test_strict_preference_waits(
    router: Router, fake: FakeProvider, db: Database, settings: Settings
) -> None:
    await db.set_preference("global", "", "fake:vision-x", strict=True)
    router.quota.on_error(router.catalog.catalog.models["fake:vision-x"], r429(retry=300))
    events = await collect(router.run([{"role": "user", "content": "Salut"}]))
    assert events[-1]["type"] == "error" and "strict" in events[-1]["message"]
    assert events[-1]["retry_at"] is not None


async def test_switch_mid_stream_restarts(router: Router, fake: FakeProvider) -> None:
    fake.fail_mid_stream.add("chatty")
    events = await collect(router.run([{"role": "user", "content": "Bonjour"}]))
    types = [e["type"] for e in events]
    assert "stream_reset" in types and "model_switched" in types
    done = events[-1]
    assert done["type"] == "done" and "parti" not in done["message"]["content"]


async def test_all_exhausted_gives_human_error(router: Router, fake: FakeProvider) -> None:
    for mid in ("chatty", "coder-pro", "small", "vision-x"):
        fake.fail(mid, r429(retry=600))
    events = await collect(router.run([{"role": "user", "content": "Bonjour"}]))
    assert events[-1]["type"] == "error"
    assert "Retour estimé" in events[-1]["message"]


async def test_daily_quota_until_midnight() -> None:
    from tests.conftest import make_models

    q = QuotaManager()
    m = make_models()[0]
    now = time.time()
    until = q.on_error(m, ProviderError("free-models-per-day limit", ErrorKind.QUOTA,
                                        status=429, scope=Scope.FREE_POOL), now)
    assert until == pytest.approx(next_utc_midnight(now))
    # La réserve gratuite partagée bloque tous les modèles gratuits du fournisseur.
    assert not q.available(make_models()[1], now)


async def test_anticipation_from_rate_limit() -> None:
    from tests.conftest import make_models

    q = QuotaManager()
    m = make_models()[0]
    m.rate_limit = "2 RPM, 100 RPD"
    now = time.time()
    q.record_request(m, now)
    assert q.available(m, now)
    q.record_request(m, now)
    assert not q.available(m, now)          # 3e requête : épuisement anticipé
    assert q.available(m, now + 61)


async def test_quota_persisted(router: Router, db: Database, settings: Settings,
                               catalog_service: Any) -> None:
    m = router.catalog.catalog.models["fake:chatty"]
    router.quota.on_error(m, r429(retry=500))
    await router.persist()
    r2 = Router(settings, catalog_service, db)
    await r2.startup()
    assert not r2.quota.available(m)


async def test_paid_ask_requires_confirmation(router: Router, fake: FakeProvider) -> None:
    router.settings.paid.fallback = PaidFallback.ASK
    router.settings.paid.daily_cap_usd = 1.0
    for mid in ("chatty", "coder-pro", "small", "vision-x"):
        fake.fail(mid, r429(retry=600))
    events = await collect(router.run([{"role": "user", "content": "Bonjour"}],
                                      conversation_id="c"))
    assert events[-1]["type"] == "paid_confirmation"
    router.approve_paid("c")
    events = await collect(router.run([{"role": "user", "content": "Bonjour"}],
                                      conversation_id="c"))
    assert events[-1]["type"] == "done" and events[-1]["model"] == "fake:paid-genius"
    assert events[-1]["cost"] > 0


async def test_paid_cap_respected(router: Router, fake: FakeProvider, db: Database) -> None:
    router.settings.paid.fallback = PaidFallback.AUTO
    router.settings.paid.daily_cap_usd = 0.001
    await db.add_spend("fake:paid-genius", 0, 0, 0.001, None)
    for mid in ("chatty", "coder-pro", "small", "vision-x"):
        fake.fail(mid, r429(retry=600))
    events = await collect(router.run([{"role": "user", "content": "Bonjour"}]))
    assert events[-1]["type"] == "error"
    assert all(c[0] != "paid-genius" for c in fake.calls)


async def test_paid_without_cap_never_called(router: Router, fake: FakeProvider) -> None:
    router.settings.paid.fallback = PaidFallback.AUTO  # plafonds à 0 : aucun appel payant
    for mid in ("chatty", "coder-pro", "small", "vision-x"):
        fake.fail(mid, r429(retry=600))
    await collect(router.run([{"role": "user", "content": "Bonjour"}]))
    assert all(c[0] != "paid-genius" for c in fake.calls)


async def test_context_adaptation_summarizes(
    router: Router, fake: FakeProvider
) -> None:
    """Bascule vers un modèle à petit contexte : anciens tours résumés."""
    msgs: list[dict[str, Any]] = []
    for i in range(30):
        msgs += [{"role": "user", "content": f"Question {i} " + "bla " * 150},
                 {"role": "assistant", "content": f"Réponse {i} " + "bla " * 150}]
    msgs.append({"role": "user", "content": "Dernière question"})
    for mid in ("chatty", "coder-pro", "vision-x"):
        fake.fail(mid, r429(retry=600))
    events = await collect(router.run(msgs, model="fake:small"))
    assert events[-1]["type"] == "done" and events[-1]["model"] == "fake:small"
    small_calls = [c for c in fake.calls if c[0] == "small"]
    assert small_calls[-1][1] < len(msgs)


async def test_short_cooldown_waits_instead_of_failing(router: Router,
                                                       fake: FakeProvider) -> None:
    """Un seul modèle disponible, coupé une seconde : on attend puis on réessaie."""
    for mid in ("coder-pro", "small", "vision-x"):
        fake.fail(mid, r429(retry=600))
    fake.fail("chatty", r429(retry=1))
    events = await collect(router.run([{"role": "user", "content": "Bonjour"}]))
    types = [e["type"] for e in events]
    assert "waiting" in types
    assert events[-1]["type"] == "done" and events[-1]["model"] == "fake:chatty"
