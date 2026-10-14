"""Terminal du bureau tenu par le cœur : une session par discussion, lisible par l'agent,
affichée par l'application (WebSocket locale uniquement)."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from tontolo.agent.terminal import TerminalManager
from tontolo.agent.workspace import is_desktop
from tontolo.catalog.service import CatalogService
from tontolo.config import Settings
from tontolo.providers.fake import FakeProvider
from tontolo.providers.registry import ProviderRegistry
from tontolo.server.app import create_app

pytestmark = pytest.mark.skipif(not is_desktop(), reason="terminal du bureau Linux")


async def _until(cond: Any, seconds: float = 5) -> None:
    for _ in range(int(seconds * 20)):
        if cond():
            return
        await asyncio.sleep(0.05)
    raise AssertionError("délai dépassé")


async def test_session_reads_and_mirrors(tmp_path: Path) -> None:
    terms = TerminalManager()
    s = terms.get("c1", tmp_path)
    try:
        assert terms.get("c1", tmp_path) is s  # réutilisée, pas une nouvelle par commande
        s.write(b"echo bonjour-$((40+2)) && pwd\n")
        await _until(lambda: "bonjour-42" in s.text())
        assert str(tmp_path) in s.text()
        s.mirror("ls", "a.txt\nb.txt")
        assert "[agent] $ ls" in s.text() and "b.txt" in s.text()
        assert "\x1b" not in s.text()  # séquences de couleurs retirées pour l'agent
    finally:
        terms.close_all()
    assert terms.sessions == {}


TOKEN = "jeton-de-test"


@pytest.fixture
def client(settings: Settings, catalog_service: CatalogService, fake: FakeProvider,
           monkeypatch: pytest.MonkeyPatch) -> Any:
    async def fake_load(self: CatalogService) -> Any:
        self.catalog = catalog_service.catalog
        return self.catalog

    monkeypatch.setattr(CatalogService, "load", fake_load)
    settings.server.token = TOKEN
    app = create_app(settings, registry=ProviderRegistry(lambda p: fake), refresh=False)
    with TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 5000),
                    headers={"authorization": f"Bearer {TOKEN}"}) as c:
        yield c


def _ws(cid: str, token: str | None = TOKEN) -> str:
    return f"/tontolo/terminal/{cid}/ws" + (f"?token={token}" if token else "")


def test_websocket_local_only(client: TestClient) -> None:
    with client.websocket_connect(_ws("abc")) as ws:
        ws.send_text(json.dumps({"resize": [30, 100]}))
        ws.send_text(json.dumps({"input": "echo depuis-l-app\n"}))
        seen = b""
        while b"depuis-l-app\r\n" not in seen.replace(b"echo depuis-l-app", b""):
            seen += ws.receive_bytes()
    core = client.app.state.core  # type: ignore[attr-defined]
    assert "depuis-l-app" in core.chat.terminals.existing("abc").text()
    for headers in ({"origin": "http://localhost:3000"}, {"origin": "https://evil.example"}):
        with pytest.raises(WebSocketDisconnect), client.websocket_connect(
                _ws("abc"), headers=headers) as ws:
            ws.receive_bytes()
    for bad in (_ws("..%2Fx"), _ws("abc", None), _ws("abc", "mauvais")):  # jeton obligatoire
        with pytest.raises(WebSocketDisconnect), client.websocket_connect(bad) as ws:
            ws.receive_bytes()


def test_remote_client_refused(settings: Settings) -> None:
    settings.server.token = TOKEN
    app = create_app(settings, refresh=False)
    with TestClient(app, base_url="http://127.0.0.1", client=("10.0.0.9", 1)) as c, \
            pytest.raises(WebSocketDisconnect), c.websocket_connect(_ws("abc")) as ws:
        ws.receive_bytes()


def test_no_token_no_shell(settings: Settings) -> None:
    app = create_app(settings, refresh=False)  # aucun jeton configuré
    with TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 5000)) as c, \
            pytest.raises(WebSocketDisconnect), c.websocket_connect(_ws("abc", None)) as ws:
        ws.receive_bytes()


async def test_child_is_reaped(tmp_path: Path) -> None:
    import os

    terms = TerminalManager()
    s = terms.get("c1", tmp_path)
    pid = s.pid
    terms.close_all()
    for _ in range(60):
        await asyncio.sleep(0.1)
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return  # récolté : plus de zombie
        except PermissionError:
            return
        try:
            Path(f"/proc/{pid}/stat").read_text()
        except OSError:
            return  # récolté entre-temps (course entre kill et lecture)
    raise AssertionError("processus fils non récolté")


def test_agent_reads_terminal_and_sees_its_commands(client: TestClient, fake: FakeProvider,
                                                    tmp_path: Path) -> None:
    core = client.app.state.core  # type: ignore[attr-defined]
    assert client.put("/tontolo/workspace", json={"path": str(tmp_path)}).status_code == 200
    (tmp_path / "notes.txt").write_text("x")
    state = {"n": 0}

    def act(model: Any, messages: list[dict[str, Any]]) -> dict[str, Any]:
        state["n"] += 1
        if state["n"] == 1:
            return {"role": "assistant", "content": "", "tool_calls": [
                {"id": "t1", "type": "function", "function": {
                    "name": "run_command", "arguments": json.dumps({"command": "ls"})}}]}
        if state["n"] == 2:
            return {"role": "assistant", "content": "", "tool_calls": [
                {"id": "t2", "type": "function", "function": {
                    "name": "terminal_read", "arguments": "{}"}}]}
        return {"role": "assistant", "content": "vu"}

    for mid in ("coder-pro", "chatty", "small", "vision-x", "paid-genius"):
        fake.behaviors[mid] = act

    def events(url: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
        with client.stream("POST", url, json=payload) as s:
            return [json.loads(x[5:]) for x in s.iter_lines() if x.startswith("data:")]

    ev = events("/tontolo/chat", {"content": "liste les fichiers", "mode": "agent"})
    conf = next(e for e in ev if e["type"] == "tool_confirmation")
    cid = conf["conversation_id"]
    ev = events(f"/tontolo/chat/{cid}/resume", {"approved": True})
    read = [e for e in ev if e["type"] == "tool_result" and e["name"] == "terminal_read"]
    assert read and "[agent] $ ls" in read[0]["preview"]
    assert "notes.txt" in core.chat.terminals.existing(cid).text()
    run = next(e for e in ev if e["type"] == "tool_result" and e["name"] == "run_command")
    assert "notes.txt" in run["output"]


def test_oversized_terminal_message_closes_the_socket(client: TestClient) -> None:
    from tontolo.server.common import TERM_MAX_MESSAGE

    with client.websocket_connect(_ws("gros")) as ws:
        ws.receive_bytes()
        ws.send_text(json.dumps({"input": "x" * (TERM_MAX_MESSAGE + 10)}))
        with pytest.raises(WebSocketDisconnect):
            for _ in range(50):
                ws.receive_bytes()


def test_rate_limiter() -> None:
    from tontolo.server.common import RateLimiter

    rl = RateLimiter(3, 60)
    assert [rl.allow("a") for _ in range(4)] == [True, True, True, False]
    assert rl.allow("b")  # une autre adresse n'est pas pénalisée
