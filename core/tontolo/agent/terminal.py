"""Terminal du bureau (Linux), tenu par le cœur : UNE session par discussion (jamais un onglet
par commande), ouverte dans le dossier de travail.

- L'application l'affiche en direct (WebSocket) et l'utilisateur peut y taper.
- L'agent peut LIRE ce qui s'y trouve (`terminal_read`), y taper du texte pour un programme
  interactif (`terminal_send`, après confirmation), et ses commandes `run_command` y sont
  recopiées avec leur sortie : tout ce que fait l'agent est visible.
"""

from __future__ import annotations

import asyncio
import contextlib
import fcntl
import os
import re
import signal
import struct
import termios
import time
import warnings
from pathlib import Path
from typing import Any

MAX_SESSIONS = 6
BUFFER = 256 * 1024
_ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(\x07|\x1b\\)|\x1b[@-Z\\-_]|\r")


class TermSession:
    def __init__(self, cwd: Path, shell: str | None = None) -> None:
        self.cwd = cwd
        self.buffer = bytearray()
        self.listeners: set[asyncio.Queue[bytes]] = set()
        self.used = time.time()
        shell = shell or os.environ.get("SHELL") or "/bin/bash"
        env = {k: v for k, v in os.environ.items()
               if not re.search(r"KEY|TOKEN|SECRET|PASSWORD", k, re.I)}
        env.update(TERM="xterm-256color", TONTOLO_TERMINAL="1")
        with warnings.catch_warnings():  # fork suivi immédiatement d'un exec
            warnings.simplefilter("ignore", DeprecationWarning)
            import pty

            pid, fd = pty.fork()
        if pid == 0:  # enfant : le shell dans le dossier de travail
            try:
                os.chdir(cwd)
                os.execvpe(shell, [shell, "-i"], env)
            finally:
                os._exit(127)
        self.pid, self.fd = pid, fd
        os.set_blocking(fd, False)
        self.alive = True
        asyncio.get_running_loop().add_reader(fd, self._on_read)

    def _on_read(self) -> None:
        try:
            data = os.read(self.fd, 65536)
        except OSError:
            data = b""
        if not data:
            self._ended()
            return
        self._push(data)

    def _push(self, data: bytes) -> None:
        self.buffer += data
        if len(self.buffer) > BUFFER:
            del self.buffer[:len(self.buffer) - BUFFER]
        for q in list(self.listeners):
            q.put_nowait(data)

    def _ended(self) -> None:
        if not self.alive:
            return
        self.alive = False
        with contextlib.suppress(Exception):
            asyncio.get_running_loop().remove_reader(self.fd)
        self._push(b"\r\n[session terminee]\r\n")
        self._reap()

    def _reap(self) -> None:
        """Récolte le processus fils (jamais de zombie) ; il est arrêté de force au besoin."""
        pid = self.pid

        def wait() -> None:
            for _ in range(50):
                try:
                    done, _ = os.waitpid(pid, os.WNOHANG)
                except ChildProcessError:
                    return
                if done:
                    return
                time.sleep(0.1)
            with contextlib.suppress(ProcessLookupError):
                os.kill(pid, signal.SIGKILL)
            with contextlib.suppress(ChildProcessError):
                os.waitpid(pid, 0)

        with contextlib.suppress(RuntimeError):
            asyncio.get_running_loop().run_in_executor(None, wait)

    def write(self, data: bytes) -> None:
        if self.alive:
            self.used = time.time()
            with contextlib.suppress(OSError):
                os.write(self.fd, data)

    def resize(self, rows: int, cols: int) -> None:
        if self.alive and 0 < rows < 1000 and 0 < cols < 1000:
            with contextlib.suppress(OSError):
                fcntl.ioctl(self.fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))

    def mirror(self, command: str, output: str) -> None:
        """Commande lancée par l'agent (hors de la session) : recopiée pour être visible."""
        text = output.replace("\r\n", "\n").replace("\n", "\r\n")
        self._push(f"\r\n\x1b[36m[agent] $ {command}\x1b[0m\r\n{text}\r\n".encode())

    def text(self, lines: int = 80) -> str:
        plain = _ANSI.sub("", self.buffer.decode("utf-8", "replace"))
        plain = re.sub(r"[^\n\t -~ -￿]", "", plain)
        return "\n".join(plain.splitlines()[-max(1, min(lines, 400)):])

    def close(self) -> None:
        if self.alive:
            with contextlib.suppress(ProcessLookupError):
                os.kill(self.pid, signal.SIGHUP)
            self._ended()
        with contextlib.suppress(OSError):
            os.close(self.fd)


class TerminalManager:
    def __init__(self) -> None:
        self.sessions: dict[str, TermSession] = {}

    def get(self, cid: str, cwd: Path) -> TermSession:
        s = self.sessions.get(cid)
        if s is not None and s.alive:
            s.used = time.time()
            return s
        if s is not None:
            s.close()
        if len(self.sessions) >= MAX_SESSIONS:
            oldest = min(self.sessions, key=lambda k: self.sessions[k].used)
            self.sessions.pop(oldest).close()
        s = TermSession(cwd)
        self.sessions[cid] = s
        return s

    def existing(self, cid: str) -> TermSession | None:
        s = self.sessions.get(cid)
        return s if s is not None and s.alive else None

    def close_all(self) -> None:
        for s in self.sessions.values():
            s.close()
        self.sessions.clear()

    def describe(self) -> list[dict[str, Any]]:
        return [{"conversation_id": k, "alive": s.alive, "cwd": str(s.cwd)}
                for k, s in self.sessions.items()]
