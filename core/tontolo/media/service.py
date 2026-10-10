"""Jobs médias asynchrones et persistés (section 3ter).

Mêmes règles que le texte : classement par catégorie, gratuit d'abord,
quotas, bascule vers le candidat suivant, modèle préféré possible. Les jobs
sont enregistrés en base ; les fichiers restent sur disque (jamais en BLOB).
La vidéo est traitée « au mieux » : sans source gratuite, on le dit clairement.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from tontolo.catalog.models import Category
from tontolo.config import Settings
from tontolo.media import providers as mp
from tontolo.providers.base import ErrorKind, ProviderError
from tontolo.router.classifier import TaskProfile
from tontolo.router.engine import Router, human_reason, is_auto
from tontolo.router.scoring import Preference, rank
from tontolo.storage.db import Database

log = logging.getLogger(__name__)

KINDS = {"image_gen", "image_edit", "stt", "tts", "music_sfx", "video_gen"}
Listener = Callable[[dict[str, Any]], None]

UNAVAILABLE_MSG = {
    "video_gen": "Génération vidéo indisponible gratuitement pour le moment. Vous pouvez "
                 "autoriser un fournisseur payant (avec plafond) dans Réglages › Avancé.",
    "music_sfx": "Aucune source gratuite de musique ou d'effets sonores n'est disponible "
                 "pour le moment.",
}

TEXT_IN_IMAGE_WARNING = (
    "Les modèles d'image rendent mal les équations et les textes longs : pour une figure "
    "exacte, demandez plutôt un graphique par code (SVG, matplotlib, TikZ) ou du LaTeX."
)


def image_text_warning(prompt: str) -> str | None:
    import re

    if re.search(r"\$|\\frac|\\int|[=∑∫√]|équation|formule|equation", prompt) or len(
            re.findall(r"[\"«].{40,}[\"»]", prompt)):
        return TEXT_IN_IMAGE_WARNING
    return None


class MediaService:
    def __init__(self, settings: Settings, db: Database, router: Router) -> None:
        self.settings = settings
        self.db = db
        self.router = router
        self.dir = settings.data_dir / "media"
        self.dir.mkdir(parents=True, exist_ok=True)
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._listeners: list[Listener] = []

    def on_event(self, cb: Listener) -> None:
        self._listeners.append(cb)

    def _emit(self, event: dict[str, Any]) -> None:
        for cb in self._listeners:
            try:
                cb(event)
            except Exception:
                log.exception("Écouteur média en échec")

    async def submit(
        self, kind: str, prompt: str = "", *, params: dict[str, Any] | None = None,
        conversation_id: str | None = None, model: str | None = None,
        input_bytes: bytes | None = None, input_name: str = "input",
    ) -> dict[str, Any]:
        if kind not in KINDS:
            raise ValueError(f"Type de média inconnu : {kind}")
        job: dict[str, Any] = {
            "id": uuid.uuid4().hex, "kind": kind, "status": "queued", "prompt": prompt,
            "params": dict(params or {}), "conversation_id": conversation_id,
            "created_at": time.time(),
        }
        if kind in ("image_gen", "image_edit") and (w := image_text_warning(prompt)):
            job["params"]["warning"] = w
        if input_bytes is not None:
            inp = self.dir / "inputs" / f"{job['id']}-{Path(input_name).name}"
            inp.parent.mkdir(parents=True, exist_ok=True)
            inp.write_bytes(input_bytes)
            job["params"]["input_path"] = str(inp)
        await self.db.upsert_job(job)
        self._tasks[job["id"]] = asyncio.create_task(self._run(job, model))
        self._emit({"type": "job", **job})
        return job

    async def wait(self, job_id: str, max_wait: float = 600) -> dict[str, Any] | None:
        task = self._tasks.get(job_id)
        if task is not None:
            await asyncio.wait_for(asyncio.shield(task), max_wait)
        return await self.db.get_job(job_id)

    def _candidates(self, kind: str, model: str | None) -> list[Any]:
        prof = TaskProfile(category=Category(kind), modality_out=kind)
        pref = None if is_auto(model) else Preference(str(model))
        decision = rank(self.router.catalog.catalog, prof,
                        usable=self.router.catalog.usable_providers(), quota=self.router.quota,
                        reliability=self.router.reliability, settings=self.router.settings,
                        preference=pref)
        return decision.chain

    async def _run(self, job: dict[str, Any], model: str | None) -> None:
        kind = job["kind"]
        job["status"] = "running"
        await self.db.upsert_job(job)
        self._emit({"type": "job", **job})
        chain = self._candidates(kind, model)
        errors: list[str] = []
        for cand in chain:
            m = cand.model
            if not m.is_free:
                gate = await self.router._paid_gate(cand, [], job.get("conversation_id") or "_")
                if gate is not None:
                    continue
            provider = self.router.catalog.catalog.providers.get(m.provider, {"id": m.provider})
            self.router.quota.record_request(m)
            try:
                out = await self._call(kind, m, provider, job)
            except ProviderError as err:
                self.router.quota.on_error(m, err)
                if err.kind in (ErrorKind.SERVER, ErrorKind.NETWORK):
                    self.router.reliability.record(m.key, False)
                errors.append(f"{m.name} : {human_reason(err)}")
                self._emit({"type": "model_switched", "job_id": job["id"], "from": m.key,
                            "reason": human_reason(err)})
                continue
            except Exception as exc:  # erreur inattendue d'un adaptateur
                log.exception("Adaptateur média en échec")
                errors.append(f"{m.name} : {type(exc).__name__}")
                continue
            self.router.quota.on_success(m)
            self.router.reliability.record(m.key, True)
            path = self.dir / kind / f"{job['id']}.{mp.ext_for(out.mime)}"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(out.data)
            job.update(status="done", model=m.key, result_path=str(path), error=None)
            job["params"].update(mime=out.mime, text=out.text, local_tts=out.local_tts,
                                 model_name=m.name)
            await self.db.upsert_job(job)
            await self.router.persist()
            self._emit({"type": "job", **job})
            await self.purge()
            return
        job["status"] = "failed"
        job["error"] = UNAVAILABLE_MSG.get(kind) if not chain else (
            "Toutes les sources gratuites ont échoué : " + "; ".join(errors[:4]))
        if not chain and kind not in UNAVAILABLE_MSG:
            job["error"] = "Aucune source gratuite disponible pour ce type de média."
        await self.db.upsert_job(job)
        await self.router.persist()
        self._emit({"type": "job", **job})

    async def _call(self, kind: str, m: Any, provider: dict[str, Any],
                    job: dict[str, Any]) -> mp.MediaOutput:
        params = job["params"]
        inp = Path(params["input_path"]) if params.get("input_path") else None
        if kind in ("image_gen", "image_edit"):
            if inp is not None and kind == "image_edit":
                import base64

                params = {**params, "image": "data:image/png;base64," + base64.b64encode(
                    inp.read_bytes()).decode()}
            return await mp.generate_image(m, provider, job["prompt"], params)
        if kind == "stt":
            if inp is None:
                raise ValueError("Fichier audio manquant")
            return await mp.transcribe(m, provider, inp.read_bytes(), inp.name, params)
        if kind in ("tts", "music_sfx"):
            return await mp.speak(m, provider, job["prompt"], params)
        raise ProviderError("Type non pris en charge par ce fournisseur", ErrorKind.BAD_REQUEST)

    async def purge(self) -> int:
        """Supprime les médias les plus anciens au-delà du quota disque configuré."""
        limit = self.settings.media_quota_mb * 1024 * 1024
        files = sorted((p for p in self.dir.rglob("*") if p.is_file()),
                       key=lambda p: p.stat().st_mtime)
        total = sum(p.stat().st_size for p in files)
        removed = 0
        for p in files:
            if total <= limit:
                break
            total -= p.stat().st_size
            p.unlink(missing_ok=True)
            removed += 1
        return removed
