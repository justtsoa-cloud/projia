"""Phase 5 : un client OpenAI standard fonctionne en pointant sur Tontolo ;
image et transcription passent par la même chaîne de bascule que le texte."""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tontolo.catalog.service import CatalogService
from tontolo.config import Settings
from tontolo.media import providers as mp
from tontolo.providers.base import ErrorKind, ProviderError
from tontolo.providers.fake import FakeProvider
from tontolo.providers.registry import ProviderRegistry
from tontolo.server.app import create_app

openai = pytest.importorskip("openai")


@pytest.fixture
def client(settings: Settings, catalog_service: CatalogService, fake: FakeProvider,
           monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    async def fake_load(self: CatalogService) -> Any:
        self.catalog = catalog_service.catalog
        return self.catalog

    monkeypatch.setattr(CatalogService, "load", fake_load)
    app = create_app(settings, registry=ProviderRegistry(lambda p: fake), refresh=False)
    with TestClient(app, base_url="http://127.0.0.1") as c:
        yield c


def test_openai_sdk_chat(client: TestClient) -> None:
    oai = openai.OpenAI(base_url="http://127.0.0.1/v1", api_key="inutile",
                        http_client=client)
    models = [m.id for m in oai.models.list()]
    assert "auto" in models and "fake:chatty" in models
    resp = oai.chat.completions.create(model="auto",
                                       messages=[{"role": "user", "content": "Bonjour"}])
    assert resp.model == "fake:chatty"
    assert resp.choices[0].message.content == "[chatty] Bonjour"


def test_openai_sdk_stream_with_switch(client: TestClient, fake: FakeProvider) -> None:
    fake.fail("chatty", ProviderError("limite", ErrorKind.RATE_LIMIT, status=429,
                                      retry_after=60))
    oai = openai.OpenAI(base_url="http://127.0.0.1/v1", api_key="x", http_client=client)
    stream = oai.chat.completions.create(model="auto", stream=True,
                                         messages=[{"role": "user", "content": "Salut"}])
    text = "".join((ch.choices[0].delta.content or "") for ch in stream if ch.choices)
    assert text.startswith("[") and "Salut" in text and "chatty" not in text


def test_native_chat_sse_and_history(client: TestClient) -> None:
    with client.stream("POST", "/tontolo/chat",
                       json={"content": "Bonjour", "use_tools": False}) as r:
        events = [json.loads(line[5:]) for line in r.iter_lines() if line.startswith("data:")]
    types = [e["type"] for e in events]
    assert types[0] == "conversation" and "route" in types and "done" in types
    cid = events[0]["id"]
    conv = client.get(f"/tontolo/conversations/{cid}").json()
    assert [m["role"] for m in conv["messages"]] == ["user", "assistant"]
    assert client.get("/tontolo/conversations", params={"q": "Bonjour"}).json()


def test_preferences_and_route_preview(client: TestClient) -> None:
    client.put("/tontolo/preferences", json={"scope": "global", "model": "fake:small"})
    r = client.post("/tontolo/route", json={"messages": [{"role": "user",
                                                          "content": "Bonjour"}]}).json()
    assert r["chain"][0]["model"] == "fake:small" and r["chain"][0]["preferred"]
    client.put("/tontolo/preferences", json={"scope": "global", "model": "auto"})
    r = client.post("/tontolo/route", json={"messages": [{"role": "user",
                                                          "content": "Bonjour"}]}).json()
    assert r["chain"][0]["model"] == "fake:chatty"


def test_image_generation_with_fallback(client: TestClient, catalog_service: CatalogService,
                                        monkeypatch: pytest.MonkeyPatch) -> None:
    from tontolo.catalog.models import ModelInfo

    catalog_service.catalog.models["fake:img-2"] = ModelInfo(
        provider="fake", model_id="img-2", name="img-2", is_free=True, needs_key=False,
        output_modalities=["image"], media=["image_gen"], quality={"image_gen": 0.5})
    calls: list[str] = []

    async def fake_gen(model: Any, provider: Any, prompt: str, params: Any) -> mp.MediaOutput:
        calls.append(model.model_id)
        if model.model_id == "img-1":
            raise ProviderError("quota", ErrorKind.QUOTA, status=429)
        return mp.MediaOutput(b"\x89PNG fake", "image/png")

    monkeypatch.setattr(mp, "generate_image", fake_gen)
    oai = openai.OpenAI(base_url="http://127.0.0.1/v1", api_key="x", http_client=client)
    img = oai.images.generate(prompt="un phare", model="auto")
    assert calls == ["img-1", "img-2"]
    assert img.data and img.data[0].b64_json
    jobs = client.get("/tontolo/media").json()
    assert jobs[0]["status"] == "done" and jobs[0]["model"] == "fake:img-2"
    assert client.get(f"/tontolo/media/{jobs[0]['id']}/file").content == b"\x89PNG fake"


def test_transcription(client: TestClient, catalog_service: CatalogService,
                       monkeypatch: pytest.MonkeyPatch) -> None:
    from tontolo.catalog.models import ModelInfo

    catalog_service.catalog.models["fake:whisper"] = ModelInfo(
        provider="fake", model_id="whisper", is_free=True, needs_key=False,
        input_modalities=["audio"], media=["stt"])

    async def fake_stt(model: Any, provider: Any, audio: bytes, name: str,
                       params: Any) -> mp.MediaOutput:
        return mp.MediaOutput(b"bonjour", "text/plain", text="bonjour")

    monkeypatch.setattr(mp, "transcribe", fake_stt)
    oai = openai.OpenAI(base_url="http://127.0.0.1/v1", api_key="x", http_client=client)
    tr = oai.audio.transcriptions.create(model="auto", file=("a.wav", b"RIFF...."))
    assert tr.text == "bonjour"


def test_video_best_effort_message(client: TestClient) -> None:
    job = client.post("/tontolo/media", json={"kind": "video_gen", "prompt": "un chat"}).json()
    import time

    for _ in range(50):
        j = client.get(f"/tontolo/media/{job['id']}").json()
        if j["status"] in ("done", "failed"):
            break
        time.sleep(0.02)
    assert j["status"] == "failed" and "indisponible gratuitement" in j["error"]


def test_token_required(settings: Settings, catalog_service: CatalogService,
                        fake: FakeProvider, monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_load(self: CatalogService) -> Any:
        self.catalog = catalog_service.catalog
        return self.catalog

    monkeypatch.setattr(CatalogService, "load", fake_load)
    settings.server.token = "secret"
    app = create_app(settings, registry=ProviderRegistry(lambda p: fake), refresh=False)
    with TestClient(app, base_url="http://127.0.0.1") as c:
        assert c.get("/tontolo/conversations").status_code == 401
        ok = c.get("/tontolo/conversations", headers={"Authorization": "Bearer secret"})
        assert ok.status_code == 200
        assert c.get("/health").status_code == 200


def test_sync_roundtrip(client: TestClient) -> None:
    with client.stream("POST", "/tontolo/chat",
                       json={"content": "À synchroniser", "use_tools": False}) as r:
        list(r.iter_lines())
    dump = client.get("/tontolo/sync", params={"since": 0}).json()
    assert dump["conversations"] and dump["messages"]
    assert client.post("/tontolo/sync", json=dump).json()["applied"] == 0  # déjà à jour


def test_native_chat_detects_image_request(client: TestClient,
                                           monkeypatch: pytest.MonkeyPatch) -> None:
    """« Dessine… » sans catégorie forcée passe par le pipeline média, pas par le chat."""
    async def fake_gen(model: Any, provider: Any, prompt: str, params: Any) -> mp.MediaOutput:
        return mp.MediaOutput(b"\x89PNG", "image/png")

    monkeypatch.setattr(mp, "generate_image", fake_gen)
    with client.stream("POST", "/tontolo/chat",
                       json={"content": "Dessine un phare au coucher du soleil"}) as r:
        events = [json.loads(line[5:]) for line in r.iter_lines() if line.startswith("data:")]
    done = next(e for e in events if e["type"] == "done")
    assert done["job"]["status"] == "done" and done["model"] == "fake:img-1"


def test_turn_survives_client_leaving_server(client: TestClient, fake: FakeProvider) -> None:
    """Un autre client peut se rattacher au tour en cours, puis l'arrêter."""
    import threading
    import time

    fake.chunk_delay = 0.15
    cid = "conv-lente-1"
    body = {"conversation_id": cid, "content": "Une réponse lente pour tester",
            "use_tools": False}
    t = threading.Thread(target=lambda: client.post("/tontolo/chat", json=body), daemon=True)
    t.start()
    for _ in range(100):
        r = client.get(f"/tontolo/conversations/{cid}")
        if r.status_code == 200 and r.json()["active"]:
            break
        time.sleep(0.02)
    assert r.json()["active"] is True
    busy = client.post("/tontolo/chat", json=body)
    assert busy.status_code == 409                       # un seul tour actif par conversation
    assert client.post(f"/tontolo/chat/{cid}/stop").json()["stopped"] is True
    t.join(timeout=5)
    assert client.get(f"/tontolo/conversations/{cid}").json()["active"] is False


@pytest.mark.parametrize("status", [502, 200])
async def test_pollinations_retries_then_succeeds(status: int,
                                                  monkeypatch: pytest.MonkeyPatch) -> None:
    """Le service gratuit est parfois instable : 3 essais avant d'abandonner."""
    import asyncio

    import httpx
    import respx

    from tontolo.catalog.models import ModelInfo

    async def fast_sleep(_: float) -> None:
        return None

    monkeypatch.setattr(asyncio, "sleep", fast_sleep)
    model = ModelInfo(provider="pollinations", model_id="auto", is_free=True, needs_key=False,
                      output_modalities=["image"], media=["image_gen"])
    with respx.mock:
        route = respx.get(url__startswith="https://image.pollinations.ai/prompt/")
        route.side_effect = [httpx.Response(status if status != 200 else 502),
                             httpx.Response(502),
                             httpx.Response(200, content=b"\xff\xd8img",
                                            headers={"content-type": "image/jpeg"})]
        out = await mp.generate_image(model, {"id": "pollinations"}, "un chat", {})
    assert out.mime == "image/jpeg" and route.call_count == 3
    assert "model" not in route.calls[0].request.url.params   # « auto » : pas de modèle imposé


def test_regenerate_image_request_stays_media(client: TestClient,
                                              monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    async def fake_gen(model: Any, provider: Any, prompt: str, params: Any) -> mp.MediaOutput:
        calls.append(prompt)
        return mp.MediaOutput(b"\x89PNG", "image/png")

    monkeypatch.setattr(mp, "generate_image", fake_gen)
    cid = "conv-image-1"
    client.post("/tontolo/chat", json={"conversation_id": cid,
                                       "content": "Dessine un phare au coucher du soleil"})
    client.post(f"/tontolo/chat/{cid}/regenerate", json={"approved": True})
    msgs = client.get(f"/tontolo/conversations/{cid}").json()["messages"]
    assert len(calls) == 2
    assert [m["role"] for m in msgs] == ["user", "assistant"]       # ni doublon ni texte
    assert msgs[1]["content"].startswith("[média:")
