"""Adaptateurs médias : image, transcription (STT), synthèse vocale (TTS), musique, vidéo.

Vérifié le 2026-10-10 :
- Pollinations : `GET https://image.pollinations.ai/prompt/{prompt}` (sans clé) ;
- OpenRouter : `POST /api/v1/images` (`b64_json`) ; audio en sortie par
  `chat/completions` avec `modalities: ["text","audio"]` et `stream: true` ;
- Fournisseurs compatibles OpenAI : `POST /audio/transcriptions` (multipart),
  `POST /audio/speech` ;
- Repli TTS local : `espeak-ng` ou `piper` sous Linux ; sous Android, la synthèse
  du système est faite par l'application (Android TextToSpeech).
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import shutil
import tempfile
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from tontolo import http, secrets, security
from tontolo.catalog.models import ModelInfo
from tontolo.catalog.sources import pollinations
from tontolo.providers.base import ErrorKind, ProviderError
from tontolo.providers.openai_compat import classify_error


@dataclass
class MediaOutput:
    data: bytes
    mime: str
    text: str | None = None       # transcription, ou texte à lire localement
    local_tts: bool = False       # l'appareil doit lire `text` avec sa voix système


_EXT = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp", "audio/wav": "wav",
        "audio/mpeg": "mp3", "audio/ogg": "ogg", "video/mp4": "mp4", "text/plain": "txt"}


def ext_for(mime: str) -> str:
    return _EXT.get(mime.split(";")[0].strip(), "bin")


def _auth(provider: dict[str, Any]) -> dict[str, str]:
    key = secrets.get_key(provider["id"])
    if key and not security.key_allowed(provider["id"], provider.get("base_url", "")):
        raise ProviderError(f"Hôte non fiable pour {provider['id']}", ErrorKind.AUTH)
    if not key and not provider.get("keyless"):
        raise ProviderError(f"Aucune clé pour {provider['id']}", ErrorKind.AUTH)
    return {"Authorization": f"Bearer {key}"} if key else {}


async def _post(url: str, **kw: Any) -> httpx.Response:
    try:
        resp = await http.client().post(url, timeout=kw.pop("timeout", 180.0), **kw)
    except httpx.HTTPError as exc:
        raise ProviderError(type(exc).__name__, ErrorKind.NETWORK) from exc
    if resp.status_code >= 400:
        raise classify_error(resp.status_code, resp.text,
                             {k.lower(): v for k, v in resp.headers.items()})
    return resp


async def generate_image(
    model: ModelInfo, provider: dict[str, Any], prompt: str, params: dict[str, Any]
) -> MediaOutput:
    if model.provider == "pollinations":
        q = {"width": str(params.get("width", 1024)), "height": str(params.get("height", 1024)),
             "model": model.model_id, "nologo": "true", "private": "true"}
        if params.get("seed") is not None:
            q["seed"] = str(params["seed"])
        url = pollinations.IMAGE_URL + urllib.parse.quote(prompt, safe="")
        try:
            resp = await http.client().get(url, params=q, timeout=180.0)
        except httpx.HTTPError as exc:
            raise ProviderError(type(exc).__name__, ErrorKind.NETWORK) from exc
        if resp.status_code >= 400:
            raise classify_error(resp.status_code, resp.text, dict(resp.headers))
        mime = resp.headers.get("content-type", "image/jpeg").split(";")[0]
        if not mime.startswith("image/"):
            raise ProviderError("Réponse non image", ErrorKind.SERVER)
        return MediaOutput(resp.content, mime)
    body: dict[str, Any] = {"model": model.model_id, "prompt": prompt, "n": 1}
    if params.get("aspect_ratio"):
        body["aspect_ratio"] = params["aspect_ratio"]
    if params.get("image"):  # image de référence (édition / image à image)
        body["input_references"] = [params["image"]]
    if model.provider == "openrouter":
        url = f"{provider['base_url']}/images"
    else:
        url = f"{provider['base_url']}/images/generations"
        body["response_format"] = "b64_json"
    resp = await _post(url, json=body, headers=_auth(provider))
    item = (resp.json().get("data") or [{}])[0]
    if item.get("b64_json"):
        return MediaOutput(base64.b64decode(item["b64_json"]),
                           item.get("media_type", "image/png"))
    if item.get("url"):
        r = await http.client().get(item["url"], timeout=120.0)
        return MediaOutput(r.content, r.headers.get("content-type", "image/png"))
    raise ProviderError("Aucune image renvoyée", ErrorKind.SERVER)


async def transcribe(
    model: ModelInfo, provider: dict[str, Any], audio: bytes, filename: str,
    params: dict[str, Any],
) -> MediaOutput:
    data = {"model": model.model_id, "response_format": "json"}
    if params.get("language"):
        data["language"] = params["language"]
    resp = await _post(f"{provider['base_url']}/audio/transcriptions", data=data,
                       files={"file": (filename, audio)}, headers=_auth(provider))
    text = resp.json().get("text", "")
    return MediaOutput(text.encode(), "text/plain", text=text)


async def speak(
    model: ModelInfo, provider: dict[str, Any], text: str, params: dict[str, Any]
) -> MediaOutput:
    if model.provider == "local":
        return await local_tts(text, params)
    if model.provider == "openrouter":
        return await _openrouter_audio(model, provider, text, params)
    body = {"model": model.model_id, "input": text, "voice": params.get("voice", "alloy"),
            "response_format": "wav"}
    resp = await _post(f"{provider['base_url']}/audio/speech", json=body,
                       headers=_auth(provider))
    return MediaOutput(resp.content, resp.headers.get("content-type", "audio/wav"))


async def _openrouter_audio(
    model: ModelInfo, provider: dict[str, Any], prompt: str, params: dict[str, Any]
) -> MediaOutput:
    body = {"model": model.model_id, "stream": True, "modalities": ["text", "audio"],
            "audio": {"voice": params.get("voice", "alloy"), "format": "wav"},
            "messages": [{"role": "user", "content": prompt}]}
    chunks: list[str] = []
    transcript: list[str] = []
    try:
        async with http.client().stream("POST", f"{provider['base_url']}/chat/completions",
                                        json=body, headers=_auth(provider),
                                        timeout=300.0) as resp:
            if resp.status_code >= 400:
                raise classify_error(resp.status_code, (await resp.aread()).decode(),
                                     dict(resp.headers))
            async for line in resp.aiter_lines():
                if not line.startswith("data:") or line.endswith("[DONE]"):
                    continue
                try:
                    delta = json.loads(line[5:])["choices"][0].get("delta", {})
                except (ValueError, KeyError, IndexError):
                    continue
                audio = delta.get("audio") or {}
                if audio.get("data"):
                    chunks.append(audio["data"])
                if audio.get("transcript"):
                    transcript.append(audio["transcript"])
    except httpx.HTTPError as exc:
        raise ProviderError(type(exc).__name__, ErrorKind.NETWORK) from exc
    if not chunks:
        raise ProviderError("Aucun audio renvoyé", ErrorKind.SERVER)
    return MediaOutput(base64.b64decode("".join(chunks)), "audio/wav",
                       text="".join(transcript) or None)


def local_tts_available() -> str | None:
    for exe in ("piper", "espeak-ng", "espeak"):
        if shutil.which(exe):
            return exe
    return None


async def local_tts(text: str, params: dict[str, Any]) -> MediaOutput:
    """Synthèse vocale locale, gratuite et sans quota."""
    exe = local_tts_available()
    if exe is None or os.environ.get("TONTOLO_PLATFORM") == "android":
        # L'application lira le texte avec la voix du système.
        return MediaOutput(text.encode(), "text/plain", text=text, local_tts=True)
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "speech.wav"
        if exe == "piper":
            voice = params.get("piper_model") or os.environ.get("TONTOLO_PIPER_MODEL")
            if not voice:
                return MediaOutput(text.encode(), "text/plain", text=text, local_tts=True)
            cmd = [exe, "--model", str(voice), "--output_file", str(out)]
            proc = await asyncio.create_subprocess_exec(*cmd, stdin=asyncio.subprocess.PIPE)
            await proc.communicate(text.encode())
        else:
            lang = params.get("language", "fr")
            proc = await asyncio.create_subprocess_exec(exe, "-v", lang, "-w", str(out), text)
            await proc.wait()
        if not out.exists():
            raise ProviderError("Synthèse locale en échec", ErrorKind.SERVER)
        return MediaOutput(out.read_bytes(), "audio/wav")


LOCAL_TTS_MODEL = ModelInfo(
    provider="local", model_id="system-tts", name="Voix du système (locale)",
    input_modalities=["text"], output_modalities=["audio"], is_free=True, needs_key=False,
    media=["tts"], quality={"tts": 0.2}, rate_limit="illimité (local)",
)
