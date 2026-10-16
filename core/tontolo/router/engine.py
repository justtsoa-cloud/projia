"""Moteur de routage : choix du modèle, bascule sur erreur, retour au meilleur.

Le moteur est sans état vis-à-vis de l'historique (il reçoit les messages
canoniques) ; la persistance des conversations est faite par l'appelant
(`tontolo.chat.ChatService`). Il produit un flux d'événements :

- `route` : modèle choisi et pourquoi ;
- `model_returned` : retour au modèle préféré ou au meilleur après une bascule ;
- `delta` : morceau de réponse ;
- `stream_reset` : la génération partielle est abandonnée (bascule en cours de flux) ;
- `model_switched` : ancien, nouveau, raison ;
- `paid_confirmation` : un appel payant attend l'accord de l'utilisateur (mode `ask`) ;
- `done` : message final, modèle, consommation ;
- `error` : plus aucun modèle disponible (phrase humaine + date de retour estimée).
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import logging
import os
import time
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime
from typing import Any

from tontolo import http, metrics, secrets
from tontolo.catalog.models import MEDIA_CATEGORIES, Category, ModelInfo
from tontolo.catalog.service import CatalogService
from tontolo.config import PaidFallback, Settings
from tontolo.providers.base import ChatResult, ErrorKind, ProviderError
from tontolo.providers.registry import ProviderRegistry
from tontolo.router import classifier
from tontolo.router.classifier import TaskProfile
from tontolo.router.context import SUMMARY_PROMPT, fit
from tontolo.router.hedge import race_streams
from tontolo.router.quota import QuotaManager
from tontolo.router.scoring import (
    LOCAL_LLM_PROVIDERS,
    Candidate,
    Preference,
    Reliability,
    RouteDecision,
    pick_preference,
    rank,
)
from tontolo.storage.db import Database

log = logging.getLogger(__name__)

MAX_ATTEMPTS = 8
# Un modèle gratuit peut rester muet (file d'attente chez le fournisseur qui n'envoie que des
# « keepalive », réponse interrompue…) : sans délai, le tour resterait bloqué indéfiniment.
FIRST_TOKEN_TIMEOUT = 90.0   # secondes avant le premier mot (réflexion comprise)
STALL_TIMEOUT = 60.0         # silence maximal en cours de réponse
CALL_TIMEOUT = 240.0         # appel sans diffusion (résumés, classifieur, anciens cœurs)
THINK_TIMEOUT = 150.0        # réflexion maximale sans aucun texte de réponse (diffusion)
CONTROL_PARAMS = frozenset({"first_token_timeout", "stall_timeout", "think_timeout",
                            "call_timeout", "hedge_after", "no_hedge"})  # jamais envoyés au modèle
MAX_WASTED = 200.0           # temps cumulé perdu sur des modèles en échec avant d'abandonner


async def _watched(source: AsyncIterator[dict[str, Any]], first: float, stall: float,
                   think: float = 0.0) -> AsyncIterator[dict[str, Any]]:
    """Relaie le flux d'un fournisseur en imposant un premier mot et un silence maximaux, et
    (`think` > 0) une durée maximale de réflexion sans aucun texte de réponse : un modèle qui
    raisonne sans fin n'est jamais « silencieux », il faut pourtant passer au suivant."""
    it = source.__aiter__()
    waiting = first
    start = time.monotonic()
    answered = False
    try:
        while True:
            left = think - (time.monotonic() - start) if think and not answered else None
            if left is not None and left <= 0:
                raise ProviderError("réflexion trop longue, sans réponse", ErrorKind.SERVER)
            try:
                item = await asyncio.wait_for(
                    it.__anext__(), waiting if left is None else min(waiting, left))
            except StopAsyncIteration:
                return
            except TimeoutError as exc:
                if left is not None and time.monotonic() - start >= think:
                    raise ProviderError("réflexion trop longue, sans réponse",
                                        ErrorKind.SERVER) from exc
                raise ProviderError("pas de réponse du modèle (délai dépassé)",
                                    ErrorKind.NETWORK) from exc
            if "delta" in item:
                waiting = stall
                delta = item["delta"]
                answered = answered or bool(delta.get("content") or delta.get("tool_calls"))
            elif "_result" in item:
                answered = True
            yield item
    finally:
        aclose = getattr(it, "aclose", None)
        if aclose is not None:
            with contextlib.suppress(Exception):
                await aclose()
async def _single(source: AsyncIterator[dict[str, Any]]
                  ) -> AsyncIterator[tuple[int, dict[str, Any]]]:
    """Flux unique, au même format que la course (index 0)."""
    async for item in source:
        yield 0, item


GLOBAL_MIN_DEVICES = 5  # notes collectives prises en compte à partir de 5 appareils
SHORT_WAIT = 30.0  # attente maximale avant un nouvel essai automatique (secondes)
EST_OUTPUT_TOKENS = 1000
OFFLINE_WAIT = 25.0  # attente maximale du retour de la connexion (secondes)
OFFLINE_STEP = 4.0
MAX_RECOVERIES = 2   # nombre de retours de connexion tolérés par tour

_REASONS_FR = {
    ErrorKind.RATE_LIMIT: "limite de débit atteinte",
    ErrorKind.QUOTA: "quota épuisé",
    ErrorKind.AUTH: "clé refusée",
    ErrorKind.CONTEXT: "historique trop long",
    ErrorKind.UNAVAILABLE: "modèle indisponible",
    ErrorKind.SERVER: "erreur du fournisseur",
    ErrorKind.NETWORK: "problème réseau",
    ErrorKind.BAD_REQUEST: "requête refusée",
}


def human_reason(err: ProviderError) -> str:
    return _REASONS_FR.get(err.kind, str(err.kind))


def is_auto(model: str | None) -> bool:
    return not model or model.lower() in ("auto", "tontolo", "tontolo/auto", "tontolo-auto")


QUICK_TIMEOUT = 30.0   # secondes par essai d'un appel court (modèles à réflexion : lents)
QUICK_STAGGER = 3.0    # un nouveau candidat est lancé toutes les 3 s (ou dès qu'un échoue)
QUICK_PARALLEL = 3     # candidats en course au plus
QUICK_CANDIDATES = 8   # modèles essayés au plus (beaucoup de gratuits sont saturés ou fermés)
QUICK_BUDGET = 50.0    # secondes au total


class Router:
    def __init__(
        self,
        settings: Settings,
        catalog: CatalogService,
        db: Database | None = None,
        registry: ProviderRegistry | None = None,
        quota: QuotaManager | None = None,
        reliability: Reliability | None = None,
    ) -> None:
        self.settings = settings
        self.catalog = catalog
        self.db = db
        self.registry = registry or ProviderRegistry()
        self.quota = quota or QuotaManager()
        self.reliability = reliability or Reliability()
        self._desired: dict[str, str] = {}          # conversation → modèle à retrouver
        self._paid_ok: set[str] = set()             # conversations où le payant est accepté
        self._class_cache: dict[str, Category] = {}
        self.probe = http.is_online  # remplaçable (tests)
        self.offline_since: float | None = None  # appareil hors ligne détecté (santé)

    async def startup(self) -> None:
        if self.db is not None:
            self.quota.load(await self.db.load_quotas())
            self.reliability.table.update(await self.db.load_reliability())
            self.reliability.set_votes(await self.db.feedback_totals())
            raw = await self.db.kv_get("global_scores")
            if raw:
                self.set_global_scores(json.loads(raw))

    async def persist(self) -> None:
        if self.db is None:
            return
        for k, v in self.quota.take_dirty().items():
            await self.db.save_quota(k, v)
        for k in list(self.reliability.dirty):
            ok, total = self.reliability.table[k]
            await self.db.save_reliability(k, ok, total)
        self.reliability.dirty.clear()

    def set_global_scores(self, rows: list[dict[str, Any]]) -> int:
        """Notes collectives anonymes (fonction Supabase `model_scores`, transmise par l'app) :
        score borné à [-1, 1], seulement au-delà d'un nombre minimal d'appareils."""
        scores: dict[tuple[str, str], float] = {}
        for r in rows[:5000] if isinstance(rows, list) else []:
            if not isinstance(r, dict):
                continue
            try:
                model, cat = str(r["model"])[:200], str(r.get("category") or "*")[:40]
                score, n = float(r["score"]), int(r.get("devices") or 0)
            except (KeyError, TypeError, ValueError):
                continue
            if n >= GLOBAL_MIN_DEVICES and -1.0 <= score <= 1.0:
                scores[(model, cat)] = score
        self.reliability.global_scores = scores
        return len(scores)

    def approve_paid(self, conversation_id: str) -> None:
        self._paid_ok.add(conversation_id)

    # --- Décision --------------------------------------------------------

    async def profile(
        self, messages: list[dict[str, Any]], *, conversation_id: str | None = None,
        tools_available: bool = False, forced: Category | str | None = None,
    ) -> TaskProfile:
        prof = classifier.classify(messages, tools_available=tools_available, forced=forced)
        if forced or not self.settings.llm_classifier or not classifier.is_ambiguous(prof):
            return prof
        last: dict[str, Any] = next(
            (m for m in reversed(messages) if m.get("role") == "user"), {})
        h = hashlib.sha1(f"{conversation_id}:{last.get('content')}".encode(),
                         usedforsecurity=False).hexdigest()  # clé de cache, pas de sécurité
        if h not in self._class_cache:
            cat = await self._llm_classify(last)
            if cat is not None:
                self._class_cache[h] = cat
        if h in self._class_cache:
            return classifier.classify(messages, tools_available=tools_available,
                                       forced=self._class_cache[h])
        return prof

    async def decide(
        self, messages: list[dict[str, Any]], *, conversation_id: str | None = None,
        model: str | None = None, tools_available: bool = False,
        forced: Category | str | None = None, strict: bool = False,
        avoid: frozenset[str] = frozenset(),
    ) -> RouteDecision:
        prof = await self.profile(messages, conversation_id=conversation_id,
                                  tools_available=tools_available, forced=forced)
        if prof.category in MEDIA_CATEGORIES:
            # Le moteur de chat ne produit que du texte : les médias passent par
            # MediaService ; ici on répond par un modèle de texte généraliste.
            prof.category = Category.CHAT
            prof.modality_out = "text"
        pref: Preference | None = None
        if not is_auto(model):
            pref = Preference(str(model), strict, "request")
        elif self.db is not None:
            pref = pick_preference(await self.db.get_preferences(), conversation_id,
                                   prof.category)
        return rank(self.catalog.catalog, prof, usable=self.catalog.usable_providers(),
                    quota=self.quota, reliability=self.reliability, settings=self.settings,
                    preference=pref, avoid=avoid)

    # --- Exécution -------------------------------------------------------

    async def run(
        self,
        messages: list[dict[str, Any]],
        *,
        conversation_id: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        stream: bool = True,
        model: str | None = None,
        forced: Category | str | None = None,
        strict: bool = False,
        summary: str | None = None,
        params: dict[str, Any] | None = None,
        avoid: frozenset[str] = frozenset(),
    ) -> AsyncIterator[dict[str, Any]]:
        """Exécute un tour ; si tous les modèles sont en attente pour quelques secondes
        seulement, attend puis réessaie une fois au lieu d'afficher une erreur."""
        for round_ in range(2):
            async for ev in self._run_once(
                messages, conversation_id=conversation_id, tools=tools, stream=stream,
                model=model, forced=forced, strict=strict, summary=summary, params=params,
                avoid=avoid,
            ):
                wait = self._short_wait(ev) if round_ == 0 else None
                if wait is not None:
                    yield {"type": "waiting", "seconds": max(1, round(wait))}
                    await asyncio.sleep(wait + 0.3)
                    break
                yield ev
            else:
                return

    def _short_wait(self, ev: dict[str, Any]) -> float | None:
        if ev.get("type") != "error" or not ev.get("retry_at"):
            return None
        wait = float(ev["retry_at"]) - time.time()
        return wait if 0 < wait <= SHORT_WAIT else (0.0 if wait <= 0 else None)

    async def _run_once(
        self,
        messages: list[dict[str, Any]],
        *,
        conversation_id: str | None,
        tools: list[dict[str, Any]] | None,
        stream: bool,
        model: str | None,
        forced: Category | str | None,
        strict: bool,
        summary: str | None,
        params: dict[str, Any] | None,
        avoid: frozenset[str] = frozenset(),
    ) -> AsyncIterator[dict[str, Any]]:
        params = params or {}
        t_turn = time.monotonic()  # début du tour : mesure du délai avant le premier mot
        decision = await self.decide(messages, conversation_id=conversation_id, model=model,
                                     tools_available=bool(tools), forced=forced, strict=strict,
                                     avoid=avoid)
        prof = decision.profile
        conv_key = conversation_id or "_"
        if not decision.chain:
            yield self._no_model_event(decision)
            return

        first = decision.chain[0]
        desired = self._desired.get(conv_key)
        if desired and first.model.key == desired:
            yield {"type": "model_returned", "model": desired, "name": first.model.name}
            self._desired.pop(conv_key, None)
        yield {
            "type": "route", "model": first.model.key, "name": first.model.name,
            "reason": first.reason(prof.category), "profile": prof.as_dict(),
            "chain": [c.model.key for c in decision.chain[:5]],
        }

        previous: Candidate | None = None
        last_reason, last_until, last_code = "", None, ""
        attempts = 0
        chain = list(decision.chain)
        idx = recoveries = 0
        wasted = 0.0
        while idx < len(chain):
            cand = chain[idx]
            idx += 1
            if attempts >= MAX_ATTEMPTS:
                break
            m = cand.model
            if not m.is_free:
                gate = await self._paid_gate(cand, messages, conv_key)
                if gate is not None:
                    if gate.get("type") == "paid_confirmation":
                        yield gate
                        return
                    continue
            if previous is not None:
                yield {"type": "model_switched", "from": previous.model.key, "to": m.key,
                       "to_name": m.name, "reason": last_reason, "reason_code": last_code,
                       "until": last_until}
            if wasted > MAX_WASTED:
                break  # trop de temps perdu sur des modèles muets : mieux vaut une erreur claire
            attempts += 1
            attempt_started = time.monotonic()
            # Résumé d'urgence (petit contexte) : non enregistré, le résumé du fil est tenu à
            # jour par la conversation elle-même (voir agent/loop.py).
            adapted, _, _ = await fit(messages, m, summary=summary, summarizer=self._summarize)
            use_tools = tools if (tools and m.supports_tools) else None
            api_params = {k: v for k, v in params.items() if k not in CONTROL_PARAMS}
            limits = self.settings.routing  # délais réglés en mode avancé (bornés)
            self.quota.record_request(m)
            started = False
            first_word_at: float | None = None
            try:
                result: ChatResult | None = None
                client = self.registry.get(self.catalog.catalog.providers[m.provider])
                if stream:
                    first_to = float(params.get("first_token_timeout",
                                                limits.first_token_s or FIRST_TOKEN_TIMEOUT))
                    stall_to = float(params.get("stall_timeout", limits.stall_s or STALL_TIMEOUT))
                    think_to = float(params.get("think_timeout", limits.think_s or THINK_TIMEOUT))

                    def source_of(model: ModelInfo, ready: list[dict[str, Any]] | None = None,
                                  *, extra: dict[str, Any] = api_params,
                                  limits_s: tuple[float, float, float] = (
                                      first_to, stall_to, think_to)) -> Any:
                        async def run() -> AsyncIterator[dict[str, Any]]:
                            msgs = ready if ready is not None else (
                                await fit(messages, model, summary=summary,
                                          summarizer=self._summarize))[0]
                            cl = self.registry.get(self.catalog.catalog.providers[model.provider])
                            tl = tools if (tools and model.supports_tools) else None
                            async for it in _watched(cl.stream(model, msgs, tools=tl, **extra),
                                                     *limits_s):
                                yield it
                        return run

                    backup_pos = self._hedge_partner(chain, idx, cand, avoid, params)
                    if backup_pos is None:
                        feed: AsyncIterator[tuple[int, dict[str, Any]]] = _single(
                            source_of(m, adapted)())
                    else:
                        backup = chain[backup_pos]

                        def hedge_failed(i: int, exc: BaseException,
                                         other: Candidate = backup) -> None:
                            if i == 1:  # le renfort est tombé : on le note, comme un échec
                                err_b = exc if isinstance(exc, ProviderError) else ProviderError(
                                    f"{type(exc).__name__}: {exc}"[:300], ErrorKind.SERVER)
                                self.quota.on_error(other.model, err_b)
                                self.reliability.record(other.model.key, False)

                        self.quota.record_request(backup.model)
                        feed = race_streams(
                            [source_of(m, adapted), source_of(backup.model)],
                            self._hedge_after(m, params), hedge_failed)
                    switched = False
                    async for which, item in feed:
                        if which == 1 and backup_pos is not None and not switched:
                            switched = True
                            # Le renfort a parlé le premier : il devient le modèle de ce tour.
                            yield {"type": "model_switched", "from": m.key,
                                   "to": chain[backup_pos].model.key,
                                   "to_name": chain[backup_pos].model.name,
                                   "reason": "réponse plus rapide", "reason_code": "hedge",
                                   "until": None}
                            self.reliability.record(m.key, False)  # trop lent ce coup-ci
                            cand = chain.pop(backup_pos)
                            m = cand.model
                            attempts += 1
                        if "_result" in item:
                            result = item["_result"]
                        else:
                            if not started:
                                first_word_at = time.monotonic()
                            started = True
                            yield {"type": "delta", **item["delta"]}
                else:
                    try:
                        result = await asyncio.wait_for(
                            client.chat(m, adapted, tools=use_tools, **api_params),
                            float(params.get("call_timeout", CALL_TIMEOUT)))
                    except TimeoutError as exc:
                        raise ProviderError("pas de réponse du modèle (délai dépassé)",
                                            ErrorKind.NETWORK) from exc
                if result is None:
                    raise ProviderError("Réponse vide", ErrorKind.SERVER)
                if not (result.message.get("content") or result.message.get("tool_calls")):
                    raise ProviderError("Réponse vide", ErrorKind.SERVER)
            except Exception as raw:
                # Toute exception d'un fournisseur (JSON illisible, KeyError, délai…) est un
                # échec de CE modèle : on passe au suivant au lieu de perdre la réponse.
                err = raw if isinstance(raw, ProviderError) else ProviderError(
                    f"{type(raw).__name__}: {raw}"[:300], ErrorKind.SERVER)
                if err.kind == ErrorKind.NETWORK and not await self.probe():
                    # C'est l'appareil qui est hors ligne, pas le modèle : ne pas défiler toute la
                    # liste des modèles ni les pénaliser. On attend le retour de la connexion.
                    self.offline_since = self.offline_since or time.time()
                    if started:
                        yield {"type": "stream_reset", "model": m.key, "reason": "hors ligne"}
                    local = next((i for i in range(idx, len(chain))
                                  if chain[i].model.provider in LOCAL_LLM_PROVIDERS), None)
                    if local is not None:
                        # Un modèle tourne sur l'appareil : il répond sans Internet.
                        previous, idx = cand, local
                        last_reason, last_until, last_code = "hors ligne", None, "offline"
                        continue
                    back = False
                    if recoveries < MAX_RECOVERIES:
                        deadline = time.monotonic() + OFFLINE_WAIT
                        while time.monotonic() < deadline:
                            yield {"type": "offline",
                                   "seconds": max(1, int(deadline - time.monotonic()))}
                            await asyncio.sleep(OFFLINE_STEP)
                            if await self.probe():
                                back = True
                                break
                    if not back:
                        await self.persist()
                        yield {"type": "error", "offline": True, "retry_at": None,
                               "code": "offline",
                               "message": "Pas de connexion Internet. Vérifiez le réseau "
                                          "(Wi-Fi ou données mobiles) puis réessayez.",
                               "category": prof.category.value}
                        return
                    recoveries += 1
                    self.offline_since = None
                    await http.reset()
                    idx -= 1       # on retente le même modèle, sans « bascule »
                    attempts -= 1
                    continue
                wasted += time.monotonic() - attempt_started
                until = self.quota.on_error(m, err)
                if err.kind in (ErrorKind.SERVER, ErrorKind.NETWORK, ErrorKind.UNAVAILABLE,
                                ErrorKind.BAD_REQUEST):
                    self.reliability.record(m.key, False)
                metrics.inc("tontolo_model_calls_total", model=m.key, result="error")
                metrics.inc("tontolo_errors_total", kind=err.kind.value)
                last_reason, last_until = human_reason(err), until or None
                last_code = err.kind.value
                log.info("Échec %s : %s", m.key, secrets.redact(str(err)))
                if started:
                    yield {"type": "stream_reset", "model": m.key,
                           "reason": last_reason}
                if cand is decision.chain[0] or cand.preferred:
                    self._desired[conv_key] = m.key
                previous = cand
                await self.persist()
                continue
            # Succès
            self.offline_since = None
            self.quota.on_success(m)
            self.reliability.record(m.key, True)
            metrics.inc("tontolo_model_calls_total", model=m.key, result="ok")
            metrics.inc("tontolo_model_seconds_sum", time.monotonic() - attempt_started,
                        model=m.key)
            now = time.monotonic()
            self.reliability.record_speed(
                m.key, len(str(result.message.get("content") or ""))
                + len(str(result.message.get("tool_calls") or "")),
                now - attempt_started)
            # Mesure (P1.1) : préparation avant l'appel, premier mot, durée totale du tour.
            timing = {"prep_s": round(attempt_started - t_turn, 3),
                      "ttft_s": (round(first_word_at - attempt_started, 3)
                                 if first_word_at is not None else None),
                      "total_s": round(now - t_turn, 3), "attempts": attempts}
            if first_word_at is not None:
                self.reliability.record_ttft(m.key, first_word_at - attempt_started)
                metrics.inc("tontolo_ttft_seconds_sum", first_word_at - attempt_started,
                            model=m.key)
                metrics.inc("tontolo_ttft_count", model=m.key)
            cost = 0.0
            if not m.is_free:
                cost = (result.usage.get("prompt_tokens", 0) * m.price_in
                        + result.usage.get("completion_tokens", 0) * m.price_out)
                if self.db is not None:
                    await self.db.add_spend(m.key, result.usage.get("prompt_tokens", 0),
                                            result.usage.get("completion_tokens", 0), cost,
                                            conversation_id)
            await self.persist()
            yield {"type": "done", "message": result.message, "model": m.key,
                   "name": m.name, "usage": result.usage, "cost": cost,
                   "finish_reason": result.finish_reason, "profile": prof.as_dict(),
                   "timing": timing}
            return

        await self.persist()
        yield self._no_model_event(decision, tried=attempts)

    async def health(self) -> dict[str, Any]:
        """État global pour la pastille de l'interface : vert (plusieurs modèles gratuits
        prêts), orange (peu de choix ou réseau incertain), rouge (aucun modèle prêt)."""
        d = await self.decide([{"role": "user", "content": "Bonjour"}])
        ready = [c for c in d.chain if c.model.is_free]
        waits = [t for c in d.waiting if (t := c.available_at) > 0]
        offline = self.offline_since is not None
        if not ready or (offline and time.time() - (self.offline_since or 0) < 120):
            state = "red"
        elif len(ready) < 3:
            state = "orange"
        else:
            state = "green"
        return {"state": state, "ready": len(ready), "waiting": len(d.waiting),
                "retry_at": min(waits) if waits else None, "offline": offline,
                "best": ready[0].model.name if ready else None,
                "best_key": ready[0].model.key if ready else None}

    def _no_model_event(self, decision: RouteDecision, tried: int = 0) -> dict[str, Any]:
        waits = [c.available_at for c in decision.waiting if c.available_at > 0]
        waits += [t for c in decision.chain if (t := self.quota.available_at(c.model)) > 0]
        retry_at = min(waits) if waits else None
        if decision.preferred and decision.preferred.strict and decision.waiting:
            msg = "Votre modèle préféré est momentanément épuisé (mode strict)."
        elif tried:
            msg = "Tous les modèles gratuits disponibles ont échoué pour le moment."
        else:
            msg = ("Aucun modèle gratuit disponible pour cette tâche. Ajoutez une clé gratuite "
                   "dans Réglages ou réessayez plus tard.")
        if retry_at and retry_at - time.time() > 90:
            when = datetime.fromtimestamp(retry_at, UTC).astimezone().strftime("%H:%M")
            msg += f" Retour estimé vers {when}."
        elif retry_at:
            msg += " Nouvel essai possible dans quelques instants."
        code = ("strict_waiting" if decision.preferred and decision.preferred.strict
                and decision.waiting else "all_failed" if tried else "no_model")
        return {"type": "error", "message": msg, "retry_at": retry_at, "code": code,
                "category": decision.profile.category.value}

    async def _paid_gate(
        self, cand: Candidate, messages: list[dict[str, Any]], conv_key: str
    ) -> dict[str, Any] | None:
        """None si l'appel payant est permis ; sinon un événement (ou `skip`)."""
        paid = self.settings.paid
        m = cand.model
        if paid.fallback == PaidFallback.OFF and not cand.preferred:
            return {"type": "skip"}
        est = (classifier.estimate_tokens(messages) * m.price_in
               + EST_OUTPUT_TOKENS * m.price_out)
        if paid.daily_cap_usd <= 0 and paid.monthly_cap_usd <= 0:
            return {"type": "skip", "reason": "plafond non défini"}
        if self.db is not None:
            now = datetime.now(UTC)
            day = now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
            month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).timestamp()
            if paid.daily_cap_usd > 0 and await self.db.spend_since(day) + est > \
                    paid.daily_cap_usd:
                return {"type": "skip", "reason": "plafond quotidien atteint"}
            if paid.monthly_cap_usd > 0 and await self.db.spend_since(month) + est > \
                    paid.monthly_cap_usd:
                return {"type": "skip", "reason": "plafond mensuel atteint"}
        if paid.fallback == PaidFallback.ASK and conv_key not in self._paid_ok:
            return {"type": "paid_confirmation", "model": m.key, "name": m.name,
                    "estimated_cost_usd": round(est, 6)}
        return None

    # --- Appels internes (résumé, classifieur) ---------------------------

    def _hedge_after(self, m: ModelInfo, params: dict[str, Any] | None = None) -> float:
        """Délai avant de couvrir un modèle silencieux : ~2 fois son délai habituel."""
        if params and params.get("hedge_after"):
            return float(params["hedge_after"])
        seen = self.reliability.ttft(m.key)
        return min(10.0, max(3.0, 2.2 * seen)) if seen else 4.0

    def _hedge_partner(self, chain: list[Candidate], idx: int, cand: Candidate,
                       avoid: frozenset[str], params: dict[str, Any]) -> int | None:
        """Position du modèle qui couvre `cand` s'il tarde : gratuit, d'un AUTRE fournisseur
        (une panne ou une limite de débit est souvent commune à un fournisseur), jamais pour un
        modèle imposé, en mode économie ou quand la course est désactivée."""
        if (self.settings.economy or params.get("no_hedge") or cand.preferred
                or os.environ.get("TONTOLO_NO_HEDGE")  # comparaison avant/après (bench)
                or not cand.model.is_free):
            return None
        for j in range(idx, min(len(chain), idx + 4)):
            other = chain[j]
            if (other.model.is_free and other.model.is_text and not other.preferred
                    and other.model.key not in avoid
                    and other.model.provider != cand.model.provider):
                return j
        return None

    def _small_free_models(self, limit: int = 4, quality: str = "chat") -> list[ModelInfo]:
        """Modèles gratuits disponibles, du plus rapide et fiable au meilleur selon `quality`
        (« chat » pour un appel court ; « writing » ou « reasoning » pour un vrai travail)."""
        usable = self.catalog.usable_providers()
        ranked: list[tuple[float, ModelInfo]] = []
        weight = 0.5 if quality == "chat" else 1.5
        for m in self.catalog.catalog.models.values():
            if not (m.is_free and m.is_text and m.provider in usable and self.quota.available(m)):
                continue
            s = (m.speed if m.speed is not None else 0.5) + self.reliability.get(m.key) \
                + weight * m.quality.get(quality, m.quality.get("chat", 0))
            ranked.append((s, m))
        ranked.sort(key=lambda x: x[0], reverse=True)
        return [m for _, m in ranked[:limit]]

    def _small_free_model(self) -> ModelInfo | None:
        models = self._small_free_models(1)
        return models[0] if models else None

    async def _quick(self, messages: list[dict[str, Any]], max_tokens: int = 600,
                     accept: Callable[[str], bool] | None = None, *,
                     per_try: float = QUICK_TIMEOUT, budget: float = QUICK_BUDGET,
                     quality: str = "chat", stagger: float = QUICK_STAGGER) -> str | None:
        """Appel court en COURSE : le meilleur petit modèle gratuit d'abord, puis un suivant
        toutes les 3 s ou dès qu'un échoue (3 en parallèle au plus) ; la première réponse
        non vide gagne, les autres sont annulées. Un modèle gratuit qui exige une connexion, qui
        est saturé, retiré ou lent ne fait donc plus échouer le résumé du fil, la mémoire ni le
        brief d'image ; un modèle en échec est mis de côté pour les appels suivants."""
        candidates = iter(self._small_free_models(QUICK_CANDIDATES, quality))
        started = time.monotonic()

        async def attempt(m: ModelInfo) -> str | None:
            t0 = time.monotonic()
            try:
                client = self.registry.get(self.catalog.catalog.providers[m.provider])
                self.quota.record_request(m)
                async with asyncio.timeout(per_try):
                    res = await client.chat(m, messages, max_tokens=max_tokens, temperature=0)
                content = res.message.get("content")
                text = str(content) if content and str(content).strip() else None
                good = text is not None and (accept is None or accept(text))
                # Un modèle qui répond vide ou à côté compte comme un échec : il passe derrière.
                self.reliability.record(m.key, good)
                if good and text:
                    self.reliability.record_speed(m.key, len(text), time.monotonic() - t0)
                return text if good else None
            except ProviderError as err:
                self.reliability.record(m.key, False)
                self.quota.on_error(m, err)
            except TimeoutError:
                self.reliability.record(m.key, False)
                self.quota.on_error(m, ProviderError("délai dépassé", ErrorKind.NETWORK))
            except Exception:
                self.reliability.record(m.key, False)
            return None

        running: set[asyncio.Task[str | None]] = set()

        def launch() -> bool:
            m = next(candidates, None)
            if m is None:
                return False
            running.add(asyncio.create_task(attempt(m)))
            return True

        try:
            launch()
            while running and time.monotonic() - started < budget:
                done, _ = await asyncio.wait(running, timeout=stagger,
                                             return_when=asyncio.FIRST_COMPLETED)
                running -= done
                for task in done:
                    if (answer := task.result()) is not None:
                        return answer
                if len(running) < (1 if self.settings.economy else QUICK_PARALLEL):
                    launch()
                if not running and not launch():
                    break
            return None
        finally:
            for task in running:
                task.cancel()

    async def quick(self, messages: list[dict[str, Any]], max_tokens: int = 600,
                    accept: Callable[[str], bool] | None = None, **options: Any) -> str | None:
        """Appel court à un petit modèle gratuit (résumé, mémoire, classifieur, brief d'image) ;
        `accept` écarte une réponse inutilisable (le candidat suivant prend alors le relais)."""
        return await self._quick(messages, max_tokens, accept, **options)

    async def describe_image(self, data_url: str, prompt: str | None = None,
                             max_chars: int = 600) -> str | None:
        """Description d'une image par un modèle gratuit à vision (photo à recréer, ou
        capture d'écran du navigateur avec `prompt`)."""
        usable = self.catalog.usable_providers()
        cands = [m for m in self.catalog.catalog.models.values()
                 if m.is_free and m.is_text and m.supports_vision and m.provider in usable
                 and self.quota.available(m)]
        cands.sort(key=lambda m: -(m.quality.get("vision", 0.0)
                                   + 0.3 * self.reliability.get(m.key)))
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": prompt or (
                "Décris précisément cette photo pour qu'un générateur d'images puisse la "
                "recréer : sujet, objets, couleurs, lumière, ambiance, composition. Réponds "
                "en une à trois phrases, en français, sans introduction.")},
            {"role": "user", "content": [
                {"type": "text", "text": "Décris cette photo."},
                {"type": "image_url", "image_url": {"url": data_url}}]},
        ]
        for m in cands[:4]:
            try:
                client = self.registry.get(self.catalog.catalog.providers[m.provider])
                self.quota.record_request(m)
                res = await client.chat(m, messages, max_tokens=300 if prompt is None else 900,
                                        temperature=0.2)
            except ProviderError as err:
                self.quota.on_error(m, err)
                continue
            except Exception:
                continue
            text = res.message.get("content")
            if text and str(text).strip():
                self.quota.on_success(m)
                return str(text).strip()[:max_chars]
        return None

    async def _summarize(self, messages: list[dict[str, Any]]) -> str | None:
        flat = "\n".join(f"{m.get('role')}: {m.get('content')}" for m in messages
                         if isinstance(m.get("content"), str))
        return await self._quick([{"role": "system", "content": SUMMARY_PROMPT},
                                  {"role": "user", "content": flat[-24000:]}])

    async def _llm_classify(self, message: dict[str, Any]) -> Category | None:
        text = message.get("content") if isinstance(message.get("content"), str) else ""
        out = await self._quick([{"role": "system", "content": classifier.CLASSIFIER_PROMPT},
                                 {"role": "user", "content": str(text)[:2000]}])
        return classifier.parse_llm_category(out or "")


def now() -> float:
    return time.time()
