"""Registre intégré des fournisseurs **gratuits avec clé** (offre gratuite permanente, limitée
en débit), en plus de la liste en ligne (`freeapis`).

- Adresses codées en dur : une liste distante ne peut jamais les remplacer, la clé n'est donc
  envoyée qu'à l'hôte prévu (voir `security.BUILTIN_PROVIDERS`).
- Modèles découverts chez le fournisseur (`GET /models`) dès que l'utilisateur a mis sa clé :
  tout ce que son offre gratuite permet, sans attendre une mise à jour de Projia.
- Un fournisseur déjà présent dans la liste en ligne garde ses modèles connus ; la découverte
  n'ajoute que ceux qui manquent.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from projia import secrets, security
from projia.catalog.cache import SourceCache
from projia.catalog.models import ModelInfo

log = logging.getLogger(__name__)

# `free` : filtre des modèles gratuits (None = toute l'offre est gratuite).
PROVIDERS: dict[str, dict[str, Any]] = {
    "groq": {
        "id": "groq", "name": "Groq", "base_url": "https://api.groq.com/openai/v1",
        "key_url": "https://console.groq.com/keys",
        "description": "Très rapide. Offre gratuite permanente (débit limité).",
    },
    "cerebras": {
        "id": "cerebras", "name": "Cerebras", "base_url": "https://api.cerebras.ai/v1",
        "key_url": "https://cloud.cerebras.ai",
        "description": "Parmi les plus rapides. Offre gratuite permanente (débit limité).",
    },
    "sambanova": {
        "id": "sambanova", "name": "SambaNova Cloud", "base_url": "https://api.sambanova.ai/v1",
        "key_url": "https://cloud.sambanova.ai/apis",
        "description": "Grands modèles ouverts, rapides. Offre gratuite (débit limité).",
    },
    "github": {
        "id": "github", "name": "GitHub Models",
        "base_url": "https://models.github.ai/inference",
        "models_url": "https://models.github.ai/catalog/models",
        "key_url": "https://github.com/settings/personal-access-tokens/new",
        "description": "GPT, Llama, DeepSeek, Mistral… avec un jeton GitHub (droit "
                       "« models: read »). Gratuit, débit limité.",
    },
    "together": {
        "id": "together", "name": "Together AI", "base_url": "https://api.together.xyz/v1",
        "key_url": "https://api.together.ai/settings/api-keys", "free": r"-free$",
        "description": "Modèles « Free » gratuits ; les autres sont payants (non utilisés).",
    },
    "mistral": {
        "id": "mistral", "name": "Mistral AI", "base_url": "https://api.mistral.ai/v1",
        "key_url": "https://console.mistral.ai/api-keys",
        "description": "Offre « Experiment » gratuite : tous les modèles Mistral, débit limité.",
    },
    "gemini": {
        "id": "gemini", "name": "Google Gemini",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "key_url": "https://aistudio.google.com/apikey",
        "description": "Gemini Flash et Pro avec une clé Google AI Studio gratuite.",
    },
    "nvidia": {
        "id": "nvidia", "name": "NVIDIA NIM", "base_url": "https://integrate.api.nvidia.com/v1",
        "key_url": "https://build.nvidia.com/settings/api-keys",
        "description": "Des dizaines de modèles ouverts, gratuits pour le développement.",
    },
    "huggingface": {
        "id": "huggingface", "name": "Hugging Face", "base_url": "https://router.huggingface.co/v1",
        "key_url": "https://huggingface.co/settings/tokens",
        "description": "Routeur d'inférence : crédits gratuits mensuels.",
    },
}

# Modèles qui ne sont pas des modèles de discussion (ne jamais leur envoyer un chat).
_NOT_CHAT = re.compile(
    r"embed|whisper|tts|speech|audio|transcri|guard|rerank|moderation|dall-?e|flux|"
    r"stable-diffusion|sdxl|imagen|image-gen|ocr|bge-|e5-|clip|nomic|safety|reward|"
    r"-vae|playai|orpheus|prompt-guard", re.I)


def _rows(data: Any) -> list[dict[str, Any]]:
    """`{"data": [...]}` (OpenAI), `[...]` (Together, GitHub) ou `{"models": [...]}`."""
    if isinstance(data, list):
        rows = data
    elif isinstance(data, dict):
        rows = data.get("data") or data.get("models") or []
    else:
        rows = []
    return [r for r in rows if isinstance(r, dict)]


def parse(pid: str, data: Any) -> list[ModelInfo]:
    p = PROVIDERS[pid]
    free = re.compile(p["free"], re.I) if p.get("free") else None
    out: list[ModelInfo] = []
    for r in _rows(data):
        mid = str(r.get("id") or r.get("name") or "").removeprefix("models/")
        if not mid or len(mid) > 200 or _NOT_CHAT.search(mid):
            continue
        if str(r.get("type") or "chat").lower() not in ("chat", "language", "model", ""):
            continue
        if free is not None and not free.search(mid):
            continue
        mods = r.get("supported_input_modalities") or r.get("input_modalities") or []
        tags = " ".join(str(t) for t in (r.get("capabilities") or r.get("tags") or []))
        ctx = r.get("context_length") or r.get("context_window") or (
            (r.get("limits") or {}).get("max_input_tokens") if isinstance(r.get("limits"), dict)
            else 0)
        out.append(ModelInfo(
            provider=pid, model_id=mid, name=str(r.get("name") or r.get("display_name") or mid),
            context_length=int(ctx or 0),
            input_modalities=["text", "image"] if ("image" in mods or "vision" in tags.lower()
                                                   or "-vl" in mid.lower()
                                                   or "vision" in mid.lower()) else ["text"],
            # Inconnu chez la plupart : supposé, puis vérifié à l'usage (fiabilité).
            supports_tools=True, is_free=True, needs_key=True,
            rate_limit="offre gratuite (débit limité)",
        ))
    return out


async def discover(cache: SourceCache, ttl: float) -> list[ModelInfo]:
    """Modèles des fournisseurs dont l'utilisateur a mis la clé (les autres : rien)."""
    found: list[ModelInfo] = []
    for pid, p in PROVIDERS.items():
        key = secrets.get_key(pid)
        if not key or not security.key_allowed(pid, p["base_url"]):
            continue
        url = p.get("models_url") or f"{p['base_url']}/models"
        try:
            entry = await cache.fetch_json(f"provider_models_{pid}", url, ttl=ttl,
                                           headers={"Authorization": f"Bearer {key}"})
        except Exception as exc:  # un fournisseur en panne ne bloque pas le catalogue
            log.warning("Découverte %s : %r", pid, exc)
            continue
        if entry is not None:
            found += parse(pid, entry.data)
    return found


def public(p: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in p.items() if k != "free"}
