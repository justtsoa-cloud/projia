"""Source OpenRouter : catalogue complet, prix, capacités, indices AA intégrés, flux RSS.

Documentation vérifiée le 2026-10-10 : `GET https://openrouter.ai/api/v1/models`
(sans clé ; `output_modalities=all` inclut image/audio), champ `created`,
`benchmarks.artificial_analysis`, flux `?use_rss=true`, limites via `/api/v1/key`.
"""

from __future__ import annotations

import re
import time
import xml.etree.ElementTree as ET
from typing import Any

from tontolo.catalog.cache import SourceCache
from tontolo.catalog.models import ModelInfo

BASE_URL = "https://openrouter.ai/api/v1"
MODELS_URL = f"{BASE_URL}/models"


def _price(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def is_free(pricing: dict[str, Any]) -> bool:
    """Gratuit seulement si **tous** les postes de prix numériques valent 0."""
    prices = [_price(v) for k, v in pricing.items() if not isinstance(v, dict | list)]
    return bool(prices) and all(p == 0 for p in prices)


def _media(raw: dict[str, Any]) -> list[str]:
    arch = raw.get("architecture") or {}
    outs = set(arch.get("output_modalities") or [])
    ins = set(arch.get("input_modalities") or [])
    media: list[str] = []
    if "image" in outs:
        media.append("image_gen")
        if "image" in ins:
            media.append("image_edit")
    if "audio" in outs:
        text = f"{raw.get('id', '')} {raw.get('description', '')}".lower()
        media.append("music_sfx" if re.search(r"music|song|lyria", text) else "tts")
    if "video" in outs:
        media.append("video_gen")
    return media


def parse_models(data: dict[str, Any]) -> list[ModelInfo]:
    now = time.time()
    out: list[ModelInfo] = []
    for raw in data.get("data", []):
        exp = raw.get("expiration_date")
        if exp:
            try:
                if time.mktime(time.strptime(exp[:10], "%Y-%m-%d")) < now:
                    continue
            except ValueError:
                pass
        pricing = raw.get("pricing") or {}
        arch = raw.get("architecture") or {}
        top = raw.get("top_provider") or {}
        metrics: dict[str, float] = {}
        aa = ((raw.get("benchmarks") or {}).get("artificial_analysis")) or {}
        for src, dst in (("intelligence_index", "or_aa.intelligence"),
                         ("coding_index", "or_aa.coding"),
                         ("agentic_index", "or_aa.agentic")):
            if isinstance(aa.get(src), int | float):
                metrics[dst] = float(aa[src])
        out.append(ModelInfo(
            provider="openrouter",
            model_id=raw["id"],
            name=raw.get("name") or raw["id"],
            created=raw.get("created"),
            context_length=int(raw.get("context_length") or top.get("context_length") or 0),
            max_output=top.get("max_completion_tokens"),
            input_modalities=arch.get("input_modalities") or ["text"],
            output_modalities=arch.get("output_modalities") or ["text"],
            supports_tools="tools" in (raw.get("supported_parameters") or []),
            is_free=is_free(pricing),
            needs_key=True,
            price_in=_price(pricing.get("prompt")),
            price_out=_price(pricing.get("completion")),
            media=_media(raw),
            metrics=metrics,
        ))
    return out


async def fetch_models(cache: SourceCache, ttl: float, force: bool = False) -> list[ModelInfo]:
    entry = await cache.fetch_json(
        "openrouter_models", MODELS_URL, ttl=ttl, params={"output_modalities": "all"},
        force=force,
    )
    return parse_models(entry.data) if entry else []


def parse_rss(xml_text: str) -> list[dict[str, str]]:
    """Extrait les entrées (titre, lien, date) du flux « nouveaux modèles »."""
    items: list[dict[str, str]] = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return items
    for item in root.iter("item"):
        items.append({
            "title": (item.findtext("title") or "").strip(),
            "link": (item.findtext("link") or "").strip(),
            "date": (item.findtext("pubDate") or "").strip(),
        })
    return items


async def fetch_rss(cache: SourceCache, ttl: float, force: bool = False) -> list[dict[str, str]]:
    entry = await cache.fetch_json(
        "openrouter_rss", MODELS_URL, ttl=ttl, params={"use_rss": "true"}, force=force,
        parse="text",
    )
    return parse_rss(entry.data) if entry else []


async def fetch_key_limits(api_key: str) -> dict[str, Any] | None:
    """Limites de la clé (`/api/v1/key`) : crédits restants, niveau gratuit…"""
    from tontolo import http

    try:
        resp = await http.client().get(
            f"{BASE_URL}/key", headers={"Authorization": f"Bearer {api_key}"}
        )
        if resp.status_code == 200:
            data: dict[str, Any] = resp.json().get("data", {})
            return data
    except Exception:
        return None
    return None
