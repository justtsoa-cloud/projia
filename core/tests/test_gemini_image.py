"""Nano Banana (Gemini 2.5+ Flash/Pro Image) avec une clé Google AI Studio gratuite :
découverte catalogue (keyed.py) + appel chat/completions+modalities (providers.py)."""

from __future__ import annotations

from typing import Any

import pytest

from projia.catalog.models import ModelInfo
from projia.catalog.sources import keyed
from projia.media import providers as mp
from projia.providers.base import ProviderError

GEMINI_PROVIDER = {"id": "gemini", "base_url": "https://generativelanguage.googleapis.com/v1beta/openai"}


def test_gemini_image_model_tagged_in_catalog() -> None:
    """Un modèle « …-image » du fournisseur gemini est marqué image_gen/image_edit ;
    un modèle texte ordinaire (même fournisseur) ne l'est pas."""
    data = {"data": [
        {"id": "gemini-2.5-flash-image", "name": "Gemini 2.5 Flash Image"},
        {"id": "gemini-2.5-flash", "name": "Gemini 2.5 Flash"},
    ]}
    models = {m.model_id: m for m in keyed.parse("gemini", data)}
    assert models["gemini-2.5-flash-image"].media == ["image_gen", "image_edit"]
    assert "image" in models["gemini-2.5-flash-image"].input_modalities
    assert models["gemini-2.5-flash"].media == []


def _model() -> ModelInfo:
    return ModelInfo(provider="gemini", model_id="gemini-2.5-flash-image", is_free=True,
                     media=["image_gen", "image_edit"])


async def test_gemini_image_generation(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, Any] = {}

    class Resp:
        def json(self) -> dict[str, Any]:
            return {"choices": [{"message": {
                "images": [{"image_url": {"url": "data:image/png;base64,aGVsbG8="}}]}}]}

    async def fake_post(url: str, **kw: Any) -> Resp:
        calls["url"] = url
        calls["json"] = kw["json"]
        return Resp()

    monkeypatch.setattr(mp, "_post", fake_post)
    monkeypatch.setattr("projia.secrets.get_key", lambda _p: "fake-key")
    monkeypatch.setattr("projia.security.key_allowed", lambda *_a: True)
    out = await mp.generate_image(_model(), GEMINI_PROVIDER, "un chat astronaute", {})
    assert out.data == b"hello" and out.mime == "image/png"
    assert calls["url"].endswith("/chat/completions")
    assert calls["json"]["modalities"] == ["text", "image"]
    assert calls["json"]["messages"][0]["content"] == "un chat astronaute"


async def test_gemini_image_edit_attaches_reference_photo(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, Any] = {}

    class Resp:
        def json(self) -> dict[str, Any]:
            return {"choices": [{"message": {"content": [
                {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,d29ybGQ="}}]}}]}

    async def fake_post(url: str, **kw: Any) -> Resp:
        calls["json"] = kw["json"]
        return Resp()

    monkeypatch.setattr(mp, "_post", fake_post)
    monkeypatch.setattr("projia.secrets.get_key", lambda _p: "fake-key")
    monkeypatch.setattr("projia.security.key_allowed", lambda *_a: True)
    out = await mp.generate_image(_model(), GEMINI_PROVIDER, "enlève le fond",
                                  {"image": "data:image/png;base64,iVBORw0KGgo="})
    assert out.data == b"world" and out.mime == "image/jpeg"
    content = calls["json"]["messages"][0]["content"]
    assert content[0] == {"type": "text", "text": "enlève le fond"}
    assert content[1]["image_url"]["url"] == "data:image/png;base64,iVBORw0KGgo="


async def test_gemini_image_no_image_in_response_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    class Resp:
        def json(self) -> dict[str, Any]:
            return {"choices": [{"message": {"content": "désolé, je ne peux pas"}}]}

    async def fake_post(url: str, **kw: Any) -> Resp:
        return Resp()

    monkeypatch.setattr(mp, "_post", fake_post)
    monkeypatch.setattr("projia.secrets.get_key", lambda _p: "fake-key")
    monkeypatch.setattr("projia.security.key_allowed", lambda *_a: True)
    with pytest.raises(ProviderError):
        await mp.generate_image(_model(), GEMINI_PROVIDER, "x", {})
