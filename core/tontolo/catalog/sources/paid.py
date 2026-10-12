"""Serveurs d'API **payants** directs (OpenAI, Anthropic, DeepSeek, xAI), proposés dans les
Réglages simples à côté d'OpenRouter.

Ils ne sont utilisés que si l'utilisateur ajoute sa clé **et** autorise les modèles payants
(« Me demander » ou « Automatique », avec plafonds journalier et mensuel). Les modèles listés
par le fournisseur (`GET /models`) sont rapprochés du catalogue OpenRouter, qui donne leur prix
et leurs scores : un modèle dont le prix est inconnu n'est jamais proposé (le plafond de
dépense ne pourrait pas être garanti)."""

from __future__ import annotations

import re
from typing import Any

from tontolo import secrets, security
from tontolo.catalog.cache import SourceCache
from tontolo.catalog.models import ModelInfo

PROVIDERS: dict[str, dict[str, Any]] = {
    "openai": {
        "id": "openai", "name": "OpenAI (ChatGPT)", "base_url": "https://api.openai.com/v1",
        "key_url": "https://platform.openai.com/api-keys", "paid": True, "or_prefix": "openai/",
        "description": "GPT-5, GPT-4.1, o3… Facturé à l'usage par OpenAI.",
    },
    "anthropic": {
        "id": "anthropic", "name": "Anthropic (Claude)", "base_url": "https://api.anthropic.com/v1",
        "key_url": "https://console.anthropic.com/settings/keys", "paid": True,
        "or_prefix": "anthropic/",
        "description": "Claude Opus, Sonnet, Haiku. Facturé à l'usage par Anthropic.",
    },
    "deepseek": {
        "id": "deepseek", "name": "DeepSeek", "base_url": "https://api.deepseek.com/v1",
        "key_url": "https://platform.deepseek.com/api_keys", "paid": True,
        "or_prefix": "deepseek/",
        "description": "Très bon marché, excellent en code et en maths.",
    },
    "xai": {
        "id": "xai", "name": "xAI (Grok)", "base_url": "https://api.x.ai/v1",
        "key_url": "https://console.x.ai", "paid": True, "or_prefix": "x-ai/",
        "description": "Modèles Grok. Facturé à l'usage par xAI.",
    },
    "moonshot": {
        "id": "moonshot", "name": "Moonshot AI (Kimi)", "base_url": "https://api.moonshot.ai/v1",
        "key_url": "https://platform.moonshot.ai/console/api-keys", "paid": True,
        "or_prefix": "moonshotai/",
        "description": "Modèles Kimi : long contexte, bons en agents. Facturé à l'usage.",
    },
    "qwen": {
        "id": "qwen", "name": "Alibaba Qwen (Model Studio)",
        "base_url": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        "key_url": "https://modelstudio.console.alibabacloud.com/?tab=playground#/api-key",
        "paid": True, "or_prefix": "qwen/",
        "description": "Qwen Max, Plus, Coder… Facturé à l'usage par Alibaba Cloud.",
    },
    "perplexity": {
        "id": "perplexity", "name": "Perplexity (Sonar)", "base_url": "https://api.perplexity.ai",
        "key_url": "https://www.perplexity.ai/account/api/keys", "paid": True,
        "or_prefix": "perplexity/", "static": True,
        "description": "Réponses avec recherche web et sources. Facturé à l'usage.",
    },
}

_DATE = re.compile(r"(-\d{4}-\d{2}-\d{2}|-\d{8}|-latest)$")


def norm(model_id: str) -> str:
    """Identifiant comparable entre fournisseurs : sans date, sans ponctuation."""
    return re.sub(r"[^a-z0-9]", "", _DATE.sub("", model_id.lower().split("/", 1)[-1]))


def match(pid: str, listed: list[str], openrouter_models: list[ModelInfo]) -> list[ModelInfo]:
    """Modèles du fournisseur `pid` dont l'équivalent OpenRouter (payant) a un prix connu."""
    prefix = PROVIDERS[pid]["or_prefix"]
    ref: dict[str, ModelInfo] = {}
    for m in openrouter_models:
        if m.model_id.startswith(prefix) and not m.is_free and m.price_out > 0 \
                and not m.model_id.endswith(":free") and m.is_text:
            ref.setdefault(norm(m.model_id), m)
    best: dict[str, str] = {}
    for mid in listed:
        n = norm(mid)
        if n in ref and (n not in best or len(mid) < len(best[n])):
            best[n] = mid  # l'alias sans date plutôt que la version datée
    out = []
    for n, mid in best.items():
        src = ref[n]
        out.append(src.model_copy(deep=True, update={
            "provider": pid, "model_id": mid, "name": f"{src.name.split(': ', 1)[-1]}",
            "needs_key": True, "is_free": False, "rate_limit": None}))
    return out


async def discover(cache: SourceCache, ttl: float,
                   openrouter_models: list[ModelInfo]) -> list[ModelInfo]:
    found: list[ModelInfo] = []
    for pid, p in PROVIDERS.items():
        key = secrets.get_key(pid)
        if not key or not security.key_allowed(pid, p["base_url"]):
            continue
        if p.get("static"):  # pas de liste des modèles : ceux d'OpenRouter, même identifiant
            listed = [m.model_id.removeprefix(p["or_prefix"]) for m in openrouter_models
                      if m.model_id.startswith(p["or_prefix"])]
            found += match(pid, listed, openrouter_models)
            continue
        headers = {"Authorization": f"Bearer {key}"}
        if pid == "anthropic":
            headers |= {"x-api-key": key, "anthropic-version": "2023-06-01"}
        entry = await cache.fetch_json(f"provider_models_{pid}", f"{p['base_url']}/models",
                                       ttl=ttl, headers=headers)
        data = entry.data if entry and isinstance(entry.data, dict) else {}
        listed = [str(r.get("id", "")) for r in data.get("data", []) if isinstance(r, dict)]
        found += match(pid, listed, openrouter_models)
    return found


def public(p: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in p.items() if k not in ("or_prefix", "static")}
