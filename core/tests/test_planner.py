"""Tâches complexes : plan, sous-tâches en parallèle sur plusieurs modèles, livraison pas à
pas avec « continuer », plan gardé dans le fil."""

from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tontolo.agent import planner
from tontolo.catalog.service import CatalogService
from tontolo.config import Settings
from tontolo.providers.fake import FakeProvider
from tontolo.providers.registry import ProviderRegistry
from tontolo.server.app import create_app

COMPLEX = ("Fais-moi un cours complet sur les probabilités : 1) définitions 2) lois "
           "usuelles 3) exercices corrigés")


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


def _chat(client: TestClient, payload: dict[str, Any]) -> list[dict[str, Any]]:
    with client.stream("POST", "/tontolo/chat", json=payload) as s:
        return [json.loads(x[5:]) for x in s.iter_lines() if x.startswith("data:")]


def _script(fake: FakeProvider, mode: str, seen: list[list[dict[str, Any]]]) -> None:
    plan = {"complex": True, "mode": mode, "goal": "Cours de probabilités",
            "steps": [{"title": "Définitions", "task": "définir"},
                      {"title": "Lois", "task": "lois usuelles"},
                      {"title": "Exercices", "task": "exercices corrigés"}]}

    def act(model: Any, messages: list[dict[str, Any]]) -> dict[str, Any]:
        seen.append(messages)
        system = str(messages[0].get("content"))
        if "planificateur" in system:
            return {"role": "assistant", "content": json.dumps(plan)}
        if "membre d'une équipe" in system:
            return {"role": "assistant", "content": f"partie par {model.model_id}"}
        return {"role": "assistant", "content": f"réponse de {model.model_id}"}

    for mid in ("coder-pro", "chatty", "small", "vision-x", "paid-genius"):
        fake.behaviors[mid] = act


def test_heuristics() -> None:
    assert planner.looks_complex(COMPLEX)
    assert not planner.looks_complex("Quelle est la capitale de Madagascar ?")
    assert planner.wants_continue("Continuer") and planner.wants_continue("tohizo")
    assert not planner.wants_continue("continue à m'expliquer les lois normales en détail")
    assert planner.parse_plan('{"complex": false}') is None
    assert planner.parse_plan("pas du json") is None


def test_parallel_plan_uses_several_models(client: TestClient, fake: FakeProvider) -> None:
    seen: list[list[dict[str, Any]]] = []
    _script(fake, "parallel", seen)
    events = _chat(client, {"content": COMPLEX})
    plan = next(e for e in events if e["type"] == "plan")["plan"]
    assert plan["mode"] == "parallel" and len(plan["steps"]) == 3
    steps = [e for e in events if e["type"] == "plan_step"]
    assert sorted(e["i"] for e in steps if e["status"] == "done") == [0, 1, 2]
    used = {e["model"] for e in steps if e["status"] == "done"}
    assert len(used) >= 2  # plusieurs modèles en même temps
    final = seen[-1]
    text = json.dumps(final, ensure_ascii=False)
    assert "Assemble-les" in text and "partie par" in text
    assert final[-1]["content"] == COMPLEX  # le fil reste la priorité
    done = [e for e in events if e["type"] == "plan"][-1]["plan"]
    assert done["status"] == "done"


def test_step_by_step_with_continue(client: TestClient, fake: FakeProvider) -> None:
    seen: list[list[dict[str, Any]]] = []
    _script(fake, "steps", seen)
    events = _chat(client, {"content": COMPLEX})
    cid = next(e["id"] for e in events if e["type"] == "conversation")
    assert "étape 1/3" in json.dumps(seen[-1], ensure_ascii=False)
    assert client.get(f"/tontolo/conversations/{cid}").json()["plan"]["current"] == 0
    _chat(client, {"conversation_id": cid, "content": "continuer", "model": "fake:chatty"})
    assert "étape 2/3" in json.dumps(seen[-1], ensure_ascii=False)  # même après un changement
    events = _chat(client, {"conversation_id": cid, "content": "continuer"})
    assert "étape 3/3" in json.dumps(seen[-1], ensure_ascii=False)
    assert [e for e in events if e["type"] == "plan"][-1]["plan"]["status"] == "done"
    _chat(client, {"conversation_id": cid, "content": "merci"})
    assert "Plan de la tâche" not in json.dumps(seen[-1], ensure_ascii=False)


def test_plan_can_be_dropped_or_disabled(client: TestClient, fake: FakeProvider) -> None:
    seen: list[list[dict[str, Any]]] = []
    _script(fake, "steps", seen)
    events = _chat(client, {"content": COMPLEX})
    cid = next(e["id"] for e in events if e["type"] == "conversation")
    assert client.delete(f"/tontolo/conversations/{cid}/plan").json() == {"ok": True}
    assert client.get(f"/tontolo/conversations/{cid}").json()["plan"] is None
    client.put("/tontolo/settings", json={"task_planning": False})
    events = _chat(client, {"content": COMPLEX})
    assert not any(e["type"] == "plan" for e in events)
