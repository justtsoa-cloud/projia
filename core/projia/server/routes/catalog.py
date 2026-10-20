"""Catalogue des modèles, nouveautés, état du routage et préférences."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException, Request

from projia.catalog.models import Category, ModelInfo
from projia.router.quota import QuotaManager
from projia.server.common import (
    Hub,
    PrefBody,
    RateLimiter,
    core_of,
)


def register(app: FastAPI, hub: Hub, ws_connects: RateLimiter) -> None:
    # --- Catalogue, nouveautés, préférences --------------------------------

    def _model_json(m: ModelInfo, usable: set[str],
                    quota: QuotaManager | None = None) -> dict[str, Any]:
        return {
            "key": m.key, "id": m.model_id, "provider": m.provider, "name": m.name,
            "family": m.family, "max_output": m.max_output,
            "inputs": m.input_modalities, "outputs": m.output_modalities,
            # Agentique : sait appeler des outils (recherche, fichiers, calcul…).
            "agentic": m.supports_tools and m.is_text,
            "free": m.is_free, "usable": m.provider in usable, "tools": m.supports_tools,
            "vision": m.supports_vision, "context": m.context_length, "media": m.media,
            "quality": m.quality, "speed": m.speed, "provisional": m.provisional,
            "rate_limit": m.rate_limit, "created": m.created,
            "price_in": m.price_in, "price_out": m.price_out,
            "available_at": quota.available_at(m) if quota is not None else 0.0,
            **_quota_json(m, quota),
        }

    def _quota_json(m: ModelInfo, quota: QuotaManager | None) -> dict[str, Any]:
        if quota is None:
            return {"status": "available"}
        st = quota.status_of(m)
        return {"status": st.status, "wait_reason": st.reason}

    @app.get("/projia/catalog")
    async def catalog(request: Request, category: str | None = None, free: bool = True,
                      usable: bool = False, q: str | None = None,
                      limit: int = 100) -> dict[str, Any]:
        core = core_of(request)
        usable_set = core.catalog.usable_providers()
        if category is not None:
            try:
                Category(category)
            except ValueError as exc:
                raise HTTPException(400, "catégorie inconnue") from exc
        models = core.catalog.catalog.filter(category=category, free_only=free,
                                             usable=usable_set if usable else None)
        if q:
            ql = q.lower()
            models = [m for m in models if ql in m.key.lower() or ql in m.name.lower()]
        return {"updated_at": core.catalog.catalog.updated_at,
                "sources": core.catalog.catalog.sources,
                "models": [_model_json(m, usable_set, core.router.quota)
                           for m in models[:limit]]}

    @app.get("/projia/generators")
    async def generators(request: Request) -> dict[str, Any]:
        """Générateurs d'images, de vidéos et de sons, par type : prêts d'abord (gratuits
        puis payants), puis ceux qui demandent une clé."""
        core = core_of(request)
        usable_set = core.catalog.usable_providers()
        out: dict[str, list[dict[str, Any]]] = {}
        for kind in ("image_gen", "image_edit", "video_gen", "tts", "stt", "music_sfx"):
            models = core.catalog.catalog.filter(category=kind)
            models.sort(key=lambda m: (m.provider not in usable_set, not m.is_free))
            out[kind] = [_model_json(m, usable_set, core.router.quota) for m in models[:40]]
        return {"kinds": out}

    @app.post("/projia/catalog/refresh")
    async def refresh_catalog(request: Request) -> dict[str, Any]:
        changes = await core_of(request).catalog.refresh(force=True)
        return {"changes": len(changes)}

    @app.get("/projia/online")
    async def online(request: Request) -> dict[str, bool]:
        return {"online": await core_of(request).router.probe()}

    @app.get("/projia/health")
    async def model_health(request: Request) -> dict[str, Any]:
        return await core_of(request).router.health()

    @app.get("/projia/status")
    async def status(request: Request) -> dict[str, Any]:
        core = core_of(request)
        return {"quotas": core.router.quota.snapshot(),
                "usable_providers": sorted(core.catalog.usable_providers()),
                "catalog_updated_at": core.catalog.catalog.updated_at,
                "sources": core.catalog.catalog.sources,
                "mcp_errors": core.mcp.errors}

    @app.post("/projia/route")
    async def route_preview(request: Request) -> dict[str, Any]:
        """« Pourquoi ce modèle ? » : décision sans appel au fournisseur."""
        core = core_of(request)
        body = await request.json()
        d = await core.router.decide(body.get("messages") or [],
                                     conversation_id=body.get("conversation_id"),
                                     model=body.get("model"))
        return {"profile": d.profile.as_dict(),
                "chain": [dict(c.reason(d.profile.category), model=c.model.key,
                               name=c.model.name) for c in d.chain[:10]]}

    @app.get("/projia/changes")
    async def changes(request: Request, limit: int = 100) -> list[dict[str, Any]]:
        return await core_of(request).db.list_changes(limit)

    @app.post("/projia/changes/seen")
    async def changes_seen(request: Request) -> dict[str, bool]:
        await core_of(request).db.mark_changes_seen()
        return {"ok": True}

    @app.get("/projia/preferences")
    async def get_prefs(request: Request) -> list[dict[str, Any]]:
        return await core_of(request).db.get_preferences()


    @app.put("/projia/preferences")
    async def put_pref(request: Request, body: PrefBody) -> dict[str, bool]:
        if body.scope not in ("global", "conversation", "category"):
            raise HTTPException(400, "portée invalide")
        model = None if body.model in (None, "", "auto") else body.model
        await core_of(request).db.set_preference(body.scope, body.scope_key, model,
                                                 body.strict)
        return {"ok": True}
