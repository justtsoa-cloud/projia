"""Mode avancé : plus de souplesse (fournisseurs personnalisés, enchaînements, exclusions,
délais, export / import) sans affaiblir la sécurité."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tontolo import secrets
from tontolo.catalog.models import Category
from tontolo.catalog.service import CatalogService
from tontolo.config import Settings
from tontolo.providers.fake import FakeProvider
from tontolo.providers.registry import ProviderRegistry
from tontolo.router.classifier import TaskProfile
from tontolo.router.engine import Router
from tontolo.router.scoring import rank
from tontolo.server import common as server
from tontolo.server.app import create_app


def _client(settings: Settings, catalog_service: CatalogService, fake: FakeProvider,
            monkeypatch: pytest.MonkeyPatch, host: str) -> Iterator[TestClient]:
    async def fake_load(self: CatalogService) -> Any:
        self.catalog = catalog_service.catalog
        return self.catalog

    async def no_refresh(self: CatalogService, force: bool = False) -> list[Any]:
        return []

    monkeypatch.setattr(CatalogService, "load", fake_load)
    monkeypatch.setattr(CatalogService, "refresh", no_refresh)
    app = create_app(settings, registry=ProviderRegistry(lambda p: fake), refresh=False)
    with TestClient(app, base_url="http://127.0.0.1", client=(host, 50000)) as c:
        yield c


@pytest.fixture
def local(settings: Settings, catalog_service: CatalogService, fake: FakeProvider,
          monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    yield from _client(settings, catalog_service, fake, monkeypatch, "127.0.0.1")


@pytest.fixture
def remote(settings: Settings, catalog_service: CatalogService, fake: FakeProvider,
           monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    yield from _client(settings, catalog_service, fake, monkeypatch, "10.0.0.7")


async def test_custom_provider_addresses() -> None:
    bad = {
        "ftp://x.example/v1": True, "https://user:pw@x.example/v1": True,
        "http://api.example.com/v1": False,          # HTTP public : jamais
        "http://192.168.1.20:1234/v1": True,         # HTTP local avec clé : jamais
        "https://169.254.169.254/latest": False,     # métadonnées cloud
        "http://metadata.google.internal/v1": False,
    }
    for url, key in bad.items():
        assert await server._custom_url_problem(url, key), url
    assert await server._custom_url_problem("https://api.example.com/v1", True) is None
    assert await server._custom_url_problem("http://192.168.1.20:1234/v1", False) is None
    assert await server._custom_url_problem("http://localhost:1234/v1", False) is None


def test_custom_provider_lifecycle(local: TestClient, settings: Settings,
                                   monkeypatch: pytest.MonkeyPatch) -> None:
    async def probe(cp: Any, key: str) -> int:
        return 4

    monkeypatch.setattr(server, "_custom_probe", probe)
    saved: dict[str, str] = {}
    monkeypatch.setattr(secrets, "set_key", lambda pid, v, persist=True: saved.update({pid: v}))
    monkeypatch.setattr(secrets, "delete_key", lambda pid: saved.pop(pid, None))
    r = local.post("/tontolo/custom-providers", json={
        "name": "Mon serveur", "base_url": "https://llm.example.org/v1/", "key": "sk-test"})
    assert r.status_code == 200 and r.json() == {"id": "custom-mon-serveur", "models": 4}
    assert saved == {"custom-mon-serveur": "sk-test"}
    assert settings.custom_providers[0].base_url == "https://llm.example.org/v1"
    # Payant sans prix : refusé (le plafond de dépense doit rester garanti).
    paid = local.post("/tontolo/custom-providers", json={
        "name": "Cher", "base_url": "https://pay.example.org/v1", "key": "k", "free": False})
    assert paid.status_code == 400 and "prix" in str(paid.json())
    # Jamais modifiable par le PUT générique (même en local) : seulement ici.
    local.put("/tontolo/settings", json={"custom_providers": []})
    assert len(settings.custom_providers) == 1
    exported = local.get("/tontolo/settings/export").json()
    assert "server" not in exported["settings"] and "sk-test" not in str(exported)
    assert local.delete("/tontolo/custom-providers/custom-mon-serveur").json() == {"ok": True}
    assert settings.custom_providers == [] and saved == {}


def test_remote_clients_cannot_add_providers_or_import(remote: TestClient) -> None:
    assert remote.post("/tontolo/custom-providers", json={
        "name": "x", "base_url": "https://x.example/v1", "key": "k"}).status_code == 403
    assert remote.post("/tontolo/settings/import", json={
        "tontolo_settings": 1, "settings": {}}).status_code == 403


def test_import_validates_everything(local: TestClient, settings: Settings) -> None:
    bad = local.post("/tontolo/settings/import", json={"tontolo_settings": 1, "settings": {
        "routing": {"stall_s": 5}}})  # hors bornes
    assert bad.status_code == 400
    evil = local.post("/tontolo/settings/import", json={"tontolo_settings": 1, "settings": {
        "custom_providers": [{"id": "custom-x", "name": "x",
                              "base_url": "http://evil.example.com/v1"}]}})
    assert evil.status_code == 400
    ok = local.post("/tontolo/settings/import", json={"tontolo_settings": 1, "settings": {
        "routing": {"stall_s": 45, "excluded_providers": ["fake2"]}, "server": {"port": 1}}})
    assert ok.status_code == 200 and settings.routing.stall_s == 45
    assert settings.server.port != 1  # jamais importé
    assert local.post("/tontolo/settings/import", json={"x": 1}).status_code == 400


def _first(router: Router, cat: Category = Category.CHAT) -> list[str]:
    dec = rank(router.catalog.catalog, TaskProfile(category=cat),
               usable=router.catalog.usable_providers(), quota=router.quota,
               reliability=router.reliability, settings=router.settings)
    return [c.model.model_id for c in dec.chain]


def test_chains_and_exclusions(router: Router, settings: Settings) -> None:
    auto = _first(router)
    assert len(auto) >= 2
    wanted = auto[-1]
    key = next(m.key for m in router.catalog.catalog.models.values() if m.model_id == wanted)
    settings.routing.chains = {"chat": [key, "fake:inexistant"]}
    assert _first(router)[0] == wanted  # l'enchaînement passe devant, l'inconnu est ignoré
    settings.routing.chains = {}
    provider = next(m.provider for m in router.catalog.catalog.models.values())
    settings.routing.excluded_providers = [provider]
    assert _first(router) == []  # tout venait de ce fournisseur : plus rien
    settings.routing.excluded_providers = []


def test_chains_are_bounded() -> None:
    s = Settings.model_validate({"routing": {"chains": {"chat": [f"m{i}" for i in range(50)]}}})
    assert len(s.routing.chains["chat"]) == 10
    with pytest.raises(ValueError):
        Settings.model_validate({"routing": {"think_s": 5000}})
