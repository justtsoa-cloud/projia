"""Vidéos explicatives : capacités de rendu et export MP4 (Manim, Linux, facultatif)."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response

from tontolo.explainer import manim_render, storyboard
from tontolo.server.common import Hub, RateLimiter

MAX_BODY = 200_000
_one_at_a_time = asyncio.Semaphore(1)


def register(app: FastAPI, hub: Hub, ws_connects: RateLimiter) -> None:
    @app.get("/tontolo/explainer/capabilities")
    async def capabilities() -> dict[str, Any]:
        """Ce que cette machine sait faire : le lecteur animé de l'application marche partout ;
        le MP4 demande Manim et ffmpeg (Linux)."""
        st = await asyncio.to_thread(manim_render.status)
        return {**st, "mp4": bool(st["manim"] and st["ffmpeg"] and st["sandbox"])}

    @app.post("/tontolo/explainer/render")
    async def render(request: Request) -> Response:
        """MP4 d'un scénario (corps : {"story": {...}, "quality": "l"|"m"}). Le scénario est
        revalidé ; aucun code n'est accepté, seulement des données."""
        raw = await request.body()
        if len(raw) > MAX_BODY:
            raise HTTPException(413, "Scénario trop volumineux")
        try:
            import json

            body = json.loads(raw)
            story = storyboard.validate(body.get("story"), language=str(
                (body.get("story") or {}).get("language", "fr")))
        except (ValueError, AttributeError, TypeError) as exc:
            raise HTTPException(400, f"Scénario invalide : {exc}") from exc
        st = await asyncio.to_thread(manim_render.status)
        if not st["sandbox"]:
            messages = {
                "fr": "Export MP4 indisponible sans bubblewrap. Le lecteur animé reste disponible.",
                "en": "MP4 export requires bubblewrap. The animated player remains available.",
                "mg": "Tsy misy bubblewrap: tsy afaka mamoaka MP4. "
                      "Mbola azo jerena eto ny horonan-tsary.",
            }
            raise HTTPException(501, messages.get(story.get("language", "fr"), messages["fr"]))
        if not st["manim"]:
            raise HTTPException(501, "Manim n'est pas installé sur cette machine : le lecteur "
                                     "animé de l'application reste disponible.")
        if _one_at_a_time.locked():
            raise HTTPException(429, "Un rendu est déjà en cours")
        async with _one_at_a_time:
            try:
                mp4 = await manim_render.render(story, quality=str(body.get("quality", "l")))
            except manim_render.RenderError as exc:
                raise HTTPException(502, str(exc)) from exc
        return Response(mp4, media_type="video/mp4", headers={
            "Content-Disposition": 'attachment; filename="explication.mp4"'})
