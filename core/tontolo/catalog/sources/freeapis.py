"""Découverte des autres fournisseurs gratuits (BYOK).

Source : `mnfst/awesome-free-llm-apis` (`data.json`, CC0-1.0), vérifiée le
2026-10-10. Le dépôt `cheahjs/free-llm-api-resources` cité par la spécification
n'est plus accessible (HTTP 404) ; il est remplacé par celui-ci.

Chaque fournisseur n'est utilisable que si l'utilisateur a fourni sa propre clé.
"""

from __future__ import annotations

import re
from typing import Any

from tontolo.catalog.cache import SourceCache
from tontolo.catalog.models import ModelInfo

DATA_URL = "https://raw.githubusercontent.com/mnfst/awesome-free-llm-apis/main/data.json"

# Noms courts pour les variables d'environnement (GEMINI_API_KEY…). Seul le
# nommage est fixé ici ; la liste des fournisseurs vient de la source en ligne.
_ALIASES = {
    "google gemini": "gemini",
    "mistral ai": "mistral",
    "z ai (zhipu ai)": "zai",
    "cloudflare workers ai": "cloudflare",
    "hugging face": "huggingface",
    "nvidia nim": "nvidia",
    "ollama cloud": "ollama",
    "ovhcloud ai endpoints": "ovh",
    "llm7.io": "llm7",
    "kilo code": "kilo",
    "aion labs": "aion",
}

# Points d'accès compatibles OpenAI quand l'URL publiée est l'API native.
_OPENAI_COMPAT = {
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai",
    "cohere": "https://api.cohere.ai/compatibility/v1",
    "cloudflare": "https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/v1",
    "ollama": "https://ollama.com/v1",
}


def provider_slug(name: str) -> str:
    low = name.strip().lower()
    return _ALIASES.get(low) or re.sub(r"[^a-z0-9]+", "-", low).strip("-")


def parse_size(value: str | None) -> int:
    """« 128K » → 128000, « 1M » → 1000000, « ~4K » → 4000."""
    if not value:
        return 0
    m = re.search(r"([\d.,]+)\s*([KkMm]?)", value)
    if not m:
        return 0
    num = float(m.group(1).replace(",", ""))
    mult = {"k": 1_000, "m": 1_000_000}.get(m.group(2).lower(), 1)
    return int(num * mult)


def parse_rate_limit(text: str | None) -> dict[str, int]:
    """Extrait rpm/rpd/tpm/tpd/rph d'un texte libre (« 30 RPM, 1,500 RPD »)."""
    out: dict[str, int] = {}
    if not text:
        return out
    pattern = r"([\d.,]+\s*[KkMm]?)\s*(RPM|RPD|TPM|TPD|RPS|req/hr)\b"
    for num, unit in re.findall(pattern, text, flags=re.I):
        key = unit.lower().replace("req/hr", "rph")
        out.setdefault(key, parse_size(num))
    if "rps" in out:
        out["rpm"] = out.pop("rps") * 60
    return out


_KEYLESS = re.compile(
    r"no (api )?key|without (an? )?(api )?key|anonymous (access|tier)|free anonymous|"
    r"no signup|keyless", re.I)


def is_keyless(description: str) -> bool:
    """Accès anonyme annoncé par la source (« no API key required », « anonymous tier »…)."""
    return bool(_KEYLESS.search(description or ""))


def _modalities(text: str) -> tuple[list[str], list[str]]:
    low = (text or "").lower()
    ins = ["text"]
    if re.search(r"image|vision|multimodal|mllm", low):
        ins.append("image")
    if "audio" in low or "speech" in low:
        ins.append("audio")
    return ins, ["text"]


def parse(data: dict[str, Any]) -> tuple[list[ModelInfo], dict[str, dict[str, Any]]]:
    """Renvoie (modèles, fournisseurs). OpenRouter est ignoré : il a sa propre source."""
    models: list[ModelInfo] = []
    providers: dict[str, dict[str, Any]] = {}
    for p in data.get("providers", []):
        slug = provider_slug(p.get("name", ""))
        if not slug or slug == "openrouter":
            continue
        base = _OPENAI_COMPAT.get(slug) or p.get("baseUrl") or ""
        keyless = is_keyless(p.get("description", "")) and "{" not in base
        providers[slug] = {
            "keyless": keyless,
            "id": slug,
            "name": p.get("name", slug),
            "base_url": base.rstrip("/"),
            "key_url": p.get("url"),
            "description": p.get("description", ""),
            "country": p.get("country"),
        }
        for m in p.get("models", []):
            mid = m.get("id")
            if not mid:
                continue
            ins, outs = _modalities(m.get("modality", ""))
            models.append(ModelInfo(
                provider=slug,
                model_id=mid,
                name=m.get("name") or mid,
                context_length=parse_size(m.get("context")),
                max_output=parse_size(m.get("maxOutput")) or None,
                input_modalities=ins,
                output_modalities=outs,
                # La source ne précise pas l'appel d'outils : supposé pour les
                # gros modèles compatibles OpenAI, vérifié à l'usage (fiabilité).
                supports_tools=True,
                is_free=True,
                needs_key=not keyless,
                rate_limit=m.get("rateLimit"),
            ))
    return models, providers


async def fetch(
    cache: SourceCache, ttl: float, force: bool = False
) -> tuple[list[ModelInfo], dict[str, dict[str, Any]]]:
    entry = await cache.fetch_json("freeapis", DATA_URL, ttl=ttl, force=force)
    return parse(entry.data) if entry else ([], {})
