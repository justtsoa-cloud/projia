"""Jobs médias (images, son, vidéo)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse

from tontolo.server.common import (
    ACTIVE_MIMES,
    Hub,
    MediaBody,
    RateLimiter,
    _read_limited,
    core_of,
    safe_mime,
)


def register(app: FastAPI, hub: Hub, ws_connects: RateLimiter) -> None:
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
        mime = safe_mime(job["params"].get("mime"))
        headers = {"X-Content-Type-Options": "nosniff",
                   "Content-Security-Policy": "sandbox; default-src 'none'"}
        if mime in ACTIVE_MIMES:  # page, SVG, XML : téléchargés, jamais affichés par le cœur
            headers["Content-Disposition"] = f'attachment; filename="{path.name}"'
            mime = "application/octet-stream"
        return FileResponse(path, media_type=mime, headers=headers)

    @app.delete("/tontolo/media/{job_id}")
    async def media_delete(request: Request, job_id: str) -> dict[str, bool]:
        core = core_of(request)
        job = await core.db.get_job(job_id)
        if job and job.get("result_path"):
            Path(job["result_path"]).unlink(missing_ok=True)
        await core.db.delete_job(job_id)
        return {"ok": True}
