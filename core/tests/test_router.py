"""Phase 3 : classification, score, chaîne de repli, choix manuel."""

from __future__ import annotations

import time

from tontolo.catalog.models import Category
from tontolo.config import PaidFallback
from tontolo.router.classifier import classify
from tontolo.router.engine import Router
from tontolo.storage.db import Database


def user(text: str) -> list[dict[str, object]]:
    return [{"role": "user", "content": text}]


def test_classifier_categories() -> None:
    assert classify(user("Écris une fonction Python qui trie une liste"))\
        .category == Category.CODE
    assert classify(user("Résous l'équation $x^2 - 4 = 0$")).category == Category.MATH
    assert classify(user("Dessine un chat astronaute")).category == Category.IMAGE_GEN
    assert classify(user("Lis ce texte à voix haute")).category == Category.TTS
    assert classify(user("Traduis « bonjour » en anglais")).category == Category.TRANSLATION
    assert classify(user("Quelles sont les actualités d'aujourd'hui ?")).force_search
    assert classify(user("Manaova sary saka")).category == Category.IMAGE_GEN  # malgache
    assert classify(user("Salut !")).category == Category.CHAT


def test_classifier_attachments() -> None:
    msg = [{"role": "user", "content": [
        {"type": "text", "text": "Que vois-tu ?"},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAA"}}]}]
    prof = classify(msg)
    assert prof.category == Category.VISION and prof.needs_vision
    edit = [{"role": "user", "content": [
        {"type": "text", "text": "Enlève le fond de cette image"},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAA"}}]}]
    assert classify(edit).category == Category.IMAGE_EDIT


async def test_code_prompt_picks_code_model(router: Router) -> None:
    d = await router.decide(user("Corrige ce bug dans ma fonction JavaScript"))
    assert d.profile.category == Category.CODE
    assert d.best is not None and d.best.model.model_id == "coder-pro"


async def test_chat_prompt_picks_chat_model(router: Router) -> None:
    d = await router.decide(user("Bonjour, comment vas-tu ?"))
    assert d.best is not None and d.best.model.model_id == "chatty"


async def test_free_before_paid(router: Router) -> None:
    router.settings.paid.fallback = PaidFallback.AUTO
    d = await router.decide(user("Écris un script bash"))
    keys = [c.model.model_id for c in d.chain]
    assert "paid-genius" in keys and keys[-1] == "paid-genius"


async def test_paid_excluded_by_default(router: Router) -> None:
    d = await router.decide(user("Écris un script bash"))
    assert all(c.model.is_free for c in d.chain)


async def test_preferred_model_goes_first(router: Router, db: Database) -> None:
    await db.set_preference("global", "", "fake:small")
    d = await router.decide(user("Écris une fonction Rust"))
    assert d.chain[0].model.model_id == "small" and d.chain[0].preferred
    assert d.chain[1].model.model_id == "coder-pro"  # chaîne automatique derrière


async def test_preference_scopes(router: Router, db: Database) -> None:
    await db.set_preference("global", "", "fake:chatty")
    await db.set_preference("category", "code", "fake:coder-pro")
    await db.set_preference("conversation", "c1", "fake:vision-x")
    d = await router.decide(user("Écris du code Python"), conversation_id="c1")
    assert d.chain[0].model.model_id == "vision-x"
    d = await router.decide(user("Écris du code Python"), conversation_id="c2")
    assert d.chain[0].model.model_id == "coder-pro"
    d = await router.decide(user("Bonjour"), conversation_id="c2")
    assert d.chain[0].model.model_id == "chatty"


async def test_request_model_override(router: Router) -> None:
    d = await router.decide(user("Bonjour"), model="fake:coder-pro")
    assert d.chain[0].model.model_id == "coder-pro"
    d = await router.decide(user("Bonjour"), model="auto")
    assert d.chain[0].model.model_id == "chatty"


async def test_context_filter(router: Router) -> None:
    long_text = "mot " * 20000
    d = await router.decide(user(long_text))
    assert "small" not in [c.model.model_id for c in d.chain]


async def test_chat_engine_never_routes_to_media_models(router: Router) -> None:
    d = await router.decide(user("Génère une image d'un phare au coucher du soleil"))
    assert d.profile.category == Category.CHAT
    assert "img-1" not in [c.model.model_id for c in d.chain]


async def test_selection_is_fast(router: Router) -> None:
    """Budget section 11 : sélection du modèle < 20 ms (scores en mémoire)."""
    msgs = user("Écris une fonction Python")
    await router.decide(msgs)
    t = time.perf_counter()
    for _ in range(20):
        await router.decide(msgs)
    assert (time.perf_counter() - t) / 20 < 0.02


async def test_first_launch_quick_catalog(settings, monkeypatch) -> None:
    """Premier lancement sans cache : les classements lents ne bloquent pas le démarrage."""
    import asyncio

    from tontolo.catalog import service as svc_mod
    from tontolo.catalog.models import ModelInfo

    slow_called = asyncio.Event()

    async def fast(cache: object, *a: object, **k: object) -> list[ModelInfo]:
        if getattr(cache, "offline", False):
            return []
        return [ModelInfo(provider="pollinations", model_id="m", is_free=True, needs_key=False)]

    async def free(*a: object, **k: object) -> tuple[list[ModelInfo], dict[str, object]]:
        return [], {}

    async def slow(cache: object, *a: object, **k: object) -> list[object]:
        if getattr(cache, "offline", False):
            return []
        slow_called.set()
        await asyncio.sleep(3600)
        return []

    monkeypatch.setattr(svc_mod.openrouter, "fetch_models", fast)
    monkeypatch.setattr(svc_mod.pollinations, "fetch_models", fast)
    monkeypatch.setattr(svc_mod.freeapis, "fetch", free)
    monkeypatch.setattr(svc_mod.rankings, "fetch_lmarena", slow)
    monkeypatch.setattr(svc_mod.rankings, "fetch_artificial_analysis", slow)
    s = svc_mod.CatalogService(settings)
    await asyncio.wait_for(s.load(), timeout=2)
    assert s.catalog.models
    assert s._task is not None
    s._task.cancel()




def test_short_followup_keeps_discussion_topic() -> None:
    msgs = [{"role": "user", "content": "Écris une fonction Python qui trie une liste"},
            {"role": "assistant", "content": "```python\ndef tri(l):\n    return sorted(l)\n```"},
            {"role": "user", "content": "et en plus rapide ?"}]
    assert classify(msgs).category == Category.CODE
    maths = [{"role": "user", "content": "Résous l'équation $x^2 - 4 = 0$"},
             {"role": "assistant", "content": "$x = \\pm 2$"},
             {"role": "user", "content": "pourquoi ?"}]
    assert classify(maths).category == Category.MATH
    # Un nouveau sujet explicite l'emporte sur le contexte.
    new = [*msgs, {"role": "assistant", "content": "..."},
           {"role": "user", "content": "Traduis en anglais : bonjour tout le monde"}]
    assert classify(new).category == Category.TRANSLATION
    assert classify([{"role": "user", "content": "salut"}]).category == Category.CHAT
