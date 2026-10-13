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

Sous Linux, un serveur stdio est lancé dans un bac à sable bubblewrap (`bwrap`) s'il est
installé : système en lecture seule, dossier personnel et /run masqués (clés, trousseau,
D-Bus), seuls les dossiers passés en arguments restent accessibles. `sandbox: false`
le désactive pour un serveur.

Un outil MCP sans l'annotation `readOnlyHint` est considéré à effet de bord
et exige la confirmation de l'utilisateur.
"""

from __future__ import annotations

import functools
import logging
import os
import re
import shutil
import subprocess
from contextlib import AsyncExitStack, suppress
from pathlib import Path
from typing import Any

import yaml

from tontolo.agent.tools import Tool, ToolBox, untrusted

log = logging.getLogger(__name__)


def is_android() -> bool:
    return os.environ.get("TONTOLO_PLATFORM") == "android" or "ANDROID_ROOT" in os.environ


MAX_SERVERS = 20
MAX_TOOLS_PER_SERVER = 100
MAX_TOOL_OUTPUT = 100_000  # caractères renvoyés par un outil MCP
# Un serveur stdio lance un programme : jamais un interpréteur de commandes, une élévation de
# droits ni un outil destructeur ou réseau brut ; jamais de code passé en ligne de commande.
_DENIED = frozenset(" ".join((
    "sh bash zsh dash fish csh tcsh ksh ash busybox cmd cmd.exe powershell powershell.exe "
    "pwsh sudo su doas pkexec runas rm rmdir dd mkfs shred wipefs fdisk parted chmod chown "
    "chattr curl wget nc ncat netcat socat telnet ssh scp sftp rsync ftp eval exec kill "
    "killall pkill reboot shutdown halt poweroff systemctl crontab at mount umount iptables "
    "nft",
)).split())
_INLINE_CODE = frozenset({"-c", "-e", "--eval", "-p", "--print", "-r", "--command", "/c"})
_INTERPRETERS = re.compile(r"^(python[\d.]*|node|nodejs|perl|ruby|php|deno|bun|lua|osascript)"
                           r"(\.exe)?$")
_BAD_ENV = re.compile(r"^(LD_|DYLD_)|^(NODE_OPTIONS|PYTHONSTARTUP|PYTHONPATH|PERL5OPT|"
                      r"RUBYOPT|BASH_ENV|ENV|PATH)$")


def check_server(srv: dict[str, Any]) -> str | None:
    """Raison du refus d'une configuration de serveur MCP, ou None si elle est acceptable."""
    name = str(srv.get("name") or "")
    if not re.fullmatch(r"[\w .-]{1,40}", name):
        return "nom invalide (40 caractères au plus : lettres, chiffres, espace, . _ -)"
    transport = srv.get("transport", "http")
    if transport not in ("stdio", "http", "sse"):
        return "transport inconnu (stdio, http ou sse)"
    if transport == "stdio":
        cmd = srv.get("command")
        args = srv.get("args", [])
        env = srv.get("env") or {}
        if not isinstance(cmd, str) or not 1 <= len(cmd) <= 200 or re.search(r"[;&|`$<>\n\r]",
                                                                              cmd):
            return "commande invalide"
        base = re.split(r"[\\/]", cmd)[-1].lower()
        if base in _DENIED or base.removesuffix(".exe") in _DENIED:
            return f"commande refusée : {base}"
        if not isinstance(args, list) or len(args) > 50 or any(
                not isinstance(a, str) or len(a) > 500 for a in args):
            return "arguments invalides (50 au plus, 500 caractères chacun)"
        if not isinstance(srv.get("sandbox", True), bool):
            return "sandbox : vrai ou faux"
        if _INTERPRETERS.match(base) and any(a in _INLINE_CODE for a in args):
            return "code en ligne refusé (utilisez un module ou un fichier)"
        if not isinstance(env, dict) or len(env) > 20 or any(
                not isinstance(k, str) or _BAD_ENV.search(k) or not isinstance(v, str)
                or len(v) > 2000 for k, v in env.items()):
            return "variables d'environnement refusées"
        return None
    url = srv.get("url")
    if not isinstance(url, str) or not re.match(r"^https?://[^\s]{3,500}$", url):
        return "adresse http(s) requise"
    headers = srv.get("headers") or {}
    if not isinstance(headers, dict) or len(headers) > 20:
        return "en-têtes invalides"
    return None


# Outillage sous le dossier personnel laissé visible (lecture seule, sauf caches).
_HOME_TOOLCHAINS_RO = (".local/bin", ".local/share/uv", ".local/share/pnpm", ".nvm", ".volta",
                       ".bun", ".deno", ".cargo/bin", ".pyenv", ".asdf")
_HOME_CACHES_RW = (".npm", ".cache/uv", ".cache/pip", ".cache/deno")
_HOME_SECRET = re.compile(r"^\.(ssh|gnupg|password-store|pki|aws|kube|docker|config|mozilla|"
                          r"local/share/(keyrings|tontolo))(/|$)")


@functools.cache
def bwrap_usable() -> str | None:
    """Chemin de bwrap s'il est installé ET fonctionne (espaces de noms utilisateur)."""
    exe = shutil.which("bwrap")
    if not exe or is_android():
        return None
    try:
        ok = subprocess.run([exe, "--ro-bind", "/", "/", "--unshare-all", "--die-with-parent",
                             "true"], capture_output=True, timeout=5).returncode == 0
    except (OSError, subprocess.SubprocessError):
        ok = False
    return exe if ok else None


def sandbox_argv(bwrap: str, command: str, args: list[str], *, home: Path,
                 hide: tuple[Path, ...] = ()) -> list[str]:
    """Ligne de commande bwrap qui enveloppe `command args`."""
    home = home.resolve()
    argv = [bwrap, "--ro-bind", "/", "/", "--dev", "/dev", "--proc", "/proc",
            "--tmpfs", "/tmp", "--tmpfs", "/run", "--tmpfs", str(home)]
    for h in hide:  # dossier de données hors du dossier personnel
        if h.exists() and not h.resolve().is_relative_to(home):
            argv += ["--tmpfs", str(h.resolve())]

    def expose(path: Path, writable: bool) -> None:
        nonlocal argv
        if path.exists():
            argv += ["--bind" if writable else "--ro-bind", str(path), str(path)]

    for rel in _HOME_TOOLCHAINS_RO:
        expose(home / rel, False)
    for rel in _HOME_CACHES_RW:
        expose(home / rel, True)
    exe = shutil.which(command)
    if exe:  # programme installé ailleurs sous le dossier personnel : son dossier, en lecture
        target = Path(exe).resolve()
        if target.is_relative_to(home):
            parts = target.relative_to(home).parts
            if parts and not _HOME_SECRET.match("/".join(parts)):
                # ~/.nvm entier (bibliothèques voisines) ; dans ~/.local, son seul dossier
                expose(target.parent if parts[0] in (".local", ".cache") else home / parts[0],
                       False)
    for a in args:  # dossiers explicitement confiés au serveur (ex. serveur de fichiers)
        if a.startswith(("/", "~")):
            p = Path(a).expanduser()
            if p.exists() and p.resolve() != Path("/"):
                r = p.resolve()
                in_home = r.is_relative_to(home)
                if in_home and (r == home or _HOME_SECRET.match(
                        "/".join(r.relative_to(home).parts))):
                    continue  # jamais tout le dossier personnel ni un dossier de secrets
                if not in_home and r.parts[1] in ("run", "proc", "dev", "sys", "var"):
                    continue  # zones masquées ou système : jamais rouvertes
                if not any(r.is_relative_to(h.resolve()) for h in hide if h.exists()):
                    expose(r, True)
    return [*argv, "--unshare-all", "--share-net", "--die-with-parent", "--new-session",
            "--chdir", "/tmp", "--", command, *args]


def load_config(path: Path) -> list[dict[str, Any]]:
    """Serveurs configurés ; ceux qui ne passent pas `check_server` (fichier modifié à la
    main) sont ignorés, jamais lancés."""
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    servers = data.get("servers", []) if isinstance(data, dict) else []
    out = []
    for s in servers[:MAX_SERVERS]:
        if not isinstance(s, dict) or not s.get("name"):
            continue
        problem = check_server(s)
        if problem:
            log.warning("Serveur MCP %s ignoré : %s", s.get("name"), problem)
            continue
        out.append(s)
    return out


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
        client_session: Any
        try:
            from mcp import ClientSession as client_session
        except ImportError:
            client_session = None  # repli : client léger HTTP (Android)
        self._stack = AsyncExitStack()
        for srv in self.servers():
            if not srv.get("enabled", True):
                continue
            name = str(srv["name"])
            try:
                transport = srv.get("transport", "http")
                if client_session is None:
                    if transport == "stdio":
                        raise RuntimeError("transport stdio indisponible sans le SDK mcp")
                    from tontolo.agent.mcp_lite import LiteSession

                    session: Any = LiteSession(srv["url"], srv.get("headers"))
                    await session.initialize()
                    self._sessions[name] = session
                    for t in (await session.list_tools()).tools[:MAX_TOOLS_PER_SERVER]:
                        self.tools.append(self._wrap(name, session, t))
                    continue
                if transport == "stdio":
                    if is_android():
                        raise RuntimeError("transport stdio indisponible sous Android")
                    from mcp.client.stdio import StdioServerParameters, stdio_client

                    command, args = srv["command"], list(srv.get("args", []))
                    bwrap = bwrap_usable() if srv.get("sandbox", True) is not False else None
                    if bwrap:
                        command, *args = sandbox_argv(bwrap, command, args, home=Path.home(),
                                                      hide=(self.config_path.parent,))
                    elif srv.get("sandbox", True) is not False:
                        log.warning("Serveur MCP %s lancé sans bac à sable (bwrap absent)",
                                    name)
                    params = StdioServerParameters(command=command, args=args,
                                                   env=srv.get("env"))
                    read, write = await self._stack.enter_async_context(stdio_client(params))
                else:
                    from mcp.client.streamable_http import streamable_http_client

                    read, write = await self._stack.enter_async_context(
                        streamable_http_client(srv["url"]))
                session = await self._stack.enter_async_context(client_session(read, write))
                await session.initialize()
                self._sessions[name] = session
                listed = await session.list_tools()
                for t in listed.tools[:MAX_TOOLS_PER_SERVER]:
                    self.tools.append(self._wrap(name, session, t))
            except Exception as exc:  # un serveur en panne ne bloque pas les autres
                self.errors[name] = f"{type(exc).__name__}: {exc}"
                log.warning("Serveur MCP %s indisponible : %s", name, exc)

    def _wrap(self, server: str, session: Any, tool: Any) -> Tool:
        annotations = getattr(tool, "annotations", None)
        read_only = bool(_attr(annotations, "readOnlyHint", "read_only_hint"))

        async def call(args: dict[str, Any]) -> str:
            res = await session.call_tool(tool.name, args)
            parts = []
            for c in getattr(res, "content", []) or []:
                text = getattr(c, "text", None)
                parts.append(text if text is not None else f"[{getattr(c, 'type', 'contenu')}]")
            out = "\n".join(parts) or str(
                _attr(res, "structuredContent", "structured_content") or "")
            if _attr(res, "isError", "is_error"):
                out = "Erreur : " + out
            if len(out) > MAX_TOOL_OUTPUT:
                out = out[:MAX_TOOL_OUTPUT] + "\n[… sortie tronquée]"
            return untrusted(out)

        safe = "".join(ch if ch.isalnum() or ch in "_-" else "_" for ch in tool.name)
        return Tool(
            name=f"mcp__{server}__{safe}"[:64],
            description=(tool.description or tool.name)[:1000],
            parameters=_attr(tool, "inputSchema", "input_schema")
            or {"type": "object", "properties": {}},
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


def _attr(obj: Any, *names: str) -> Any:
    """Compatibilité entre versions du SDK (camelCase 1.x, snake_case 2.x)."""
    for n in names:
        if obj is not None and (v := getattr(obj, n, None)) is not None:
            return v
    return None
