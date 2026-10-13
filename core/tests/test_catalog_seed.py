"""Premier lancement hors ligne : le catalogue de secours embarqué évite un écran vide."""

from __future__ import annotations

import copy
from typing import Any

import pytest

from tontolo.catalog.service import CatalogService
from tontolo.config import Settings


async def test_offline_first_launch_uses_seed(settings: Settings,
                                              monkeypatch: pytest.MonkeyPatch) -> None:
    svc = CatalogService(settings)

    async def no_network(*a: Any, **kw: Any) -> list[dict[str, Any]]:
        return []  # ni cache ni réseau

    monkeypatch.setattr(svc, "_build", no_network)
    monkeypatch.setattr(svc, "refresh_in_background", lambda: None)
    cat = await svc.load()
    remote = [m for m in cat.models.values() if m.provider not in ("local", "hf_spaces")]
    assert len(remote) >= 20
    assert all(cat.providers[m.provider].get("keyless") for m in remote)
    assert all(m.is_free for m in remote)


async def test_seed_does_not_override_downloaded(settings: Settings) -> None:
    svc = CatalogService(settings)
    svc._load_seed()
    key = next(iter(svc.catalog.models))
    before = svc.catalog.models[key] = copy.copy(svc.catalog.models[key])
    svc._load_seed()
    assert svc.catalog.models[key] is before
