"""Cohérence d'une longue discussion : le fil, les documents et la continuité survivent à une
heure d'échanges et aux changements de modèle."""

from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tontolo.agent import threadmemory
from tontolo.catalog.service import CatalogService
from tontolo.config import Settings
from tontolo.providers.fake import FakeProvider
from tontolo.providers.registry import ProviderRegistry
from tontolo.server.app import create_app


def _talk(n: int, secret_at: int = 1) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for i in range(n):
        role = "user" if i % 2 == 0 else "assistant"
        text = f"Message numéro {i} sur des sujets divers et variés pour remplir le fil."
        if i == secret_at:
            text = "Mon budget pour la rénovation de la cuisine est de 4500 euros, pas plus."
        out.append({"role": role, "content": text})
    return out


def test_recall_finds_an_old_fact_the_summary_may_have_lost() -> None:
    history = _talk(80)
    history.append({"role": "user", "content": "Rappelle-moi le budget de la cuisine"})
    found = threadmemory.recall(history, "Rappelle-moi le budget de la cuisine")
    assert found is not None and "4500 euros" in found and "message 2" in found
    assert threadmemory.recall(history, "Bonjour") is None            # rien de pertinent
    # Fil court : tout est déjà envoyé mot pour mot, rien à rappeler.
    assert threadmemory.recall(_talk(10), "budget cuisine") is None


def test_recall_never_repeats_what_is_already_sent_verbatim() -> None:
    history = _talk(30, secret_at=29)  # le fait est dans les 18 derniers messages
    assert threadmemory.recall(history, "quel budget pour la cuisine ?") is None


def test_short_requests_borrow_the_previous_ones() -> None:
    history = [{"role": "user", "content": "Explique la loi binomiale avec un exemple"},
               {"role": "assistant", "content": "…"},
               {"role": "user", "content": "et la suite ?"}]
    q = threadmemory.search_query(history, "et la suite ?")
    assert "binomiale" in q and q.endswith("et la suite ?")
    full = "Explique en détail la loi de Poisson et ses applications"
    assert threadmemory.search_query(history, full) == full


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


def test_a_long_thread_keeps_files_facts_and_style_whatever_the_model(
        client: TestClient, fake: FakeProvider) -> None:
    seen: list[list[dict[str, Any]]] = []

    def reply(model: Any, messages: list[dict[str, Any]]) -> dict[str, Any]:
        seen.append(messages)
        return {"role": "assistant", "content": "Voici la suite, dans le même style."}

    for mid in [*fake.behaviors, "coder-pro", "chatty", "small", "vision-x", "paid-genius"]:
        fake.behaviors[mid] = reply
    snap = {"snapshot_name": "Rénovation", "chat_messages": [
        {"sender": "human" if m["role"] == "user" else "assistant",
         "content": [{"type": "text", "text": m["content"]}]} for m in _talk(90)]}
    cid = client.post("/tontolo/import", json={"data": json.dumps(snap)}).json()[
        "conversations"][0]["id"]
    up = client.post("/tontolo/documents", data={"conversation_id": cid},
                     files={"file": ("devis-cuisine.txt", "Devis : plan de travail en chêne, "
                                     "hotte, évier double. Total 4200 euros.".encode())})
    assert up.status_code == 200
    with client.stream("POST", "/tontolo/chat", json={
            "conversation_id": cid, "content": "et la suite ?"}) as r:
        assert any('"done"' in line for line in r.iter_lines())
    sent = seen[-1]
    system = "\n".join(str(m["content"]) for m in sent if m["role"] == "system")
    assert "devis-cuisine.txt" in system                 # le fichier joint est rappelé
    assert "Continuité" in system                        # même ton, aucun changement annoncé
    assert sent[-1]["content"] == "et la suite ?"        # la demande courante reste la dernière
    # Un fait ancien, perdu par le résumé : retrouvé quand la demande y fait référence.
    with client.stream("POST", "/tontolo/chat", json={
            "conversation_id": cid, "content": "rappelle-moi mon budget pour la cuisine"}) as r:
        assert any('"done"' in line for line in r.iter_lines())
    system = "\n".join(str(m["content"]) for m in seen[-1] if m["role"] == "system")
    assert "4500 euros" in system or any("4500 euros" in str(m["content"]) for m in seen[-1])
