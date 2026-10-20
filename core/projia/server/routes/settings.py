"""Fournisseurs et clés (BYOK), réglages."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request

from projia import (
    secrets,
)
from projia.catalog.i18n import texts as provider_texts
from projia.config import Settings, save_settings
from projia.server.common import (
    Hub,
    KeyBody,
    RateLimiter,
    _validate_key,
    core_of,
    settings_json,
)


def register(app: FastAPI, hub: Hub, ws_connects: RateLimiter) -> None:
    # --- Fournisseurs et clés (BYOK) --------------------------------------

    @app.get("/projia/providers")
    async def providers(request: Request) -> list[dict[str, Any]]:
        core = core_of(request)
        counts: dict[str, int] = {}
        paid_counts: dict[str, int] = {}
        for m in core.catalog.catalog.models.values():
            target = counts if m.is_free else paid_counts
            target[m.provider] = target.get(m.provider, 0) + 1
        return [{**{k: v for k, v in p.items() if k not in ("base_url", "or_prefix")},
                 "has_key": secrets.has_key(pid), "free_models": counts.get(pid, 0),
                 "paid_models": paid_counts.get(pid, 0), "i18n": provider_texts(pid, p)}
                for pid, p in sorted(core.catalog.catalog.providers.items())]


    @app.put("/projia/keys/{provider}")
    async def put_key(request: Request, provider: str, body: KeyBody) -> dict[str, Any]:
        core = core_of(request)
        ok, detail = (await _validate_key(core, provider, body.key.strip())
                      if body.validate_key else (True, "Clé chargée"))
        if ok:
            secrets.set_key(provider, body.key.strip(), persist=body.persist)
            core.router.registry.reset()
            core.catalog.refresh_in_background()
        return {"valid": ok, "detail": detail}

    @app.delete("/projia/keys/{provider}")
    async def delete_key(request: Request, provider: str) -> dict[str, bool]:
        secrets.delete_key(provider)
        core_of(request).router.registry.reset()
        return {"ok": True}

    # --- Réglages ----------------------------------------------------------

    @app.get("/projia/settings")
    async def get_settings(request: Request) -> dict[str, Any]:
        return settings_json(core_of(request))

    @app.put("/projia/settings")
    async def put_settings(request: Request) -> dict[str, Any]:
        core = core_of(request)
        patch = await request.json()
        patch.pop("server", None)  # jamais modifiable à distance
        patch.pop("custom_providers", None)  # points d'accès dédiés, sur l'appareil seulement
        if isinstance(patch.get("agent"), dict):
            patch["agent"].pop("workdir", None)  # dossier des outils fichiers : local seulement
        merged = core.settings.model_dump(mode="json")
        for k, v in patch.items():
            if isinstance(v, dict) and isinstance(merged.get(k), dict):
                merged[k].update(v)
            else:
                merged[k] = v
        new = Settings.model_validate(merged)
        for field_name in type(new).model_fields:
            setattr(core.settings, field_name, getattr(new, field_name))
        save_settings(core.settings)
        return await get_settings(request)
