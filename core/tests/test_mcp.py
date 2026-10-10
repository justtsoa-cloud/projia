"""Client MCP : SDK officiel et client léger Android contre un vrai serveur Streamable HTTP."""

from __future__ import annotations

import socket
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
import uvicorn

from tontolo.agent.mcp_client import McpManager, save_config
from tontolo.agent.mcp_lite import LiteSession
from tontolo.agent.tools import ToolBox

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
