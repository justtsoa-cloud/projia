"""Webapp statique : servie par le même serveur FastAPI (même origine, pas de CORS),
montée en dernier pour ne jamais avaler les routes `/projia/*` ou `/v1/*`."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from projia.catalog.service import CatalogService
from projia.config import Settings
from projia.providers.fake import FakeProvider
from projia.providers.registry import ProviderRegistry
from projia.server.app import create_app


@pytest.fixture
def client(settings: Settings, catalog_service: CatalogService, fake: FakeProvider,
           monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    async def fake_load(self: CatalogService) -> Any:
        self.catalog = catalog_service.catalog
        return self.catalog

    monkeypatch.setattr(CatalogService, "load", fake_load)
    app = create_app(settings, registry=ProviderRegistry(lambda p: fake), refresh=False)
    with TestClient(app, base_url="http://127.0.0.1") as c:
        yield c


def test_index_served(client: TestClient) -> None:
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert '<script type="module" src="/js/app.js">' in resp.text


def test_static_assets_served(client: TestClient) -> None:
    for path, content_type in (
        ("/js/app.js", "javascript"),
        ("/css/base.css", "text/css"),
        ("/assets/icon.svg", "svg"),
    ):
        resp = client.get(path)
        assert resp.status_code == 200, path
        assert content_type in resp.headers["content-type"]


def test_api_routes_not_shadowed_by_static_mount(client: TestClient) -> None:
    resp = client.get("/projia/health")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/json")


def test_token_required_app_still_serves_shell_but_not_api(
    settings: Settings, catalog_service: CatalogService, fake: FakeProvider,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_load(self: CatalogService) -> Any:
        self.catalog = catalog_service.catalog
        return self.catalog

    monkeypatch.setattr(CatalogService, "load", fake_load)
    settings.server.token = "s3cret"
    app = create_app(settings, registry=ProviderRegistry(lambda p: fake), refresh=False)
    with TestClient(app, base_url="http://127.0.0.1") as c:
        # La coquille (GET, lecture seule) reste joignable sans jeton...
        assert c.get("/").status_code == 200
        assert c.get("/js/app.js").status_code == 200
        # ...mais toute route API reste protégée normalement.
        assert c.get("/projia/health").status_code == 401
        auth = {"Authorization": "Bearer s3cret"}
        assert c.get("/projia/health", headers=auth).status_code == 200
