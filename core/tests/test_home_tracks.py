"""Piste du jour : intérêts locaux, variété, respect (sujets sensibles, « pas pour moi »)."""

from __future__ import annotations

import time
from typing import Any

import pytest
from fastapi.testclient import TestClient

from projia.catalog.service import CatalogService
from projia.config import Settings
from projia.home import tracks
from projia.providers.fake import FakeProvider
from projia.providers.registry import ProviderRegistry
from projia.server.app import create_app

NOW = 1_800_000_000.0
DAY = 86400.0


def conv(title: str, days_ago: float = 0, mode: str = "") -> dict:
    return {"title": title, "updated_at": NOW - days_ago * DAY, "mode": mode}


def test_topics_come_from_titles_most_recent_and_repeated_first() -> None:
    cs = [conv("Peux-tu m'expliquer la photosynthèse ?", 20), conv("Les fractions", 1),
          conv("Les fractions en 6e", 2), conv("Bonjour", 0), conv("Nouvelle conversation", 0)]
    topics = tracks.interests(cs, NOW)
    assert topics[0].lower().startswith("les fractions")
    assert topics[1] == "la photosynthèse"                 # la tournure est retirée
    assert "Bonjour" not in topics and len(topics) == 2


def test_sensitive_subjects_are_never_proposed() -> None:
    cs = [conv("Mon diagnostic médical"), conv("Dette et crédit immobilier"),
          conv("My therapy notes"), conv("Les volcans")]
    assert tracks.interests(cs, NOW) == ["Les volcans"]


def test_no_history_means_no_track() -> None:
    assert tracks.build([], "fr", now=NOW) == []
    assert tracks.build([conv("Salut")], "fr", now=NOW) == []


def test_tracks_are_varied_and_stable_during_the_day() -> None:
    cs = [conv("Les fractions", 1), conv("La Guerre froide", 2), conv("Les volcans", 3)]
    a = tracks.build(cs, "fr", now=NOW)
    b = tracks.build(cs, "fr", now=NOW + 3600)
    assert a == b and len(a) == 3
    assert len({t["kind"] for t in a}) == 3          # natures différentes
    assert all(t["topic"] in t["title"] and t["topic"] in t["prompt"] for t in a)
    assert tracks.build(cs, "fr", now=NOW + 2 * DAY) != a   # change d'un jour à l'autre


def test_one_topic_still_gives_several_kinds() -> None:
    out = tracks.build([conv("Les volcans")], "en", now=NOW)
    assert len(out) == 3 and len({t["kind"] for t in out}) == 3


def test_dismissed_topic_is_hidden_for_two_weeks() -> None:
    cs = [conv("Les volcans", 1), conv("Les fractions", 2)]
    hidden = {"les volcans": NOW - 3 * DAY}
    assert all("volcans" not in t["topic"] for t in tracks.build(cs, "fr", hidden, NOW))
    old = {"les volcans": NOW - 20 * DAY}
    assert any("volcans" in t["topic"] for t in tracks.build(cs, "fr", old, NOW))


def test_three_languages() -> None:
    cs = [conv("Les volcans")]
    for lang in ("fr", "en", "mg"):
        assert tracks.build(cs, lang, now=NOW)[0]["prompt"]
    assert time.time() > 0


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


def test_home_endpoint_proposes_and_dismisses(client: TestClient) -> None:
    """Bout en bout : un titre de discussion devient une piste ; « pas pour moi » la retire."""
    import json as _json

    cid = client.post("/projia/import", json={"data": _json.dumps({
        "snapshot_name": "Les volcans", "chat_messages": [
            {"sender": "human", "content": [{"type": "text", "text": "Parle-moi des volcans"}]},
            {"sender": "assistant", "content": [{"type": "text", "text": "Ce sont des reliefs…"}]},
        ]})}).json()["conversations"][0]["id"]
    assert cid
    home = client.get("/projia/home").json()
    assert home["tracks"] and "volcans" in home["tracks"][0]["topic"].lower()
    assert client.post("/projia/home/dismiss", json={"topic": home["tracks"][0]["topic"]}
                       ).json() == {"ok": True}
    assert client.get("/projia/home").json()["tracks"] == []
    assert client.put("/projia/settings", json={"home_tracks": False}).status_code == 200
    assert "tracks" not in client.get("/projia/home").json()
