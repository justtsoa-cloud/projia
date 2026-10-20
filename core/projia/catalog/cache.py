"""Cache disque des sources du catalogue : TTL, ETag et mode dégradé hors ligne."""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from projia import http

log = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    data: Any
    fetched_at: float
    etag: str | None = None

    def age(self) -> float:
        return time.time() - self.fetched_at


class SourceCache:
    def __init__(self, directory: Path, offline: bool = False) -> None:
        self.dir = directory
        self.dir.mkdir(parents=True, exist_ok=True)
        # Hors ligne : uniquement le cache (démarrage instantané).
        self.offline = offline

    def _path(self, name: str) -> Path:
        return self.dir / f"{name}.json"

    def get(self, name: str) -> CacheEntry | None:
        p = self._path(name)
        if not p.exists():
            return None
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
            return CacheEntry(raw["data"], float(raw["fetched_at"]), raw.get("etag"))
        except (OSError, ValueError, KeyError):
            return None

    def put(self, name: str, data: Any, etag: str | None = None) -> CacheEntry:
        entry = CacheEntry(data, time.time(), etag)
        tmp = self._path(name).with_suffix(".tmp")
        tmp.write_text(
            json.dumps({"data": data, "fetched_at": entry.fetched_at, "etag": etag},
                       ensure_ascii=False),
            encoding="utf-8",
        )
        tmp.replace(self._path(name))
        return entry

    def touch(self, name: str, entry: CacheEntry) -> CacheEntry:
        return self.put(name, entry.data, entry.etag)

    async def fetch_json(
        self,
        name: str,
        url: str,
        *,
        ttl: float,
        headers: Mapping[str, str] | None = None,
        params: Mapping[str, str] | None = None,
        force: bool = False,
        parse: str = "json",
    ) -> CacheEntry | None:
        """Renvoie la donnée en cache si fraîche ; sinon télécharge (requête conditionnelle).

        En cas d'échec réseau, renvoie le dernier cache valide (mode dégradé).
        """
        cached = self.get(name)
        if self.offline or (cached and not force and cached.age() < ttl):
            return cached
        req_headers = dict(headers or {})
        if cached and cached.etag:
            req_headers["If-None-Match"] = cached.etag
        try:
            resp = await http.client().get(url, headers=req_headers, params=params)
            if resp.status_code == 304 and cached:
                return self.touch(name, cached)
            resp.raise_for_status()
            data: Any = resp.json() if parse == "json" else resp.text
            return self.put(name, data, resp.headers.get("etag"))
        except (httpx.HTTPError, ValueError) as exc:
            log.warning("Source %s indisponible (%s) : cache utilisé", name, type(exc).__name__)
            return cached
