"""Documents joints à une discussion."""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from tontolo import (
    attachments,
    documents,
)
from tontolo.server.common import (
    MAX_UPLOAD_BYTES,
    MAX_VIDEO_BYTES,
    Hub,
    RateLimiter,
    _audio_track,
    _read_limited,
    core_of,
)


def register(app: FastAPI, hub: Hub, ws_connects: RateLimiter) -> None:
    # --- Documents joints ---------------------------------------------------

    @app.post("/tontolo/documents")
    async def upload_document(request: Request, file: UploadFile = File(...),
                              conversation_id: str | None = Form(None)) -> dict[str, Any]:
        """Joint une pièce (PDF, bureautique, texte, code, archive, son, vidéo…) à une
        conversation (créée si besoin) : son texte sert à répondre en citant les pages."""
        import shutil

        core = core_of(request)
        name = Path(file.filename or "document").name[:120] or "document"
        kind = attachments.media_kind(name)
        big = kind == "video" and shutil.which("ffmpeg") is not None
        data = await _read_limited(file, MAX_VIDEO_BYTES if big else 0)
        if kind is not None:
            # Son ou vidéo : transcription par le service vocal (modèle gratuit routé).
            audio_name, audio = await _audio_track(name, data) if kind == "video" else (name, data)
            if len(audio) > MAX_UPLOAD_BYTES:
                raise HTTPException(413, "Vidéo trop longue à transcrire sur cet appareil "
                                         "(25 Mo maximum sans ffmpeg).")
            job = await core.media.submit("stt", input_bytes=audio, input_name=audio_name)
            done = await core.media.wait(job["id"])
            text = str(((done or {}).get("params") or {}).get("text") or "").strip()
            if not done or done["status"] != "done" or not text:
                raise HTTPException(422, "Transcription impossible pour l'instant : "
                                         + str((done or {}).get("error") or "aucun texte"))
            what = "de la vidéo" if kind == "video" else "de l'enregistrement"
            pages = [f"Transcription {what} « {name} » :\n{text}"]
        else:
            try:
                pages = await asyncio.to_thread(documents.extract_pages, name, data)
            except documents.DocumentError as exc:
                raise HTTPException(422, str(exc)) from exc
        cid = conversation_id
        if not cid or not await core.db.conversation_exists(cid):
            cid = await core.db.create_conversation(name[:60])
        doc_id = uuid.uuid4().hex
        # Long document (livre…) : fiche compacte calculée une fois, sur l'appareil.
        digest = (await asyncio.to_thread(documents.digest, pages)
                  if sum(len(p) for p in pages) > documents.LONG_DOC else "")
        await core.db.add_document(cid, doc_id, name, pages, digest)
        return {"id": doc_id, "conversation_id": cid, "name": name, "pages": len(pages),
                "chars": sum(len(p) for p in pages)}

    @app.get("/tontolo/conversations/{cid}/documents")
    async def list_documents(request: Request, cid: str) -> list[dict[str, Any]]:
        return await core_of(request).db.list_documents(cid)

    @app.delete("/tontolo/conversations/{cid}/documents/{doc_id}")
    async def delete_document(request: Request, cid: str, doc_id: str) -> dict[str, bool]:
        await core_of(request).db.delete_document(cid, doc_id)
        return {"ok": True}

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
