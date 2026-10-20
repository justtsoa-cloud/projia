"""Source Pollinations : modèles texte et image utilisables **sans clé** (niveau anonyme).

Vérifié le 2026-10-10 : `GET https://text.pollinations.ai/models` (champ
`tier == "anonymous"`), `POST https://text.pollinations.ai/openai` (compatible
OpenAI), `GET https://image.pollinations.ai/models` et
`GET https://image.pollinations.ai/prompt/{prompt}`. Débit limité.
"""

from __future__ import annotations

from typing import Any

from projia.catalog.cache import SourceCache
from projia.catalog.models import ModelInfo

TEXT_MODELS_URL = "https://text.pollinations.ai/models"
IMAGE_MODELS_URL = "https://image.pollinations.ai/models"
TEXT_BASE_URL = "https://text.pollinations.ai/openai"
IMAGE_URL = "https://image.pollinations.ai/prompt/"


def parse_text_models(data: Any) -> list[ModelInfo]:
    out: list[ModelInfo] = []
    if not isinstance(data, list):
        return out
    for raw in data:
        if not isinstance(raw, dict) or raw.get("tier") not in (None, "anonymous"):
            continue
        ins = raw.get("input_modalities") or ["text"]
        outs = raw.get("output_modalities") or ["text"]
        media = ["tts"] if "audio" in outs else []
        out.append(ModelInfo(
            provider="pollinations",
            model_id=raw["name"],
            name=raw.get("description") or raw["name"],
            family=raw.get("description") or raw["name"],
            input_modalities=ins,
            output_modalities=outs,
            supports_tools=bool(raw.get("tools")),
            is_free=True,
            needs_key=False,
            context_length=int(raw.get("context_length") or raw.get("maxInputChars", 0) // 4
                               or 8192),
            rate_limit="anonyme (débit limité)",
            media=media,
        ))
    return out


def parse_image_models(data: Any) -> list[ModelInfo]:
    names = [d if isinstance(d, str) else d.get("name") for d in data or []]
    # « auto » : sans paramètre de modèle, le service choisit lui-même (plus fiable que
    # « sana », parfois indisponible) ; sert de second candidat de repli.
    names = ["auto", *names] if data else names
    return [
        ModelInfo(
            provider="pollinations", model_id=n, name=f"Pollinations {n}", family=n,
            input_modalities=["text"], output_modalities=["image"], is_free=True,
            needs_key=False, media=["image_gen"], rate_limit="anonyme (débit limité)",
        )
        for n in names if n
    ]


async def fetch_models(cache: SourceCache, ttl: float, force: bool = False) -> list[ModelInfo]:
    models: list[ModelInfo] = []
    text = await cache.fetch_json("pollinations_text", TEXT_MODELS_URL, ttl=ttl, force=force)
    if text:
        models += parse_text_models(text.data)
    image = await cache.fetch_json("pollinations_image", IMAGE_MODELS_URL, ttl=ttl, force=force)
    if image:
        models += parse_image_models(image.data)
    return models
