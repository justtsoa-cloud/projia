"""Notes, métriques, cache de réponses, mémoire, dépenses, synchronisation, MCP."""

from __future__ import annotations

import base64
import binascii
import json
import re
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response

from projia import (
    metrics,
)
from projia.agent.mcp_client import MAX_SERVERS as MCP_MAX_SERVERS
from projia.agent.mcp_client import check_server as check_mcp_server
from projia.agent.mcp_client import load_config, save_config
from projia.security import (
    assert_public_url,
)
from projia.server.common import (
    LOOPBACK,
    SYNC_CREATION_MAX,
    FeedbackBody,
    Hub,
    MemoryBody,
    RateLimiter,
    core_of,
    safe_mime,
)


def register(app: FastAPI, hub: Hub, ws_connects: RateLimiter) -> None:
    # --- Dépenses, synchronisation, MCP, mise à jour ---------------------

    @app.post("/projia/feedback")
    async def feedback(request: Request, body: FeedbackBody) -> dict[str, Any]:
        """👍 / 👎 sur une réponse (0 : annuler). Renvoie le modèle et le type de demande, que
        l'application peut partager anonymement (jamais le texte)."""
        out = await core_of(request).chat.rate(body.uid, body.rating, body.reason)
        if out is None:
            raise HTTPException(404, "Réponse introuvable")
        return out

    @app.put("/projia/feedback/global")
    async def feedback_global(request: Request) -> dict[str, int]:
        """Notes collectives anonymes (fonction Supabase `model_scores`), relayées par l'app."""
        core = core_of(request)
        body = await request.json()
        rows = body.get("scores") if isinstance(body, dict) else None
        kept = core.router.set_global_scores(rows if isinstance(rows, list) else [])
        await core.db.kv_set("global_scores", json.dumps(
            [{"model": m, "category": c, "score": v, "devices": 999}
             for (m, c), v in core.router.reliability.global_scores.items()]))
        return {"kept": kept}

    @app.get("/projia/metrics")
    async def metrics_text(request: Request) -> Response:
        """Métriques locales au format Prometheus (rien n'est envoyé ailleurs)."""
        core = core_of(request)
        gauges = {"projia_turns_running": float(len(core.turns.running())),
                  "projia_models_usable": float(sum(
                      1 for m in core.catalog.catalog.models.values()
                      if m.provider in core.catalog.usable_providers())),
                  "projia_ws_clients": float(len(hub.queues))}
        return Response(metrics.render(gauges), media_type="text/plain; version=0.0.4")

    @app.get("/projia/answers")
    async def answers_info(request: Request) -> dict[str, Any]:
        """Réponses déjà données gardées sur l'appareil (cache sémantique)."""
        core = core_of(request)
        return {"enabled": core.settings.answer_cache, "count": await core.db.count_answers()}

    @app.delete("/projia/answers")
    async def answers_clear(request: Request) -> dict[str, int]:
        core = core_of(request)
        removed = await core.db.delete_answers()
        core.chat.answers.invalidate()
        return {"removed": removed}

    @app.get("/projia/memory")
    async def memory_list(request: Request) -> dict[str, Any]:
        core = core_of(request)
        return {"enabled": core.settings.memory_enabled,
                "items": await core.db.list_memories()}

    @app.post("/projia/memory")
    async def memory_add(request: Request, body: MemoryBody) -> dict[str, bool]:
        ok = await core_of(request).chat.memory.remember(
            body.text, "instruction" if body.kind == "instruction" else "fact", "manuel")
        if not ok:
            raise HTTPException(400, "Souvenir refusé (vide ou contenant un secret)")
        return {"ok": True}

    @app.delete("/projia/memory/{mem_id}")
    async def memory_delete(request: Request, mem_id: int) -> dict[str, bool]:
        await core_of(request).chat.memory.delete(mem_id)
        return {"ok": True}

    @app.delete("/projia/memory")
    async def memory_clear(request: Request) -> dict[str, bool]:
        await core_of(request).chat.memory.delete(None)
        return {"ok": True}

    @app.post("/projia/memory/compact")
    async def memory_compact(request: Request) -> dict[str, int]:
        return {"count": await core_of(request).chat.memory.maybe_compact(force=True)}

    @app.get("/projia/spend")
    async def spend(request: Request) -> dict[str, Any]:
        db = core_of(request).db
        now = time.time()
        return {"today": await db.spend_since(now - now % 86400),
                "month": await db.spend_since(now - 31 * 86400),
                "entries": await db.list_spend()}

    @app.get("/projia/cloud/export")
    async def cloud_export(request: Request, since: float = 0) -> dict[str, Any]:
        """Conversations modifiées depuis `since` (entières) pour la synchronisation par
        compte ; l'application les chiffre avant de les envoyer."""
        db = core_of(request).db
        until = time.time()
        return {"conversations": await db.export_conversations(since), "until": until}

    @app.post("/projia/cloud/import")
    async def cloud_import(request: Request) -> dict[str, Any]:
        body = await request.json()
        db = core_of(request).db
        applied, rejected = 0, 0
        reasons: list[str] = []
        items = body.get("conversations") if isinstance(body, dict) else None
        for conv in (items if isinstance(items, list) else [])[:5000]:
            try:
                applied += await db.replace_conversation(conv)
            except (KeyError, TypeError, ValueError) as exc:
                # Élément refusé : signalé (jamais en silence), les autres sont appliqués.
                rejected += 1
                if len(reasons) < 10:
                    reasons.append(str(exc)[:120])
        return {"applied": applied, "rejected": rejected, "reasons": reasons}

    @app.get("/projia/cloud/creations")
    async def cloud_creations(request: Request, since: float = 0) -> dict[str, Any]:
        """Créations terminées (images, audio, fichiers…) de 1 Mo au plus, modifiées depuis
        `since`, avec leur contenu : l'application les chiffre avant envoi. `until` : date de
        la dernière vue (les plus lourdes restent sur l'appareil, mais avancent le curseur)."""
        core = core_of(request)
        out: list[dict[str, Any]] = []
        until = since
        for job in await core.db.jobs_since(since):
            until = max(until, float(job.get("updated_at") or 0))
            path = Path(str(job.get("result_path") or ""))
            try:
                if not path.is_file() or path.stat().st_size > SYNC_CREATION_MAX:
                    continue
                data = path.read_bytes()
            except OSError:
                continue
            item = {k: job.get(k) for k in ("id", "kind", "status", "model", "prompt", "params",
                                            "conversation_id", "created_at", "updated_at")}
            item.update(name=path.name, data_b64=base64.b64encode(data).decode())
            out.append(item)
        return {"creations": out, "until": until}

    @app.post("/projia/cloud/creations")
    async def cloud_creation_import(request: Request) -> dict[str, int]:
        """Création venue d'un autre appareil : fichier écrit dans le dossier des médias puis
        enregistrée (jamais d'écrasement d'une création locale)."""
        core = core_of(request)
        body = await request.json()
        applied = 0
        for item in (body.get("creations") or [])[:50]:
            try:
                job_id = str(item["id"])
                if not re.fullmatch(r"[0-9a-f]{8,64}", job_id) or await core.db.get_job(job_id):
                    continue
                data = base64.b64decode(str(item["data_b64"]), validate=True)
                if len(data) > SYNC_CREATION_MAX:
                    continue
                name = re.sub(r"[^\w.\-]", "_", Path(str(item.get("name") or job_id)).name)[:120]
                folder = core.settings.data_dir / "media" / "synced"
                folder.mkdir(parents=True, exist_ok=True)
                path = folder / (name if name.startswith(job_id) else f"{job_id}-{name}")
                path.write_bytes(data)
                params = item.get("params") if isinstance(item.get("params"), dict) else {}
                params.pop("source_path", None)  # chemin d'un autre appareil : sans objet
                params["mime"] = safe_mime(params.get("mime"))
                await core.db.upsert_job({
                    "id": job_id, "kind": str(item.get("kind") or "image_gen")[:20],
                    "status": "done", "model": item.get("model"),
                    "prompt": str(item.get("prompt") or "")[:4000], "params": params,
                    "result_path": str(path), "conversation_id": item.get("conversation_id"),
                    "created_at": float(item.get("created_at") or time.time())})
                applied += 1
            except (KeyError, TypeError, ValueError, binascii.Error, OSError):
                continue
        return {"applied": applied}

    @app.get("/projia/activity")
    async def activity(request: Request) -> dict[str, Any]:
        """Tâches en cours sur cet appareil (suivi en direct depuis les autres appareils)."""
        core = core_of(request)
        items = []
        for turn in core.turns.running():
            p = turn.progress()
            p["title"] = await core.db.get_title(turn.conversation_id) or ""
            items.append(p)
        waiting = [{"conversation_id": cid, "reason": reason,
                    "title": await core.db.get_title(cid) or ""}
                   for cid, reason in core.turns.waiting.items()]
        return {"tasks": items, "waiting": waiting, "at": time.time()}

    @app.get("/projia/sync")
    async def sync_export(request: Request, since: float = 0) -> dict[str, Any]:
        return await core_of(request).db.export_since(since)

    @app.post("/projia/sync")
    async def sync_import(request: Request) -> dict[str, int]:
        try:
            return {"applied": await core_of(request).db.import_sync(await request.json())}
        except (KeyError, TypeError, ValueError) as exc:
            raise HTTPException(400, "Lot de synchronisation invalide") from exc

    @app.get("/projia/mcp")
    async def mcp_get(request: Request) -> dict[str, Any]:
        core = core_of(request)
        return {"servers": load_config(core.mcp.config_path), "errors": core.mcp.errors,
                "tools": [t.name for t in core.mcp.tools]}

    @app.put("/projia/mcp")
    async def mcp_put(request: Request) -> dict[str, bool]:
        core = core_of(request)
        raw = await request.body()
        if len(raw) > 64 * 1024:
            raise HTTPException(413, "Configuration MCP trop volumineuse")
        body = json.loads(raw or b"{}")
        if not isinstance(body, dict) or not isinstance(body.get("servers", []), list):
            raise HTTPException(400, "Liste de serveurs attendue")
        servers = [s for s in body.get("servers", []) if isinstance(s, dict)]
        if len(servers) > MCP_MAX_SERVERS:
            raise HTTPException(400, f"{MCP_MAX_SERVERS} serveurs MCP au plus")
        client_local = (request.client is not None
                        and request.client.host in ("127.0.0.1", "::1"))
        if any(s.get("transport") == "stdio" for s in servers) and not (
                client_local and core.settings.server.host in LOOPBACK):
            # Un serveur stdio lance un programme : jamais configurable à distance.
            raise HTTPException(403, "Serveurs MCP stdio : configuration locale uniquement")
        for srv in servers:
            if problem := check_mcp_server(srv):
                raise HTTPException(400, f"Serveur MCP « {srv.get('name')} » : {problem}")
        if not (client_local and core.settings.server.host in LOOPBACK):
            # Depuis un autre appareil : seulement des serveurs HTTPS publics (pas d'accès au
            # réseau interne de la machine par ce biais).
            for srv in servers:
                if srv.get("transport", "http") != "stdio":
                    try:
                        if not str(srv.get("url", "")).startswith("https://"):
                            raise PermissionError("HTTPS requis")
                        await assert_public_url(str(srv["url"]))
                    except PermissionError as exc:
                        raise HTTPException(403, f"Serveur MCP « {srv.get('name')} » : "
                                                 f"{exc}") from exc
        if any(s.get("transport") == "stdio" for s in servers) and not (
                client_local and core.settings.server.host in LOOPBACK):
            # Un serveur stdio lance un programme : jamais configurable à distance.
            raise HTTPException(403, "Serveurs MCP stdio : configuration locale uniquement")
        save_config(core.mcp.config_path, servers)
        await core.mcp.close()
        return {"ok": True}
