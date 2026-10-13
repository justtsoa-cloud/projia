#!/usr/bin/env python3
"""Instantané de secours du catalogue (modèles gratuits SANS clé, avec leurs scores), embarqué
dans le cœur : utilisé seulement au tout premier lancement si aucun catalogue n'a pu être
téléchargé. À régénérer de temps en temps depuis un catalogue à jour :

    cd core && uv run python ../scripts/catalog_seed.py
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from tontolo.catalog.service import CatalogService
from tontolo.config import load_settings

OUT = Path(__file__).resolve().parents[1] / "core" / "tontolo" / "catalog" / "seed.json"
KEEP = ("provider", "model_id", "name", "family", "context_length", "max_output",
        "input_modalities", "output_modalities", "supports_tools", "is_free", "needs_key",
        "quality", "speed", "media")


async def main() -> None:
    svc = CatalogService(load_settings())
    await svc.load()
    cat = svc.catalog
    keyless = {pid for pid, p in cat.providers.items() if p.get("keyless")
               and pid not in ("local", "ollama_local", "llamacpp_local")}
    models = [m for m in cat.models.values() if m.provider in keyless and m.is_free]
    models.sort(key=lambda m: -max(m.quality.values(), default=0))
    rows = []
    for m in models[:60]:
        d = m.model_dump()
        rows.append({k: (round(v, 3) if isinstance(v, float) else
                         {kk: round(vv, 3) for kk, vv in v.items()} if k == "quality" else v)
                     for k, v in d.items() if k in KEEP})
    providers = {pid: {k: v for k, v in cat.providers[pid].items() if k != "description"}
                 for pid in sorted({r["provider"] for r in rows})}
    OUT.write_text(json.dumps({"providers": providers, "models": rows}, ensure_ascii=False,
                              separators=(",", ":")), encoding="utf-8")
    print(OUT, OUT.stat().st_size // 1024, "Ko,", len(rows), "modèles")


asyncio.run(main())
