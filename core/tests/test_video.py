"""Vidéo gratuite par Space Hugging Face (API Gradio simulée) et détection des demandes."""

from __future__ import annotations

import json
import struct
from typing import Any

import httpx
import pytest

from tontolo import http
from tontolo.catalog.models import Category
from tontolo.catalog.sources import hfspaces
from tontolo.media import providers as mp
from tontolo.providers.base import ErrorKind, ProviderError
from tontolo.router.classifier import classify

BASE = hfspaces.VIDEO_SPACES[0].base_url


def png(w: int, h: int) -> bytes:
    return b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + struct.pack(">II", w, h) + b"\x08\x02"


def mock(monkeypatch: pytest.MonkeyPatch, outcome: dict[str, Any],
         seen: list[dict[str, Any]]) -> None:
    """Space simulé : `/config`, `/upload`, `queue/join` et le flux `queue/data`."""
    def handler(req: httpx.Request) -> httpx.Response:
        path = req.url.path
        if path.endswith("/config"):
            return httpx.Response(200, json={"dependencies": [
                {"id": 3, "api_name": "image_to_video"}, {"id": 4, "api_name": "text_to_video"}]})
        if path.endswith("/upload"):
            return httpx.Response(200, json=["/tmp/gradio/photo.jpg"])
        if path.endswith("/queue/join"):
            seen.append(json.loads(req.content))
            return httpx.Response(200, json={"event_id": "abc"})
        if path.endswith("/queue/data"):
            done = {"msg": "process_completed", "event_id": "abc", **outcome}
            text = (f'data: {json.dumps({"msg": "estimation", "rank": 0})}\n\n'
                    f"data: {json.dumps(done)}\n\n")
            return httpx.Response(200, text=text, headers={"content-type": "text/event-stream"})
        if "file=" in str(req.url):
            return httpx.Response(200, content=b"\x00\x00\x00\x18ftypmp42video")
        return httpx.Response(404)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(http, "client", lambda: client)
    mp._FN_INDEX.clear()


def complete(url: str) -> dict[str, Any]:
    data = [{"video": {"url": url, "path": "/tmp/x.mp4"}, "subtitles": None}, 1]
    return {"success": True, "output": {"data": data}}


async def test_text_to_video(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[dict[str, Any]] = []
    mock(monkeypatch, complete(f"{BASE}/gradio_api/file=/tmp/x.mp4"), seen)
    out = await mp.generate_video(hfspaces.models()[0], "un renard dans la neige",
                                  {"duration": 3})
    assert out.mime == "video/mp4" and out.data.startswith(b"\x00\x00\x00\x18ftyp")
    assert seen[0]["fn_index"] == 4
    data = seen[0]["data"]
    assert data[0] == "un renard dans la neige" and data[6] == "text-to-video" and data[7] == 3


async def test_image_to_video_keeps_portrait(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[dict[str, Any]] = []
    mock(monkeypatch, complete(f"{BASE}/gradio_api/file=/tmp/x.mp4"), seen)
    await mp.generate_video(hfspaces.models()[0], "anime", {"image_bytes": png(1080, 1920)})
    data = seen[0]["data"]
    assert seen[0]["fn_index"] == 3 and data[6] == "image-to-video"
    assert data[2]["path"] == "/tmp/gradio/photo.jpg"
    height, width = data[4], data[5]
    assert height > width and width % 32 == 0 and height % 32 == 0


async def test_foreign_video_url_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    mock(monkeypatch, complete("https://evil.example/x.mp4"), [])
    with pytest.raises(ProviderError):
        await mp.generate_video(hfspaces.models()[0], "x", {})


async def test_gpu_quota_maps_to_quota(monkeypatch: pytest.MonkeyPatch) -> None:
    err = ("You have exceeded your ZeroGPU quota (120s requested vs. -60s left). "
           "Try again in 2:10:05.")
    mock(monkeypatch, {"success": False, "output": {"error": err}}, [])
    with pytest.raises(ProviderError) as exc:
        await mp.generate_video(hfspaces.models()[0], "x", {})
    assert exc.value.kind == ErrorKind.QUOTA and exc.value.retry_after == 2 * 3600 + 605


def test_jpeg_size() -> None:
    sof = b"\xff\xc0\x00\x11\x08" + struct.pack(">HH", 600, 800) + b"\x03" + b"\x00" * 9
    data = b"\xff\xd8" + b"\xff\xe0\x00\x10" + b"JFIF\x00" + b"\x00" * 9 + sof
    assert mp.image_size(data) == (800, 600)


@pytest.mark.parametrize("text", [
    "Crée une vidéo d'un chat qui danse", "fais-moi une courte vidéo de la mer",
    "génère un clip d'une fusée", "une vidéo de dauphins au coucher du soleil",
    "make a video of a dragon", "Mamorona horonan-tsary",
])
def test_video_requests(text: str) -> None:
    assert classify([{"role": "user", "content": text}]).category == Category.VIDEO_GEN


@pytest.mark.parametrize("text", [
    "explique-moi cette vidéo sur la photosynthèse", "quelle est la meilleure caméra vidéo ?",
    "comment monter une vidéo sur YouTube", "résume la vidéo d'hier",
])
def test_video_mentions_are_not_generation(text: str) -> None:
    assert classify([{"role": "user", "content": text}]).category != Category.VIDEO_GEN


def test_animate_attached_photo() -> None:
    msg = {"role": "user", "content": [
        {"type": "text", "text": "anime cette photo"},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}}]}
    assert classify([msg]).category == Category.VIDEO_GEN


@pytest.mark.parametrize(("text", "cat"), [
    ("Manaova sary tilikambo jiro", Category.IMAGE_GEN),
    ("Mamorona horonan-tsary momba ny ranomasina", Category.VIDEO_GEN),
    ("Karohy amin'ny tranonkala: vidin'ny vary", Category.SEARCH),
    ("Adikao amin'ny teny anglisy: manao ahoana", Category.TRANSLATION),
])
def test_malagasy_requests(text: str, cat: Category) -> None:
    assert classify([{"role": "user", "content": text}]).category == cat


def test_malagasy_photo_requests() -> None:
    def with_photo(text: str) -> dict[str, Any]:
        return {"role": "user", "content": [
            {"type": "text", "text": text},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}}]}

    assert classify([with_photo("Ampihetsiho ity sary ity")]).category == Category.VIDEO_GEN
    assert classify([with_photo("Hatsarao ity sary ity")]).category == Category.IMAGE_EDIT
