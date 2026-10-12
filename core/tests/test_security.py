"""Audit de sécurité : protections vérifiées par des tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tontolo.agent.tools import calculator, file_tools, safe_get
from tontolo.catalog.service import CatalogService
from tontolo.config import Settings
from tontolo.providers.fake import FakeProvider
from tontolo.providers.registry import ProviderRegistry
from tontolo.secrets import redact
from tontolo.security import ProviderPins, host_of, origin_allowed
from tontolo.server.app import create_app


@pytest.fixture
def client(settings: Settings, catalog_service: CatalogService, fake: FakeProvider,
           monkeypatch: pytest.MonkeyPatch) -> Any:
    async def fake_load(self: CatalogService) -> Any:
        self.catalog = catalog_service.catalog
        return self.catalog

    monkeypatch.setattr(CatalogService, "load", fake_load)
    app = create_app(settings, registry=ProviderRegistry(lambda p: fake), refresh=False)
    with TestClient(app, base_url="http://127.0.0.1") as c:
        yield c


def test_csrf_foreign_origin_rejected(client: TestClient) -> None:
    r = client.post("/tontolo/keys/openrouter", headers={"Origin": "https://evil.example"},
                    json={"key": "x"})
    assert r.status_code == 403
    assert client.get("/health", headers={"Origin": "http://localhost:3000"}).status_code == 200


def test_dns_rebinding_rejected(client: TestClient) -> None:
    assert client.get("/health", headers={"Host": "evil.example:8765"}).status_code == 403
    assert client.get("/health", headers={"Host": "127.0.0.1:8765"}).status_code == 200


def test_mcp_stdio_not_configurable_remotely(client: TestClient, settings: Settings) -> None:
    settings.server.host = "0.0.0.0"
    settings.server.token = "t"
    r = client.put("/tontolo/mcp", headers={"Authorization": "Bearer t"},
                   json={"servers": [{"name": "x", "transport": "stdio", "command": "rm"}]})
    assert r.status_code == 403


def test_helpers() -> None:
    assert host_of("[::1]:8765") == "::1" and host_of("localhost:1") == "localhost"
    assert origin_allowed(None) and not origin_allowed("null")
    assert "abcdefgh" not in redact("Bearer abcdefghijklmnop sk-or-v1-0123456789abcdef")


@pytest.mark.parametrize("url", [
    "http://127.0.0.1:8765/tontolo/keys", "http://localhost/", "http://169.254.169.254/latest",
    "http://10.0.0.1/", "http://[::1]/", "file:///etc/passwd", "ftp://example.org/",
])
async def test_ssrf_blocked(url: str) -> None:
    with pytest.raises(PermissionError):
        await safe_get(url)


def test_provider_pinning(tmp_path: Path) -> None:
    pins = ProviderPins(tmp_path / "pins.json")
    assert not pins.check("groq", "http://api.groq.com/openai/v1")      # HTTPS obligatoire
    assert pins.check("groq", "https://api.groq.com/openai/v1")          # 1re fois : épinglé
    assert pins.check("groq", "https://api.groq.com/other")
    assert not pins.check("groq", "https://evil.example/v1")             # hôte changé : refusé
    assert ProviderPins(tmp_path / "pins.json").check("groq", "https://api.groq.com/x")


async def test_calculator_rejects_code() -> None:
    assert "non autorisé" in await calculator({"expression": "__import__('os').system('id')"})
    assert "non autorisé" in await calculator({"expression": "().__class__"})
    assert "4" in await calculator({"expression": "2+2"})
    assert "trop longue" in await calculator({"expression": "1+" * 200 + "1"})


async def test_file_tools_confined(tmp_path: Path) -> None:
    work = tmp_path / "w"
    tools = {t.name: t for t in file_tools(work)}
    (tmp_path / "secret.txt").write_text("secret")
    (work / "lien").symlink_to(tmp_path / "secret.txt")
    for path in ("../secret.txt", "/etc/passwd", "lien"):
        with pytest.raises(PermissionError):
            await tools["read_file"].func({"path": path})


def test_latex_cannot_read_or_run_files() -> None:
    from tontolo.creator import book, bundle

    files = {"main.tex": "\\documentclass{x}\\input{/etc/passwd}"}
    _, missing = bundle.inline_tex(files, "main.tex")
    assert missing == ["/etc/passwd"]  # chemin hors projet : jamais lu
    from tontolo.creator.pipeline import latex_problems

    nasty = ["\\openin5=/etc/passwd", "\\read5 to \\x", "\\InputIfFileExists{/etc/passwd}{}{}",
             "\\verbatiminput{/etc/hosts}", "\\lstinputlisting{/etc/hosts}",
             "\\directlua{os.execute('id')}", "\\input{/etc/passwd}", "\\write18{id}"]
    for cmd in nasty:
        assert latex_problems(f"\\documentclass{{article}}\\begin{{document}}{cmd}\\end"
                              "{document}"), cmd
        if "\\input" not in cmd:  # \input vers le projet est légitime (résolu, jamais lu)
            assert bundle.problems({"a.tex": cmd}), cmd
        assert cmd.split("{")[0].split("=")[0].split(" ")[0] not in book.clean_chapter(
            f"\\chapter{{A}}\n{cmd}\n", "A")


def test_media_served_safely(client: TestClient, tmp_path: Path) -> None:
    from tontolo.server.app import safe_mime

    assert safe_mime("text/html") == "text/html" and safe_mime("<script>") == \
        "application/octet-stream"
    core = client.app.state.core  # type: ignore[attr-defined]
    page = core.media.dir / "page.html"
    page.write_text("<script>fetch('/tontolo/memory')</script>")

    async def make() -> None:
        await core.db.upsert_job({"id": "e" * 32, "kind": "file_gen", "status": "done",
                                  "params": {"mime": "text/html"}, "result_path": str(page)})

    client.portal.call(make)  # type: ignore[attr-defined]
    r = client.get("/tontolo/media/" + "e" * 32 + "/file")
    assert r.headers["content-type"].startswith("application/octet-stream")
    assert "attachment" in r.headers["content-disposition"]
    assert r.headers["x-content-type-options"] == "nosniff"
    assert "sandbox" in r.headers["content-security-policy"]
