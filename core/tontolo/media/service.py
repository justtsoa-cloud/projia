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
from tontolo.router.refusal import preserves_subject
from tontolo.router.scoring import Preference, rank
from tontolo.storage.db import Database

log = logging.getLogger(__name__)

KINDS = {"image_gen", "image_edit", "stt", "tts", "music_sfx", "video_gen"}
Listener = Callable[[dict[str, Any]], None]

UNAVAILABLE_MSG = {
    "video_gen": "La source vidéo gratuite ne répond pas pour le moment (GPU partagé saturé ou "
                 "quota du jour atteint). Réessayez plus tard, ajoutez une clé Hugging Face "
                 "gratuite dans Réglages, ou autorisez un fournisseur payant (avec plafond).",
    "music_sfx": "Aucune source gratuite de musique ou d'effets sonores n'est disponible "
                 "pour le moment.",
    "image_edit": "Aucune source gratuite ne sait retoucher une photo pour le moment, et la "
                  "création de remplacement a échoué. Réessayez dans un instant.",
}

VIDEO_QUOTA_MSG = (
    "Quota vidéo gratuit atteint : le GPU partagé de Hugging Face n'accorde que quelques "
    "vidéos par jour sans compte. Ajoutez une clé Hugging Face gratuite dans Réglages pour en "
    "obtenir davantage, ou réessayez dans quelques heures.")

REINTERPRETATION_NOTE = (
    "Aucun service gratuit ne retouche vraiment une photo : elle a été envoyée à une IA "
    "gratuite pour être décrite, puis une nouvelle image a été créée avec votre "
    "transformation. C'est une réinterprétation : la personne et la composition peuvent "
    "avoir changé."
)
PRESERVE_REFUSAL = (
    "La retouche fidèle gratuite (FLUX Kontext, qui garde la personne et la composition) est "
    "occupée pour le moment (quota GPU partagé) : réessayez plus tard. En attendant, une retouche "
    "simple se fait directement sur votre téléphone, sans rien envoyer : éclaircir, contraste, "
    "couleurs vives, noir et blanc, sépia, vintage, style professionnel, netteté."
)
NO_VISION_NOTE = (
    "Aucune IA gratuite n'a pu lire votre photo : l'image a été créée à partir de votre "
    "texte seul, sans reprendre la photo."
)

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
            job["params"]["warning_code"] = "text_in_image"
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
        """Sources prêtes ; si toutes sont en pause, on les retente quand même (dans l'ordre
        de retour) : l'utilisateur a demandé ce média, et une pause posée après une panne
        passagère est souvent déjà levée côté service."""
        prof = TaskProfile(category=Category(kind), modality_out=kind)
        pref = None if is_auto(model) else Preference(str(model))
        decision = rank(self.router.catalog.catalog, prof,
                        usable=self.router.catalog.usable_providers(), quota=self.router.quota,
                        reliability=self.router.reliability, settings=self.router.settings,
                        preference=pref)
        if decision.chain:
            return decision.chain
        waiting = sorted((c for c in decision.waiting if c.model.is_free),
                         key=lambda c: c.available_at)
        return [c for c in waiting if self.router.quota.status_of(c.model).reason
                not in ("auth", "unavailable")][:3]

    def _retry_at(self, kind: str) -> float | None:
        """Prochain retour d'une source de ce type (None si aucune n'est en pause)."""
        prof = TaskProfile(category=Category(kind), modality_out=kind)
        decision = rank(self.router.catalog.catalog, prof,
                        usable=self.router.catalog.usable_providers(), quota=self.router.quota,
                        reliability=self.router.reliability, settings=self.router.settings)
        waits = [c.available_at for c in decision.waiting if c.available_at > 0]
        return min(waits) if waits else None

    async def _run(self, job: dict[str, Any], model: str | None) -> None:
        kind = job["kind"]
        job["status"] = "running"
        await self.db.upsert_job(job)
        self._emit({"type": "job", **job})
        chain = self._candidates(kind, model)
        done, errors = await self._try_chain(job, kind, chain)
        if not done and kind == "image_edit":
            # Aucune édition gratuite : on décrit la photo puis on la recrée (réinterprétation).
            done, more = await self._edit_fallback(job)
            errors += more
        if done:
            await self.db.upsert_job(job)
            await self.router.persist()
            self._emit({"type": "job", **job})
            await self.purge()
            return
        job["status"] = "failed"
        # Code stable (traduit par l'application) + heure de retour estimée (notification).
        params = job["params"]  # enregistré tel quel en base (pas de changement de schéma)
        params["retry_at"] = self._retry_at(kind)
        if params.get("refused_preserve"):
            job["error"], params["error_code"] = PRESERVE_REFUSAL, "preserve_refusal"
        elif kind == "video_gen" and params.get("quota_hit"):
            job["error"], params["error_code"] = VIDEO_QUOTA_MSG, "video_quota"
        elif errors:
            job["error"] = "Toutes les sources gratuites ont échoué : " + "; ".join(errors[:4])
            params["error_code"] = "sources_failed"
        else:
            job["error"] = UNAVAILABLE_MSG.get(
                kind, "Aucune source gratuite disponible pour ce type de média.")
            params["error_code"] = "no_source"
        await self.db.upsert_job(job)
        await self.router.persist()
        self._emit({"type": "job", **job})

    async def _try_chain(self, job: dict[str, Any], kind: str,
                         chain: list[Any]) -> tuple[bool, list[str]]:
        """Essaie les candidats dans l'ordre ; en cas de succès, remplit `job`."""
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
                if err.kind == ErrorKind.QUOTA:
                    job["params"]["quota_hit"] = True
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
            path = self.dir / job["kind"] / f"{job['id']}.{mp.ext_for(out.mime)}"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(out.data)
            job.update(status="done", model=m.key, result_path=str(path), error=None)
            job["params"].update(mime=out.mime, text=out.text, local_tts=out.local_tts,
                                 model_name=m.name)
            return True, errors
        return False, errors

    async def _edit_fallback(self, job: dict[str, Any]) -> tuple[bool, list[str]]:
        """Édition de photo sans source gratuite : un modèle gratuit à vision décrit la photo,
        puis on crée une nouvelle image avec la transformation demandée. Dit clairement à
        l'utilisateur qu'il s'agit d'une réinterprétation et non d'une retouche exacte."""
        import base64

        params = job["params"]
        description: str | None = None
        if preserves_subject(job["prompt"]):
            # L'utilisateur interdit de changer la personne : recréer une image désobéirait.
            params["refused_preserve"] = True
            return False, []
        if params.get("input_path"):
            data = Path(params["input_path"]).read_bytes()
            mime = ("image/jpeg" if data[:2] == b"\xff\xd8" else
                    "image/webp" if data[:4] == b"RIFF" else "image/png")
            description = await self.router.describe_image(
                f"data:{mime};base64," + base64.b64encode(data).decode())
        prompt = (f"{description} — Transformation demandée : {job['prompt']}"
                  if description else job["prompt"])
        gen_job = {**job, "kind": "image_gen", "prompt": prompt[:900],
                   "params": {k: v for k, v in params.items() if k not in ("input_path", "image")}}
        done, errors = await self._try_chain(
            gen_job, "image_gen", self._candidates("image_gen", None))
        if done:
            for key in ("status", "model", "result_path", "error"):
                job[key] = gen_job.get(key)
            job["params"].update(gen_job["params"])
            job["params"]["warning"] = REINTERPRETATION_NOTE if description else NO_VISION_NOTE
            job["params"]["warning_code"] = "reinterpretation" if description else "no_vision"
        return done, errors

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
        if kind == "video_gen":
            vparams = dict(params)
            if inp is not None:
                vparams["image_bytes"] = inp.read_bytes()
            return await mp.generate_video(m, job["prompt"], vparams)
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
