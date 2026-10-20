"""Veille des nouveautés (F9) : différences entre deux catalogues successifs."""

from __future__ import annotations

import time
from typing import Any

from projia.catalog.catalog import Catalog
from projia.catalog.models import Category

WATCHED_TOPS = (Category.CHAT, Category.CODE, Category.MATH, Category.IMAGE_GEN)


def diff(prev: dict[str, dict[str, Any]], new: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Compare deux instantanés (`Catalog.snapshot()`) et liste les changements."""
    ts = time.time()
    changes: list[dict[str, Any]] = []
    if not prev:
        return changes  # premier lancement : pas de « nouveautés » artificielles
    for key, cur in new.items():
        old = prev.get(key)
        if old is None:
            kind = "new_free" if cur["free"] else "new"
            changes.append({"ts": ts, "kind": kind, "model_id": key,
                            "detail": {"name": cur["name"]}})
            continue
        if old["free"] and not cur["free"]:
            changes.append({"ts": ts, "kind": "no_longer_free", "model_id": key,
                            "detail": {"name": cur["name"]}})
        elif not old["free"] and cur["free"]:
            changes.append({"ts": ts, "kind": "became_free", "model_id": key,
                            "detail": {"name": cur["name"]}})
        elif (old["price_in"], old["price_out"]) != (cur["price_in"], cur["price_out"]):
            changes.append({"ts": ts, "kind": "price_changed", "model_id": key,
                            "detail": {"name": cur["name"],
                                       "old": [old["price_in"], old["price_out"]],
                                       "new": [cur["price_in"], cur["price_out"]]}})
        caps_old = (old["tools"], old["ctx"], old["in"], old["out"])
        caps_new = (cur["tools"], cur["ctx"], cur["in"], cur["out"])
        if caps_old != caps_new:
            changes.append({"ts": ts, "kind": "capabilities_changed", "model_id": key,
                            "detail": {"name": cur["name"]}})
    for key, old in prev.items():
        if key not in new:
            changes.append({"ts": ts, "kind": "removed", "model_id": key,
                            "detail": {"name": old["name"]}})
    return changes


def top_free(catalog: Catalog, usable: set[str] | None = None) -> dict[str, str]:
    """N°1 gratuit par catégorie surveillée."""
    tops: dict[str, str] = {}
    for cat in WATCHED_TOPS:
        ranked = catalog.filter(category=cat, free_only=True, usable=usable)
        if ranked:
            tops[cat.value] = ranked[0].key
    return tops


def top_changes(prev: dict[str, str], new: dict[str, str]) -> list[dict[str, Any]]:
    ts = time.time()
    return [
        {"ts": ts, "kind": "new_top", "model_id": key, "detail": {"category": cat}}
        for cat, key in new.items() if prev and prev.get(cat) and prev.get(cat) != key
    ]
