"""Gestionnaire de quotas (section 5.2).

États par (fournisseur, modèle) — la clé est unique par fournisseur (BYOK) :
`available`, `cooldown(until)`, `exhausted_daily(until)`. Les erreurs de portée
fournisseur (clé invalide, crédits épuisés) ou « réserve gratuite » (quota
partagé par tous les modèles gratuits d'OpenRouter) bloquent tout le groupe.

On n'envoie **jamais** de requête de test : un modèle redevient éligible
quand son `until` est passé, et c'est le prochain vrai tour qui le réessaie.
"""

from __future__ import annotations

import re
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from tontolo.catalog.models import ModelInfo
from tontolo.catalog.sources.freeapis import parse_rate_limit
from tontolo.providers.base import ErrorKind, ProviderError, Scope

BASE_BACKOFF = 15.0
MAX_BACKOFF = 3600.0
AUTH_COOLDOWN = 6 * 3600.0


@dataclass
class QuotaState:
    status: str = "available"          # available | cooldown | exhausted_daily
    until: float = 0.0
    reason: str = ""
    failures: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "until": self.until, "reason": self.reason,
                "failures": self.failures}


@dataclass
class _Counter:
    minute: deque[float] = field(default_factory=deque)
    day: deque[float] = field(default_factory=deque)


def next_utc_midnight(now: float) -> float:
    d = datetime.fromtimestamp(now, UTC)
    return (d.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)).timestamp()


def _reset_from_headers(headers: dict[str, str], now: float) -> float | None:
    """Lit `x-ratelimit-reset*` (secondes, durée « 1m30s » ou horodatage en ms)."""
    for name in ("x-ratelimit-reset", "x-ratelimit-reset-requests", "x-ratelimit-reset-tokens"):
        raw = headers.get(name)
        if not raw:
            continue
        try:
            val = float(raw)
            if val > 1e12:      # horodatage en millisecondes (OpenRouter)
                return val / 1000
            if val > 1e9:       # horodatage en secondes
                return val
            return now + val
        except ValueError:
            total = 0.0
            for num, unit in re.findall(r"([\d.]+)(ms|s|m|h)", raw):
                total += float(num) * {"ms": 0.001, "s": 1, "m": 60, "h": 3600}[unit]
            if total:
                return now + total
    return None


class QuotaManager:
    def __init__(self) -> None:
        self.states: dict[str, QuotaState] = {}
        self._counters: dict[str, _Counter] = {}
        self._limits: dict[str, dict[str, int]] = {}
        self.dirty: set[str] = set()

    # --- Clés de groupe --------------------------------------------------

    @staticmethod
    def group_keys(model: ModelInfo) -> list[str]:
        keys = [model.key, f"provider:{model.provider}"]
        if model.is_free:
            keys.append(f"free_pool:{model.provider}")
        return keys

    # --- Lecture ---------------------------------------------------------

    def state(self, key: str, now: float | None = None) -> QuotaState:
        now = now or time.time()
        st = self.states.get(key)
        if st and st.status != "available" and st.until <= now:
            st.status, st.reason = "available", ""
            self.dirty.add(key)
        return st or QuotaState()

    def available_at(self, model: ModelInfo, now: float | None = None) -> float:
        """0 si disponible maintenant, sinon l'instant de disponibilité."""
        now = now or time.time()
        until = 0.0
        for k in self.group_keys(model):
            st = self.state(k, now)
            if st.status != "available":
                until = max(until, st.until)
        anticip = self._anticipated(model, now)
        return max(until, anticip)

    def status_of(self, model: ModelInfo, now: float | None = None) -> QuotaState:
        """État le plus contraignant du modèle et de ses groupes (fournisseur, quota partagé)."""
        now = now or time.time()
        worst = QuotaState()
        for k in self.group_keys(model):
            st = self.state(k, now)
            if st.status != "available" and st.until > worst.until:
                worst = st
        return worst

    def available(self, model: ModelInfo, now: float | None = None) -> bool:
        return self.available_at(model, now) == 0.0

    def pressure(self, model: ModelInfo, now: float | None = None) -> float:
        """Proportion du quota local consommée (0 → 1) pour pénaliser avant le 429."""
        now = now or time.time()
        limits = self._limits_for(model)
        c = self._counter(model.key, now)
        ratios = []
        if limits.get("rpm"):
            ratios.append(len(c.minute) / limits["rpm"])
        if limits.get("rpd"):
            ratios.append(len(c.day) / limits["rpd"])
        return min(1.0, max(ratios, default=0.0))

    # --- Comptage local (anticipation) ----------------------------------

    def _limits_for(self, model: ModelInfo) -> dict[str, int]:
        if model.key not in self._limits:
            self._limits[model.key] = parse_rate_limit(model.rate_limit)
        return self._limits[model.key]

    def _counter(self, key: str, now: float) -> _Counter:
        c = self._counters.setdefault(key, _Counter())
        while c.minute and c.minute[0] <= now - 60:
            c.minute.popleft()
        while c.day and c.day[0] <= now - 86400:
            c.day.popleft()
        return c

    def _anticipated(self, model: ModelInfo, now: float) -> float:
        limits = self._limits_for(model)
        c = self._counter(model.key, now)
        if limits.get("rpm") and len(c.minute) >= limits["rpm"]:
            return c.minute[0] + 60
        if limits.get("rpd") and len(c.day) >= limits["rpd"]:
            return c.day[0] + 86400
        return 0.0

    def record_request(self, model: ModelInfo, now: float | None = None) -> None:
        now = now or time.time()
        c = self._counter(model.key, now)
        c.minute.append(now)
        c.day.append(now)

    # --- Mise à jour après appel ----------------------------------------

    def on_success(self, model: ModelInfo) -> None:
        st = self.states.get(model.key)
        if st and st.failures:
            st.failures = 0
            self.dirty.add(model.key)

    def on_error(self, model: ModelInfo, err: ProviderError, now: float | None = None) -> float:
        """Met le modèle (ou son groupe) en attente. Renvoie `until`."""
        now = now or time.time()
        if err.kind in (ErrorKind.BAD_REQUEST, ErrorKind.CONTEXT):
            return 0.0  # problème de requête : pas de pénalité de quota
        if err.scope == Scope.PROVIDER:
            key = f"provider:{model.provider}"
        elif err.scope == Scope.FREE_POOL:
            key = f"free_pool:{model.provider}"
        else:
            key = model.key
        st = self.states.setdefault(key, QuotaState())
        st.failures += 1
        until = None
        if err.retry_after:
            until = now + err.retry_after
        until = until or _reset_from_headers(err.headers, now)
        status = "cooldown"
        if err.kind == ErrorKind.QUOTA:
            status = "exhausted_daily"
            until = until if until and until > now + 60 else next_utc_midnight(now)
        elif err.kind == ErrorKind.AUTH:
            until = now + AUTH_COOLDOWN
        elif err.kind == ErrorKind.UNAVAILABLE:
            until = now + 12 * 3600
        if until is None:
            until = now + min(MAX_BACKOFF, BASE_BACKOFF * 2 ** (st.failures - 1))
        st.status, st.until, st.reason = status, until, err.kind.value
        self.dirty.add(key)
        return until

    # --- Persistance -----------------------------------------------------

    def load(self, data: dict[str, dict[str, Any]]) -> None:
        for k, v in data.items():
            self.states[k] = QuotaState(v.get("status", "available"), float(v.get("until", 0)),
                                        v.get("reason", ""), int(v.get("failures", 0)))

    def take_dirty(self) -> dict[str, dict[str, Any]]:
        out = {k: self.states[k].to_dict() for k in self.dirty if k in self.states}
        self.dirty.clear()
        return out

    def snapshot(self, now: float | None = None) -> dict[str, dict[str, Any]]:
        now = now or time.time()
        return {k: st.to_dict() for k in list(self.states)
                if (st := self.state(k, now)).status != "available"}
