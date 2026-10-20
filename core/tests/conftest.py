"""Fixtures communes : catalogue simulé, fournisseur simulé, base en mémoire."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

os.environ.setdefault("PROJIA_NO_KEYRING", "1")

from projia.catalog.catalog import Catalog
from projia.catalog.models import ModelInfo
from projia.catalog.service import CatalogService
from projia.config import Settings
from projia.providers.fake import FakeProvider
from projia.providers.registry import ProviderRegistry
from projia.router.engine import Router
from projia.storage.db import Database

FIXTURES = Path(__file__).parent / "fixtures"


def make_models() -> list[ModelInfo]:
    def m(mid: str, **kw: object) -> ModelInfo:
        base: dict[str, object] = dict(provider="fake", model_id=mid, name=mid, is_free=True,
                                       needs_key=False, context_length=128_000,
                                       supports_tools=True)
        base.update(kw)
        return ModelInfo(**base)  # type: ignore[arg-type]

    return [
        m("coder-pro", quality={"code": 0.92, "chat": 0.60, "math": 0.5, "search": 0.6}),
        m("chatty", quality={"code": 0.40, "chat": 0.85, "math": 0.4, "search": 0.7}),
        m("small", quality={"code": 0.20, "chat": 0.30, "math": 0.2, "search": 0.3},
          context_length=4096, supports_tools=False),
        m("vision-x", quality={"vision": 0.8, "chat": 0.5, "code": 0.3},
          input_modalities=["text", "image"]),
        m("paid-genius", is_free=False, price_in=1e-6, price_out=4e-6,
          quality={"code": 0.99, "chat": 0.99, "math": 0.99}),
        m("img-1", input_modalities=["text"], output_modalities=["image"], media=["image_gen"],
          quality={"image_gen": 0.7}, supports_tools=False),
    ]


@pytest.fixture
def tmp_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("PROJIA_HOME", str(tmp_path))
    return tmp_path


@pytest.fixture
def settings(tmp_home: Path) -> Settings:
    return Settings()


@pytest.fixture
def fake() -> FakeProvider:
    return FakeProvider()


@pytest.fixture
def catalog_service(settings: Settings) -> CatalogService:
    svc = CatalogService(settings)
    cat = Catalog(providers={"fake": {"id": "fake", "name": "Fake", "base_url": "http://x",
                                      "keyless": True}})
    for model in make_models():
        cat.models[model.key] = model
    svc.catalog = cat
    return svc


@pytest.fixture
async def db() -> AsyncIterator[Database]:
    database = await Database(":memory:").open()
    yield database
    await database.close()


@pytest.fixture
async def router(settings: Settings, catalog_service: CatalogService, db: Database,
                 fake: FakeProvider) -> Router:
    r = Router(settings, catalog_service, db, registry=ProviderRegistry(lambda p: fake))
    await r.startup()

    async def online() -> bool:
        return True

    r.probe = online  # pas de vrai réseau dans les tests
    return r
