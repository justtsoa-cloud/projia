"""Fusion des sources en un catalogue classé par catégorie de tâche."""

from __future__ import annotations

import math
import time
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from projia.catalog.matcher import Matcher, canonical, family
from projia.catalog.models import Category, ModelInfo
from projia.catalog.sources.rankings import RankingEntry

# Métriques utilisées pour la qualité de chaque catégorie (par ordre d'intérêt).
QUALITY_METRICS: dict[Category, tuple[str, ...]] = {
    Category.CHAT: ("lmarena.text.overall", "aa.intelligence", "or_aa.intelligence"),
    Category.CODE: ("aa.coding", "or_aa.coding", "lmarena.text.coding",
                    "lmarena.webdev.overall"),
    Category.MATH: ("aa.math", "lmarena.text.math"),
    Category.REASONING: ("aa.intelligence", "or_aa.intelligence", "lmarena.text.hard_prompts"),
    Category.WRITING: ("lmarena.text.creative_writing", "lmarena.text.overall"),
    Category.TRANSLATION: ("lmarena.text.non_english", "lmarena.text.french"),
    Category.VISION: ("lmarena.vision.overall",),
    Category.LONG_CONTEXT: ("lmarena.text.longer_query", "aa.intelligence",
                            "or_aa.intelligence"),
    Category.AGENTIC: ("or_aa.agentic", "lmarena.agent.overall", "aa.intelligence",
                       "or_aa.intelligence"),
    Category.SEARCH: ("lmarena.search.overall", "aa.intelligence", "or_aa.intelligence"),
    Category.IMAGE_GEN: ("lmarena.text_to_image.overall", "aa.image_gen"),
    Category.IMAGE_EDIT: ("lmarena.image_edit.overall", "aa.image_edit"),
    Category.TTS: ("aa.tts",),
    Category.VIDEO_GEN: ("lmarena.text_to_video.overall", "aa.video_gen"),
    Category.STT: (),
    Category.MUSIC_SFX: (),
}
GENERAL_METRICS = ("aa.intelligence", "or_aa.intelligence", "lmarena.text.overall")
# Score prudent pour un modèle sans aucun classement ni famille connue.
DEFAULT_QUALITY = 0.25
PROVISIONAL_FACTOR = 0.9


@dataclass
class Catalog:
    models: dict[str, ModelInfo] = field(default_factory=dict)
    providers: dict[str, dict[str, Any]] = field(default_factory=dict)
    updated_at: float = 0.0
    sources: dict[str, int] = field(default_factory=dict)

    def get(self, key: str) -> ModelInfo | None:
        if key in self.models:
            return self.models[key]
        # Tolère un identifiant sans fournisseur (« google/gemma-4-31b-it:free »).
        for m in self.models.values():
            if m.model_id == key:
                return m
        return None

    def filter(
        self,
        *,
        category: Category | str | None = None,
        free_only: bool = False,
        usable: Iterable[str] | None = None,
        needs_tools: bool = False,
    ) -> list[ModelInfo]:
        usable_set = set(usable) if usable is not None else None
        out = []
        for m in self.models.values():
            if free_only and not m.is_free:
                continue
            if category and not m.serves(category):
                continue
            if needs_tools and not m.supports_tools:
                continue
            if usable_set is not None and m.provider not in usable_set:
                continue
            out.append(m)
        cat = Category(category) if category else Category.CHAT
        return sorted(out, key=lambda m: m.quality.get(cat.value, 0.0), reverse=True)

    def snapshot(self) -> dict[str, dict[str, Any]]:
        """Vue compacte pour le calcul des différences (veille)."""
        return {
            k: {"free": m.is_free, "price_in": m.price_in, "price_out": m.price_out,
                "tools": m.supports_tools, "ctx": m.context_length,
                "in": sorted(m.input_modalities), "out": sorted(m.output_modalities),
                "name": m.name, "provider": m.provider}
            for k, m in self.models.items()
        }


def _merge_rankings(entries: Iterable[RankingEntry]) -> tuple[Matcher, dict[str, dict[str, float]]]:
    """Regroupe les entrées par clé canonique (variantes d'effort → meilleure note)."""
    merged: dict[str, dict[str, float]] = defaultdict(dict)
    names: dict[str, set[str]] = defaultdict(set)
    for e in entries:
        ident = canonical(e.names[0])
        if not ident:
            continue
        for k, v in e.metrics.items():
            merged[ident][k] = max(v, merged[ident].get(k, v))
        names[ident].update(e.names)
    matcher = Matcher()
    for ident, ns in names.items():
        matcher.add(ident, ns)
    return matcher, dict(merged)


def _normalizers(metric_tables: Iterable[dict[str, float]]) -> dict[str, tuple[float, float]]:
    lo: dict[str, float] = {}
    hi: dict[str, float] = {}
    for table in metric_tables:
        for k, v in table.items():
            lo[k] = min(v, lo.get(k, v))
            hi[k] = max(v, hi.get(k, v))
    return {k: (lo[k], hi[k]) for k in lo}


def _norm(metric: str, value: float, bounds: dict[str, tuple[float, float]]) -> float:
    lo, hi = bounds.get(metric, (value, value))
    if metric == "aa.ttft":  # plus petit = meilleur
        return 1.0 - (value - lo) / (hi - lo) if hi > lo else 0.5
    if metric == "aa.tps":   # échelle logarithmique pour la vitesse
        value, lo, hi = math.log1p(value), math.log1p(lo), math.log1p(hi)
    return (value - lo) / (hi - lo) if hi > lo else 0.5


def build_catalog(
    models: list[ModelInfo],
    rankings: list[RankingEntry],
    providers: dict[str, dict[str, Any]] | None = None,
) -> Catalog:
    # Les indices AA publiés par OpenRouter servent aussi de classement pour
    # apparier les mêmes modèles hébergés ailleurs (Groq, NVIDIA…).
    or_entries = [
        RankingEntry([m.model_id, m.name], dict(m.metrics))
        for m in models if m.provider == "openrouter" and m.metrics
    ]
    matcher, merged = _merge_rankings([*rankings, *or_entries])
    bounds = _normalizers(merged.values())

    for m in models:
        m.family = m.family or family(m.model_id)
        res = matcher.match(m.model_id, m.name)
        if res:
            for k, v in merged[res.key].items():
                m.metrics.setdefault(k, v)

    by_family: dict[str, list[ModelInfo]] = defaultdict(list)
    for m in models:
        _score(m, bounds)
        if not m.provisional:
            by_family[m.family].append(m)

    # Scores provisoires : modèles trop récents ou absents des classements.
    for m in models:
        if not m.provisional:
            continue
        peers = by_family.get(m.family, [])
        for cat in Category:
            if not m.serves(cat):
                continue
            vals = [p.quality[cat.value] for p in peers if cat.value in p.quality]
            base = (sum(vals) / len(vals)) if vals else DEFAULT_QUALITY / PROVISIONAL_FACTOR
            m.quality[cat.value] = round(base * PROVISIONAL_FACTOR, 4)

    catalog = Catalog(updated_at=time.time(), providers=dict(providers or {}))
    for m in models:
        catalog.models.setdefault(m.key, m)
    return catalog


def _score(m: ModelInfo, bounds: dict[str, tuple[float, float]]) -> None:
    m.quality = {}
    general = [_norm(k, m.metrics[k], bounds) for k in GENERAL_METRICS if k in m.metrics]
    has_any = False
    for cat, keys in QUALITY_METRICS.items():
        if not m.serves(cat):
            continue
        vals = [_norm(k, m.metrics[k], bounds) for k in keys if k in m.metrics]
        if vals:
            m.quality[cat.value] = round(sum(vals) / len(vals), 4)
            has_any = True
        elif general and m.is_text:
            m.quality[cat.value] = round(0.95 * sum(general) / len(general), 4)
            has_any = True
    m.provisional = not has_any
    if "aa.tps" in m.metrics:
        m.speed = round(_norm("aa.tps", m.metrics["aa.tps"], bounds), 4)
