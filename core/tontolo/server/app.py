"""Serveur FastAPI : API compatible OpenAI (`/v1/*`), API native (`/tontolo/*`) et
WebSocket d'événements (bascules, nouveautés, jobs médias).

Le même serveur tourne embarqué dans l'application (127.0.0.1, mode local)
ou sur une machine Linux (mode client-serveur, jeton obligatoire).
"""

from __future__ import annotations

import asyncio
import base64
import hmac
import json
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile, WebSocket
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from pydantic import BaseModel

from tontolo import __version__, secrets
from tontolo.agent.loop import dumps
from tontolo.agent.mcp_client import load_config, save_config
from tontolo.app_state import Core
from tontolo.catalog.models import Category, ModelInfo
from tontolo.config import Settings, load_settings, save_settings
from tontolo.providers.registry import ProviderRegistry
from tontolo.router.classifier import classify
from tontolo.security import LOOPBACK_NAMES, host_of, key_allowed, origin_allowed
from tontolo.update import check_update, download_update

LOOPBACK = {"127.0.0.1", "::1", "localhost"}
MEDIA_TURN_KINDS = {"image_gen", "image_edit", "tts", "music_sfx", "video_gen"}


MAX_UPLOAD_BYTES = 25 * 1024 * 1024


async def _read_limited(file: UploadFile) -> bytes:
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "Fichier trop volumineux (25 Mo maximum)")
    return data


def _first_image(content: Any) -> bytes | None:
    """Première image jointe (data URL) d'un message, pour l'édition d'image."""
    if not isinstance(content, list):
        return None
    for part in content:
        url = (part.get("image_url") or {}).get("url", "") if isinstance(part, dict) else ""
        if url.startswith("data:") and "," in url:
            return base64.b64decode(url.split(",", 1)[1])
    return None


class ChatBody(BaseModel):
    conversation_id: str | None = None
    content: str | list[dict[str, Any]]
    model: str | None = None
    category: str | None = None
    strict: bool = False
    use_tools: bool = True


class EditBody(BaseModel):
    seq: int
    content: str
    model: str | None = None


class PinBody(BaseModel):
    pinned: bool


class MemoryBody(BaseModel):
    text: str
    kind: str = "fact"


class ResumeBody(BaseModel):
    approved: bool
    model: str | None = None


class RenameBody(BaseModel):
    title: str


class PrefBody(BaseModel):
    scope: str = "global"            # global | conversation | category
    scope_key: str = ""
    model: str | None = None         # None ou « auto » : retour en Auto
    strict: bool = False


class KeyBody(BaseModel):
    key: str
    persist: bool = True
    validate_key: bool = True   # l'application renvoie ses clés au démarrage sans revalider


class MediaBody(BaseModel):
    kind: str
    prompt: str = ""
    model: str | None = None
    conversation_id: str | None = None
    params: dict[str, Any] = {}


class Hub:
    """Diffusion des événements aux clients WebSocket."""

    def __init__(self) -> None:
        self.queues: set[asyncio.Queue[dict[str, Any]]] = set()

    def publish(self, event: dict[str, Any]) -> None:
        for q in list(self.queues):
            if q.qsize() < 200:
                q.put_nowait(event)


def create_app(
    settings: Settings | None = None, *, registry: ProviderRegistry | None = None,
    refresh: bool = True,
) -> FastAPI:
    hub = Hub()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        core = await Core.start(settings, registry=registry, refresh=refresh)
        app.state.core = core
        core.catalog.on_changes(lambda ch: hub.publish({"type": "catalog_changes",
                                                        "changes": ch}))
        core.media.on_event(hub.publish)
        yield
        await core.stop()

    app = FastAPI(title="Tontolo", version=__version__, lifespan=lifespan)
    app.state.hub = hub

    def core_of(request: Request | WebSocket) -> Core:
        c: Core = request.app.state.core
        return c

    @app.middleware("http")
    async def auth(request: Request, call_next: Any) -> Response:
        core: Core | None = getattr(request.app.state, "core", None)
        token = core.settings.server.token if core else None
        # Anti-CSRF : une page web ne peut pas piloter le serveur local.
        if not origin_allowed(request.headers.get("origin")):
            return JSONResponse({"error": {"message": "Origine refusée"}}, status_code=403)
        # Anti-DNS rebinding : en écoute locale, seul un Host de boucle locale est accepté.
        bind = core.settings.server.host if core else "127.0.0.1"
        if bind in LOOPBACK and host_of(request.headers.get("host", "")) not in LOOPBACK_NAMES:
            return JSONResponse({"error": {"message": "Hôte refusé"}}, status_code=403)
        if token and request.url.path not in ("/health",):
            given = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
            if not hmac.compare_digest(given, token):
                return JSONResponse({"error": {"message": "Jeton invalide"}}, status_code=401)
        response: Response = await call_next(request)
        return response

    # --- Santé -----------------------------------------------------------

    @app.get("/health")
    async def health(request: Request) -> dict[str, Any]:
        core = core_of(request)
        return {"status": "ok", "version": __version__,
                "models": len(core.catalog.catalog.models),
                "catalog_updated_at": core.catalog.catalog.updated_at}

    # --- API compatible OpenAI -------------------------------------------

    @app.get("/v1/models")
    async def v1_models(request: Request) -> dict[str, Any]:
        core = core_of(request)
        usable = core.catalog.usable_providers()
        data = [{"id": "auto", "object": "model", "created": 0, "owned_by": "tontolo"}]
        for m in core.catalog.catalog.models.values():
            if m.provider in usable and (m.is_free or core.settings.paid.fallback != "off"):
                data.append({"id": m.key, "object": "model", "created": int(m.created or 0),
                             "owned_by": m.provider})
        return {"object": "list", "data": data}

    @app.post("/v1/chat/completions")
    async def v1_chat(request: Request) -> Any:
        core = core_of(request)
        body = await request.json()
        messages = body.get("messages") or []
        if not messages:
            raise HTTPException(400, "messages requis")
        stream = bool(body.get("stream"))
        params = {k: body[k] for k in ("temperature", "max_tokens", "top_p", "stop",
                                       "response_format", "tool_choice", "seed") if k in body}
        gen = core.router.run(messages, tools=body.get("tools"), stream=stream,
                              model=body.get("model"), params=params)
        cid = f"chatcmpl-{uuid.uuid4().hex[:24]}"
        created = int(time.time())
        if not stream:
            final: dict[str, Any] | None = None
            switches = []
            async for ev in gen:
                if ev["type"] == "done":
                    final = ev
                elif ev["type"] == "model_switched":
                    switches.append(ev)
                elif ev["type"] in ("error", "paid_confirmation"):
                    return JSONResponse({"error": {"message": ev.get("message")
                                                   or "Confirmation de paiement requise",
                                                   "type": ev["type"]}}, status_code=503)
            if final is None:
                raise HTTPException(503, "Aucun modèle disponible")
            return {
                "id": cid, "object": "chat.completion", "created": created,
                "model": final["model"],
                "choices": [{"index": 0, "message": final["message"],
                             "finish_reason": final.get("finish_reason") or (
                                 "tool_calls" if final["message"].get("tool_calls")
                                 else "stop")}],
                "usage": final.get("usage") or {},
                "tontolo": {"switches": switches, "profile": final.get("profile")},
            }

        async def sse() -> AsyncIterator[str]:
            model = "auto"
            async for ev in gen:
                t = ev["type"]
                if t == "route":
                    model = ev["model"]
                    yield f": tontolo route {model}\n\n"
                elif t == "delta":
                    delta = {k: v for k, v in ev.items() if k != "type"}
                    chunk = {"id": cid, "object": "chat.completion.chunk", "created": created,
                             "model": model, "choices": [{"index": 0, "delta": delta,
                                                          "finish_reason": None}]}
                    yield f"data: {dumps(chunk)}\n\n"
                elif t in ("model_switched", "stream_reset", "model_returned"):
                    if t == "model_switched":
                        model = ev["to"]
                    yield f"data: {dumps({'id': cid, 'object': 'tontolo.event', **ev})}\n\n"
                elif t == "done":
                    fr = "tool_calls" if ev["message"].get("tool_calls") else "stop"
                    chunk = {"id": cid, "object": "chat.completion.chunk", "created": created,
                             "model": ev["model"], "choices": [{"index": 0, "delta": {},
                                                                "finish_reason": fr}],
                             "usage": ev.get("usage") or None}
                    yield f"data: {dumps(chunk)}\n\n"
                elif t in ("error", "paid_confirmation"):
                    err = {"error": {"message": ev.get("message") or
                                     "Confirmation de paiement requise", "type": t}}
                    yield f"data: {dumps(err)}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(sse(), media_type="text/event-stream")

    @app.post("/v1/images/generations")
    async def v1_images(request: Request) -> Any:
        core = core_of(request)
        body = await request.json()
        job = await core.media.submit("image_gen", body.get("prompt", ""),
                                      model=body.get("model"),
                                      params={k: body[k] for k in ("size", "seed",
                                                                   "aspect_ratio") if k in body})
        done = await core.media.wait(job["id"])
        if not done or done["status"] != "done":
            return JSONResponse({"error": {"message": (done or {}).get("error")}},
                                status_code=503)
        data = Path(done["result_path"]).read_bytes()
        return {"created": int(time.time()), "model": done["model"],
                "data": [{"b64_json": base64.b64encode(data).decode(),
                          "media_type": done["params"].get("mime")}]}

    @app.post("/v1/audio/transcriptions")
    async def v1_transcribe(request: Request, file: UploadFile = File(...),
                            model: str = Form("auto"), language: str | None = Form(None)) -> Any:
        core = core_of(request)
        job = await core.media.submit("stt", model=model, input_bytes=await _read_limited(file),
                                      input_name=file.filename or "audio.wav",
                                      params={"language": language} if language else {})
        done = await core.media.wait(job["id"])
        if not done or done["status"] != "done":
            return JSONResponse({"error": {"message": (done or {}).get("error")}},
                                status_code=503)
        return {"text": done["params"].get("text", "")}

    @app.post("/v1/audio/speech")
    async def v1_speech(request: Request) -> Any:
        core = core_of(request)
        body = await request.json()
        job = await core.media.submit("tts", body.get("input", ""), model=body.get("model"),
                                      params={"voice": body.get("voice", "alloy")})
        done = await core.media.wait(job["id"])
        if not done or done["status"] != "done":
            return JSONResponse({"error": {"message": (done or {}).get("error")}},
                                status_code=503)
        if done["params"].get("local_tts"):
            return JSONResponse({"local_tts": True, "text": done["params"].get("text")},
                                status_code=200)
        return FileResponse(done["result_path"], media_type=done["params"].get("mime"))

    # --- API native : conversations ---------------------------------------


    def _sse(gen: AsyncIterator[dict[str, Any]]) -> StreamingResponse:
        async def run() -> AsyncIterator[str]:
            async for ev in gen:
                if ev["type"] in ("model_switched", "model_returned"):
                    hub.publish(ev)
                yield f"data: {dumps(ev)}\n\n"
            yield "data: {\"type\": \"end\"}\n\n"

        return StreamingResponse(run(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache",
                                          "X-Accel-Buffering": "no"})

    @app.post("/tontolo/chat")
    async def chat(request: Request, body: ChatBody) -> StreamingResponse:
        core = core_of(request)
        if body.conversation_id is None:
            core.catalog.refresh_in_background()  # veille « à chaque utilisation »
        category = Category(body.category) if body.category else None
        if category is None:
            # Modalité détectée automatiquement (« dessine… », « lis à voix haute… ») :
            # aucun mode à choisir pour l'utilisateur.
            detected = classify([{"role": "user", "content": body.content}]).category
            if detected.value in MEDIA_TURN_KINDS:
                category = detected
        if category is not None and category.value in MEDIA_TURN_KINDS:
            return _sse(_media_turn(core, body, category))
        return _sse(core.chat.send(body.conversation_id, body.content, model=body.model,
                                   forced=category, strict=body.strict,
                                   use_tools=body.use_tools))

    async def _media_turn(core: Core, body: ChatBody,
                          category: Category) -> AsyncIterator[dict[str, Any]]:
        """Tour de conversation dont le résultat est un média (image, voix, vidéo)."""
        text = body.content if isinstance(body.content, str) else " ".join(
            p.get("text", "") for p in body.content if p.get("type") == "text")
        cid = body.conversation_id
        if not cid or not await core.db.conversation_exists(cid):
            cid = await core.db.create_conversation(text[:60])
            yield {"type": "conversation", "id": cid}
        await core.db.add_message(cid, {"role": "user", "content": body.content})
        image = _first_image(body.content)
        job = await core.media.submit(category.value, text, conversation_id=cid,
                                      model=body.model, input_bytes=image,
                                      input_name="image.png")
        yield {"type": "job", **job}
        done = await core.media.wait(job["id"]) or job
        yield {"type": "job", **done}
        note = (f"[média:{done['id']}]" if done["status"] == "done"
                else str(done.get("error")))
        msg = await core.db.add_message(cid, {"role": "assistant", "content": note},
                                        model=done.get("model"))
        yield {"type": "done", "message": {"role": "assistant", "content": note},
               "model": done.get("model"), "uid": msg["uid"], "conversation_id": cid,
               "name": (done.get("params") or {}).get("model_name"),
               "job": done}


    @app.post("/tontolo/chat/{cid}/resume")
    async def resume(request: Request, cid: str, body: ResumeBody) -> StreamingResponse:
        return _sse(core_of(request).chat.resume(cid, approved=body.approved,
                                                 model=body.model))

    @app.post("/tontolo/chat/{cid}/regenerate")
    async def regenerate(request: Request, cid: str, body: ResumeBody | None = None
                         ) -> StreamingResponse:
        return _sse(core_of(request).chat.regenerate(cid, model=body.model if body else None))

    @app.post("/tontolo/chat/{cid}/edit")
    async def edit_message(request: Request, cid: str, body: EditBody) -> StreamingResponse:
        return _sse(core_of(request).chat.edit_and_resend(cid, body.seq, body.content,
                                                          model=body.model))

    @app.post("/tontolo/chat/{cid}/approve-paid")
    async def approve_paid(request: Request, cid: str) -> dict[str, bool]:
        core_of(request).router.approve_paid(cid)
        return {"ok": True}

    @app.get("/tontolo/conversations")
    async def conversations(request: Request, q: str | None = None, limit: int = 50,
                            offset: int = 0) -> list[dict[str, Any]]:
        return await core_of(request).db.list_conversations(limit, offset, q)

    @app.get("/tontolo/conversations/{cid}")
    async def conversation(request: Request, cid: str, after: int = 0,
                           limit: int | None = None) -> dict[str, Any]:
        db = core_of(request).db
        if not await db.conversation_exists(cid):
            raise HTTPException(404, "Conversation introuvable")
        return {"id": cid, "messages": await db.get_messages(cid, after, limit)}


    @app.patch("/tontolo/conversations/{cid}")
    async def rename(request: Request, cid: str, body: RenameBody) -> dict[str, bool]:
        await core_of(request).db.rename_conversation(cid, body.title)
        return {"ok": True}

    @app.put("/tontolo/conversations/{cid}/pin")
    async def pin(request: Request, cid: str, body: PinBody) -> dict[str, bool]:
        await core_of(request).db.pin_conversation(cid, body.pinned)
        return {"ok": True}

    @app.get("/tontolo/conversations/{cid}/export")
    async def export(request: Request, cid: str) -> Response:
        """Export Markdown d'une conversation (partage, archivage)."""
        db = core_of(request).db
        if not await db.conversation_exists(cid):
            raise HTTPException(404, "Conversation introuvable")
        convs = {c["id"]: c for c in await db.list_conversations(limit=10_000)}
        title = convs.get(cid, {}).get("title") or "Conversation"
        lines = [f"# {title}", ""]
        for m in await db.get_messages(cid):
            if m["role"] not in ("user", "assistant"):
                continue
            content = m.get("content")
            if isinstance(content, list):
                content = "\n".join(p.get("text", "[image]") for p in content)
            if not content:
                continue
            who = "**Vous**" if m["role"] == "user" else f"**Tontolo** · _{m['_meta']['model']}_"
            lines += [who, "", str(content), ""]
        return Response("\n".join(lines), media_type="text/markdown; charset=utf-8")

    @app.delete("/tontolo/conversations/{cid}")
    async def delete_conv(request: Request, cid: str) -> dict[str, bool]:
        await core_of(request).db.delete_conversation(cid)
        return {"ok": True}

    # --- Catalogue, nouveautés, préférences --------------------------------

    def _model_json(m: ModelInfo, usable: set[str]) -> dict[str, Any]:
        return {
            "key": m.key, "id": m.model_id, "provider": m.provider, "name": m.name,
            "free": m.is_free, "usable": m.provider in usable, "tools": m.supports_tools,
            "vision": m.supports_vision, "context": m.context_length, "media": m.media,
            "quality": m.quality, "speed": m.speed, "provisional": m.provisional,
            "rate_limit": m.rate_limit, "created": m.created,
            "price_in": m.price_in, "price_out": m.price_out,
        }

    @app.get("/tontolo/catalog")
    async def catalog(request: Request, category: str | None = None, free: bool = True,
                      usable: bool = False, q: str | None = None,
                      limit: int = 100) -> dict[str, Any]:
        core = core_of(request)
        usable_set = core.catalog.usable_providers()
        models = core.catalog.catalog.filter(category=category, free_only=free,
                                             usable=usable_set if usable else None)
        if q:
            ql = q.lower()
            models = [m for m in models if ql in m.key.lower() or ql in m.name.lower()]
        return {"updated_at": core.catalog.catalog.updated_at,
                "sources": core.catalog.catalog.sources,
                "models": [_model_json(m, usable_set) for m in models[:limit]]}

    @app.post("/tontolo/catalog/refresh")
    async def refresh_catalog(request: Request) -> dict[str, Any]:
        changes = await core_of(request).catalog.refresh(force=True)
        return {"changes": len(changes)}

    @app.get("/tontolo/status")
    async def status(request: Request) -> dict[str, Any]:
        core = core_of(request)
        return {"quotas": core.router.quota.snapshot(),
                "usable_providers": sorted(core.catalog.usable_providers()),
                "catalog_updated_at": core.catalog.catalog.updated_at,
                "sources": core.catalog.catalog.sources,
                "mcp_errors": core.mcp.errors}

    @app.post("/tontolo/route")
    async def route_preview(request: Request) -> dict[str, Any]:
        """« Pourquoi ce modèle ? » : décision sans appel au fournisseur."""
        core = core_of(request)
        body = await request.json()
        d = await core.router.decide(body.get("messages") or [],
                                     conversation_id=body.get("conversation_id"),
                                     model=body.get("model"))
        return {"profile": d.profile.as_dict(),
                "chain": [dict(c.reason(d.profile.category), model=c.model.key,
                               name=c.model.name) for c in d.chain[:10]]}

    @app.get("/tontolo/changes")
    async def changes(request: Request, limit: int = 100) -> list[dict[str, Any]]:
        return await core_of(request).db.list_changes(limit)

    @app.post("/tontolo/changes/seen")
    async def changes_seen(request: Request) -> dict[str, bool]:
        await core_of(request).db.mark_changes_seen()
        return {"ok": True}

    @app.get("/tontolo/preferences")
    async def get_prefs(request: Request) -> list[dict[str, Any]]:
        return await core_of(request).db.get_preferences()


    @app.put("/tontolo/preferences")
    async def put_pref(request: Request, body: PrefBody) -> dict[str, bool]:
        if body.scope not in ("global", "conversation", "category"):
            raise HTTPException(400, "portée invalide")
        model = None if body.model in (None, "", "auto") else body.model
        await core_of(request).db.set_preference(body.scope, body.scope_key, model,
                                                 body.strict)
        return {"ok": True}

    # --- Fournisseurs et clés (BYOK) --------------------------------------

    @app.get("/tontolo/providers")
    async def providers(request: Request) -> list[dict[str, Any]]:
        core = core_of(request)
        counts: dict[str, int] = {}
        for m in core.catalog.catalog.models.values():
            if m.is_free:
                counts[m.provider] = counts.get(m.provider, 0) + 1
        return [{**{k: v for k, v in p.items() if k != "base_url"},
                 "has_key": secrets.has_key(pid), "free_models": counts.get(pid, 0)}
                for pid, p in sorted(core.catalog.catalog.providers.items())]


    @app.put("/tontolo/keys/{provider}")
    async def put_key(request: Request, provider: str, body: KeyBody) -> dict[str, Any]:
        core = core_of(request)
        ok, detail = (await _validate_key(core, provider, body.key.strip())
                      if body.validate_key else (True, "Clé chargée"))
        if ok:
            secrets.set_key(provider, body.key.strip(), persist=body.persist)
            core.router.registry.reset()
            core.catalog.refresh_in_background()
        return {"valid": ok, "detail": detail}

    @app.delete("/tontolo/keys/{provider}")
    async def delete_key(request: Request, provider: str) -> dict[str, bool]:
        secrets.delete_key(provider)
        core_of(request).router.registry.reset()
        return {"ok": True}

    # --- Réglages ----------------------------------------------------------

    @app.get("/tontolo/settings")
    async def get_settings(request: Request) -> dict[str, Any]:
        data = core_of(request).settings.model_dump(mode="json")
        data["server"].pop("token", None)
        return data

    @app.put("/tontolo/settings")
    async def put_settings(request: Request) -> dict[str, Any]:
        core = core_of(request)
        patch = await request.json()
        patch.pop("server", None)  # jamais modifiable à distance
        merged = core.settings.model_dump(mode="json")
        for k, v in patch.items():
            if isinstance(v, dict) and isinstance(merged.get(k), dict):
                merged[k].update(v)
            else:
                merged[k] = v
        new = Settings.model_validate(merged)
        for field_name in type(new).model_fields:
            setattr(core.settings, field_name, getattr(new, field_name))
        save_settings(core.settings)
        return await get_settings(request)

    # --- Médias -----------------------------------------------------------


    @app.post("/tontolo/media")
    async def media_submit(request: Request, body: MediaBody) -> dict[str, Any]:
        try:
            return await core_of(request).media.submit(
                body.kind, body.prompt, params=body.params, model=body.model,
                conversation_id=body.conversation_id)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post("/tontolo/media/upload")
    async def media_upload(request: Request, kind: str = Form(...), prompt: str = Form(""),
                           model: str | None = Form(None),
                           file: UploadFile = File(...)) -> dict[str, Any]:
        return await core_of(request).media.submit(
            kind, prompt, model=model, input_bytes=await _read_limited(file),
            input_name=file.filename or "fichier")

    @app.get("/tontolo/media")
    async def media_list(request: Request, kind: str | None = None,
                         status: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        return await core_of(request).db.list_jobs(limit, status, kind)

    @app.get("/tontolo/media/{job_id}")
    async def media_get(request: Request, job_id: str) -> dict[str, Any]:
        job = await core_of(request).db.get_job(job_id)
        if not job:
            raise HTTPException(404, "Job introuvable")
        return job

    @app.get("/tontolo/media/{job_id}/file")
    async def media_file(request: Request, job_id: str) -> FileResponse:
        core = core_of(request)
        job = await core.db.get_job(job_id)
        if not job or not job.get("result_path") or not Path(job["result_path"]).exists():
            raise HTTPException(404, "Fichier introuvable")
        path = Path(job["result_path"]).resolve()
        if not path.is_relative_to(core.media.dir.resolve()):
            raise HTTPException(403, "Accès refusé")
        return FileResponse(path, media_type=job["params"].get("mime"))

    @app.delete("/tontolo/media/{job_id}")
    async def media_delete(request: Request, job_id: str) -> dict[str, bool]:
        core = core_of(request)
        job = await core.db.get_job(job_id)
        if job and job.get("result_path"):
            Path(job["result_path"]).unlink(missing_ok=True)
        await core.db.delete_job(job_id)
        return {"ok": True}

    # --- Dépenses, synchronisation, MCP, mise à jour ---------------------

    @app.get("/tontolo/memory")
    async def memory_list(request: Request) -> dict[str, Any]:
        core = core_of(request)
        return {"enabled": core.settings.memory_enabled,
                "items": await core.db.list_memories()}

    @app.post("/tontolo/memory")
    async def memory_add(request: Request, body: MemoryBody) -> dict[str, bool]:
        ok = await core_of(request).chat.memory.remember(
            body.text, "instruction" if body.kind == "instruction" else "fact", "manuel")
        if not ok:
            raise HTTPException(400, "Souvenir refusé (vide ou contenant un secret)")
        return {"ok": True}

    @app.delete("/tontolo/memory/{mem_id}")
    async def memory_delete(request: Request, mem_id: int) -> dict[str, bool]:
        await core_of(request).db.delete_memory(mem_id)
        return {"ok": True}

    @app.delete("/tontolo/memory")
    async def memory_clear(request: Request) -> dict[str, bool]:
        await core_of(request).db.delete_memory(None)
        return {"ok": True}

    @app.post("/tontolo/memory/compact")
    async def memory_compact(request: Request) -> dict[str, int]:
        return {"count": await core_of(request).chat.memory.maybe_compact(force=True)}

    @app.get("/tontolo/spend")
    async def spend(request: Request) -> dict[str, Any]:
        db = core_of(request).db
        now = time.time()
        return {"today": await db.spend_since(now - now % 86400),
                "month": await db.spend_since(now - 31 * 86400),
                "entries": await db.list_spend()}

    @app.get("/tontolo/sync")
    async def sync_export(request: Request, since: float = 0) -> dict[str, Any]:
        return await core_of(request).db.export_since(since)

    @app.post("/tontolo/sync")
    async def sync_import(request: Request) -> dict[str, int]:
        try:
            return {"applied": await core_of(request).db.import_sync(await request.json())}
        except (KeyError, TypeError, ValueError) as exc:
            raise HTTPException(400, "Lot de synchronisation invalide") from exc

    @app.get("/tontolo/mcp")
    async def mcp_get(request: Request) -> dict[str, Any]:
        core = core_of(request)
        return {"servers": load_config(core.mcp.config_path), "errors": core.mcp.errors,
                "tools": [t.name for t in core.mcp.tools]}

    @app.put("/tontolo/mcp")
    async def mcp_put(request: Request) -> dict[str, bool]:
        core = core_of(request)
        body = await request.json()
        servers = [s for s in body.get("servers", []) if isinstance(s, dict)]
        client_local = (request.client is not None
                        and request.client.host in ("127.0.0.1", "::1"))
        if any(s.get("transport") == "stdio" for s in servers) and not (
                client_local and core.settings.server.host in LOOPBACK):
            # Un serveur stdio lance un programme : jamais configurable à distance.
            raise HTTPException(403, "Serveurs MCP stdio : configuration locale uniquement")
        save_config(core.mcp.config_path, servers)
        await core.mcp.close()
        return {"ok": True}

    @app.get("/tontolo/update")
    async def update(request: Request, target: str | None = None,
                     arch: str | None = None) -> dict[str, Any]:
        return await check_update(target=target, arch=arch)

    @app.post("/tontolo/update/download")
    async def update_download(request: Request, target: str,
                              arch: str | None = None) -> dict[str, Any]:
        if target not in ("linux", "android"):
            raise HTTPException(400, "cible invalide")
        core = core_of(request)
        return await download_update(core.settings.data_dir / "updates", target, arch)

    @app.get("/tontolo/about")
    async def about() -> dict[str, Any]:
        return {"version": __version__, "license": "Apache-2.0",
                "attributions": ATTRIBUTIONS}

    # --- WebSocket d'événements ------------------------------------------

    @app.websocket("/tontolo/ws")
    async def ws(websocket: WebSocket) -> None:
        core = core_of(websocket)
        token = core.settings.server.token
        if token and not hmac.compare_digest(websocket.query_params.get("token", ""), token):
            await websocket.close(code=4401)
            return
        if not origin_allowed(websocket.headers.get("origin")):
            await websocket.close(code=4403)
            return
        await websocket.accept()
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        hub.queues.add(q)
        try:
            while True:
                ev = await q.get()
                await websocket.send_text(json.dumps(ev, ensure_ascii=False, default=str))
        except Exception:
            pass
        finally:
            hub.queues.discard(q)

    return app


ATTRIBUTIONS = [
    {"name": "Artificial Analysis", "url": "https://artificialanalysis.ai/",
     "use": "Indices d'intelligence, de code, de maths et de vitesse"},
    {"name": "LMArena", "url": "https://lmarena.ai/",
     "use": "Classements ELO par catégorie (jeu de données CC BY 4.0)"},
    {"name": "OpenRouter", "url": "https://openrouter.ai/",
     "use": "Catalogue des modèles, prix et capacités"},
    {"name": "awesome-free-llm-apis", "url": "https://github.com/mnfst/awesome-free-llm-apis",
     "use": "Découverte des fournisseurs gratuits (CC0)"},
    {"name": "Pollinations", "url": "https://pollinations.ai/",
     "use": "Texte et images sans clé"},
]


async def _validate_key(core: Core, provider: str, key: str) -> tuple[bool, str]:
    """Validation immédiate de la clé (aucun appel de génération, aucun quota consommé)."""
    from tontolo import http

    if provider == "artificial-analysis":
        url, headers = ("https://artificialanalysis.ai/api/v2/data/llms/models",
                        {"x-api-key": key})
    else:
        p = core.catalog.catalog.providers.get(provider)
        if p is None or not p.get("base_url"):
            return False, "Fournisseur inconnu"
        base = p["base_url"]
        if not key_allowed(provider, base):
            return False, "Adresse du fournisseur non fiable (HTTPS requis, hôte épinglé)"
        url = f"{base}/key" if provider == "openrouter" else f"{base}/models"
        headers = {"Authorization": f"Bearer {key}"}
    try:
        resp = await http.client().get(url, headers=headers, timeout=20)
    except Exception as exc:
        return False, f"Réseau : {type(exc).__name__}"
    if resp.status_code == 200:
        return True, "Clé valide"
    if resp.status_code in (401, 403):
        return False, "Clé refusée par le fournisseur"
    return False, f"Réponse inattendue ({resp.status_code})"


def run(host: str | None = None, port: int | None = None) -> None:
    import uvicorn

    settings = load_settings()
    host = host or settings.server.host
    port = port or settings.server.port
    if host not in LOOPBACK and not settings.server.token:
        raise SystemExit("Un jeton (server.token ou TONTOLO_TOKEN) est obligatoire pour "
                         "écouter hors de la boucle locale.")
    settings.server.host, settings.server.port = host, port
    uvicorn.run(create_app(settings), host=host, port=port, log_level="info")
