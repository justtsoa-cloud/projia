"""Phase 5 : un client OpenAI standard fonctionne en pointant sur Tontolo ;
image et transcription passent par la même chaîne de bascule que le texte."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
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
    assert j["status"] == "failed" and "vidéo" in j["error"]


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
    """Le service gratuit est parfois instable : 2 essais avant d'abandonner."""
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
                             httpx.Response(200, content=b"\xff\xd8img",
                                            headers={"content-type": "image/jpeg"})]
        out = await mp.generate_image(model, {"id": "pollinations"}, "un chat", {})
    assert out.mime == "image/jpeg" and route.call_count == 2
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


def _png_data_url() -> str:
    import base64

    return "data:image/png;base64," + base64.b64encode(b"\x89PNG fake photo").decode()


def _edit_request(client: TestClient, cid: str) -> dict[str, Any]:
    client.post("/tontolo/chat", json={"conversation_id": cid, "content": [
        {"type": "text", "text": "Edite cette photo de façon très créative"},
        {"type": "image_url", "image_url": {"url": _png_data_url()}}]})
    msgs = client.get(f"/tontolo/conversations/{cid}").json()["messages"]
    job_id = msgs[1]["content"].removeprefix("[média:").removesuffix("]")
    job: dict[str, Any] = client.get(f"/tontolo/media/{job_id}").json()
    return job


def test_photo_edit_falls_back_to_describe_then_recreate(
        client: TestClient, fake: FakeProvider, monkeypatch: pytest.MonkeyPatch) -> None:
    """Aucune édition gratuite : la photo est décrite par une IA à vision puis recréée."""
    prompts: list[str] = []

    async def fake_gen(model: Any, provider: Any, prompt: str, params: Any) -> mp.MediaOutput:
        prompts.append(prompt)
        return mp.MediaOutput(b"\x89PNG new", "image/png")

    monkeypatch.setattr(mp, "generate_image", fake_gen)
    fake.behaviors["vision-x"] = lambda m, msgs: {
        "role": "assistant", "content": "Deux verres sur une table sombre, lumière chaude."}
    job = _edit_request(client, "conv-edit-1")
    assert job["status"] == "done" and job["kind"] == "image_edit"
    assert "Deux verres sur une table sombre" in prompts[0]
    assert "Edite cette photo" in prompts[0]
    assert "réinterprétation" in job["params"]["warning"]


def test_photo_edit_without_vision_model_still_creates_image(
        client: TestClient, fake: FakeProvider, catalog_service: CatalogService,
        monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_gen(model: Any, provider: Any, prompt: str, params: Any) -> mp.MediaOutput:
        return mp.MediaOutput(b"\x89PNG new", "image/png")

    monkeypatch.setattr(mp, "generate_image", fake_gen)
    catalog_service.catalog.models["fake:vision-x"].input_modalities = ["text"]  # plus de vision
    job = _edit_request(client, "conv-edit-2")
    assert job["status"] == "done"
    assert "texte seul" in job["params"]["warning"]


def _chat_events(client: TestClient, cid: str, text: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    with client.stream("POST", "/tontolo/chat",
                       json={"conversation_id": cid, "content": text, "use_tools": False}) as r:
        out = [json.loads(line[5:]) for line in r.iter_lines() if line.startswith("data:")]
    return out


def _last_done(events: list[dict[str, Any]]) -> dict[str, Any]:
    return next(e for e in reversed(events) if e["type"] == "done")


def test_followup_wording_is_recognised_as_image_request(
        client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Scénario réel : « crée la photo » (avec « la ») partait vers un modèle de texte."""
    prompts: list[str] = []

    async def fake_gen(model: Any, provider: Any, prompt: str, params: Any) -> mp.MediaOutput:
        prompts.append(prompt)
        return mp.MediaOutput(b"\x89PNG", "image/png")

    monkeypatch.setattr(mp, "generate_image", fake_gen)
    events = _chat_events(client, "conv-photo-1", "crée la photo")
    assert any(e["type"] == "job" for e in events) and _last_done(events)["job"]["status"] == "done"
    # « vas-y » après une demande d'image : on reprend la description précédente.
    _chat_events(client, "conv-photo-2", "dessine un phare au coucher du soleil")
    events = _chat_events(client, "conv-photo-2", "vas-y refais")
    assert _last_done(events)["job"]["status"] == "done"
    assert "phare" in prompts[-1]


def test_auto_switch_when_text_model_refuses_images(
        client: TestClient, fake: FakeProvider, monkeypatch: pytest.MonkeyPatch) -> None:
    """Le modèle de texte répond « je ne peux pas générer d'images » : bascule automatique."""
    async def fake_gen(model: Any, provider: Any, prompt: str, params: Any) -> mp.MediaOutput:
        return mp.MediaOutput(b"\x89PNG", "image/png")

    monkeypatch.setattr(mp, "generate_image", fake_gen)
    fake.behaviors["chatty"] = lambda m, msgs: {
        "role": "assistant",
        "content": "Je dois être honnête : je ne peux pas générer d'images. Voici un prompt "
                   "prêt à coller dans Midjourney."}
    events = _chat_events(client, "conv-refus-1", "Peux-tu me montrer à quoi ressemblerait "
                                                  "une belle photo de montagne ?")
    types = [e["type"] for e in events]
    assert "media_switch" in types, types
    done = _last_done(events)
    assert done["job"]["status"] == "done"
    assert all("ne peux pas générer" not in str(e.get("message", "")) for e in events
               if e["type"] == "done" and not e.get("job"))
    msgs = client.get("/tontolo/conversations/conv-refus-1").json()["messages"]
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    assert msgs[1]["content"].startswith("[média:")          # le refus n'est pas conservé


def test_media_placeholders_are_explained_to_text_models(
        client: TestClient, fake: FakeProvider, monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_gen(model: Any, provider: Any, prompt: str, params: Any) -> mp.MediaOutput:
        return mp.MediaOutput(b"\x89PNG", "image/png")

    monkeypatch.setattr(mp, "generate_image", fake_gen)
    _chat_events(client, "conv-ctx-1", "dessine un chat")
    seen: list[list[dict[str, Any]]] = []
    fake.behaviors["chatty"] = lambda m, msgs: seen.append(msgs) or {
        "role": "assistant", "content": "ok"}
    _chat_events(client, "conv-ctx-1", "Merci, tu peux m'expliquer comment ça marche ?")
    text = "\n".join(str(m.get("content")) for m in seen[-1])
    assert "[média:" not in text and "généré une image" in text
    assert "ne dis jamais que tu ne peux pas" in text


def test_preserve_instruction_never_generates_another_person(
        client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Signalement réel : « sans changer la personne » + remplacement du décor → on refuse
    honnêtement au lieu de générer une autre personne."""
    called: list[str] = []

    async def fake_gen(model: Any, provider: Any, prompt: str, params: Any) -> mp.MediaOutput:
        called.append(prompt)
        return mp.MediaOutput(b"\x89PNG", "image/png")

    monkeypatch.setattr(mp, "generate_image", fake_gen)
    client.post("/tontolo/chat", json={"conversation_id": "conv-keep-1", "content": [
        {"type": "text", "text": "Remplace le décor par une plage sans changer la personne"},
        {"type": "image_url", "image_url": {"url": _png_data_url()}}]})
    msgs = client.get("/tontolo/conversations/conv-keep-1").json()["messages"]
    job_id = msgs[1]["content"].removeprefix("[média:").removesuffix("]")
    job = client.get(f"/tontolo/media/{job_id}").json()
    assert job["status"] == "failed" and called == []
    assert "FLUX Kontext" in job["error"] and "sur votre téléphone" in job["error"]


def test_local_retouch_result_is_stored_in_conversation(client: TestClient) -> None:
    import base64

    r = client.post("/tontolo/chat/local-media", json={
        "conversation_id": "conv-local-1", "content": [
            {"type": "text", "text": "édite cette photo, style professionnel"},
            {"type": "image_url", "image_url": {"url": _png_data_url()}}],
        "result_b64": base64.b64encode(b"\xff\xd8\xffJPEG").decode(),
        "note": "Retouche appliquée sur votre appareil"}).json()
    assert r["job"]["status"] == "done" and r["job"]["model"] == "local:retouche"
    msgs = client.get("/tontolo/conversations/conv-local-1").json()["messages"]
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    assert client.get(f"/tontolo/media/{r['job']['id']}/file").content == b"\xff\xd8\xffJPEG"
    assert client.get("/tontolo/media", params={"kind": "image_edit"}).json()[0]["id"] == \
        r["job"]["id"]
    bad = client.post("/tontolo/chat/local-media", json={
        "content": "x", "result_b64": "pas du base64 !!"})
    assert bad.status_code == 400


def _wait_job(client: TestClient, job_id: str) -> dict[str, Any]:
    import time

    for _ in range(100):
        j = client.get(f"/tontolo/media/{job_id}").json()
        if j["status"] in ("done", "failed"):
            return j
        time.sleep(0.02)
    return j


def test_video_from_hf_space(client: TestClient, catalog_service: CatalogService,
                             monkeypatch: pytest.MonkeyPatch) -> None:
    from tontolo.catalog.service import BUILTIN_PROVIDERS
    from tontolo.catalog.sources import hfspaces

    cat = catalog_service.catalog
    cat.providers["hf_spaces"] = BUILTIN_PROVIDERS["hf_spaces"]
    for m in hfspaces.models():
        cat.models[m.key] = m

    async def fake_video(model: Any, prompt: str, params: Any) -> mp.MediaOutput:
        return mp.MediaOutput(b"\x00\x00\x00\x18ftypmp42", "video/mp4")

    monkeypatch.setattr(mp, "generate_video", fake_video)
    job = client.post("/tontolo/media", json={"kind": "video_gen", "prompt": "un renard"}).json()
    j = _wait_job(client, job["id"])
    assert j["status"] == "done" and j["params"]["mime"] == "video/mp4"
    assert client.get(f"/tontolo/media/{job['id']}/file").content.startswith(b"\x00\x00\x00\x18")

    async def no_quota(model: Any, prompt: str, params: Any) -> mp.MediaOutput:
        from tontolo.providers.base import ErrorKind, ProviderError
        raise ProviderError("Quota GPU gratuit épuisé", ErrorKind.QUOTA, retry_after=3600)

    monkeypatch.setattr(mp, "generate_video", no_quota)
    job = client.post("/tontolo/media", json={"kind": "video_gen", "prompt": "encore"}).json()
    j = _wait_job(client, job["id"])
    assert j["status"] == "failed" and "clé Hugging Face" in j["error"]


def test_model_health(client: TestClient) -> None:
    h = client.get("/tontolo/health").json()
    assert h["state"] in ("green", "orange") and h["ready"] >= 1 and h["best_key"]
    models = client.get("/tontolo/catalog", params={"usable": True}).json()["models"]
    assert all("available_at" in m for m in models)


def test_online_endpoint(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    core = client.app.state.core  # type: ignore[attr-defined]

    async def up() -> bool:
        return True

    core.router.probe = up
    assert client.get("/tontolo/online").json() == {"online": True}


def test_paused_image_source_is_retried(client: TestClient, catalog_service: CatalogService,
                                        monkeypatch: pytest.MonkeyPatch) -> None:
    """Toutes les sources d'images en pause : on retente quand même (bug « aucune source »)."""
    from tontolo.providers.base import ErrorKind, ProviderError

    core = client.app.state.core  # type: ignore[attr-defined]
    img = next(m for m in catalog_service.catalog.models.values() if "image_gen" in m.media)
    core.router.quota.on_error(img, ProviderError("x", ErrorKind.NETWORK))

    async def fake_image(model: Any, provider: Any, prompt: str, params: Any) -> mp.MediaOutput:
        return mp.MediaOutput(b"\x89PNG\r\n\x1a\n", "image/png")

    monkeypatch.setattr(mp, "generate_image", fake_image)
    job = client.post("/tontolo/media", json={"kind": "image_gen", "prompt": "phare"}).json()
    assert _wait_job(client, job["id"])["status"] == "done"

    async def broken(model: Any, provider: Any, prompt: str, params: Any) -> mp.MediaOutput:
        raise ProviderError("x", ErrorKind.SERVER)

    monkeypatch.setattr(mp, "generate_image", broken)
    job = client.post("/tontolo/media", json={"kind": "image_gen", "prompt": "phare"}).json()
    j = _wait_job(client, job["id"])
    assert j["status"] == "failed" and j["params"]["error_code"] == "sources_failed"
    assert j["params"]["retry_at"]


async def test_media_prompt_translated_to_english() -> None:
    from tontolo.server.common import _english_prompt

    class R:
        async def quick(self, messages: list[dict[str, Any]]) -> str:
            return "A tall lighthouse on a rocky coast at sunset"

    class C:
        router = R()

    out = await _english_prompt(C(), "Manaova sary tilikambo jiro")  # type: ignore[arg-type]
    assert out.startswith("A tall lighthouse")
    assert await _english_prompt(C(), "a cat on a sofa") == "a cat on a sofa"  # type: ignore[arg-type]


def _events(client: TestClient, url: str, body: dict[str, Any]) -> list[dict[str, Any]]:
    with client.stream("POST", url, json=body) as r:
        return [json.loads(line[5:]) for line in r.iter_lines() if line.startswith("data:")]


def test_edited_message_becomes_image(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Bug utilisateur : message modifié en « Draw a woman… » → répondu par un modèle texte."""
    async def fake_gen(model: Any, provider: Any, prompt: str, params: Any) -> mp.MediaOutput:
        return mp.MediaOutput(b"\x89PNG", "image/png")

    monkeypatch.setattr(mp, "generate_image", fake_gen)
    ev = _events(client, "/tontolo/chat", {"content": "Bonjour"})
    cid = next(e["id"] for e in ev if e["type"] == "conversation")
    seq = next(e["seq"] for e in ev if e["type"] == "user_saved")
    ev = _events(client, f"/tontolo/chat/{cid}/edit",
                 {"seq": seq, "content": "Draw a woman wearing gucci."})
    done = next(e for e in ev if e["type"] == "done")
    assert done["job"]["status"] == "done"


def test_text_model_false_image_claim_switches(client: TestClient, fake: FakeProvider,
                                               monkeypatch: pytest.MonkeyPatch) -> None:
    from tontolo.router.refusal import looks_like_image_refusal

    assert looks_like_image_refusal("I've generated an image of a woman wearing Gucci.")
    assert looks_like_image_refusal("Voici l'image demandée :")
    assert not looks_like_image_refusal("Here is the code you asked for.")


def test_agent_workdir_not_remotely_changeable(client: TestClient) -> None:
    before = client.get("/tontolo/settings").json()["agent"]["workdir"]
    client.put("/tontolo/settings", json={"agent": {"workdir": "/etc"}, "server": {"token": "x"}})
    after = client.get("/tontolo/settings").json()
    assert after["agent"]["workdir"] == before and "token" not in after["server"]


def test_document_upload_api(client: TestClient) -> None:
    from tests.test_documents import tiny_pdf

    r = client.post("/tontolo/documents",
                    files={"file": ("cours.pdf", tiny_pdf(["Un", "Deux"]), "application/pdf")})
    assert r.status_code == 200, r.text
    doc = r.json()
    assert doc["pages"] == 2
    cid = doc["conversation_id"]
    listed = client.get(f"/tontolo/conversations/{cid}/documents").json()
    assert [d["name"] for d in listed] == ["cours.pdf"] and "pages" not in listed[0]
    bad = client.post("/tontolo/documents",
                      files={"file": ("x.pdf", b"%PDF-xx", "application/pdf")})
    assert bad.status_code == 422


def test_folders_and_full_text_search(client: TestClient) -> None:
    ev = _events(client, "/tontolo/chat", {"content": "Recette du romazava 100% malgache"})
    cid = next(e["id"] for e in ev if e["type"] == "conversation")
    assert client.patch(f"/tontolo/conversations/{cid}", json={"folder": "Cuisine"}).json()["ok"]
    assert client.get("/tontolo/folders").json() == [{"folder": "Cuisine", "count": 1,
                                                       "shared": False}]
    in_folder = client.get("/tontolo/conversations", params={"folder": "Cuisine"}).json()
    assert [c["id"] for c in in_folder] == [cid] and in_folder[0]["folder"] == "Cuisine"
    hits = client.get("/tontolo/conversations", params={"q": "romazava"}).json()
    assert hits and "romazava" in hits[0]["snippet"].lower()
    # « % » cherché littéralement (pas comme joker SQL)
    assert client.get("/tontolo/conversations", params={"q": "100%"}).json()
    assert not client.get("/tontolo/conversations", params={"q": "%zz%"}).json()


def test_import_conversation_then_continue(client: TestClient) -> None:
    snap = {"snapshot_name": "Depuis Claude", "chat_messages": [
        {"sender": "human", "content": [{"type": "text", "text": "Ma question"}]},
        {"sender": "assistant", "content": [{"type": "text", "text": "Ma réponse"}]}]}
    r = client.post("/tontolo/import", json={"data": json.dumps(snap)})
    assert r.status_code == 200
    conv = r.json()["conversations"][0]
    assert conv["count"] == 2 and conv["source"] == "claude"
    msgs = client.get(f"/tontolo/conversations/{conv['id']}").json()["messages"]
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    with client.stream("POST", "/tontolo/chat", json={
            "conversation_id": conv["id"], "content": "Et la suite ?"}) as s:
        assert any('"done"' in line for line in s.iter_lines())
    r = client.post("/tontolo/import", json={
        "url": "https://claude.ai/chat/04393426-e2c1-4fce-a779-ad538512da66"})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "import_private"


def test_export_markdown_and_pdf(client: TestClient, tmp_path: Any) -> None:
    long = " ".join(["Réponse détaillée, très longue, avec des accents ôàè."] * 400)
    snap = {"snapshot_name": "Révision (export)", "chat_messages": [
        {"sender": "human", "content": [{"type": "text", "text": "Ma question 🚀 → ?"}]},
        {"sender": "assistant", "content": [{"type": "text", "text":
            f"## Titre\n\n- **point** un\n\n```python\nprint('(x)')\n```\n\n{long}"}]}]}
    cid = client.post("/tontolo/import", json={"data": json.dumps(snap)}).json()[
        "conversations"][0]["id"]
    md = client.get(f"/tontolo/conversations/{cid}/export")
    assert md.status_code == 200 and "**Vous**" in md.text and "## Titre" in md.text
    r = client.get(f"/tontolo/conversations/{cid}/export", params={"format": "pdf",
                                                                  "lang": "mg"})
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
    assert r.content.startswith(b"%PDF-") and r.content.rstrip().endswith(b"%%EOF")
    assert client.get(f"/tontolo/conversations/{cid}/export",
                      params={"format": "exe"}).status_code == 400
    if shutil.which("pdftotext"):
        f = tmp_path / "c.pdf"
        f.write_bytes(r.content)
        text = subprocess.run(["pdftotext", "-layout", str(f), "-"], capture_output=True,
                              text=True, check=True).stdout
        assert "Ianao" in text and "Ma question" in text and "print('(x)')" in text
        assert "accents ôàè" in text and "• point un" in text
        info = subprocess.run(["pdfinfo", str(f)], capture_output=True, text=True).stdout
        assert int(re.search(r"Pages:\s+(\d+)", info).group(1)) >= 3  # type: ignore[union-attr]


def test_learn_mode_is_kept_per_conversation(client: TestClient, fake: FakeProvider) -> None:
    with client.stream("POST", "/tontolo/chat", json={
            "content": "Explique-moi les fractions", "mode": "learn", "level": "college"}) as s:
        lines = list(s.iter_lines())
    cid = next(json.loads(x[5:])["id"] for x in lines if '"conversation"' in x)
    conv = client.get(f"/tontolo/conversations/{cid}").json()
    assert conv["mode"] == "learn:college"
    system = fake.last_messages[0]["content"]
    assert "mode Apprendre" in system and "collège" in system
    assert "language of the student's latest message" in system  # anglais → anglais
    # Message suivant sans « mode » : le mode de la discussion est conservé.
    with client.stream("POST", "/tontolo/chat", json={
            "conversation_id": cid, "content": "et 1/2 + 1/3 ?"}) as s:
        list(s.iter_lines())
    assert "mode Apprendre" in fake.last_messages[0]["content"]
    with client.stream("POST", "/tontolo/chat", json={
            "conversation_id": cid, "content": "merci", "mode": "general"}) as s:
        list(s.iter_lines())
    assert "mode Apprendre" not in fake.last_messages[0]["content"]
    assert client.post("/tontolo/chat", json={"content": "x", "mode": "hack"}).status_code == 422


def test_cloud_sync_whole_conversations(client: TestClient, tmp_path: Any) -> None:
    with client.stream("POST", "/tontolo/chat", json={"content": "Bonjour"}) as s:
        list(s.iter_lines())
    exported = client.get("/tontolo/cloud/export", params={"since": 0}).json()
    conv = exported["conversations"][0]
    assert [m["role"] for m in conv["messages"]] == ["user", "assistant"]
    # Même conversation, modifiée « ailleurs » : plus récente → remplace (sans doublons).
    newer = {**conv, "title": "Depuis le téléphone", "updated_at": conv["updated_at"] + 10,
             "messages": conv["messages"][:1]}
    assert client.post("/tontolo/cloud/import", json={"conversations": [newer]}).json()[
        "applied"] == 1
    got = client.get(f"/tontolo/conversations/{conv['id']}").json()["messages"]
    assert len(got) == 1
    # Version plus ancienne : ignorée ; élément illisible : ignoré.
    old = {**conv, "updated_at": conv["updated_at"] - 100}
    report = client.post("/tontolo/cloud/import", json={"conversations": [old, {"x": 1}]}).json()
    assert report["applied"] == 0 and report["rejected"] == 1 and report["reasons"]
    # Conversation à moitié invalide : refusée en entier, l'existante n'est jamais effacée.
    broken = {**newer, "updated_at": newer["updated_at"] + 10,
              "messages": [*conv["messages"][:1], {"uid": "x", "seq": "pas un nombre"}]}
    assert client.post("/tontolo/cloud/import", json={"conversations": [broken]}).json()[
        "rejected"] == 1
    assert len(client.get(f"/tontolo/conversations/{conv['id']}").json()["messages"]) == 1
    for bad in ({"id": "../x", "updated_at": 1, "created_at": 1},
                {"id": "a", "updated_at": -5, "created_at": 1},
                {"id": "a", "updated_at": 2, "created_at": 1, "messages": [
                    {"uid": "u", "seq": 0, "role": "admin", "body": "{}", "created_at": 1,
                     "updated_at": 1}]}):
        assert client.post("/tontolo/cloud/import", json={"conversations": [bad]}).json()[
            "rejected"] == 1
    assert client.get("/tontolo/cloud/export",
                      params={"since": exported["until"] + 20}).json()["conversations"] == []


def test_file_request_creates_downloadable_docx(client: TestClient,
                                                monkeypatch: pytest.MonkeyPatch) -> None:
    from tontolo.creator.service import CreatorService

    async def ask(self: Any, messages: Any, *, category: Any = None,
                  model: Any = None) -> tuple[str, str, str]:
        return "# Cours sur l'eau\n## Cycle\nTexte.", "fake:writer", "Rédacteur"

    async def pick(self: Any, *, exclude: str, vision: bool = False) -> None:
        return None

    monkeypatch.setattr(CreatorService, "ask", ask)
    monkeypatch.setattr(CreatorService, "pick_reviewer", pick)
    with client.stream("POST", "/tontolo/chat", json={
            "content": "Génère un fichier Word de 2 pages sur le cycle de l'eau pour des "
                       "collégiens"}) as s:
        events = [json.loads(x[5:]) for x in s.iter_lines() if x.startswith("data:")]
    steps = [e["step"] for e in events if e["type"] == "step"]
    assert steps[0] == "doc_writing" and steps[-1] == "doc_done"
    job = next(e for e in events if e["type"] == "done")["job"]
    assert job["status"] == "done" and job["params"]["filename"] == "cours-sur-l-eau.docx"
    r = client.get(f"/tontolo/media/{job['id']}/file")
    assert r.status_code == 200 and r.content[:2] == b"PK"
    assert client.post("/tontolo/chat", json={"content": "x", "category": "file:../x"}
                       ).status_code == 400


def test_math_answer_cross_checked_by_second_model(client: TestClient,
                                                   monkeypatch: pytest.MonkeyPatch) -> None:
    from tontolo.creator.service import CreatorService

    seen: dict[str, str] = {}

    async def review(self: Any, question: str, answer: str, writer: str,
                     context: str = "") -> dict[str, Any]:
        seen.update(question=question, writer=writer, context=context)
        return {"ok": False, "issues": ["erreur de signe"], "model": "fake:b", "name": "B"}

    monkeypatch.setattr(CreatorService, "review_answer", review)
    question = "Résous l'équation $x^2 - 4 = 0$ et détaille chaque étape du calcul, merci beaucoup"
    with client.stream("POST", "/tontolo/chat", json={"content": question}) as s:
        events = [json.loads(x[5:]) for x in s.iter_lines() if x.startswith("data:")]
    kinds = [e["type"] for e in events]
    assert kinds.index("done") < kinds.index("review")
    rev = next(e for e in events if e["type"] == "review")
    assert rev["ok"] is False and rev["issues"] == ["erreur de signe"]
    assert seen["question"] == question
    # Conversation courante (« salut ») : pas de vérification.
    with client.stream("POST", "/tontolo/chat", json={"content": "salut"}) as s:
        assert not any('"review"' in x for x in s.iter_lines())
    # Le relecteur voit les documents joints (sinon il prend leur contenu pour une invention).
    up = client.post("/tontolo/documents", files={"file": (
        "calc.py", b"def add(a, b):\n    return a + b  # fonction d'addition\n")}).json()
    with client.stream("POST", "/tontolo/chat", json={
            "conversation_id": up["conversation_id"],
            "content": "Démontre que la fonction add de calc.py calcule bien la somme, étape par "
                       "étape, avec une preuve mathématique rigoureuse"}) as s:
        list(s.iter_lines())
    assert "fonction d'addition" in seen["context"]


def test_animate_reuses_last_generated_image(client: TestClient, catalog_service: CatalogService,
                                             monkeypatch: pytest.MonkeyPatch) -> None:
    from tontolo.catalog.service import BUILTIN_PROVIDERS
    from tontolo.catalog.sources import hfspaces

    cat = catalog_service.catalog
    cat.providers["hf_spaces"] = BUILTIN_PROVIDERS["hf_spaces"]
    for m in hfspaces.models():
        cat.models[m.key] = m
    png = b"\x89PNG\r\n\x1a\nIMAGE-BAOBAB"
    seen: dict[str, Any] = {}

    async def fake_image(model: Any, provider: Any, prompt: str, params: Any) -> mp.MediaOutput:
        return mp.MediaOutput(png, "image/png")

    async def fake_video(model: Any, prompt: str, params: Any) -> mp.MediaOutput:
        seen["image"] = params.get("image_bytes")
        return mp.MediaOutput(b"\x00\x00\x00\x18ftypmp42", "video/mp4")

    async def same(core: Any, text: str) -> str:
        return text

    monkeypatch.setattr(mp, "generate_image", fake_image)
    monkeypatch.setattr(mp, "generate_video", fake_video)
    monkeypatch.setattr("tontolo.server.common._english_prompt", same)
    with client.stream("POST", "/tontolo/chat", json={
            "content": "Dessine un baobab au coucher du soleil"}) as s:
        events = [json.loads(x[5:]) for x in s.iter_lines() if x.startswith("data:")]
    cid = next(e["id"] for e in events if e["type"] == "conversation")
    with client.stream("POST", "/tontolo/chat", json={"conversation_id": cid,
                                                      "content": "anime-la"}) as s:
        events = [json.loads(x[5:]) for x in s.iter_lines() if x.startswith("data:")]
    job = next(e for e in events if e["type"] == "done")["job"]
    assert job["kind"] == "video_gen" and seen["image"] == png
    source_id = job["params"]["source_job_id"]
    assert source_id and job["params"]["input_mode"] == "image"
    # Régénérer garde la même source, même après une réponse vidéo.
    with client.stream("POST", f"/tontolo/chat/{cid}/regenerate", json={"approved": True}) as s:
        replay = [json.loads(x[5:]) for x in s.iter_lines() if x.startswith("data:")]
    retry_job = _last_done(replay)["job"]
    assert retry_job["params"]["source_job_id"] == source_id and seen["image"] == png
    # Une nouvelle scène vidéo ne doit pas reprendre le baobab.
    events = _chat_events(client, cid, "Create a video of a whale swimming in the ocean")
    assert _last_done(events)["job"]["params"]["input_mode"] == "text"
    assert seen["image"] is None


def test_revision_of_last_file_keeps_format_and_previous_version(
        client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from tontolo.creator.service import CreatorService

    asked: list[str] = []
    outline = {"title": "Analyse fonctionnelle", "children": [
        {"label": "Besoin", "children": [{"label": "bête à cornes"}]},
        {"label": "Fonctions", "children": [{"label": "FP / FC"}]}]}

    async def ask(self: Any, messages: Any, *, category: Any = None,
                  model: Any = None) -> tuple[str, str, str]:
        asked.append(str(messages[-1]["content"]))
        return json.dumps(outline), "fake:w", "W"

    async def pick(self: Any, *, exclude: str, vision: bool = False) -> None:
        return None

    async def render(data: Any) -> tuple[bytes, str]:
        return b"\x89PNG\r\n\x1a\n" + b"\x00" * 16, "test"

    from tontolo.creator import diagram
    monkeypatch.setattr(CreatorService, "ask", ask)
    monkeypatch.setattr(CreatorService, "pick_reviewer", pick)
    monkeypatch.setattr(diagram, "render_mindmap", render)

    def chat(payload: dict[str, Any]) -> list[dict[str, Any]]:
        with client.stream("POST", "/tontolo/chat", json=payload) as s:
            return [json.loads(x[5:]) for x in s.iter_lines() if x.startswith("data:")]

    first = chat({"content": "Fais une carte mentale sur l'analyse fonctionnelle"})
    cid = next(e["id"] for e in first if e["type"] == "conversation")
    second = chat({"conversation_id": cid, "content": "rajoute des détails et des exemples"})
    job = next(e for e in second if e["type"] == "done")["job"]
    assert job["kind"] == "file_gen" and job["params"]["format"] == "mindmap"
    assert job["params"]["revision"] is True
    assert "bête à cornes" in asked[-1] and "rajoute des détails" in asked[-1]
    # Une question après le fichier reste une discussion normale.
    third = chat({"conversation_id": cid, "content": "c'est quoi une fonction contrainte ?"})
    assert not any(e["type"] == "step" for e in third)


def test_tool_loop_ends_with_an_answer_not_an_error(client: TestClient,
                                                    monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def answer(self: FakeProvider, model: Any, messages: list[dict[str, Any]]) -> dict[str, Any]:
        last = messages[-1]
        if last["role"] == "system" and "Assez d'outils" in str(last["content"]):
            return {"role": "assistant", "content": "Voici les sites : A, B et C."}
        calls.append("tool")
        return {"role": "assistant", "content": "", "tool_calls": [{
            "id": f"c{len(calls)}", "type": "function",
            "function": {"name": "calculator", "arguments": '{"expression": "1+1"}'}}]}

    monkeypatch.setattr(FakeProvider, "_answer", answer)
    with client.stream("POST", "/tontolo/chat", json={
            "content": "Existe-t-il des sites pour créer des portfolios ?"}) as s:
        events = [json.loads(x[5:]) for x in s.iter_lines() if x.startswith("data:")]
    assert not any(e["type"] == "error" for e in events)
    done = [e for e in events if e["type"] == "done"]
    assert done[-1]["message"]["content"] == "Voici les sites : A, B et C."
    results = [e for e in events if e["type"] == "tool_result"]
    assert len(results) >= 2 and "déjà effectué" in results[-1]["preview"]  # pas de répétition


def test_photo_plus_pdf_request_reads_the_photo_first(client: TestClient,
                                                      monkeypatch: pytest.MonkeyPatch) -> None:
    from tontolo.creator import latex
    from tontolo.creator.service import CreatorService

    prompts: list[Any] = []

    async def ask(self: Any, messages: Any, *, category: Any = None,
                  model: Any = None) -> tuple[str, str, str]:
        prompts.append(messages[-1]["content"])
        if isinstance(messages[-1]["content"], list):  # transcription de la photo
            return "Exercice 8. Calculer la transformée de Laplace de t e^{-2t}.", "v:x", "V"
        return ("\\documentclass{article}\\title{Exercice 8}\\begin{document}F(p)=1/(p+2)^2"
                "\\end{document}"), "w:x", "W"

    async def pick(self: Any, *, exclude: str, vision: bool = False) -> None:
        return None

    async def compile_pdf(source: str) -> tuple[bytes, str, str]:
        return b"%PDF-1.7 test", "", "test"

    monkeypatch.setattr(CreatorService, "ask", ask)
    monkeypatch.setattr(CreatorService, "pick_reviewer", pick)
    monkeypatch.setattr(latex, "compile_pdf", compile_pdf)
    content = [{"type": "text", "text": "traite l'exercice 8, rends la réponse en pdf"},
               {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,/9j/AA=="}}]
    with client.stream("POST", "/tontolo/chat", json={"content": content}) as s:
        events = [json.loads(x[5:]) for x in s.iter_lines() if x.startswith("data:")]
    steps = [e["step"] for e in events if e["type"] == "step"]
    assert steps[0] == "doc_reading"
    job = next(e for e in events if e["type"] == "done")["job"]
    assert job["kind"] == "file_gen" and job["params"]["mime"] == "application/pdf"
    assert "Laplace" in str(prompts[1])  # le rédacteur travaille sur la transcription



def test_animation_without_image_reports_missing_reference(client: TestClient) -> None:
    events = _chat_events(client, "missing-image", "anime-la")
    assert any(e.get("code") == "media_reference_missing" for e in events)
    assert not any(e["type"] == "job" for e in events)


def test_invalid_attached_image_rejected_before_detached_turn(client: TestClient) -> None:
    r = client.post('/tontolo/chat', json={"category": "video_gen", "content": [
        {"type": "text", "text": "anime-la"},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,???"}}]})
    assert r.status_code == 400


def test_html_document_converted_to_pdf_uses_its_content(
        client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Bug mobile 0.5.0 : « convertis ce HTML en PDF » ne transmettait pas le HTML joint."""
    from tontolo.creator import latex
    from tontolo.creator.service import CreatorService

    seen: list[str] = []

    async def ask(self: Any, messages: Any, *, category: Any = None,
                  model: Any = None) -> tuple[str, str, str]:
        seen.append(str(messages[-1]["content"]))
        return ("\\documentclass{article}\\title{Baobabs}\\begin{document}Baobabs de "
                "Morondava\\end{document}", "fake:writer", "Rédacteur")

    async def pick(self: Any, *, exclude: str, vision: bool = False) -> None:
        return None

    async def compile_pdf(source: str) -> tuple[bytes, str, str]:
        return b"%PDF-1.7", "", "local"

    monkeypatch.setattr(CreatorService, "ask", ask)
    monkeypatch.setattr(CreatorService, "pick_reviewer", pick)
    monkeypatch.setattr(latex, "compile_pdf", compile_pdf)
    page = (b"<!doctype html><html><body><h1>Les baobabs</h1>"
            b"<p>Avenue de Morondava</p></body></html>")
    doc = client.post("/tontolo/documents",
                      files={"file": ("page.html", page, "text/html")}).json()
    events = _events(client, "/tontolo/chat", {"conversation_id": doc["conversation_id"],
                                                "content": "convertis ce html en pdf"})
    job = next(e for e in events if e["type"] == "done")["job"]
    assert job["status"] == "done" and job["params"]["mime"] == "application/pdf"
    assert "Avenue de Morondava" in seen[0] and "page.html" in seen[0]
    drafts = client.get(f"/tontolo/conversations/{doc['conversation_id']}/tasks").json()
    assert drafts[0]["kind"] == "draft" and drafts[0]["title"].startswith("baobabs.pdf")


def test_home_name_and_recent(client: TestClient) -> None:
    core = client.app.state.core  # type: ignore[attr-defined]
    assert client.get("/tontolo/home").json() == {"name": "", "name_from": "", "recent": []}

    async def setup() -> None:
        await core.db.add_memory("L'utilisateur s'appelle Antsa", "explicit", None)
        await core.db.create_conversation("Révision des probabilités")

    client.portal.call(setup)  # type: ignore[attr-defined]
    home = client.get("/tontolo/home").json()
    assert home["name"] == "Antsa" and home["name_from"] == "memory"
    assert home["recent"][0]["title"] == "Révision des probabilités"
    client.put("/tontolo/settings", json={"user_name": "Antsa Malala"})
    assert client.get("/tontolo/home").json()["name_from"] == "settings"


def test_versions_never_share_a_filename(client: TestClient,
                                         monkeypatch: pytest.MonkeyPatch) -> None:
    from tontolo.creator.service import CreatorService

    async def ask(self: Any, messages: Any, *, category: Any = None, model: Any = None,
                  limit: float = 0) -> tuple[str, str, str]:
        return "# Cours sur l'eau\n## Cycle\nTexte.", "fake:writer", "Rédacteur"

    async def pick(self: Any, *, exclude: str, vision: bool = False) -> None:
        return None

    monkeypatch.setattr(CreatorService, "ask", ask)
    monkeypatch.setattr(CreatorService, "pick_reviewer", pick)
    first = _events(client, "/tontolo/chat",
                    {"content": "Génère un fichier Word court sur l'eau pour des élèves"})
    cid = next(e["id"] for e in first if e["type"] == "conversation")
    names = [next(e for e in first if e["type"] == "done")["job"]["params"]["filename"]]
    for text in ("rajoute des exemples", "excellent mais des vraies citations"):
        ev = _events(client, "/tontolo/chat", {"conversation_id": cid, "content": text})
        job = next(e for e in ev if e["type"] == "done")["job"]
        names.append(job["params"]["filename"])
        assert job["params"]["revision"] is True  # corrigé, pas recréé de zéro
    assert names == ["cours-sur-l-eau.docx", "cours-sur-l-eau-v2.docx", "cours-sur-l-eau-v3.docx"]


def test_feedback_after_a_failed_revision_starts_from_the_last_good_file(
        client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Cas réel (essai de bout en bout) : la 1re correction échoue, « excellent mais plus
    court » partait en discussion au lieu de reprendre la dernière version livrée."""
    from tontolo.creator.pipeline import CreationError
    from tontolo.creator.service import CreatorService

    state = {"n": 0}

    async def ask(self: Any, messages: Any, *, category: Any = None, model: Any = None,
                  limit: float = 0) -> tuple[str, str, str]:
        state["n"] += 1
        if state["n"] in (2, 3, 4, 5, 6):  # la correction échoue (et ses reprises)
            raise CreationError("modèle indisponible")
        return "# Cours sur l'eau\n## Cycle\nTexte du cours.", "fake:writer", "Rédacteur"

    async def pick(self: Any, *, exclude: str, vision: bool = False) -> None:
        return None

    monkeypatch.setattr(CreatorService, "ask", ask)
    monkeypatch.setattr(CreatorService, "pick_reviewer", pick)
    first = _events(client, "/tontolo/chat",
                    {"content": "Génère un fichier Word court sur l'eau pour des élèves"})
    cid = next(e["id"] for e in first if e["type"] == "conversation")
    failed = _events(client, "/tontolo/chat", {"conversation_id": cid,
                                                "content": "rajoute un exercice"})
    assert next(e for e in failed if e["type"] == "done")["job"]["status"] == "failed"
    state["n"] = 10
    ok = _events(client, "/tontolo/chat", {"conversation_id": cid,
                                            "content": "excellent mais plus court"})
    job = next(e for e in ok if e["type"] == "done")["job"]
    assert job["status"] == "done" and job["params"]["revision"] is True


def test_long_thread_loads_by_window(client: TestClient) -> None:
    core = client.app.state.core  # type: ignore[attr-defined]
    first = _events(client, "/tontolo/chat", {"content": "début"})
    cid = next(e["id"] for e in first if e["type"] == "conversation")

    async def fill() -> None:
        for i in range(150):
            await core.db.add_message(cid, {"role": "user", "content": f"q{i}"})
            await core.db.add_message(cid, {"role": "tool", "name": "x", "content": f"t{i}",
                                            "tool_call_id": str(i)})
            await core.db.add_message(cid, {"role": "assistant", "content": f"r{i}"})

    client.portal.call(fill)  # type: ignore[attr-defined]
    total = 2 + 450
    last = client.get(f"/tontolo/conversations/{cid}", params={"tail": 100}).json()
    assert last["total"] == total and last["messages"][0]["role"] == "user"
    assert last["messages"][-1]["_meta"]["seq"] == total and len(last["messages"]) <= 100
    older = client.get(f"/tontolo/conversations/{cid}", params={
        "tail": 100, "before": last["messages"][0]["_meta"]["seq"]}).json()
    assert older["messages"][-1]["_meta"]["seq"] < last["messages"][0]["_meta"]["seq"]
    seqs = [m["_meta"]["seq"] for m in older["messages"] + last["messages"]]
    assert seqs == sorted(set(seqs))  # aucun doublon ni trou à la jonction (sauf début de tour)
    assert len(client.get(f"/tontolo/conversations/{cid}").json()["messages"]) == total


def test_vague_creation_asks_first_then_resumes(client: TestClient,
                                                monkeypatch: pytest.MonkeyPatch) -> None:
    """« Écris un rapport sur l'eau » : public et longueur demandés d'abord (sans modèle), puis
    la réponse relance la création avec la demande complétée."""
    from tontolo.creator.service import CreatorService

    seen: list[str] = []

    async def ask(self: Any, messages: Any, *, category: Any = None,
                  model: Any = None, **_: Any) -> tuple[str, str, str]:
        seen.append(str(messages[-1]["content"]))
        return "# Rapport sur l'eau\n## Cycle\nTexte.", "fake:writer", "Rédacteur"

    async def pick(self: Any, *, exclude: str, vision: bool = False) -> None:
        return None

    monkeypatch.setattr(CreatorService, "ask", ask)
    monkeypatch.setattr(CreatorService, "pick_reviewer", pick)
    first = _events(client, "/tontolo/chat", {"content": "Écris un rapport Word sur l'eau"})
    q = next(e for e in first if e["type"] == "question")
    assert [x["question"] for x in q["questions"]] == ["Pour quel public ?", "Quelle longueur ?"]
    assert not seen  # aucune rédaction avant la réponse
    cid = q["conversation_id"]
    reopened = client.get(f"/tontolo/conversations/{cid}").json()["messages"]
    assert any(c["function"]["name"] == "ask_user"
               for m in reopened for c in m.get("tool_calls") or [])
    answer = "Pour quel public ? → Élèves\nQuelle longueur ? → Courte (1-2 pages)"
    second = _events(client, "/tontolo/chat", {"conversation_id": cid, "content": answer})
    job = next(e for e in second if e["type"] == "done")["job"]
    assert job["status"] == "done"
    assert any("rapport Word sur l'eau" in x and "Élèves" in x for x in seen)
    # Déjà précisé, en anglais : aucune question.
    direct = _events(client, "/tontolo/chat",
                     {"content": "Write a 3 pages Word report about water for students"})
    assert not any(e["type"] == "question" for e in direct)


def test_clarify_questions_by_language() -> None:
    from tontolo.creator.clarify import questions_for

    assert questions_for("docx", "Manorata tatitra momba ny rano azafady")[0]["question"] == (
        "Ho an'iza?")
    assert questions_for("book", "Write a book about the history of maths")[1]["options"][0] == (
        "10 pages")
    assert questions_for("docx", "convertis ce html en pdf") == []
    assert questions_for("text:py", "écris un script python") == []


def test_clarify_follows_the_request_language_not_the_interface() -> None:
    from tontolo.creator.clarify import language_of, questions_for

    assert language_of("Ecris un rapport Word sur la pollution", "mg") == "fr"
    assert language_of("Write a report about pollution", "fr") == "en"
    assert language_of("Manorata tatitra momba ny fandotoana", "fr") == "mg"
    assert language_of("Word pollution", "mg") == "mg"  # rien de net : langue de l'interface
    assert questions_for("docx", "Ecris un rapport Word sur la pollution", "mg")[0][
        "question"] == "Pour quel public ?"


def test_answers_endpoints(client: TestClient) -> None:
    info = client.get("/tontolo/answers").json()
    assert info == {"enabled": True, "count": 0}
    assert client.delete("/tontolo/answers").json() == {"removed": 0}
    off = client.put("/tontolo/settings", json={"answer_cache": False}).json()
    assert off["answer_cache"] is False


def test_feedback_endpoints(client: TestClient) -> None:
    ev = _events(client, "/tontolo/chat", {"content": "Dis bonjour"})
    done = next(e for e in ev if e["type"] == "done")
    cid = done["conversation_id"]
    r = client.post("/tontolo/feedback", json={"uid": done["uid"], "rating": -1,
                                                "reason": "too_long"})
    assert r.status_code == 200 and r.json()["rating"] == -1 and r.json()["model"]
    assert client.get(f"/tontolo/conversations/{cid}").json()["feedback"] == {done["uid"]: -1}
    assert client.post("/tontolo/feedback", json={"uid": "0" * 32, "rating": 1}).status_code == 404
    for bad in ({"uid": "../x", "rating": 1}, {"uid": done["uid"], "rating": 5},
                {"uid": done["uid"], "rating": 1, "reason": "<script>"}):
        assert client.post("/tontolo/feedback", json=bad).status_code in (400, 422)
    kept = client.put("/tontolo/feedback/global", json={"scores": [
        {"model": done["model"], "category": "chat", "score": 0.5, "devices": 9}]}).json()
    assert kept == {"kept": 1}


def test_any_attachment_type(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    import io
    import shutil
    import zipfile

    from tontolo.media.service import MediaService

    sent: list[str] = []

    async def submit(self: Any, kind: str, prompt: str = "", **kw: Any) -> dict[str, Any]:
        sent.append(f"{kind}:{kw.get('input_name')}")
        return {"id": "j1"}

    async def wait(self: Any, job_id: str, *a: Any, **k: Any) -> dict[str, Any]:
        return {"status": "done", "params": {"text": "Bonjour à tous, voici la leçon."}}

    monkeypatch.setattr(MediaService, "submit", submit)
    monkeypatch.setattr(MediaService, "wait", wait)
    monkeypatch.setattr(shutil, "which", lambda exe: None)  # sans ffmpeg : envoyée telle quelle
    for name in ("cours.m4a", "clip.mp4"):
        r = client.post("/tontolo/documents", files={"file": (name, b"\x00\x01media")})
        assert r.status_code == 200, r.text
        doc = client.get(f"/tontolo/conversations/{r.json()['conversation_id']}/documents").json()
        assert doc[0]["name"] == name
    assert sent == ["stt:cours.m4a", "stt:clip.mp4"]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("notes.md", "# Notes\nPhotosynthèse")
    r = client.post("/tontolo/documents", files={"file": ("cours.zip", buf.getvalue())})
    assert r.status_code == 200 and r.json()["pages"] == 2
    bad = client.post("/tontolo/documents", files={"file": ("x.docx", b"pas un zip")})
    assert bad.status_code == 422

    async def fail(self: Any, job_id: str, *a: Any, **k: Any) -> dict[str, Any]:
        return {"status": "failed", "error": "quota", "params": {}}

    monkeypatch.setattr(MediaService, "wait", fail)
    r = client.post("/tontolo/documents", files={"file": ("x.mp3", b"\x00audio")})
    assert r.status_code == 422 and "Transcription impossible" in r.text


@pytest.mark.skipif(not (shutil.which("ffmpeg") and shutil.which("ffprobe")),
                    reason="ffmpeg absent")
def test_video_keyframes_described_even_without_sound(client: TestClient, tmp_path: Any,
                                                      monkeypatch: pytest.MonkeyPatch) -> None:
    from tontolo.creator.service import CreatorService
    from tontolo.media.service import MediaService

    clip = tmp_path / "cours.mp4"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i",
                    "testsrc=duration=8:size=320x240:rate=10", "-pix_fmt", "yuv420p", str(clip)],
                   check=True)
    seen: list[Any] = []

    async def ask(self: Any, messages: Any, **kw: Any) -> tuple[str, str, str]:
        seen.append((messages[-1]["content"], kw.get("category")))
        return "[0:01] Mire de couleurs avec un compteur.\n[0:07] Même mire.", "v:x", "V"

    async def submit(self: Any, kind: str, prompt: str = "", **kw: Any) -> dict[str, Any]:
        return {"id": "j1"}

    async def silent(self: Any, job_id: str, *a: Any, **k: Any) -> dict[str, Any]:
        return {"status": "failed", "error": "aucune piste son", "params": {}}

    monkeypatch.setattr(CreatorService, "ask", ask)
    monkeypatch.setattr(MediaService, "submit", submit)
    monkeypatch.setattr(MediaService, "wait", silent)
    r = client.post("/tontolo/documents", files={"file": ("cours.mp4", clip.read_bytes())})
    assert r.status_code == 200, r.text
    content, category = seen[0]
    images = [p for p in content if p["type"] == "image_url"]
    assert len(images) == 4 and str(category) == "vision"
    assert images[0]["image_url"]["url"].startswith("data:image/jpeg;base64,/9j/")
    assert "0:01, 0:03, 0:05, 0:07" in content[0]["text"]
    assert r.json()["pages"] == 1  # pas de transcription : seulement les images clés


def test_video_frames_from_the_app_are_used(client: TestClient,
                                            monkeypatch: pytest.MonkeyPatch) -> None:
    """Android (sans ffmpeg) : les images clés extraites par l'application sont décrites ;
    une pièce qui n'est pas un JPEG est ignorée."""
    import shutil

    from tontolo.creator.service import CreatorService
    from tontolo.media.service import MediaService

    seen: list[Any] = []

    async def ask(self: Any, messages: Any, **kw: Any) -> tuple[str, str, str]:
        seen.append(messages[-1]["content"])
        return "[0:02] Un tableau noir avec a² + b² = c².", "v:x", "V"

    async def submit(self: Any, kind: str, prompt: str = "", **kw: Any) -> dict[str, Any]:
        return {"id": "j1"}

    async def heard(self: Any, job_id: str, *a: Any, **k: Any) -> dict[str, Any]:
        return {"status": "done", "params": {"text": "Aujourd'hui, Pythagore."}}

    monkeypatch.setattr(CreatorService, "ask", ask)
    monkeypatch.setattr(MediaService, "submit", submit)
    monkeypatch.setattr(MediaService, "wait", heard)
    monkeypatch.setattr(shutil, "which", lambda exe: None)
    jpg = b"\xff\xd8\xff\xe0" + b"\x00" * 64
    r = client.post("/tontolo/documents", data={"frame_times": "2.5,7.5,9"},
                    files=[("file", ("cours.mp4", b"\x00\x01video")),
                           ("frames", ("f0.jpg", jpg)), ("frames", ("f1.jpg", jpg)),
                           ("frames", ("x.png", b"\x89PNG\r\n"))])
    assert r.status_code == 200, r.text
    assert r.json()["pages"] == 2  # transcription + images clés
    images = [p for p in seen[0] if p["type"] == "image_url"]
    assert len(images) == 2 and "0:02, 0:07" in seen[0][0]["text"]


def test_event_websocket_connection_cap(client: TestClient) -> None:
    from starlette.websockets import WebSocketDisconnect

    from tontolo.server import common as server

    opened = []
    for _ in range(server.WS_MAX_CLIENTS):
        ws = client.websocket_connect("/tontolo/ws")
        opened.append(ws.__enter__())
    with pytest.raises(WebSocketDisconnect), client.websocket_connect("/tontolo/ws") as extra:
        extra.receive_text()
    for ws in opened:
        ws.__exit__(None, None, None)


async def test_long_document_material_uses_the_compact_digest(client: TestClient) -> None:
    from tontolo.server.common import _file_material

    pages = [f"Chapitre {c} Sujet {c}\nOn appelle concept{c} une idée du chapitre {c}. "
             + "Remplissage du chapitre. " * 400 for c in range(1, 41)]
    text = "\n\n".join(pages).encode()
    up = client.post("/tontolo/documents", files={"file": ("livre.txt", text)}).json()
    core = client.app.state.core  # type: ignore[attr-defined]
    docs = await core.db.list_documents(up["conversation_id"], with_pages=True)
    assert docs[0]["digest"].startswith("Fiche compacte")
    material = await _file_material(core, up["conversation_id"], request="concept37")
    assert "Chapitre 40 Sujet 40" in material  # tout le livre, pas seulement le début
    assert "concept37" in material and len(material) <= 36000
    listed = client.get(f"/tontolo/conversations/{up['conversation_id']}/documents").json()
    assert "digest" not in listed[0]  # liste légère pour l'application


def test_api_docs_are_up_to_date_and_docs_pages_are_off(client: TestClient) -> None:
    """docs/API.md reflète toutes les routes (régénérer : scripts/api_docs.py) ; pas de /docs
    (page chargée depuis un CDN externe)."""
    import runpy
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    render = runpy.run_path(str(root / "scripts" / "api_docs.py"))["render"]
    assert (root / "docs" / "API.md").read_text(encoding="utf-8") == render(), (
        "docs/API.md est à régénérer : cd core && uv run python ../scripts/api_docs.py")
    assert client.get("/docs").status_code == 404 and client.get("/redoc").status_code == 404
    assert "/tontolo/chat" in client.get("/openapi.json").json()["paths"]


def test_local_metrics(client: TestClient) -> None:
    from tontolo import metrics

    metrics.reset()
    _events(client, "/tontolo/chat", {"content": "Bonjour"})
    text = client.get("/tontolo/metrics").text
    assert "tontolo_turns_total 1" in text
    assert 'tontolo_model_calls_total{model="fake:' in text and 'result="ok"' in text
    assert "tontolo_uptime_seconds" in text and "tontolo_models_usable" in text
    assert "Bonjour" not in text  # aucun contenu de discussion
