"""Orchestration du catalogue : chargement instantané depuis le cache, rafraîchissement
incrémental en arrière-plan à chaque utilisation, journal des nouveautés."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from collections.abc import Callable
from typing import Any

from tontolo import http, secrets, security
from tontolo.catalog import watcher
from tontolo.catalog.cache import SourceCache
from tontolo.catalog.catalog import Catalog, build_catalog
from tontolo.catalog.models import ModelInfo
from tontolo.catalog.sources import (
    freeapis,
    hfspaces,
    keyed,
    local_llm,
    openrouter,
    paid,
    pollinations,
    rankings,
)
from tontolo.config import CustomProvider, Settings
from tontolo.media.providers import LOCAL_TTS_MODEL
from tontolo.storage.db import Database

log = logging.getLogger(__name__)

BUILTIN_PROVIDERS: dict[str, dict[str, Any]] = {
    "openrouter": {
        "id": "openrouter", "name": "OpenRouter", "base_url": openrouter.BASE_URL,
        "key_url": "https://openrouter.ai/settings/keys",
        "description": "Agrégateur : nombreux modèles « :free » avec une clé gratuite.",
    },
    "local": {
        "id": "local", "name": "Appareil", "base_url": "", "key_url": None, "keyless": True,
        "description": "Synthèse vocale du système, sans quota.",
    },
    "pollinations": {
        "id": "pollinations", "name": "Pollinations", "base_url": pollinations.TEXT_BASE_URL,
        "key_url": None, "keyless": True,
        "description": "Texte et images sans clé (débit limité).",
    },
    "hf_spaces": {
        "id": "hf_spaces", "name": "Spaces Hugging Face", "base_url": "https://huggingface.co",
        "key_url": None, "keyless": True,
        "description": "Vidéo sans clé via des Spaces publics (GPU partagé, quota quotidien).",
    },
}


class CatalogService:
    def __init__(self, settings: Settings, db: Database | None = None) -> None:
        self.settings = settings
        self.db = db
        self.cache_dir = settings.data_dir / "cache"
        self.catalog = Catalog(providers=dict(BUILTIN_PROVIDERS))
        self._task: asyncio.Task[list[dict[str, Any]]] | None = None
        self._listeners: list[Callable[[list[dict[str, Any]]], None]] = []

    @property
    def ttl(self) -> float:
        return self.settings.catalog_ttl_hours * 3600

    def on_changes(self, cb: Callable[[list[dict[str, Any]]], None]) -> None:
        self._listeners.append(cb)

    def usable_providers(self) -> set[str]:
        """Fournisseurs appelables : sans clé, ou dont l'utilisateur a fourni la clé."""
        out = set()
        for pid, p in self.catalog.providers.items():
            if p.get("keyless") or secrets.has_key(pid):
                out.add(pid)
        return out

    async def load(self) -> Catalog:
        """Démarrage : catalogue construit depuis le cache, sans réseau ; s'il n'y a pas
        de cache (premier lancement), rafraîchissement bloquant."""
        await self._build(SourceCache(self.cache_dir, offline=True), record=False)
        if not any(m.provider not in ("local", "hf_spaces")
                   for m in self.catalog.models.values()):
            # Premier lancement : catalogues rapides d'abord (quelques secondes) ; les
            # classements, plus lents, arrivent ensuite en arrière-plan.
            await self._build(SourceCache(self.cache_dir), record=True, quick=True)
            self.refresh_in_background()
        return self.catalog

    async def refresh(self, force: bool = False) -> list[dict[str, Any]]:
        return await self._build(SourceCache(self.cache_dir), force=force, record=True)

    def refresh_in_background(self, force: bool = False) -> asyncio.Task[list[dict[str, Any]]]:
        """Mise à jour non bloquante (à l'ouverture et avant chaque conversation)."""
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self.refresh(force=force))
        return self._task

    async def _build(
        self, cache: SourceCache, force: bool = False, record: bool = True,
        quick: bool = False,
    ) -> list[dict[str, Any]]:
        ttl = self.ttl
        aa_key = secrets.get_key("artificial-analysis")
        results = await asyncio.gather(
            openrouter.fetch_models(cache, ttl, force),
            pollinations.fetch_models(cache, ttl, force),
            freeapis.fetch(cache, ttl, force),
            _none() if quick else rankings.fetch_artificial_analysis(cache, aa_key, ttl, force),
            _none() if quick else rankings.fetch_lmarena(cache, ttl, force),
            local_llm.discover(),
            return_exceptions=True,
        )
        or_models, poll_models, free_res, aa, lma, local_models = (
            r if not isinstance(r, BaseException) else None for r in results
        )
        for r in results:
            if isinstance(r, BaseException):
                log.warning("Source en échec : %r", r)
        models: list[ModelInfo] = [*(or_models or []), *(poll_models or []),
                                   LOCAL_TTS_MODEL.model_copy(deep=True), *hfspaces.models(),
                                   *(local_models or [])]
        providers = dict(BUILTIN_PROVIDERS)
        providers.update(local_llm.PROVIDERS)
        if isinstance(free_res, tuple):
            free_models, free_providers = free_res
            models += free_models
            providers.update(free_providers)
        # Fournisseurs intégrés en dernier : une liste distante ne peut jamais remplacer leur
        # adresse (leur clé n'est envoyée qu'à l'adresse codée en dur).
        providers.update(BUILTIN_PROVIDERS)
        providers.update({pid: paid.public(p) for pid, p in paid.PROVIDERS.items()})
        for pid, p in keyed.PROVIDERS.items():  # adresse intégrée prioritaire sur la liste en ligne
            providers[pid] = {**providers.get(pid, {}), **keyed.public(p), "keyless": False}
        for cp in self.settings.custom_providers:  # mode avancé : ajoutés par l'utilisateur
            providers[cp.id] = custom_public(cp)
        try:
            models += await self._discover_custom(cache, ttl)
        except Exception as exc:
            log.warning("Fournisseurs personnalisés : %r", exc)
        try:  # gratuits avec clé : tous les modèles de l'offre, dès que la clé est là
            known = {m.key for m in models}
            models += [m for m in await keyed.discover(cache, ttl) if m.key not in known]
        except Exception as exc:
            log.warning("Fournisseurs à clé : %r", exc)
        try:  # serveurs payants directs : seulement si l'utilisateur a mis sa clé
            models += await paid.discover(cache, ttl, or_models or [])
        except Exception as exc:  # une source en panne ne doit pas bloquer le catalogue
            log.warning("Serveurs payants : %r", exc)
        if not cache.offline:
            models += await self._discover_media(providers, cache)
        if not any(m.provider not in ("local", "hf_spaces", *local_llm.PROVIDERS)
                   for m in models):
            return []  # rien en cache ni en ligne : on garde l'ancien catalogue
        ranking_entries = [*(aa or []), *(lma or [])]
        catalog = build_catalog(models, ranking_entries, providers)
        catalog.sources = {
            "openrouter": len(or_models or []), "pollinations": len(poll_models or []),
            "freeapis": len(free_res[0]) if isinstance(free_res, tuple) else 0,
            "artificial_analysis": len(aa or []), "lmarena": len(lma or []),
        }
        changes = self._record(catalog, cache) if record else []
        self.catalog = catalog
        if changes:
            if self.db is not None:
                await self.db.add_changes(changes)
            for cb in self._listeners:
                cb(changes)
        return changes

    async def _discover_custom(self, cache: SourceCache, ttl: float) -> list[ModelInfo]:
        """Modèles des fournisseurs personnalisés (`GET /models`, clé envoyée seulement en HTTPS
        à l'hôte épinglé ; serveur local HTTP : sans clé)."""
        out: list[ModelInfo] = []
        for cp in self.settings.custom_providers:
            headers: dict[str, str] = {}
            key = secrets.get_key(cp.id)
            if cp.needs_key:
                if not key or not security.key_allowed(cp.id, cp.base_url):
                    continue
                headers["Authorization"] = f"Bearer {key}"
            entry = await cache.fetch_json(f"provider_models_{cp.id}",
                                           f"{cp.base_url.rstrip('/')}/models", ttl=ttl,
                                           headers=headers)
            out += custom_models(cp, entry.data if entry else None)
        return out

    def _record(self, catalog: Catalog, cache: SourceCache) -> list[dict[str, Any]]:
        prev = cache.get("catalog_snapshot")
        prev_tops = cache.get("catalog_tops")
        snap = catalog.snapshot()
        tops = watcher.top_free(catalog)
        changes = watcher.diff(prev.data if prev else {}, snap)
        changes += watcher.top_changes(prev_tops.data if prev_tops else {}, tops)
        cache.put("catalog_snapshot", snap)
        cache.put("catalog_tops", tops)
        return changes

    async def _discover_media(
        self, providers: dict[str, dict[str, Any]], cache: SourceCache
    ) -> list[ModelInfo]:
        """Pour les fournisseurs à niveau gratuit dont l'utilisateur a la clé, liste
        leurs modèles (`GET /models`) pour détecter la transcription et la synthèse vocale."""
        found: list[ModelInfo] = []
        for pid, p in providers.items():
            if pid in BUILTIN_PROVIDERS or p.get("paid") or "{" in p.get("base_url", ""):
                continue
            key = secrets.get_key(pid)
            if not key or not security.key_allowed(pid, p.get("base_url", "")):
                continue
            entry = await cache.fetch_json(
                f"provider_models_{pid}", f"{p['base_url']}/models", ttl=self.ttl,
                headers={"Authorization": f"Bearer {key}"},
            )
            data = entry.data if entry and isinstance(entry.data, dict) else {}
            for raw in data.get("data", []):
                mid = str(raw.get("id", ""))
                media = []
                if re.search(r"whisper|transcri|stt", mid, re.I):
                    media = ["stt"]
                elif re.search(r"tts|speech|orpheus|playai", mid, re.I):
                    media = ["tts"]
                if media:
                    found.append(ModelInfo(
                        provider=pid, model_id=mid, name=mid, input_modalities=["audio"]
                        if media == ["stt"] else ["text"],
                        output_modalities=["text"] if media == ["stt"] else ["audio"],
                        is_free=True, needs_key=True, media=media,
                        rate_limit="niveau gratuit du fournisseur",
                    ))
        return found


async def close() -> None:
    await http.aclose()


def dump(models: list[ModelInfo]) -> str:
    return json.dumps([m.model_dump() for m in models], ensure_ascii=False, indent=1)


async def _none() -> list[Any]:
    return []


def custom_public(cp: CustomProvider) -> dict[str, Any]:
    return {"id": cp.id, "name": cp.name, "base_url": cp.base_url.rstrip("/"),
            "keyless": not cp.needs_key, "custom": True, "paid": not cp.free,
            "description": "Fournisseur personnalisé (mode avancé)."}


def custom_models(cp: CustomProvider, data: Any) -> list[ModelInfo]:
    """Modèles listés par un fournisseur personnalisé (mêmes filtres que les intégrés)."""
    rows = keyed._rows(data)
    out: list[ModelInfo] = []
    for r in rows[:500]:
        mid = str(r.get("id") or "")
        if not mid or len(mid) > 200 or keyed._NOT_CHAT.search(mid):
            continue
        out.append(ModelInfo(
            provider=cp.id, model_id=mid, name=str(r.get("name") or mid),
            context_length=int(r.get("context_length") or 0), supports_tools=True,
            is_free=cp.free, needs_key=cp.needs_key,
            price_in=0.0 if cp.free else cp.price_in_per_m / 1e6,
            price_out=0.0 if cp.free else cp.price_out_per_m / 1e6))
    return out
