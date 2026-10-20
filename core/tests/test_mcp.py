"""Client MCP : SDK officiel et client léger Android contre un vrai serveur Streamable HTTP."""

from __future__ import annotations

import socket
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
import uvicorn

from projia.agent.mcp_client import McpManager, save_config
from projia.agent.mcp_lite import LiteSession
from projia.agent.tools import ToolBox
from projia.config import Settings

pytest.importorskip("mcp")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture(scope="module")
def mcp_url() -> Iterator[str]:
    from mcp.server.mcpserver import MCPServer

    server = MCPServer("demo")

    @server.tool()
    def add(a: int, b: int) -> int:
        """Additionne deux entiers."""
        return a + b

    port = _free_port()
    app = server.streamable_http_app()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    srv = uvicorn.Server(config)
    t = threading.Thread(target=srv.run, daemon=True)
    t.start()
    for _ in range(100):
        if srv.started:
            break
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}/mcp"
    srv.should_exit = True
    t.join(timeout=5)


async def test_lite_client(mcp_url: str) -> None:
    s = LiteSession(mcp_url)
    await s.initialize()
    tools = (await s.list_tools()).tools
    assert [t.name for t in tools] == ["add"]
    res = await s.call_tool("add", {"a": 2, "b": 3})
    assert not res.isError and res.content[0].text == "5"


async def test_manager_sdk(mcp_url: str, tmp_path: Path) -> None:
    cfg = tmp_path / "mcp_servers.yaml"
    save_config(cfg, [{"name": "demo", "transport": "http", "url": mcp_url}])
    mgr = McpManager(cfg)
    await mgr.connect()
    assert not mgr.errors
    box = ToolBox()
    mgr.merge_into(box)
    tool = box.tools["mcp__demo__add"]
    assert tool.side_effect  # pas d'annotation readOnlyHint → confirmation requise
    out = await box.call("mcp__demo__add", '{"a": 4, "b": 5}')
    assert "9" in out and "NON FIABLES" in out
    await mgr.close()


async def test_manager_lite_fallback(mcp_url: str, tmp_path: Path,
                                     monkeypatch: pytest.MonkeyPatch) -> None:
    import sys

    monkeypatch.setitem(sys.modules, "mcp", None)  # simule l'absence du SDK (Android)
    cfg = tmp_path / "mcp_servers.yaml"
    save_config(cfg, [{"name": "demo", "transport": "http", "url": mcp_url},
                      {"name": "local", "transport": "stdio", "command": "x"}])
    mgr = McpManager(cfg)
    await mgr.connect()
    assert "local" in mgr.errors and "demo" not in mgr.errors
    box = ToolBox()
    mgr.merge_into(box)
    assert "9" in await box.call("mcp__demo__add", {"a": 4, "b": 5})
    await mgr.close()


def test_dangerous_mcp_servers_are_refused() -> None:
    from projia.agent.mcp_client import check_server

    ok = [
        {"name": "fichiers", "transport": "stdio", "command": "npx",
         "args": ["-y", "@modelcontextprotocol/server-filesystem", "/home/moi/Documents"]},
        {"name": "outils py", "transport": "stdio", "command": "python3", "args": ["-m", "srv"]},
        {"name": "web", "transport": "http", "url": "https://mcp.example.com/mcp"},
    ]
    bad = [
        {"name": "x", "transport": "stdio", "command": "bash", "args": ["-c", "rm -rf ~"]},
        {"name": "x", "transport": "stdio", "command": "/usr/bin/sudo", "args": ["npx"]},
        {"name": "x", "transport": "stdio", "command": "python3", "args": ["-c", "import os"]},
        {"name": "x", "transport": "stdio", "command": "node", "args": ["-e", "1"]},
        {"name": "x", "transport": "stdio", "command": "npx; rm -rf /"},
        {"name": "x", "transport": "stdio", "command": "npx", "env": {"LD_PRELOAD": "/tmp/x.so"}},
        {"name": "x", "transport": "stdio", "command": "cmd.exe", "args": ["/c", "del"]},
        {"name": "x", "transport": "ftp", "url": "ftp://x"},
        {"name": "../etc", "transport": "http", "url": "https://x.example"},
        {"name": "x", "transport": "stdio", "command": "npx", "args": ["a"] * 60},
    ]
    assert all(check_server(s) is None for s in ok)
    assert all(check_server(s) for s in bad)


def test_mcp_endpoint_limits(settings: Settings, tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from projia.server.app import create_app

    app = create_app(settings, refresh=False)
    with TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 5000)) as c:
        r = c.put("/projia/mcp", json={"servers": [
            {"name": "x", "transport": "stdio", "command": "bash", "args": ["-c", "id"]}]})
        assert r.status_code == 400 and "refusée" in r.text
        assert c.put("/projia/mcp", content=b"{" + b" " * 70_000 + b"}").status_code == 413
        assert c.put("/projia/mcp", json={"servers": [
            {"name": f"s{i}", "url": "https://x.example"} for i in range(25)]}).status_code == 400
    with TestClient(app, base_url="http://127.0.0.1", client=("10.0.0.5", 1)) as remote:
        r = remote.put("/projia/mcp", json={"servers": [
            {"name": "interne", "transport": "http", "url": "http://127.0.0.1:9000/mcp"}]})
        assert r.status_code == 403  # pas d'accès au réseau interne depuis un autre appareil


def test_stdio_sandbox_hides_home(tmp_path: Path) -> None:
    import shutil
    import subprocess

    from projia.agent.mcp_client import bwrap_usable, check_server, sandbox_argv

    assert check_server({"name": "x", "transport": "stdio", "command": "npx",
                         "sandbox": "non"}) is not None
    home = tmp_path / "home"
    (home / ".ssh").mkdir(parents=True)
    (home / ".ssh" / "id_ed25519").write_text("SECRET")
    (home / ".local" / "share" / "projia").mkdir(parents=True)
    docs = home / "Documents"
    docs.mkdir()
    (docs / "cours.md").write_text("ok")
    ls = shutil.which("ls") or "/usr/bin/ls"
    argv = sandbox_argv("bwrap", ls, [str(docs), str(home), str(home / ".ssh")], home=home)
    binds = [argv[i + 1] for i, a in enumerate(argv) if a in ("--bind", "--ro-bind")]
    assert str(docs.resolve()) in binds
    assert str(home.resolve()) not in binds and str((home / ".ssh").resolve()) not in binds
    assert argv[argv.index("--") + 1:] == [ls, str(docs), str(home), str(home / ".ssh")]
    bwrap = bwrap_usable()
    if not bwrap:
        return
    argv = sandbox_argv(bwrap, ls, ["-a", str(docs)], home=home)
    out = subprocess.run(argv, capture_output=True, text=True, timeout=10)
    assert out.returncode == 0 and "cours.md" in out.stdout
    cat = shutil.which("cat") or "/usr/bin/cat"
    out = subprocess.run(sandbox_argv(bwrap, cat, [str(home / ".ssh" / "id_ed25519")],
                                      home=home), capture_output=True, text=True, timeout=10)
    assert out.returncode != 0 and "SECRET" not in out.stdout
    out = subprocess.run(sandbox_argv(bwrap, ls, ["/run"], home=home), capture_output=True,
                         text=True, timeout=10)
    assert out.stdout.strip() == ""  # trousseau, D-Bus : masqués
