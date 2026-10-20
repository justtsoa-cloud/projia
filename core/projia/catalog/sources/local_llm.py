"""Modèles **locaux** (sur l'appareil), utilisés en dernier recours et sans réseau.

Détectés automatiquement sur la boucle locale uniquement (rien ne sort de l'appareil) :
- Ollama : `GET http://127.0.0.1:11434/api/tags`, API compatible OpenAI sur `/v1` ;
- llama.cpp (`llama-server`, modèles GGUF) : `GET http://127.0.0.1:8080/v1/models`.
Sous Android, les deux tournent dans Termux ; sous Linux, en service ou à la main.
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from projia.catalog.models import ModelInfo

OLLAMA_URL = "http://127.0.0.1:11434"
LLAMACPP_URL = "http://127.0.0.1:8080"
PROBE_TIMEOUT = 0.4

PROVIDERS: dict[str, dict[str, Any]] = {
    "ollama_local": {
        "id": "ollama_local", "name": "Ollama (sur l'appareil)", "base_url": f"{OLLAMA_URL}/v1",
        "key_url": None, "keyless": True, "local": True,
        "description": "Modèles installés avec Ollama : marchent sans Internet.",
    },
    "llamacpp_local": {
        "id": "llamacpp_local", "name": "llama.cpp (sur l'appareil)",
        "base_url": f"{LLAMACPP_URL}/v1", "key_url": None, "keyless": True, "local": True,
        "description": "Modèle GGUF servi par llama-server : marche sans Internet.",
    },
}


def _model(provider: str, model_id: str, name: str) -> ModelInfo:
    return ModelInfo(
        provider=provider, model_id=model_id, name=name, family=model_id.split(":")[0],
        input_modalities=["text"], output_modalities=["text"], is_free=True, needs_key=False,
        supports_tools=False, context_length=8192, rate_limit="illimité (local)",
        quality={"chat": 0.3, "writing": 0.25, "translation": 0.2},
    )


async def _ollama(client: httpx.AsyncClient) -> list[ModelInfo]:
    r = await client.get(f"{OLLAMA_URL}/api/tags")
    r.raise_for_status()
    out = []
    for m in (r.json().get("models") or [])[:20]:
        mid = str(m.get("name") or m.get("model") or "")
        if mid and "embed" not in mid:
            out.append(_model("ollama_local", mid, f"{mid} (local)"))
    return out


async def _llamacpp(client: httpx.AsyncClient) -> list[ModelInfo]:
    r = await client.get(f"{LLAMACPP_URL}/v1/models")
    r.raise_for_status()
    out = []
    for m in (r.json().get("data") or [])[:5]:
        mid = str(m.get("id") or "")
        if mid:
            out.append(_model("llamacpp_local", mid, f"{mid.rsplit('/', 1)[-1]} (local)"))
    return out


async def discover() -> list[ModelInfo]:
    """Modèles locaux disponibles maintenant (liste vide si aucun serveur local)."""
    async with httpx.AsyncClient(timeout=PROBE_TIMEOUT, trust_env=False) as client:
        results = await asyncio.gather(_ollama(client), _llamacpp(client),
                                       return_exceptions=True)
    return [m for r in results if isinstance(r, list) for m in r]
