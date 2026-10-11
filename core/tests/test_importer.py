"""Import d'une discussion d'un autre assistant (lien Claude/ChatGPT, JSON, texte collé)."""

from __future__ import annotations

import json
from typing import ClassVar

import pytest

from tontolo import importer
from tontolo.importer import ConversationImportError


def test_find_link() -> None:
    assert importer.find_link("continue https://claude.ai/share/04393426-e2c1-4fce-a779-"
                              "ad538512da66 stp") == (
        "claude", "https://claude.ai/share/04393426-e2c1-4fce-a779-ad538512da66")
    assert importer.find_link("https://chatgpt.com/share/67b32cae-0604-8000-b143-"
                              "de94ac59f082")[0] == "chatgpt"
    assert importer.find_link("https://gemini.google.com/share/07a336b9f81f")[0] == "gemini"
    assert importer.find_link("https://claude.ai/chat/04393426-e2c1-4fce-a779-"
                              "ad538512da66")[0] == "claude_private"
    assert importer.find_link("https://example.com/share/x") is None


def test_parse_claude_snapshot() -> None:
    snap = {"snapshot_name": "Container", "chat_messages": [
        {"sender": "human", "content": [{"type": "text", "text": "Bonjour"}]},
        {"sender": "assistant", "content": [{"type": "text", "text": "Salut"},
                                            {"type": "tool_use", "name": "x"},
                                            {"type": "text", "text": "!"}]},
        {"sender": "human", "text": "Et ensuite ?", "content": []}]}
    conv = importer.parse_any(json.dumps(snap))[0]
    assert conv.title == "Container" and conv.source == "claude"
    assert [m["role"] for m in conv.messages] == ["user", "assistant", "user"]
    assert conv.messages[1]["text"] == "Salut\n\n!"
    assert conv.messages[2]["text"] == "Et ensuite ?"


def _turbo(obj: object) -> list[object]:
    """Encodeur minimal du format turbo-stream (pour fabriquer une page de test)."""
    flat: list[object] = []

    def enc(v: object) -> int:
        i = len(flat)
        flat.append(None)
        if isinstance(v, dict):
            d = {}
            for k, x in v.items():
                ki = len(flat)
                flat.append(k)
                d[f"_{ki}"] = enc(x)
            flat[i] = d
        elif isinstance(v, list):
            flat[i] = [enc(x) for x in v]
        else:
            flat[i] = v
        return i

    enc(obj)
    return flat


def test_parse_chatgpt_page() -> None:
    data = {"loaderData": {"route": {"serverResponse": {"data": {
        "title": "RP2350", "linear_conversation": [
            {"message": {"author": {"role": "system"},
                         "content": {"content_type": "text", "parts": [""]}}},
            {"message": {"author": {"role": "user"},
                         "content": {"content_type": "text", "parts": ["SIMD ?"]}}},
            {"message": {"author": {"role": "tool"},
                         "content": {"content_type": "text", "parts": ["(caché)"]}}},
            {"message": {"author": {"role": "assistant"},
                         "content": {"content_type": "text", "parts": ["Oui."]}}}]}}}}}
    flat = json.dumps(_turbo(data))
    page = f"<script>window.__x.streamController.enqueue({json.dumps(flat)});</script>"
    conv = importer.parse_chatgpt_html(page)
    assert conv.title == "RP2350"
    assert conv.messages == [{"role": "user", "text": "SIMD ?"},
                             {"role": "assistant", "text": "Oui."}]


def test_parse_pasted_text() -> None:
    conv = importer.parse_any("You said:\nC'est quoi pi ?\nChatGPT said:\nEnviron 3,14.\n"
                              "Vous : merci\nClaude : De rien")[0]
    assert [m["role"] for m in conv.messages] == ["user", "assistant", "user", "assistant"]
    assert conv.messages[1]["text"] == "Environ 3,14."
    plain = importer.parse_any("Un texte sans locuteurs.")[0]
    assert plain.messages[0]["role"] == "user" and "sans locuteurs" in plain.messages[0]["text"]


def test_parse_message_list_and_empty() -> None:
    conv = importer.parse_any('[{"role":"user","content":"a"},{"role":"model","text":"b"}]')[0]
    assert [m["role"] for m in conv.messages] == ["user", "assistant"]
    with pytest.raises(ConversationImportError):
        importer.parse_any('{"chat_messages": []}')
    with pytest.raises(ConversationImportError):
        importer.parse_any("x" * (importer.MAX_DATA + 1))


async def test_fetch_private_and_browser(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ConversationImportError) as e:
        await importer.fetch("https://claude.ai/chat/04393426-e2c1-4fce-a779-ad538512da66")
    assert e.value.code == "import_private"
    with pytest.raises(ConversationImportError) as e:
        await importer.fetch("https://gemini.google.com/share/07a336b9f81f")
    assert e.value.code == "import_browser" and e.value.extra["extract"] == "script"

    class Resp:
        status_code = 403
        headers: ClassVar[dict[str, str]] = {"content-type": "text/html"}

    class Client:
        async def get(self, url: str, **_: object) -> Resp:
            assert url.startswith("https://claude.ai/api/chat_snapshots/04393426-")
            return Resp()

    monkeypatch.setattr(importer.http, "client", lambda: Client())
    with pytest.raises(ConversationImportError) as e:
        await importer.fetch("https://claude.ai/share/04393426-E2C1-4fce-a779-ad538512da66")
    assert e.value.code == "import_browser"
    assert e.value.extra["api_url"].endswith("render_all_tools=true")
