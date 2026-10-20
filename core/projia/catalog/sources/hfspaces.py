"""Spaces Hugging Face publics utilisés comme sources médias **sans clé**.

Vérifié le 2026-10-11 : `Lightricks/ltx-video-distilled` (Space officiel de LTX-Video,
GPU partagé « ZeroGPU ») expose l'API REST Gradio `POST /gradio_api/call/text_to_video`
puis `GET /gradio_api/call/text_to_video/{event_id}` (flux SSE) ; une vidéo de 2 s en
704×512 est produite en ≈ 8 s sans compte. Le quota GPU anonyme est limité par jour ;
une clé Hugging Face (gratuite) l'augmente.

Images (vérifié le 2026-10-11, point d'entrée Gradio `infer`) : FLUX.1-schnell et FLUX.1-dev
(Black Forest Labs) et Stable Diffusion 3.5 Large Turbo (Stability AI). Le quota ZeroGPU est
commun à tous les Spaces : quand il est épuisé, Pollinations prend le relais.
"""

from __future__ import annotations

from dataclasses import dataclass

from projia.catalog.models import ModelInfo


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


@dataclass(frozen=True)
class ImageSpace:
    space: str
    base_url: str
    name: str
    quality: float
    speed: float
    steps: int          # nombre d'étapes de diffusion (vitesse / qualité)


IMAGE_SPACES: tuple[ImageSpace, ...] = (
    ImageSpace("black-forest-labs/FLUX.1-schnell",
               "https://black-forest-labs-flux-1-schnell.hf.space", "FLUX.1 schnell", 0.72,
               0.75, 4),
    ImageSpace("stabilityai/stable-diffusion-3.5-large-turbo",
               "https://stabilityai-stable-diffusion-3-5-large-turbo.hf.space",
               "Stable Diffusion 3.5 Large Turbo", 0.66, 0.7, 4),
    ImageSpace("black-forest-labs/FLUX.1-dev",
               "https://black-forest-labs-flux-1-dev.hf.space", "FLUX.1 dev", 0.8, 0.3, 28),
)


# Retouche guidée par une consigne (la personne ou l'objet est conservé, la scène change).
EDIT_SPACES: tuple[ImageSpace, ...] = (
    ImageSpace("black-forest-labs/FLUX.1-Kontext-dev",
               "https://black-forest-labs-flux-1-kontext-dev.hf.space", "FLUX.1 Kontext",
               0.8, 0.35, 28),
)


def by_id(model_id: str) -> VideoSpace | None:
    return next((s for s in VIDEO_SPACES if s.space == model_id), None)


def image_by_id(model_id: str) -> ImageSpace | None:
    return next((s for s in (*IMAGE_SPACES, *EDIT_SPACES) if s.space == model_id), None)


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
    ] + [
        ModelInfo(
            provider="hf_spaces", model_id=s.space, name=s.name, family=s.name,
            input_modalities=["text"], output_modalities=["image"],
            is_free=True, needs_key=False, media=["image_gen"],
            quality={"image_gen": s.quality}, speed=s.speed,
            rate_limit="GPU partagé : quota quotidien anonyme",
        )
        for s in IMAGE_SPACES
    ] + [
        ModelInfo(
            provider="hf_spaces", model_id=s.space, name=s.name, family=s.name,
            input_modalities=["text", "image"], output_modalities=["image"],
            is_free=True, needs_key=False, media=["image_edit"],
            quality={"image_edit": s.quality}, speed=s.speed,
            rate_limit="GPU partagé : quota quotidien anonyme",
        )
        for s in EDIT_SPACES
    ]
