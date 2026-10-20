"""Banc d'essai du cœur : Core complet (base SQLite réelle sur disque) avec fournisseur simulé.
Utilisé par les scripts de `bench/` (endurance, charge, robustesse). Non lancé par la CI."""

from __future__ import annotations

import os
import resource
import sys
import tempfile
import time
import tracemalloc
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

os.environ.setdefault("PROJIA_NO_KEYRING", "1")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from projia.app_state import Core
from projia.catalog.catalog import Catalog
from projia.catalog.service import CatalogService
from projia.config import Settings
from projia.providers.fake import FakeProvider
from projia.providers.registry import ProviderRegistry
from tests.conftest import make_models


def rss_mb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024


class Timer:
    def __init__(self) -> None:
        self.rows: list[tuple[str, float]] = []

    def __call__(self, name: str) -> Any:
        outer = self

        class _Ctx:
            def __enter__(self) -> None:
                self.t = time.perf_counter()

            def __exit__(self, *exc: object) -> None:
                outer.rows.append((name, time.perf_counter() - self.t))

        return _Ctx()

    def report(self) -> None:
        for name, sec in self.rows:
            print(f"  {name:<55} {sec * 1000:9.1f} ms")


@asynccontextmanager
async def core(fake: FakeProvider | None = None, home: Path | None = None
               ) -> AsyncIterator[tuple[Core, FakeProvider, Path]]:
    fake = fake or FakeProvider()
    home = home or Path(tempfile.mkdtemp(prefix="projia-bench-"))
    previous_home = os.environ.get("PROJIA_HOME")
    previous_load = CatalogService.load
    os.environ["PROJIA_HOME"] = str(home)
    settings = Settings()
    svc = CatalogService(settings)
    cat = Catalog(providers={"fake": {"id": "fake", "name": "Fake", "base_url": "http://x",
                                      "keyless": True}})
    for m in make_models():
        cat.models[m.key] = m
    svc.catalog = cat

    async def fake_load(self: CatalogService) -> Any:
        self.catalog = cat
        return cat

    CatalogService.load = fake_load  # type: ignore[method-assign]
    c = await Core.start(settings, registry=ProviderRegistry(lambda p: fake), refresh=False)

    async def online() -> bool:
        return True

    c.router.probe = online  # type: ignore[method-assign]
    try:
        yield c, fake, home
    finally:
        await c.stop()
        # Rien ne déborde du banc (utilisé aussi par les tests de performance de la CI).
        CatalogService.load = previous_load  # type: ignore[method-assign]
        if previous_home is None:
            os.environ.pop("PROJIA_HOME", None)
        else:
            os.environ["PROJIA_HOME"] = previous_home


async def drain(gen: AsyncIterator[dict[str, Any]]) -> list[dict[str, Any]]:
    return [ev async for ev in gen]


__all__ = ["Timer", "core", "drain", "rss_mb", "tracemalloc"]
