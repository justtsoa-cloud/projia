"""Espace disque : TOUS les caches dans un seul dossier `<données>/cache/`, sans doublons.

    cache/            catalogue des modèles (sources en ligne mises en cache)
    cache/updates/    la mise à jour téléchargée (une seule : les anciennes sont effacées)
    cache/tmp/        fichiers temporaires de l'application (dictée, vidéos, partages)
    cache/browser/    cache web du navigateur de l'agent (plafonné)

Les données (discussions, créations, résultats de tâches, sauvegardes du dossier de travail)
restent hors du cache : « Vider le cache » ne les touche jamais.
"""

from __future__ import annotations

import re
import shutil
import time
from pathlib import Path
from typing import Any

TMP_MAX_AGE = 24 * 3600
BROWSER_CACHE_BYTES = 64 * 1024 * 1024
_VERSION = re.compile(r"(\d+)\.(\d+)\.(\d+)")


def cache_dir(data: Path, sub: str = "") -> Path:
    path = data / "cache" / sub if sub else data / "cache"
    path.mkdir(parents=True, exist_ok=True)
    return path


def size_of(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    total = 0
    if path.is_dir():
        for p in path.rglob("*"):
            try:
                if p.is_file() and not p.is_symlink():
                    total += p.stat().st_size
            except OSError:
                continue
    return total


def _version(name: str) -> tuple[int, ...] | None:
    m = _VERSION.search(name)
    return tuple(int(x) for x in m.groups()) if m else None


def tidy(data: Path, current_version: str, now: float | None = None) -> int:
    """Nettoyage au démarrage : anciens dossiers déplacés, mises à jour déjà installées ou
    remplacées, fichiers temporaires de plus d'un jour. Renvoie les octets libérés."""
    now = now or time.time()
    freed = 0
    old_updates = data / "updates"  # avant 0.5.1 : hors du cache
    if old_updates.is_dir():
        freed += size_of(old_updates)
        shutil.rmtree(old_updates, ignore_errors=True)
    current = _version(current_version) or (0, 0, 0)
    updates = cache_dir(data, "updates")
    files = [p for p in updates.iterdir() if p.is_file()]
    newest = max((v for p in files if (v := _version(p.name))), default=None)
    for p in files:
        v = _version(p.name)
        if (p.name.endswith(".part") and now - p.stat().st_mtime > TMP_MAX_AGE) or (
                v is not None and (v <= current or (newest is not None and v < newest))):
            freed += p.stat().st_size
            p.unlink(missing_ok=True)
    tmp = cache_dir(data, "tmp")
    for p in tmp.rglob("*"):
        try:
            if p.is_file() and now - p.stat().st_mtime > TMP_MAX_AGE:
                freed += p.stat().st_size
                p.unlink()
        except OSError:
            continue
    return freed


def keep_only(updates: Path, keep: Path) -> None:
    """Une seule mise à jour gardée : celle qui vient d'être vérifiée."""
    for p in updates.iterdir():
        if p.is_file() and p != keep:
            p.unlink(missing_ok=True)


def report(data: Path) -> dict[str, Any]:
    cache = data / "cache"
    parts = {
        "conversations": size_of(data / "projia.db"),
        "creations": size_of(data / "media"),
        "tasks": size_of(data / "tasks"),
        "backups": size_of(data / "workspace_backups"),
        "browser_profile": max(0, size_of(data / "browser-profile")),
        "cache_catalog": sum(size_of(p) for p in cache.iterdir() if p.is_file())
        if cache.is_dir() else 0,
        "cache_updates": size_of(cache / "updates"),
        "cache_tmp": size_of(cache / "tmp"),
        "cache_browser": size_of(cache / "browser"),
    }
    parts["cache_total"] = sum(v for k, v in parts.items() if k.startswith("cache_"))
    parts["total"] = sum(v for k, v in parts.items()
                         if not k.startswith("cache_") or k == "cache_total")
    return parts


def clear_cache(data: Path) -> int:
    """« Vider le cache » : temporaires, mises à jour, cache web. Le catalogue (re-téléchargé
    au besoin) et toutes les données restent."""
    freed = 0
    for sub in ("tmp", "updates", "browser"):
        path = data / "cache" / sub
        freed += size_of(path)
        shutil.rmtree(path, ignore_errors=True)
        path.mkdir(parents=True, exist_ok=True)
    return freed
