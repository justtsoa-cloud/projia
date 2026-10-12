"""Orchestration hiérarchique (optionnelle, `orchestrate=true`) : découpage → sous-tâches
indépendantes en parallèle (`asyncio.gather`) → sous-tâches dépendantes avec les résultats
précédents → fusion. Chaque sous-tâche passe par le routeur existant (catégorie adaptée,
replis, quotas), avec les seuls modèles GRATUITS.

Cache : résultats des sous-tâches identiques réutilisés pendant quelques minutes (mémoire,
borné). Délai par sous-tâche, puis un second essai en évitant le modèle qui a échoué.
"""

from __future__ import annotations

import asyncio
import hashlib
import time
from collections import OrderedDict
from typing import Any

from tontolo.catalog.models import Category
from tontolo.orchestrator.decomposer import SPLIT_PROMPT, Plan, Subtask, TaskDecomposer
from tontolo.orchestrator.synthesizer import PartResult, ResponseSynthesizer

SUBTASK_TIMEOUT = 180.0
CACHE_SIZE = 256
CACHE_TTL = 600.0
LOCAL_SPLIT_TIMEOUT = 20.0
SUB_PROMPT = (
    "Tu traites UNE partie d'une demande plus large (indiquée pour contexte). Réponds "
    "uniquement à cette partie, complètement, dans la langue de la demande, sans répéter les "
    "autres parties.")


class HierarchicalPipeline:
    def __init__(self, router: Any) -> None:
        self.router = router
        self.decomposer = TaskDecomposer(self._local_split)
        self.synthesizer = ResponseSynthesizer(quick=self._quick, best=self._best)
        self._cache: OrderedDict[str, tuple[float, PartResult]] = OrderedDict()

    # --- Modèles ---------------------------------------------------------------------------

    def _paid(self) -> frozenset[str]:
        """Modèles payants évités : l'orchestration ne consomme jamais de crédit."""
        return frozenset(m.key for m in self.router.catalog.catalog.models.values()
                         if not m.is_free)

    async def _ask(self, messages: list[dict[str, Any]], *, forced: Category | None = None,
                   model: str | None = None, avoid: frozenset[str] = frozenset()
                   ) -> tuple[str, str]:
        async for ev in self.router.run(messages, stream=False, forced=forced, model=model,
                                        summary=None, avoid=avoid | self._paid(),
                                        params={"temperature": 0.3}):
            if ev["type"] == "done":
                return str(ev["message"].get("content") or ""), str(ev.get("model") or "")
            if ev["type"] in ("error", "paid_confirmation"):
                break
        return "", ""

    async def _quick(self, messages: list[dict[str, Any]]) -> tuple[str, str]:
        text = await self.router.quick(messages)
        return (text or ""), "quick"

    async def _best(self, messages: list[dict[str, Any]]) -> tuple[str, str]:
        return await self._ask(messages, forced=Category.WRITING)

    async def _local_split(self, request: str) -> str | None:
        local = [m for m in self.router.catalog.catalog.models.values()
                 if m.provider == "ollama_local" and m.is_text
                 and m.provider in self.router.catalog.usable_providers()]
        if not local:
            return None
        async with asyncio.timeout(LOCAL_SPLIT_TIMEOUT):
            text, _ = await self._ask([{"role": "system", "content": SPLIT_PROMPT},
                                       {"role": "user", "content": request[:6000]}],
                                      model=local[0].key)
        return text

    # --- Cache -----------------------------------------------------------------------------

    def _key(self, sub: Subtask, prior: str) -> str:
        raw = f"{sub.category.value}|{' '.join(sub.text.lower().split())}|{prior}"
        return hashlib.sha256(raw.encode()).hexdigest()

    def _cached(self, key: str) -> PartResult | None:
        hit = self._cache.get(key)
        if hit is None or time.monotonic() - hit[0] > CACHE_TTL:
            self._cache.pop(key, None)
            return None
        self._cache.move_to_end(key)
        return hit[1]

    def _store(self, key: str, part: PartResult) -> None:
        if part.ok:
            self._cache[key] = (time.monotonic(), part)
            while len(self._cache) > CACHE_SIZE:
                self._cache.popitem(last=False)

    # --- Exécution -------------------------------------------------------------------------

    async def _solve(self, plan: Plan, sub: Subtask, prior: str, context: str,
                     metrics: list[dict[str, Any]]) -> PartResult:
        started = time.monotonic()
        key = self._key(sub, prior)
        if (hit := self._cached(key)) is not None:
            metrics.append({"index": sub.index, "category": sub.category.value,
                            "model": hit.model, "seconds": 0.0, "cached": True})
            return hit
        system = SUB_PROMPT + f"\nDemande complète : {plan.request[:3000]}"
        if context:
            system += f"\nDébut de la discussion (contexte) :\n{context[:4000]}"
        user = sub.text if not prior else (
            f"{sub.text}\n\nRésultats des parties précédentes :\n{prior[:20_000]}")
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        avoid: frozenset[str] = frozenset()
        text, model = "", ""
        for _ in range(2):  # un second essai en évitant le modèle qui a échoué ou tardé
            try:
                async with asyncio.timeout(SUBTASK_TIMEOUT):
                    text, model = await self._ask(messages, forced=sub.category, avoid=avoid)
            except TimeoutError:
                text = ""
            if text.strip():
                break
            avoid = avoid | ({model} if model else frozenset())
        part = PartResult(title=sub.text[:80], text=text.strip() or
                          "_(Cette partie n'a pas pu être traitée : réessayez plus tard.)_",
                          model=model, ok=bool(text.strip()))
        metrics.append({"index": sub.index, "category": sub.category.value, "model": model,
                        "seconds": round(time.monotonic() - started, 2), "cached": False,
                        "ok": part.ok})
        self._store(key, part)
        return part

    async def run(self, plan: Plan, context: str = "") -> dict[str, Any]:
        """Exécute un plan ; renvoie la réponse fusionnée et les mesures."""
        started = time.monotonic()
        metrics: list[dict[str, Any]] = []
        results: dict[int, PartResult] = {}
        first = await asyncio.gather(*(self._solve(plan, s, "", context, metrics)
                                       for s in plan.parallel))
        for s, r in zip(plan.parallel, first, strict=True):
            results[s.index] = r
        for s in plan.sequential:  # dans l'ordre : chacune voit tout ce qui précède
            prior = "\n\n".join(f"[{results[i].title}]\n{results[i].text}"
                                for i in sorted(results) if i < s.index)
            results[s.index] = await self._solve(plan, s, prior, context, metrics)
        parts = [results[i] for i in sorted(results)]
        merge_started = time.monotonic()
        text, strategy, synth_model = await self.synthesizer.merge(plan.request, parts,
                                                                   plan.complexity)
        return {
            "text": text,
            "model": synth_model if synth_model not in ("", "quick") else next(
                (p.model for p in parts if p.model), ""),
            "metrics": {
                "complexity": plan.complexity, "source": plan.source,
                "subtasks": sorted(metrics, key=lambda m: m["index"]),
                "parallel": len(plan.parallel), "sequential": len(plan.sequential),
                "synthesis": strategy, "synthesis_model": synth_model,
                "synthesis_seconds": round(time.monotonic() - merge_started, 2),
                "seconds": round(time.monotonic() - started, 2),
                "models": sorted({p.model for p in parts if p.model}),
            },
        }
