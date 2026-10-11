"""Graphiques précis (barres, courbes, camemberts…) : configuration Chart.js écrite par le
modèle, rendue en PNG par QuickChart (quickchart.io, gratuit et anonyme, vérifié le
2026-10-11). Aucune fonction JavaScript n'est acceptée dans la configuration."""

from __future__ import annotations

import json
import re
from typing import Any

import httpx

from tontolo import http
from tontolo.creator.diagram import png_size

QUICKCHART = "https://quickchart.io/chart"
TYPES = {"bar", "line", "pie", "doughnut", "radar", "scatter", "polarArea", "bubble"}


class ChartError(Exception):
    def __init__(self, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable


def parse_config(text: str) -> dict[str, Any]:
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        raise ChartError("configuration Chart.js introuvable (JSON attendu)")
    try:
        config = json.loads(m.group(0))
    except (ValueError, RecursionError) as exc:
        raise ChartError(f"JSON invalide : {exc}") from exc
    if not isinstance(config, dict) or config.get("type") not in TYPES:
        raise ChartError(f"« type » doit être l'un de : {', '.join(sorted(TYPES))}")
    if "function" in json.dumps(config):
        raise ChartError("pas de fonction JavaScript dans la configuration")
    return config


def title_of(config: dict[str, Any]) -> str:
    title = (((config.get("options") or {}).get("plugins") or {}).get("title") or {})
    text = title.get("text") if isinstance(title, dict) else None
    return " ".join(text) if isinstance(text, list) else str(text or "")


def problems(config: dict[str, Any]) -> list[str]:
    out = []
    data = config.get("data") or {}
    sets = data.get("datasets") or []
    labels = data.get("labels") or []
    if not sets:
        out.append("aucune série de données (« datasets »)")
    for ds in sets:
        values = ds.get("data") or []
        if (labels and config.get("type") not in ("scatter", "bubble")
                and len(values) != len(labels)):
            out.append(f"série « {ds.get('label', '')} » : {len(values)} valeurs pour "
                       f"{len(labels)} étiquettes")
    if not title_of(config):
        out.append("ajoute un titre (options.plugins.title)")
    return out[:6]


async def render(config: dict[str, Any]) -> bytes:
    body = {"version": "4", "backgroundColor": "white", "width": 1000, "height": 600,
            "devicePixelRatio": 2, "format": "png", "chart": config}
    try:
        r = await http.client().post(QUICKCHART, json=body, timeout=60.0)
    except httpx.HTTPError as exc:
        raise ChartError("service de graphiques injoignable", retryable=True) from exc
    if r.status_code != 200 or not r.content.startswith(b"\x89PNG"):
        raise ChartError(f"service de graphiques : réponse {r.status_code}", retryable=True)
    _, height = png_size(r.content)
    if height < 200:  # QuickChart renvoie une petite image d'erreur avec le code 200
        raise ChartError("configuration refusée par le moteur de graphiques")
    return r.content
