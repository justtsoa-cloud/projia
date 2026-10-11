"""Score des modèles éligibles et chaîne de repli (sections 4.2 et 4.3).

    score = w_q · Qualité(catégorie) + w_s · Vitesse + w_r · Fiabilité − pénalités

Ordre de coût strict : tous les modèles gratuits passent avant les payants,
qui n'entrent dans le classement que si l'utilisateur l'a autorisé (F4).
Un modèle choisi manuellement passe en tête ; la chaîne automatique suit.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from tontolo.catalog.catalog import Catalog
from tontolo.catalog.models import MEDIA_CATEGORIES, Category, ModelInfo
from tontolo.config import PaidFallback, Settings
from tontolo.router.classifier import TaskProfile
from tontolo.router.quota import QuotaManager

DEFAULT_SPEED = 0.5
RELIABILITY_PRIOR = (4.0, 5.0)  # (succès, essais) a priori : 0,8


@dataclass
class Candidate:
    model: ModelInfo
    score: float
    quality: float
    speed: float
    reliability: float
    preferred: bool = False
    available_at: float = 0.0

    def reason(self, category: Category) -> dict[str, Any]:
        return {
            "category": category.value, "score": round(self.score, 3),
            "quality": round(self.quality, 3), "speed": round(self.speed, 3),
            "reliability": round(self.reliability, 3), "preferred": self.preferred,
            "free": self.model.is_free, "provisional": self.model.provisional,
        }


@dataclass
class Preference:
    model: str
    strict: bool = False
    scope: str = "global"


@dataclass
class RouteDecision:
    profile: TaskProfile
    chain: list[Candidate] = field(default_factory=list)
    preferred: Preference | None = None
    waiting: list[Candidate] = field(default_factory=list)  # éligibles mais en attente

    @property
    def best(self) -> Candidate | None:
        return self.chain[0] if self.chain else None


class Reliability:
    """Taux de succès observé localement (moyenne glissante exponentielle)."""

    def __init__(self, decay: float = 0.97) -> None:
        self.decay = decay
        self.table: dict[str, tuple[float, float]] = {}
        self.dirty: set[str] = set()

    def get(self, key: str) -> float:
        ok, total = self.table.get(key, (0.0, 0.0))
        p_ok, p_total = RELIABILITY_PRIOR
        return (ok + p_ok) / (total + p_total)

    def record(self, key: str, success: bool) -> None:
        ok, total = self.table.get(key, (0.0, 0.0))
        self.table[key] = (ok * self.decay + (1.0 if success else 0.0), total * self.decay + 1.0)
        self.dirty.add(key)


# Demandes simples : la vitesse peut primer (option « réponse rapide d'abord »).
SIMPLE_CATEGORIES = frozenset({Category.CHAT, Category.WRITING, Category.TRANSLATION,
                               Category.SEARCH})

def pick_preference(
    prefs: list[dict[str, Any]], conversation_id: str | None, category: Category
) -> Preference | None:
    """Priorité : conversation > catégorie > global."""
    by_scope = {(p["scope"], p["scope_key"]): p for p in prefs}
    for scope, key in (("conversation", conversation_id or ""), ("category", category.value),
                       ("global", "")):
        p = by_scope.get((scope, key))
        if p and p.get("model") and p["model"] != "auto":
            return Preference(p["model"], bool(p.get("strict")), scope)
    return None


def _eligible(m: ModelInfo, profile: TaskProfile, category: Category) -> bool:
    if not m.serves(category):
        return False
    if profile.needs_tools and not m.supports_tools:
        return False
    if profile.needs_vision and not m.supports_vision:
        return False
    return not (m.context_length and m.context_length < profile.min_context
                and category not in MEDIA_CATEGORIES)


def paid_allowed(m: ModelInfo, settings: Settings) -> bool:
    if m.is_free:
        return True
    if settings.paid.fallback == PaidFallback.OFF:
        return False
    allowed = settings.paid.allowed_models
    return not allowed or m.key in allowed or m.model_id in allowed


def rank(
    catalog: Catalog,
    profile: TaskProfile,
    *,
    usable: set[str],
    quota: QuotaManager,
    reliability: Reliability,
    settings: Settings,
    preference: Preference | None = None,
    now: float | None = None,
) -> RouteDecision:
    now = now or time.time()
    w = settings.weights
    category = profile.category
    w_q, w_s, w_r = w.quality, w.speed, w.reliability
    if settings.speed_first and category in SIMPLE_CATEGORIES:
        w_q, w_s, w_r = 0.3, 0.45, 0.25
    decision = RouteDecision(profile=profile, preferred=preference)

    def collect(cat: Category) -> list[Candidate]:
        cands = []
        for m in catalog.models.values():
            if m.provider not in usable or not paid_allowed(m, settings):
                continue
            if not _eligible(m, profile, cat):
                continue
            q = m.quality.get(cat.value, m.quality.get(Category.CHAT.value, 0.0))
            s = m.speed if m.speed is not None else DEFAULT_SPEED
            if profile.latency_pref == "fast" and m.speed is not None:
                s = min(1.0, s * 1.2)
            r = reliability.get(m.key)
            penalty = 0.05 if m.provisional else 0.0
            if m.provider == "local":
                penalty += 0.3  # repli local : toujours en dernier
            penalty += 0.15 * quota.pressure(m, now)
            score = w_q * q + w_s * s + w_r * r - penalty
            cands.append(Candidate(m, score, q, s, r, available_at=quota.available_at(m, now)))
        return cands

    cands = collect(category)
    if not cands and category not in MEDIA_CATEGORIES and category != Category.CHAT:
        # Aucun modèle spécialisé éligible : repli sur les modèles généralistes.
        cands = collect(Category.CHAT)

    # Gratuit d'abord (strict), puis score décroissant.
    cands.sort(key=lambda c: (not c.model.is_free, -c.score))
    ready = [c for c in cands if c.available_at == 0.0]
    decision.waiting = [c for c in cands if c.available_at > 0.0]

    if preference:
        pm = catalog.get(preference.model)
        if pm is not None:
            pref_c = next((c for c in cands if c.model.key == pm.key), None)
            if pref_c is None and pm.provider in usable:
                # Préféré mais hors critères automatiques : on le tente quand même en tête.
                pref_c = Candidate(pm, 1.0, pm.quality.get(category.value, 0.0),
                                   pm.speed or DEFAULT_SPEED, reliability.get(pm.key),
                                   available_at=quota.available_at(pm, now))
            if pref_c is not None:
                pref_c.preferred = True
                ready = [c for c in ready if c.model.key != pm.key]
                if pref_c.available_at == 0.0:
                    ready.insert(0, pref_c)
                elif preference.strict:
                    ready = []  # mode strict : attendre plutôt que basculer
                    decision.waiting.insert(0, pref_c)
    decision.chain = ready
    return decision
