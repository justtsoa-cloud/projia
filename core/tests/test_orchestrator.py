"""Orchestration multi-modèles optionnelle : découpage, synthèse, flux parallèle puis
dépendant, modèles gratuits seulement, rien de changé par défaut."""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tontolo.catalog.models import Category
from tontolo.catalog.service import CatalogService
from tontolo.config import Settings
from tontolo.orchestrator import HierarchicalPipeline, PartResult, ResponseSynthesizer
from tontolo.orchestrator.decomposer import TaskDecomposer
from tontolo.providers.fake import FakeProvider
from tontolo.providers.registry import ProviderRegistry
from tontolo.router.engine import Router
from tontolo.server.app import create_app


@pytest.fixture
def client(settings: Settings, catalog_service: CatalogService, fake: FakeProvider,
           monkeypatch: pytest.MonkeyPatch) -> Any:
    async def fake_load(self: CatalogService) -> Any:
        self.catalog = catalog_service.catalog
        return self.catalog

    monkeypatch.setattr(CatalogService, "load", fake_load)
    app = create_app(settings, registry=ProviderRegistry(lambda p: fake), refresh=False)
    with TestClient(app, base_url="http://127.0.0.1") as c:
        yield c


@pytest.mark.parametrize(("text", "expected"), [
    ("Bonjour, comment ça va ?", [("chat", False)]),
    ("Écris une fonction Python qui trie une liste et explique-la",
     [("code", False), ("chat", True)]),
    ("Écris un code Python pour fibonacci ; explique la complexité du tri rapide ; traduis "
     "bonjour en anglais", [("code", False), ("chat", False), ("translation", False)]),
    ("1. Calcule 12 * 7\n2. Écris un haïku sur la mer\n3. Donne la capitale du Japon",
     [("math", False), ("writing", False), ("chat", False)]),
    ("Write a Python script that parses CSV then summarize it",
     [("code", False), ("writing", True)]),
])
def test_regex_decomposition(text: str, expected: list[tuple[str, bool]]) -> None:
    plan = asyncio.run(TaskDecomposer().decompose(text))
    assert [(s.category.value, s.depends) for s in plan.subtasks] == expected
    assert plan.complexity == ("low" if len(expected) == 1 else "medium")


def test_decomposition_is_fast_and_bounded() -> None:
    d = TaskDecomposer()
    started = time.perf_counter()
    for _ in range(200):
        asyncio.run(d.decompose("Écris un code Python ; explique-le ; teste-le ; traduis-le"))
    assert (time.perf_counter() - started) / 200 < 0.05  # bien sous les 500 ms demandées
    many = " ; ".join(f"écris le point {i}" for i in range(20))
    assert len(asyncio.run(d.decompose(many)).subtasks) == 6


def test_local_model_proposes_a_split_only_for_long_unsplit_requests() -> None:
    async def local(text: str) -> str:
        return '{"subtasks": ["Analyse le marché", "Rédige le plan"]}'

    long = "Prépare une étude complète pour ma coopérative de vanille " * 10
    plan = asyncio.run(TaskDecomposer(local).decompose(long))
    assert plan.source == "local_llm" and len(plan.subtasks) == 2

    async def broken(text: str) -> str:
        return "pas du json"

    assert len(asyncio.run(TaskDecomposer(broken).decompose(long)).subtasks) == 1


def test_synthesis_strategies() -> None:
    parts = [PartResult("Code", "```python\nprint(1)\n```", "m1"),
             PartResult("Explication", "Affiche 1.", "m2")]
    plain = ResponseSynthesizer.concatenate(parts)
    assert "### Code" in plain and "print(1)" in plain

    async def good(messages: list[dict[str, Any]]) -> tuple[str, str]:
        return "Voici le code :\n```python\nprint(1)\n```\nIl affiche 1. " * 2, "fake:best"

    async def lossy(messages: list[dict[str, Any]]) -> tuple[str, str]:
        return "ok", "fake:x"  # fusion trop courte : du contenu a été perdu

    async def fails(messages: list[dict[str, Any]]) -> tuple[str, str]:
        raise RuntimeError

    s = ResponseSynthesizer(quick=good, best=good)
    assert asyncio.run(s.merge("r", parts, "low"))[1] == "concat"
    assert asyncio.run(s.merge("r", parts, "medium"))[1:] == ("medium", "fake:best")
    assert asyncio.run(ResponseSynthesizer(quick=lossy).merge("r", parts, "medium"))[1] == \
        "concat"
    # Petit modèle trop court → modèle d'écriture essayé avant de concaténer.
    assert asyncio.run(ResponseSynthesizer(quick=lossy, best=good).merge(
        "r", parts, "medium"))[1:] == ("medium", "fake:best")
    assert asyncio.run(ResponseSynthesizer(best=fails).merge("r", parts, "high"))[0] == plain


async def test_parallel_then_dependent_flow(router: Router, fake: FakeProvider) -> None:
    """« Code Python + explication » : le code d'abord, l'explication voit le code."""
    seen: list[str] = []

    def act(model: Any, messages: list[dict[str, Any]]) -> dict[str, Any]:
        user = str(messages[-1]["content"])
        seen.append(user)
        if "explique" in user.lower():
            return {"role": "assistant", "content": "La fonction trie avec sorted()."}
        return {"role": "assistant", "content": "```python\ndef tri(l):\n    return sorted(l)\n```"}

    for mid in ("coder-pro", "chatty", "small", "vision-x", "paid-genius"):
        fake.behaviors[mid] = act
    pipe = HierarchicalPipeline(router)
    plan = await pipe.decomposer.decompose(
        "Écris une fonction Python qui trie une liste et explique-la")
    out = await pipe.run(plan)
    assert "sorted" in out["text"] and "trie avec sorted()" in out["text"]
    explain = next(u for u in seen if "explique" in u.lower())
    assert "def tri" in explain  # la partie dépendante a reçu le code
    m = out["metrics"]
    assert m["parallel"] == 1 and m["sequential"] == 1 and len(m["subtasks"]) == 2
    assert not any("paid-genius" in (s["model"] or "") for s in m["subtasks"])  # gratuits
    again = await pipe.run(plan)  # même demande : sous-tâches en cache
    assert all(s["cached"] for s in again["metrics"]["subtasks"])


async def test_independent_subtasks_run_in_parallel(router: Router, fake: FakeProvider,
                                                    monkeypatch: pytest.MonkeyPatch) -> None:
    pipe = HierarchicalPipeline(router)
    active, peak = 0, 0
    original = pipe._ask

    async def slow(messages: list[dict[str, Any]], **kw: Any) -> tuple[str, str]:
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.05)
        active -= 1
        return await original(messages, **kw)

    monkeypatch.setattr(pipe, "_ask", slow)
    plan = await pipe.decomposer.decompose(
        "Calcule 12 * 7 ; écris un haïku sur la mer ; donne la capitale du Japon")
    await pipe.run(plan)
    assert peak == 3


async def test_failed_subtask_never_loses_the_rest(router: Router, fake: FakeProvider,
                                                   monkeypatch: pytest.MonkeyPatch) -> None:
    pipe = HierarchicalPipeline(router)
    original = pipe._ask

    async def flaky(messages: list[dict[str, Any]], **kw: Any) -> tuple[str, str]:
        if "haïku" in str(messages[-1]["content"]):
            return "", ""
        return await original(messages, **kw)

    monkeypatch.setattr(pipe, "_ask", flaky)
    plan = await pipe.decomposer.decompose("Calcule 12 * 7 ; écris un haïku sur la mer")
    out = await pipe.run(plan)
    assert "n'a pas pu être traitée" in out["text"] and out["metrics"]["synthesis"] == "concat"
    assert sum(1 for s in out["metrics"]["subtasks"] if s.get("ok") is False) == 1


def test_default_chat_is_unchanged_and_orchestration_is_opt_in(
        client: TestClient) -> None:
    def chat(body: dict[str, Any]) -> list[dict[str, Any]]:
        with client.stream("POST", "/tontolo/chat", json=body) as s:
            return [json.loads(x[5:]) for x in s.iter_lines() if x.startswith("data:")]

    composed = "Écris un code Python pour fibonacci ; traduis bonjour en anglais"
    normal = chat({"content": composed})
    assert not any(e["type"] == "orchestration" for e in normal)  # par défaut : inchangé
    simple = chat({"content": "Bonjour !", "orchestrate": True})
    assert not any(e["type"] == "orchestration" for e in simple)  # faible : flux normal
    orch = chat({"content": composed, "orchestrate": True})
    assert any(e["type"] == "orchestration" for e in orch)
    done = next(e for e in orch if e["type"] == "done")
    assert done["metrics"]["subtasks"] and done["metrics"]["seconds"] >= 0
    assert done["message"]["content"]
    assert Category.CODE.value in [s["category"] for s in done["metrics"]["subtasks"]]
    # Avancement en direct : chaque partie lancée puis terminée avec son modèle, puis réunion.
    parts = [e for e in orch if e["type"] == "subtask"]
    n = len(done["metrics"]["subtasks"])
    assert [e["status"] for e in parts].count("running") == n
    finished = [e for e in parts if e["status"] in ("done", "failed")]
    assert len(finished) == n and all(e.get("model") and e.get("name") for e in finished)
    steps = [e for e in orch if e["type"] == "step"]
    assert steps and steps[-1]["step"] == "synthesizing"
    assert orch.index(steps[-1]) < orch.index(done)


def test_orchestration_setting_applies_to_every_chat(client: TestClient) -> None:
    client.put("/tontolo/settings", json={"orchestrate": True})
    with client.stream("POST", "/tontolo/chat", json={
            "content": "Calcule 12 * 7 ; traduis bonjour en anglais"}) as s:
        events = [json.loads(x[5:]) for x in s.iter_lines() if x.startswith("data:")]
    assert any(e["type"] == "orchestration" for e in events)
    client.put("/tontolo/settings", json={"orchestrate": False})
