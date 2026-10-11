"""Branche le pipeline de création sur le routeur (choix des modèles) et sur le stockage des
créations (même table et même dossier que les médias : le fichier apparaît dans Créations)."""

from __future__ import annotations

import asyncio
import re
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any

from tontolo.catalog.models import Category
from tontolo.creator.pipeline import CALL_TIMEOUT, CreationError, Creator, Output
from tontolo.router.engine import Router
from tontolo.storage.db import Database

MAX_TOKENS = 8000


class CreatorService:
    def __init__(self, db: Database, router: Router, media_dir: Any, language: str = "fr",
                 review: bool = True) -> None:
        self.review = review  # équipe de modèles : relecture par un second modèle
        self.db = db
        self.router = router
        self.dir = media_dir / "files"
        self.language = language

    async def ask(self, messages: list[dict[str, Any]], *, category: Category | None = None,
                  model: str | None = None) -> tuple[str, str, str]:
        text, key = "", ""
        async with asyncio.timeout(CALL_TIMEOUT):
            async for ev in self.router.run(messages, stream=False, forced=category, model=model,
                                            params={"max_tokens": MAX_TOKENS,
                                                    "temperature": 0.3}):
                if ev["type"] == "done":
                    text = str(ev["message"].get("content") or "")
                    key = str(ev.get("model") or model or "")
                elif ev["type"] == "error":
                    raise CreationError(str(ev.get("message") or "aucun modèle disponible"))
        if not text.strip():
            raise CreationError("réponse vide du modèle")
        m = self.router.catalog.catalog.get(key)
        return text, key, (m.name if m else key)

    async def pick_reviewer(self, *, exclude: str, vision: bool = False) -> str | None:
        """Meilleur modèle disponible d'une autre famille que le rédacteur (regard neuf)."""
        writer = self.router.catalog.catalog.get(exclude)
        probe: list[dict[str, Any]] = [{"role": "user", "content": "relecture"}]
        decision = await self.router.decide(
            probe, forced=Category.VISION if vision else Category.REASONING)
        def base(model_id: str) -> str:  # même modèle servi par plusieurs fournisseurs
            return re.sub(r"[^a-z0-9]", "", model_id.lower().split("/")[-1].split(":")[0])

        for c in decision.chain:
            m = c.model
            if m.key == exclude or (vision and not m.supports_vision):
                continue
            if writer is not None and (base(m.model_id) == base(writer.model_id)
                                       or (m.family and m.family == writer.family)):
                continue
            return m.key
        return None

    async def transcribe(self, images: list[str]) -> str:
        """Transcription fidèle des photos (énoncés, formules en LaTeX) par un modèle à vision."""
        content: list[dict[str, Any]] = [{"type": "text", "text": (
            "Transcris fidèlement TOUT le texte de cette image : énoncés, numéros d'exercices, "
            "formules en LaTeX ($…$), tableaux. L'image peut être tournée ou inclinée : lis-la "
            "quand même. Ne résous rien, ne commente rien.")}]
        content += [{"type": "image_url", "image_url": {"url": u}} for u in images]
        text, _, _ = await self.ask([{"role": "user", "content": content}],
                                    category=Category.VISION)
        if len(text.strip()) < 20:
            raise CreationError("la photo n'a pas pu être lue")
        return text.strip()[:15000]

    async def review_answer(self, question: str, answer: str, writer: str
                            ) -> dict[str, Any] | None:
        """Vérification croisée d'une réponse par un modèle d'une autre famille.
        None si aucun relecteur n'est disponible ou s'il tarde."""
        reviewer = await self.pick_reviewer(exclude=writer)
        if reviewer is None:
            return None
        prompt = ("Tu vérifies la réponse d'un autre assistant. Cherche uniquement les ERREURS "
                  "réelles : calcul faux, raisonnement incorrect, code qui ne marche pas, fait "
                  "inexact. Ignore le style. Réponds UNIQUEMENT en JSON : {\"ok\": true|false, "
                  "\"issues\": [\"erreur précise, en une phrase, dans la langue de la "
                  "question\"]} (0 à 3 erreurs).")
        try:
            async with asyncio.timeout(75):
                text, key, name = await self.ask(
                    [{"role": "system", "content": prompt},
                     {"role": "user", "content": f"Question :\n{question[:6000]}\n\n"
                                                 f"Réponse à vérifier :\n{answer[:12000]}"}],
                    model=reviewer)
        except Exception:  # relecture facultative : jamais d'erreur visible
            return None
        from tontolo.creator.pipeline import same_model

        if same_model(key, writer):
            return None  # bascule revenue au même modèle : pas de vraie vérification croisée
        import json
        import re

        m = re.search(r"\{.*\}", text, re.S)
        try:
            data = json.loads(m.group(0)) if m else None
        except ValueError:
            data = None
        if not isinstance(data, dict) or "ok" not in data:
            return None
        issues = [str(i)[:300] for i in data.get("issues") or [] if str(i).strip()][:3]
        return {"ok": bool(data["ok"]) or not issues, "issues": issues, "model": key,
                "name": name}

    async def create(self, kind: str, request: str, *, conversation_id: str | None,
                     context: str = "", base: str | None = None,
                     images: list[str] | None = None) -> AsyncIterator[dict[str, Any]]:
        """Événements `step` puis `job` (terminé ou en échec), comme un média."""
        job: dict[str, Any] = {
            "id": uuid.uuid4().hex, "kind": "file_gen", "status": "running", "prompt": request,
            "params": {"format": kind, "revision": bool(base)},
            "conversation_id": conversation_id,
            "created_at": time.time(),
        }
        await self.db.upsert_job(job)
        yield {"type": "job", **job}
        out = Output(b"", "", "", "", "", "")
        creator = Creator(self.ask, self.pick_reviewer if self.review else None)
        try:
            if images:
                # Photo jointe (exercice, document…) : lue d'abord par un modèle qui voit,
                # puis le meilleur rédacteur travaille sur cette transcription.
                yield {"type": "step", "step": "doc_reading"}
                transcript = await self.transcribe(images)
                request = (f"{request}\n\nContenu de la photo jointe (transcription fidèle) :\n"
                           f"{transcript}")
            async for ev in creator.run(kind, request, context=context, language=self.language,
                                        out=out, base=base):
                yield ev
            self.dir.mkdir(parents=True, exist_ok=True)
            path = self.dir / f"{job['id']}-{out.filename}"
            path.write_bytes(out.data)
            src = self.dir / f"{job['id']}-source-{out.source_name}"
            if out.source_name and out.source_name != out.filename:
                src.write_text(out.source, encoding="utf-8")
            job.update(status="done", result_path=str(path), model=out.models[0] if out.models
                       else None)
            job["params"].update(mime=out.mime, filename=out.filename, title=out.title,
                                 size=len(out.data), steps=out.steps, models=out.models,
                                 source_path=str(src) if src.exists() else None,
                                 model_name=out.steps[0].get("model") if out.steps else None)
        except (CreationError, TimeoutError) as exc:
            job.update(status="failed", error=str(exc) or "délai dépassé")
            job["params"]["error_code"] = "file_failed"
        await self.db.upsert_job(job)
        yield {"type": "job", **job}
