"""Client MCP minimal (transport Streamable HTTP) en `httpx` pur, pour Android.

Le SDK officiel `mcp` tire cryptography, jsonschema et opentelemetry (≈ 14 Mo
par ABI) : sous Android, où seul le transport HTTP est possible, ce client
léger implémente le strict nécessaire du protocole (initialize, tools/list,
tools/call) avec la même interface que la session du SDK.
"""

from __future__ import annotations

import itertools
import json
from dataclasses import dataclass, field
from typing import Any

from projia import __version__, http

PROTOCOL_VERSION = "2025-06-18"


@dataclass
class LiteTool:
    name: str
    description: str | None
    inputSchema: dict[str, Any]
    annotations: Any = None


@dataclass
class LiteContent:
    type: str
    text: str | None = None


@dataclass
class LiteResult:
    content: list[LiteContent] = field(default_factory=list)
    isError: bool = False
    structuredContent: Any = None


@dataclass
class _Annotations:
    readOnlyHint: bool = False


class LiteSession:
    def __init__(self, url: str, headers: dict[str, str] | None = None) -> None:
        self.url = url
        self.headers = dict(headers or {})
        self.session_id: str | None = None
        self._ids = itertools.count(1)

    async def _rpc(self, method: str, params: dict[str, Any] | None = None,
                   notify: bool = False) -> dict[str, Any]:
        msg: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            msg["params"] = params
        rid = None
        if not notify:
            rid = next(self._ids)
            msg["id"] = rid
        headers = {"Content-Type": "application/json",
                   "Accept": "application/json, text/event-stream",
                   "MCP-Protocol-Version": PROTOCOL_VERSION, **self.headers}
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        resp = await http.client().post(self.url, json=msg, headers=headers, timeout=60)
        if sid := resp.headers.get("mcp-session-id"):
            self.session_id = sid
        if notify:
            return {}
        resp.raise_for_status()
        if "text/event-stream" in resp.headers.get("content-type", ""):
            for line in resp.text.splitlines():
                if line.startswith("data:"):
                    data = json.loads(line[5:])
                    if data.get("id") == rid:
                        return _result(data)
            raise RuntimeError("Réponse MCP absente du flux")
        return _result(resp.json())

    async def initialize(self) -> dict[str, Any]:
        res = await self._rpc("initialize", {
            "protocolVersion": PROTOCOL_VERSION, "capabilities": {},
            "clientInfo": {"name": "projia", "version": __version__}})
        await self._rpc("notifications/initialized", notify=True)
        return res

    async def list_tools(self) -> Any:
        res = await self._rpc("tools/list", {})
        tools = []
        for t in res.get("tools", []):
            ann = t.get("annotations") or {}
            tools.append(LiteTool(t["name"], t.get("description"),
                                  t.get("inputSchema") or {"type": "object"},
                                  _Annotations(bool(ann.get("readOnlyHint")))))
        return type("ListToolsResult", (), {"tools": tools})()

    async def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> LiteResult:
        res = await self._rpc("tools/call", {"name": name, "arguments": arguments or {}})
        return LiteResult([LiteContent(c.get("type", "text"), c.get("text"))
                           for c in res.get("content", [])],
                          bool(res.get("isError")), res.get("structuredContent"))


def _result(data: dict[str, Any]) -> dict[str, Any]:
    if "error" in data:
        raise RuntimeError(f"Erreur MCP : {data['error'].get('message')}")
    result: dict[str, Any] = data.get("result") or {}
    return result
