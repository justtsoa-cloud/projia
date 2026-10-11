"""Spaces Hugging Face publics utilisés comme sources médias **sans clé**.

Vérifié le 2026-10-11 : `Lightricks/ltx-video-distilled` (Space officiel de LTX-Video,
GPU partagé « ZeroGPU ») expose l'API REST Gradio `POST /gradio_api/call/text_to_video`
puis `GET /gradio_api/call/text_to_video/{event_id}` (flux SSE) ; une vidéo de 2 s en
704×512 est produite en ≈ 8 s sans compte. Le quota GPU anonyme est limité par jour ;
une clé Hugging Face (gratuite) l'augmente.
"""

from __future__ import annotations

from dataclasses import dataclass

from tontolo.catalog.models import ModelInfo


@dataclass(frozen=True)
class VideoSpace:
    space: str          # identifiant Hugging Face
    base_url: str       # domaine *.hf.space
    name: str
    quality: float      # estimation (0-1) pour le classement


VIDEO_SPACES: tuple[VideoSpace, ...] = (
    VideoSpace("Lightricks/ltx-video-distilled",
               "https://lightricks-ltx-video-distilled.hf.space", "LTX-Video (Lightricks)", 0.7),
)


def by_id(model_id: str) -> VideoSpace | None:
    return next((s for s in VIDEO_SPACES if s.space == model_id), None)


def models() -> list[ModelInfo]:
    return [
        ModelInfo(
            provider="hf_spaces", model_id=s.space, name=s.name, family=s.name,
            input_modalities=["text", "image"], output_modalities=["video"],
            is_free=True, needs_key=False, media=["video_gen"],
            quality={"video_gen": s.quality},
            rate_limit="GPU partagé : quota quotidien anonyme",
        )
        for s in VIDEO_SPACES
    ]
