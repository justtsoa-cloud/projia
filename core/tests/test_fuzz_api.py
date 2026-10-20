"""Entrées extrêmes : jamais de plantage ni de 500, jamais de tour perdu."""

from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from projia.catalog.service import CatalogService
from projia.config import Settings
from projia.providers.fake import FakeProvider
from projia.providers.registry import ProviderRegistry
from projia.server.app import create_app


@pytest.fixture
def client(settings: Settings, catalog_service: CatalogService, fake: FakeProvider,
           monkeypatch: pytest.MonkeyPatch) -> Any:
    async def fake_load(self: CatalogService) -> Any:
        self.catalog = catalog_service.catalog
        return self.catalog

    monkeypatch.setattr(CatalogService, "load", fake_load)
    app = create_app(settings, registry=ProviderRegistry(lambda p: fake), refresh=False)
    with TestClient(app, base_url="http://127.0.0.1", raise_server_exceptions=False) as c:
        yield c


def _post(client: TestClient, payload: Any) -> tuple[int, list[dict[str, Any]]]:
    with client.stream("POST", "/projia/chat", content=json.dumps(payload),
                       headers={"content-type": "application/json"}) as r:
        events = [json.loads(x[5:]) for x in r.iter_lines() if x.startswith("data:")]
        return r.status_code, events


NASTY = [
    "\ud800 surrogate isolé",
    "nul\x00dans le texte",
    "🧑🏽‍🚀 emoji ZWJ " * 50,
    "‮RTL override‬",
    "​" * 500,  # espaces de largeur nulle
    "'; DROP TABLE messages; --",
    "<script>alert(1)</script>{{7*7}}${jndi:ldap://x}",
    "\r\n\r\ndata: {\"type\": \"done\"}\r\n\r\n",  # injection de trame SSE
    "a" * 200_000,
    "é" * 100_000,
]


@pytest.mark.parametrize("text", NASTY, ids=[str(i) for i in range(len(NASTY))])
def test_nasty_text_never_breaks_a_turn(client: TestClient, text: str) -> None:
    status, events = _post(client, {"content": text})
    assert status == 200, events
    kinds = [e["type"] for e in events]
    assert "done" in kinds or "error" in kinds  # une réponse ou une erreur claire, jamais rien
    assert all(isinstance(e, dict) and "type" in e for e in events)
    cid = next((e["id"] for e in events if e["type"] == "conversation"), None)
    if cid:
        conv = client.get(f"/projia/conversations/{cid}")
        assert conv.status_code == 200
        client.get(f"/projia/conversations/{cid}/export", params={"format": "markdown"})


def test_oversized_message_is_refused_cleanly(client: TestClient) -> None:
    status, events = _post(client, {"content": "x" * 3_000_000})
    assert status in (200, 413, 422)
    if status == 200:  # accepté : jamais de plantage
        assert events


@pytest.mark.parametrize("payload", [
    {}, {"content": None}, {"content": 12}, {"content": []}, {"content": [None]},
    {"content": [{"type": "image_url"}]}, {"content": [{"type": "image_url",
                                                         "image_url": {"url": 5}}]},
    {"content": "ok", "model": "x" * 10_000}, {"content": "ok", "category": "inconnu"},
    {"content": "ok", "conversation_id": "../../etc/passwd"},
    {"content": "ok", "mode": "root"}, {"content": "ok", "level": "A" * 100},
])
def test_malformed_payloads_give_4xx_not_500(client: TestClient, payload: Any) -> None:
    with client.stream("POST", "/projia/chat", content=json.dumps(payload),
                       headers={"content-type": "application/json"}) as r:
        assert r.status_code < 500, (payload, r.status_code)
        list(r.iter_lines())


def test_garbage_bodies(client: TestClient) -> None:
    for body in (b"", b"{", b"\xff\xfe\x00", b"null", b"[]", b'{"content": "\\ud800"}'):
        r = client.post("/projia/chat", content=body,
                        headers={"content-type": "application/json"})
        assert r.status_code < 500, (body, r.status_code)


def test_weird_ids_and_paths(client: TestClient) -> None:
    for path in ("/projia/conversations/%00", "/projia/conversations/" + "a" * 5000,
                 "/projia/media/..%2f..%2fetc%2fpasswd/file", "/projia/media/%00",
                 "/projia/conversations/x/tasks/..%2f..%2findex",
                 "/projia/folders/share", "/projia/conversations?limit=-5&offset=-1",
                 "/projia/conversations?limit=999999999", "/projia/catalog?limit=-1",
                 "/projia/catalog?category=nimportequoi"):
        r = client.get(path)
        assert r.status_code < 500, (path, r.status_code)


def test_model_output_with_lone_surrogate_is_saved(client: TestClient, fake: FakeProvider) -> None:
    def odd(model: Any, messages: list[dict[str, Any]]) -> dict[str, Any]:
        return {"role": "assistant", "content": "réponse \ud800 étrange \udfff fin"}

    for mid in ("coder-pro", "chatty", "small", "vision-x", "paid-genius"):
        fake.behaviors[mid] = odd
    status, events = _post(client, {"content": "bonjour"})
    assert status == 200 and any(e["type"] == "done" for e in events)
    cid = next(e["id"] for e in events if e["type"] == "conversation")
    msgs = client.get(f"/projia/conversations/{cid}").json()["messages"]
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    assert "réponse" in msgs[1]["content"] and "fin" in msgs[1]["content"]
