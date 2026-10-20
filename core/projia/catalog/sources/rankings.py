"""Sources de classement : Artificial Analysis (clé gratuite) et LMArena (CC BY 4.0).

- Artificial Analysis, vérifié le 2026-10-10 : `GET https://artificialanalysis.ai/api/v2/data/llms/models`
  et `/data/media/{text-to-image,image-editing,text-to-speech,text-to-video}`,
  en-tête `x-api-key`, 1000 requêtes/jour, attribution obligatoire.
- LMArena, vérifié le 2026-10-10 : jeu de données Hugging Face
  `lmarena-ai/leaderboard-dataset` (configs `text`, `vision`, `webdev`,
  `text_to_image`…, split `latest`), lu en JSON via l'API datasets-server pour
  éviter une dépendance parquet. Licence CC BY 4.0 : attribution obligatoire.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from projia.catalog.cache import SourceCache

log = logging.getLogger(__name__)

AA_BASE = "https://artificialanalysis.ai/api/v2/data"
LMARENA_FILTER = "https://datasets-server.huggingface.co/filter"
LMARENA_DATASET = "lmarena-ai/leaderboard-dataset"

# (config, catégorie LMArena) récupérées ; les catégories manquantes sont ignorées.
# Réduit à l'usage réel (chat général, vision, image) : moins de tranches = moins
# d'appels réseau par cycle de rafraîchissement, et donc moins de temps perdu si une
# tranche échoue côté serveur (LMArena/Hugging Face).
LMARENA_SLICES: tuple[tuple[str, str], ...] = (
    ("text", "overall"), ("vision", "overall"),
    ("text_to_image", "overall"), ("image_edit", "overall"),
)

AA_MEDIA = {
    "text-to-image": "image_gen",
    "image-editing": "image_edit",
    "text-to-speech": "tts",
    "text-to-video": "video_gen",
}


@dataclass
class RankingEntry:
    """Une ligne de classement, avant appariement avec le catalogue."""

    names: list[str]
    metrics: dict[str, float] = field(default_factory=dict)
    organization: str | None = None


def _num(v: Any) -> float | None:
    return float(v) if isinstance(v, int | float) and not isinstance(v, bool) else None


def parse_aa_llms(payload: Any) -> list[RankingEntry]:
    rows = payload.get("data", payload) if isinstance(payload, dict) else payload
    out: list[RankingEntry] = []
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        ev: dict[str, Any] = r["evaluations"] if isinstance(r.get("evaluations"), dict) else r
        metrics: dict[str, float] = {}
        for src, dst in (("artificial_analysis_intelligence_index", "aa.intelligence"),
                         ("artificial_analysis_coding_index", "aa.coding"),
                         ("artificial_analysis_math_index", "aa.math")):
            if (v := _num(ev.get(src))) is not None:
                metrics[dst] = v
        if (v := _num(r.get("median_output_tokens_per_second"))) is not None and v > 0:
            metrics["aa.tps"] = v
        if (v := _num(r.get("median_time_to_first_token_seconds"))) is not None and v > 0:
            metrics["aa.ttft"] = v
        creator = r.get("model_creator") or {}
        names = [n for n in (r.get("slug"), r.get("name")) if n]
        if names and metrics:
            out.append(RankingEntry(names, metrics, creator.get("slug") or creator.get("name")))
    return out


def parse_aa_media(payload: Any, category: str) -> list[RankingEntry]:
    rows = payload.get("data", payload) if isinstance(payload, dict) else payload
    out: list[RankingEntry] = []
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        elo = _num(r.get("elo"))
        names = [n for n in (r.get("slug"), r.get("name")) if n]
        if names and elo is not None:
            out.append(RankingEntry(names, {f"aa.{category}": elo}))
    return out


async def fetch_artificial_analysis(
    cache: SourceCache, api_key: str | None, ttl: float, force: bool = False
) -> list[RankingEntry]:
    if not api_key:
        cached = cache.get("aa_llms")  # dernier cache éventuel (clé retirée)
        return parse_aa_llms(cached.data) if cached else []
    headers = {"x-api-key": api_key}
    entries: list[RankingEntry] = []
    llms = await cache.fetch_json("aa_llms", f"{AA_BASE}/llms/models", ttl=ttl,
                                  headers=headers, force=force)
    if llms:
        entries += parse_aa_llms(llms.data)
    for path, cat in AA_MEDIA.items():
        media = await cache.fetch_json(f"aa_{cat}", f"{AA_BASE}/media/{path}", ttl=ttl,
                                       headers=headers, force=force)
        if media:
            entries += parse_aa_media(media.data, cat)
    return entries


def parse_lmarena(payload: Any, config: str, category: str) -> list[RankingEntry]:
    out: list[RankingEntry] = []
    for item in (payload or {}).get("rows", []):
        row = item.get("row", item)
        name, rating = row.get("model_name"), _num(row.get("rating"))
        if name and rating is not None:
            out.append(RankingEntry([name], {f"lmarena.{config}.{category}": rating},
                                    row.get("organization")))
    return out


COOLDOWN_S = 300.0  # une tranche en échec n'est pas retentée avant ce délai : sans ça, un
                    # rafraîchissement déclenché à chaque conversation retape un serveur en
                    # panne (ex. datasets-server HF) en boucle plutôt que d'attendre qu'il
                    # se rétablisse.


async def fetch_lmarena(
    cache: SourceCache, ttl: float, force: bool = False, concurrency: int = 4
) -> list[RankingEntry]:
    sem = asyncio.Semaphore(concurrency)

    async def one(config: str, category: str) -> list[RankingEntry]:
        name = f"lmarena_{config}_{category}"
        cooldown = cache.get(f"{name}_cooldown")
        if not force and cooldown and cooldown.age() < COOLDOWN_S:
            return []
        params = {
            "dataset": LMARENA_DATASET, "config": config, "split": "latest",
            "where": f"\"category\"='{category}'", "orderby": "\"rating\" DESC",
            "length": "100",
        }
        async with sem:
            entry = None
            for attempt in range(3):  # l'API datasets-server est parfois instable
                entry = await cache.fetch_json(name, LMARENA_FILTER, ttl=ttl, params=params,
                                               force=force or attempt > 0)
                if cache.offline or (
                    entry and isinstance(entry.data, dict) and "rows" in entry.data
                ):
                    break
                await asyncio.sleep(1.5 * (attempt + 1))
        ok = bool(entry and isinstance(entry.data, dict) and "rows" in entry.data)
        if not ok and not cache.offline:
            cache.put(f"{name}_cooldown", {"failed_at": time.time()})
        if ok:
            return parse_lmarena(entry.data, config, category)
        return []

    results = await asyncio.gather(*(one(c, k) for c, k in LMARENA_SLICES))
    return [e for chunk in results for e in chunk]
