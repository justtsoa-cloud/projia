"""« Ouvre le navigateur et montre-moi un site » : hors mode Agent, un lien direct et un bouton
« Ouvrir » plutôt qu'un refus."""

from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tontolo.agent import openlinks
from tontolo.catalog.service import CatalogService
from tontolo.config import Settings
from tontolo.providers.fake import FakeProvider
from tontolo.providers.registry import ProviderRegistry
from tontolo.server.app import create_app


@pytest.mark.parametrize("text", [
    "ouvre le navigateur et montre moi un site qui enseigne gratuitement le pentest",
    "choisi un et ouvre le dans le navigateur",
    "Montre-moi un site pour apprendre Python",
    "open the browser and show me a free course site",
    "Sokafy ny tranonkala iray hianarana",
    "ouvre ce lien",
])
def test_open_requests_are_recognised(text: str) -> None:
    assert openlinks.wants_open(text)


@pytest.mark.parametrize("text", [
    "Explique le pentest", "ouvre le fichier Word", "quel site pour apprendre ?",
    "Écris un site web en HTML", "Merci", "x" * 700 + " ouvre le navigateur",
])
def test_ordinary_requests_are_not(text: str) -> None:
    assert not openlinks.wants_open(text)


def test_links_are_cleaned_and_limited() -> None:
    answer = ("| TryHackMe | <https://tryhackme.com> |\nVoir [HTB](https://www.hackthebox.com), "
              "puis https://tryhackme.com. Aussi (https://frenchcyber.fr/) et https://a.example/x?y=1;"
              " https://b.example")
    assert openlinks.links_in(answer) == ["https://tryhackme.com", "https://www.hackthebox.com",
                                          "https://frenchcyber.fr/"]
    assert openlinks.links_in("aucun lien ici") == []


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


def _chat(client: TestClient, body: dict[str, Any]) -> list[dict[str, Any]]:
    with client.stream("POST", "/tontolo/chat", json=body) as r:
        return [json.loads(x[5:]) for x in r.iter_lines() if x.startswith("data:")]


def test_chat_offers_the_link_and_guides_the_model(client: TestClient, fake: FakeProvider) -> None:
    seen: list[str] = []

    def reply(model: Any, messages: list[dict[str, Any]]) -> dict[str, Any]:
        seen.append(str(messages[0]["content"]))
        return {"role": "assistant", "content": "Commence par https://tryhackme.com (gratuit)."}

    for mid in [*fake.behaviors, "coder-pro", "chatty", "small", "vision-x", "paid-genius"]:
        fake.behaviors[mid] = reply
    events = _chat(client, {"content": "ouvre le navigateur et montre-moi un site gratuit"})
    links = [e for e in events if e["type"] == "open_links"]
    assert links and links[0]["urls"] == ["https://tryhackme.com"]
    assert "bouton « Ouvrir »" in seen[0]  # le modèle sait que l'application ouvre le lien
    assert events.index(links[0]) > max(i for i, e in enumerate(events) if e["type"] == "done")
    plain = _chat(client, {"content": "Explique-moi la photosynthèse"})
    assert not any(e["type"] == "open_links" for e in plain)
    assert "bouton « Ouvrir »" not in seen[-1]
