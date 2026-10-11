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
    assert "Impossible gratuitement" in job["error"] and "sur votre téléphone" in job["error"]


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
    from tontolo.server.app import _english_prompt

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
    assert client.get("/tontolo/folders").json() == [{"folder": "Cuisine", "count": 1}]
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
