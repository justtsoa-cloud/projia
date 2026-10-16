"""Mode avancé, espace de travail, mise à jour, stockage, à propos."""

from __future__ import annotations

import asyncio
import json
import re
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request

from tontolo import (
    __version__,
    sandbox,
    secrets,
    security,
)
from tontolo.agent.workspace import is_desktop
from tontolo.app_state import Core
from tontolo.config import CustomProvider, Settings, save_settings
from tontolo.home import tracks
from tontolo.memory import name_from
from tontolo.security import (
    key_allowed,
)
from tontolo.server import common
from tontolo.server.common import (
    ATTRIBUTIONS,
    CustomProviderBody,
    Hub,
    RateLimiter,
    WorkspaceBody,
    _custom_url_problem,
    _local_only,
    core_of,
    settings_json,
)
from tontolo.storage import space
from tontolo.update import check_update, download_update


def register(app: FastAPI, hub: Hub, ws_connects: RateLimiter) -> None:
    # --- Mode avancé : fournisseurs personnalisés, export / import des réglages ----------

    @app.get("/tontolo/custom-providers")
    async def custom_list(request: Request) -> list[dict[str, Any]]:
        core = core_of(request)
        counts: dict[str, int] = {}
        for m in core.catalog.catalog.models.values():
            counts[m.provider] = counts.get(m.provider, 0) + 1
        return [{**cp.model_dump(), "has_key": secrets.has_key(cp.id),
                 "models": counts.get(cp.id, 0)} for cp in core.settings.custom_providers]

    @app.post("/tontolo/custom-providers")
    async def custom_add(request: Request, body: CustomProviderBody) -> dict[str, Any]:
        core = core_of(request)
        _local_only(request, core, "Fournisseurs personnalisés")
        if len(core.settings.custom_providers) >= 20:
            raise HTTPException(400, "20 fournisseurs personnalisés au plus")
        base = body.base_url.strip().rstrip("/")
        problem = await _custom_url_problem(base, body.needs_key)
        if problem:
            raise HTTPException(400, problem)
        if not body.free and (body.price_in_per_m <= 0 or body.price_out_per_m <= 0):
            raise HTTPException(400, "Fournisseur payant : indiquez ses prix (sinon le plafond "
                                     "de dépense ne peut pas être garanti)")
        key = (body.key or "").strip()
        if body.needs_key and not key:
            raise HTTPException(400, "Clé requise")
        slug = re.sub(r"[^a-z0-9]+", "-", body.name.lower()).strip("-")[:30] or "fournisseur"
        pid, n = f"custom-{slug}", 2
        taken = {cp.id for cp in core.settings.custom_providers} | set(
            core.catalog.catalog.providers)
        while pid in taken:
            pid, n = f"custom-{slug}-{n}", n + 1
        cp = CustomProvider(id=pid, name=body.name.strip()[:60], base_url=base, free=body.free,
                            needs_key=body.needs_key, price_in_per_m=body.price_in_per_m,
                            price_out_per_m=body.price_out_per_m)
        found = await common._custom_probe(cp, key)
        if isinstance(found, str):
            raise HTTPException(400, found)
        security.pins().reset(pid)
        if key:
            if not key_allowed(pid, base):  # épingle l'hôte maintenant
                raise HTTPException(400, "Adresse refusée pour une clé (HTTPS requis)")
            secrets.set_key(pid, key)
        core.settings.custom_providers.append(cp)
        save_settings(core.settings)
        core.router.registry.reset()
        await core.catalog.refresh()
        return {"id": pid, "models": found}

    @app.delete("/tontolo/custom-providers/{pid}")
    async def custom_delete(request: Request, pid: str) -> dict[str, bool]:
        core = core_of(request)
        _local_only(request, core, "Fournisseurs personnalisés")
        before = len(core.settings.custom_providers)
        core.settings.custom_providers = [cp for cp in core.settings.custom_providers
                                          if cp.id != pid]
        if len(core.settings.custom_providers) == before:
            raise HTTPException(404, "Fournisseur inconnu")
        save_settings(core.settings)
        secrets.delete_key(pid)
        security.pins().reset(pid)
        core.router.registry.reset()
        await core.catalog.refresh()
        return {"ok": True}

    @app.get("/tontolo/settings/export")
    async def settings_export(request: Request) -> dict[str, Any]:
        """Réglages à sauvegarder ou copier sur un autre appareil : jamais de clé ni de jeton."""
        data = core_of(request).settings.model_dump(mode="json")
        data.pop("server", None)
        return {"tontolo_settings": 1, "settings": data}

    @app.post("/tontolo/settings/import")
    async def settings_import(request: Request) -> dict[str, Any]:
        core = core_of(request)
        _local_only(request, core, "Import des réglages")
        body = await request.json()
        data = body.get("settings") if isinstance(body, dict) else None
        if not isinstance(data, dict) or body.get("tontolo_settings") != 1:
            raise HTTPException(400, "Fichier de réglages Tontolo attendu")
        data.pop("server", None)
        if isinstance(data.get("agent"), dict):
            data["agent"].pop("workdir", None)
        merged = core.settings.model_dump(mode="json")
        merged.update(data)
        try:
            new = Settings.model_validate(merged)
        except ValueError as exc:
            raise HTTPException(400, f"Réglages invalides : {str(exc)[:300]}") from exc
        for cp in new.custom_providers:  # mêmes garde-fous qu'à l'ajout manuel
            if await _custom_url_problem(cp.base_url, cp.needs_key):
                raise HTTPException(400, f"Adresse refusée : {cp.name}")
        for field_name in type(new).model_fields:
            if field_name != "server":
                setattr(core.settings, field_name, getattr(new, field_name))
        save_settings(core.settings)
        core.router.registry.reset()
        core.catalog.refresh_in_background()
        return settings_json(core)

    def _workspace_json(core: Core) -> dict[str, Any]:
        ws = core.chat.workspace
        return {"path": str(ws.root) if ws else None, "desktop": is_desktop(),
                "commands": bool(ws) and is_desktop() and sandbox.available(),
                "history": [{k: e.get(k) for k in ("rel", "action", "at")}
                            for e in (ws.journal() if ws else [])][-20:][::-1]}

    @app.get("/tontolo/execution/capabilities")
    async def execution_capabilities(request: Request) -> dict[str, Any]:
        isolated = await asyncio.to_thread(sandbox.available)
        return {"sandbox": isolated, "latex": True, "latex_local": isolated,
                "commands": isolated and is_desktop(),
                "reason": None if isolated else sandbox.unavailable_message(
                    core_of(request).settings.language)}

    @app.get("/tontolo/workspace")
    async def workspace_get(request: Request) -> dict[str, Any]:
        return _workspace_json(core_of(request))

    @app.put("/tontolo/workspace")
    async def workspace_put(request: Request, body: WorkspaceBody) -> dict[str, Any]:
        core = core_of(request)
        _local_only(request, core)
        try:
            root = core.chat.set_workdir(body.path)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        core.settings.agent.workdir = str(root) if root else None
        save_settings(core.settings)
        return _workspace_json(core)

    @app.post("/tontolo/workspace/undo")
    async def workspace_undo(request: Request) -> dict[str, Any]:
        core = core_of(request)
        _local_only(request, core)
        if core.chat.workspace is None:
            raise HTTPException(400, "Aucun dossier de travail choisi")
        return {"message": core.chat.workspace.undo(), **_workspace_json(core)}

    @app.get("/tontolo/update")
    async def update(request: Request, target: str | None = None,
                     arch: str | None = None) -> dict[str, Any]:
        return await check_update(target=target, arch=arch)

    @app.post("/tontolo/update/download")
    async def update_download(request: Request, target: str,
                              arch: str | None = None) -> dict[str, Any]:
        if target not in ("linux", "android"):
            raise HTTPException(400, "cible invalide")
        core = core_of(request)
        result = await download_update(space.cache_dir(core.settings.data_dir, "updates"),
                                       target, arch, language=core.settings.language)
        if result.get("ok"):
            space.keep_only(Path(result["path"]).parent, Path(result["path"]))
        return result

    @app.get("/tontolo/home")
    async def home(request: Request) -> dict[str, Any]:
        """Accueil d'une nouvelle discussion : prénom (réglage, sinon mémoire) et sujets
        récents pour des suggestions personnalisées."""
        core = core_of(request)
        name = core.settings.user_name.strip()
        if not name and core.settings.memory_enabled:
            name = name_from([str(m.get("text") or "") for m in await core.db.list_memories()])
        recent = [{"id": c["id"], "title": c["title"]}
                  for c in await core.db.list_conversations(6, 0, None, None)
                  if str(c.get("title") or "").strip()][:4]
        out: dict[str, Any] = {"name": name, "name_from": "settings" if core.settings.user_name
                               .strip() else ("memory" if name else ""), "recent": recent}
        if core.settings.home_tracks:  # piste du jour : centres d'intérêt locaux (jamais envoyés)
            raw = await core.db.kv_get("home_dismissed")
            gone = json.loads(raw) if raw else {}
            history = await core.db.list_conversations(40, 0, None, None)
            out["tracks"] = tracks.build(history, core.settings.language, gone)
        return out

    @app.post("/tontolo/home/dismiss")
    async def home_dismiss(request: Request) -> dict[str, Any]:
        """« Pas pour moi » : ce thème n'est plus proposé pendant deux semaines."""
        core = core_of(request)
        body = await request.json()
        topic = tracks.plain(str(body.get("topic") or "")[:tracks.MAX_TOPIC])
        if topic:
            raw = await core.db.kv_get("home_dismissed")
            gone = {k: v for k, v in (json.loads(raw) if raw else {}).items()
                    if k in tracks.active_dismissals(json.loads(raw) if raw else {})}
            gone[topic] = time.time()
            await core.db.kv_set("home_dismissed", json.dumps(dict(list(gone.items())[-50:])))
        return {"ok": True}

    @app.get("/tontolo/storage")
    async def storage(request: Request) -> dict[str, Any]:
        """Place occupée : données (discussions, créations, tâches…) et cache unique."""
        data = core_of(request).settings.data_dir
        return await asyncio.to_thread(space.report, data)

    @app.post("/tontolo/storage/clear-cache")
    async def storage_clear(request: Request) -> dict[str, Any]:
        core = core_of(request)
        freed = await asyncio.to_thread(space.clear_cache, core.settings.data_dir)
        return {"freed": freed, **await asyncio.to_thread(space.report,
                                                          core.settings.data_dir)}

    @app.get("/tontolo/about")
    async def about() -> dict[str, Any]:
        return {"version": __version__, "license": "Apache-2.0",
                "attributions": ATTRIBUTIONS}
