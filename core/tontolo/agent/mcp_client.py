"""Client MCP (SDK officiel `mcp`) : outils des serveurs fusionnés avec les outils natifs.

Configuration : `mcp_servers.yaml` dans le dossier de données ::

    servers:
      - name: docs
        transport: http            # Streamable HTTP (seul transport sous Android)
        url: https://exemple.org/mcp
        enabled: true
      - name: fichiers
        transport: stdio           # Linux uniquement : lance un processus local
        command: npx
        args: ["-y", "@modelcontextprotocol/server-filesystem", "/home/moi/Documents"]
        enabled: false

Un outil MCP sans l'annotation `readOnlyHint` est considéré à effet de bord
et exige la confirmation de l'utilisateur.
"""

from __future__ import annotations

import logging
import os
from contextlib import AsyncExitStack, suppress
from pathlib import Path
from typing import Any

import yaml

from tontolo.agent.tools import Tool, ToolBox, untrusted

log = logging.getLogger(__name__)


def is_android() -> bool:
    return os.environ.get("TONTOLO_PLATFORM") == "android" or "ANDROID_ROOT" in os.environ


def load_config(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    servers = data.get("servers", []) if isinstance(data, dict) else []
    return [s for s in servers if isinstance(s, dict) and s.get("name")]


def save_config(path: Path, servers: list[dict[str, Any]]) -> None:
    path.write_text(yaml.safe_dump({"servers": servers}, allow_unicode=True, sort_keys=False),
                    encoding="utf-8")


class McpManager:
    def __init__(self, config_path: Path) -> None:
        self.config_path = config_path
        self._stack: AsyncExitStack | None = None
        self._sessions: dict[str, Any] = {}
        self.tools: list[Tool] = []
        self.errors: dict[str, str] = {}

    def servers(self) -> list[dict[str, Any]]:
        return load_config(self.config_path)

    async def connect(self) -> None:
        """Connexion paresseuse à tous les serveurs activés (appelée au premier besoin)."""
        if self._stack is not None:
            return
        try:
            from mcp import ClientSession
        except ImportError:
            log.info("SDK mcp absent : outils MCP désactivés")
            self._stack = AsyncExitStack()
            return
        self._stack = AsyncExitStack()
        for srv in self.servers():
            if not srv.get("enabled", True):
                continue
            name = str(srv["name"])
            try:
                transport = srv.get("transport", "http")
                if transport == "stdio":
                    if is_android():
                        raise RuntimeError("transport stdio indisponible sous Android")
                    from mcp.client.stdio import StdioServerParameters, stdio_client

                    params = StdioServerParameters(command=srv["command"],
                                                   args=list(srv.get("args", [])),
                                                   env=srv.get("env"))
                    read, write = await self._stack.enter_async_context(stdio_client(params))
                else:
                    from mcp.client.streamable_http import streamable_http_client

                    read, write = await self._stack.enter_async_context(
                        streamable_http_client(srv["url"]))
                session = await self._stack.enter_async_context(ClientSession(read, write))
                await session.initialize()
                self._sessions[name] = session
                listed = await session.list_tools()
                for t in listed.tools:
                    self.tools.append(self._wrap(name, session, t))
            except Exception as exc:  # un serveur en panne ne bloque pas les autres
                self.errors[name] = f"{type(exc).__name__}: {exc}"
                log.warning("Serveur MCP %s indisponible : %s", name, exc)

    def _wrap(self, server: str, session: Any, tool: Any) -> Tool:
        annotations = getattr(tool, "annotations", None)
        read_only = bool(getattr(annotations, "readOnlyHint", False)) if annotations else False

        async def call(args: dict[str, Any]) -> str:
            res = await session.call_tool(tool.name, args)
            parts = []
            for c in getattr(res, "content", []) or []:
                text = getattr(c, "text", None)
                parts.append(text if text is not None else f"[{getattr(c, 'type', 'contenu')}]")
            out = "\n".join(parts) or str(getattr(res, "structuredContent", "") or "")
            if getattr(res, "isError", False):
                out = "Erreur : " + out
            return untrusted(out)

        safe = "".join(ch if ch.isalnum() or ch in "_-" else "_" for ch in tool.name)
        return Tool(
            name=f"mcp__{server}__{safe}"[:64],
            description=(tool.description or tool.name)[:1000],
            parameters=tool.inputSchema or {"type": "object", "properties": {}},
            func=call, side_effect=not read_only, source=f"mcp:{server}",
        )

    def merge_into(self, box: ToolBox) -> None:
        for t in self.tools:
            box.add(t)

    async def close(self) -> None:
        if self._stack is not None:
            with suppress(Exception):
                await self._stack.aclose()
        self._stack = None
        self._sessions.clear()
        self.tools.clear()
