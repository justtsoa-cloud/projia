"""Santé et API compatible OpenAI (`/v1/*`)."""

from __future__ import annotations

import base64
import time
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from tontolo import (
    __version__,
)
from tontolo.agent.loop import dumps
from tontolo.server.common import (
    Hub,
    RateLimiter,
    core_of,
)


def register(app: FastAPI, hub: Hub, ws_connects: RateLimiter) -> None:
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
