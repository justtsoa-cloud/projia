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
import contextlib
import json
import os
import re
import shutil
import tempfile
import time
import urllib.parse
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from projia import http, secrets, security
from projia.catalog.models import ModelInfo
from projia.catalog.sources import hfspaces, pollinations
from projia.providers.base import ErrorKind, ProviderError, Scope
from projia.providers.openai_compat import classify_error


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
        return await _pollinations_image(model, prompt, params)
    if model.provider == "hf_spaces":
        return await _space_image(model, prompt, params)
    if model.provider == "gemini":
        return await _gemini_image(model, provider, prompt, params)
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


async def _gemini_image(
    model: ModelInfo, provider: dict[str, Any], prompt: str, params: dict[str, Any]
) -> MediaOutput:
    """Nano Banana (Gemini 2.5+ Flash/Pro Image) avec une clé Google AI Studio gratuite.

    Pas de `/images/generations` chez Google : l'image sort du MÊME point d'entrée
    `chat/completions` que le texte, avec `modalities` — même convention déjà utilisée
    ci-dessous pour l'audio OpenRouter (`_openrouter_audio`). Retouche (image_edit) :
    la photo de référence part comme pièce jointe `image_url` du message, pas de champ
    dédié séparé.
    """
    content: Any = prompt
    if params.get("image"):
        content = [{"type": "text", "text": prompt},
                  {"type": "image_url", "image_url": {"url": params["image"]}}]
    body = {"model": model.model_id, "modalities": ["text", "image"],
            "messages": [{"role": "user", "content": content}]}
    resp = await _post(f"{provider['base_url']}/chat/completions", json=body,
                       headers=_auth(provider))
    message = ((resp.json().get("choices") or [{}])[0]).get("message") or {}
    url = None
    for img in message.get("images") or []:
        url = (img.get("image_url") or {}).get("url") if isinstance(img, dict) else None
        if url:
            break
    if not url and isinstance(message.get("content"), list):
        for part in message["content"]:
            if isinstance(part, dict) and part.get("type") == "image_url":
                url = (part.get("image_url") or {}).get("url")
                break
    if not url or ";base64," not in url:
        raise ProviderError("Aucune image renvoyée par Gemini", ErrorKind.SERVER)
    mime, b64 = url.split(";base64,", 1)
    return MediaOutput(base64.b64decode(b64), mime.removeprefix("data:") or "image/png")


IMAGE_MAX_BYTES = 20 * 1024 * 1024


async def _space_image(model: ModelInfo, prompt: str, params: dict[str, Any]) -> MediaOutput:
    """Image par un Space Hugging Face public (FLUX, Stable Diffusion), sans clé."""
    space = hfspaces.image_by_id(model.model_id)
    if space is None:
        raise ProviderError("Space inconnu", ErrorKind.UNAVAILABLE)
    headers = {}
    if hf := secrets.get_key("huggingface"):
        headers["Authorization"] = f"Bearer {hf}"
    w = max(256, min(int(params.get("width", 1024)), 1440)) // 32 * 32
    h = max(256, min(int(params.get("height", 1024)), 1440)) // 32 * 32
    seed = int(params.get("seed") or 0)
    rand = params.get("seed") is None
    if "Kontext" in space.space:
        # Retouche guidée : la photo est envoyée au Space, puis la consigne est appliquée.
        source = params.get("image")
        if not isinstance(source, str) or "," not in source:
            raise ProviderError("Photo manquante pour la retouche", ErrorKind.BAD_REQUEST)
        raw = base64.b64decode(source.split(",", 1)[1])
        up = await _post(f"{space.base_url}/gradio_api/upload", headers=headers, timeout=60.0,
                         files={"files": ("photo.png", raw, "image/png")})
        paths = up.json()
        if not paths:
            raise ProviderError("Envoi de la photo refusé", ErrorKind.SERVER)
        data: list[Any] = [{"path": paths[0], "meta": {"_type": "gradio.FileData"}}, prompt,
                           seed, rand, 2.5, space.steps]
    elif "stable-diffusion" in space.space:
        data = [prompt, "", seed, rand, w, h, 0.0, space.steps]
    elif space.steps > 4:  # FLUX.1-dev (et Qwen-Image, même forme supposée) : échelle de guidage
        data = [prompt, seed, rand, w, h, 3.5, space.steps]
    else:
        data = [prompt, seed, rand, w, h, space.steps]
    # File GPU saturée : mieux vaut passer vite à la source suivante (Pollinations).
    result = await _gradio_queue(space.base_url, "infer", data, headers,
                                 timeout=150.0 if "Kontext" in space.space else 90.0)
    item = result[0] if isinstance(result, list) and result else result
    url = item.get("url") if isinstance(item, dict) else None
    if not isinstance(url, str) or not url.startswith(space.base_url + "/"):
        raise ProviderError("Réponse image inattendue", ErrorKind.SERVER)
    body = await _download_limited(url, headers, IMAGE_MAX_BYTES)
    mime = ("image/webp" if body[8:12] == b"WEBP" else "image/jpeg" if body[:2] == b"\xff\xd8"
            else "image/png")
    return MediaOutput(body, mime)


VIDEO_MAX_BYTES = 60 * 1024 * 1024
VIDEO_TIMEOUT = 300.0
_QUOTA_RE = re.compile(r"(\d+):(\d{2}):(\d{2})")


async def generate_video(model: ModelInfo, prompt: str, params: dict[str, Any]) -> MediaOutput:
    """Vidéo par un Space Hugging Face public (API REST Gradio, sans clé).

    Texte → vidéo, ou image → vidéo si une photo est jointe (`image_bytes`)."""
    space = hfspaces.by_id(model.model_id)
    if space is None:
        raise ProviderError("Space inconnu", ErrorKind.UNAVAILABLE)
    api = f"{space.base_url}/gradio_api"
    headers = {}
    if hf := secrets.get_key("huggingface"):  # quota GPU plus large avec une clé gratuite
        headers["Authorization"] = f"Bearer {hf}"
    duration = max(1.0, min(float(params.get("duration") or 4), 8.0))
    image = params.get("image_bytes")
    fn = "text_to_video"
    image_arg: Any = None
    if image:
        fn = "image_to_video"
        up = await _post(f"{api}/upload", headers=headers, timeout=60.0,
                         files={"files": ("photo.jpg", image, "image/jpeg")})
        paths = up.json()
        if not paths:
            raise ProviderError("Envoi de la photo refusé", ErrorKind.SERVER)
        image_arg = {"path": paths[0], "meta": {"_type": "gradio.FileData"}}
    width, height = _video_dims(image, params.get("aspect_ratio"))
    data = [prompt, "worst quality, inconsistent motion, blurry, jittery, distorted",
            image_arg, None, height, width, "image-to-video" if image else "text-to-video",
            duration, 9, 42, True, 1, True]
    result = await _gradio_queue(space.base_url, fn, data, headers)
    url = _video_url(result, space.base_url)
    return MediaOutput(await _download_limited(url, headers), "video/mp4")


async def _download_limited(url: str, headers: dict[str, str],
                            limit: int | None = None) -> bytes:
    """Téléchargement borné : sans redirection (la clé Hugging Face ne quitte jamais le
    domaine du Space) et arrêté dès que la taille maximale est dépassée."""
    buf = bytearray()
    try:
        async with http.client().stream("GET", url, headers=headers, timeout=120.0,
                                        follow_redirects=False) as r:
            if r.status_code >= 300:
                raise ProviderError("Vidéo introuvable", ErrorKind.SERVER, status=r.status_code)
            async for chunk in r.aiter_bytes():
                buf.extend(chunk)
                if len(buf) > (limit or VIDEO_MAX_BYTES):
                    raise ProviderError("Vidéo trop volumineuse", ErrorKind.SERVER)
    except httpx.HTTPError as exc:
        raise ProviderError(type(exc).__name__, ErrorKind.NETWORK) from exc
    if not buf:
        raise ProviderError("Vidéo vide", ErrorKind.SERVER)
    return bytes(buf)


def image_size(data: bytes) -> tuple[int, int] | None:
    """Largeur et hauteur d'une image PNG ou JPEG (sans bibliothèque d'images)."""
    if data[:8] == b"\x89PNG\r\n\x1a\n" and len(data) >= 24:
        return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")
    if data[:2] == b"\xff\xd8":
        i = 2
        while i + 9 < len(data):
            if data[i] != 0xFF:
                i += 1
                continue
            marker = data[i + 1]
            if marker in (0xC0, 0xC1, 0xC2):
                h = int.from_bytes(data[i + 5:i + 7], "big")
                w = int.from_bytes(data[i + 7:i + 9], "big")
                return w, h
            if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
                i += 2
                continue
            i += 2 + int.from_bytes(data[i + 2:i + 4], "big")
    return None


def _video_dims(image: bytes | None, aspect: str | None) -> tuple[int, int]:
    """Dimensions (multiples de 32, ≈ 704×512 pixels) qui respectent le cadrage voulu."""
    ratio = 704 / 512
    size = image_size(image) if image else None
    if size and size[0] > 0 and size[1] > 0:
        ratio = size[0] / size[1]
    elif aspect and ":" in aspect:
        a, _, b = aspect.partition(":")
        with contextlib.suppress(ValueError, ZeroDivisionError):
            ratio = float(a) / float(b)
    ratio = max(9 / 21, min(21 / 9, ratio))
    area = 704 * 512
    w = (area * ratio) ** 0.5
    h = w / ratio
    return (max(256, min(1024, round(w / 32) * 32)), max(256, min(1024, round(h / 32) * 32)))


_FN_INDEX: dict[tuple[str, str], int] = {}


async def _fn_index(base_url: str, api_name: str, headers: dict[str, str]) -> int:
    key = (base_url, api_name)
    if key not in _FN_INDEX:
        try:
            r = await http.client().get(f"{base_url}/config", headers=headers, timeout=30.0)
        except httpx.HTTPError as exc:
            raise ProviderError(type(exc).__name__, ErrorKind.NETWORK) from exc
        if r.status_code >= 400:
            raise ProviderError("Space indisponible", ErrorKind.UNAVAILABLE, status=r.status_code)
        for i, dep in enumerate(r.json().get("dependencies") or []):
            if dep.get("api_name") == api_name:
                _FN_INDEX[key] = int(dep.get("id", i))
                break
        else:
            raise ProviderError("Fonction absente du Space", ErrorKind.UNAVAILABLE)
    return _FN_INDEX[key]


async def _gradio_queue(base_url: str, api_name: str, data: list[Any],
                        headers: dict[str, str], timeout: float = VIDEO_TIMEOUT) -> Any:  # noqa: ASYNC109
    """File d'attente Gradio (`queue/join` puis flux `queue/data`). Contrairement à l'API
    `call/`, elle renvoie la vraie raison d'un échec (quota GPU épuisé, etc.)."""
    session = uuid.uuid4().hex[:11]
    body = {"data": data, "fn_index": await _fn_index(base_url, api_name, headers),
            "session_hash": session, "event_data": None, "trigger_id": None}
    await _post(f"{base_url}/gradio_api/queue/join", json=body, headers=headers, timeout=30.0)
    try:
        async with http.client().stream(
                "GET", f"{base_url}/gradio_api/queue/data", params={"session_hash": session},
                headers=headers, timeout=httpx.Timeout(timeout, connect=15.0)) as resp:
            if resp.status_code >= 400:
                body_text = (await resp.aread()).decode("utf-8", "replace")
                raise classify_error(resp.status_code, body_text, {})
            async for line in resp.aiter_lines():
                if not line.startswith("data:"):
                    continue
                try:
                    msg = json.loads(line[5:].strip())
                except ValueError:
                    continue
                if msg.get("msg") == "process_completed":
                    out = msg.get("output") or {}
                    if msg.get("success") and "data" in out:
                        return out["data"]
                    raise _gradio_error(str(out.get("error") or msg.get("title") or "null"))
                if msg.get("msg") == "unexpected_error":
                    raise _gradio_error(str(msg.get("message") or "null"))
    except httpx.HTTPError as exc:
        raise ProviderError(type(exc).__name__, ErrorKind.NETWORK) from exc
    raise ProviderError("Génération interrompue", ErrorKind.SERVER)


def _gradio_error(payload: str) -> ProviderError:
    text = payload if payload not in ("null", "") else "erreur du Space"
    low = text.lower()
    if "quota" in low or ("gpu" in low and ("exceed" in low or "limit" in low)):
        retry = 3600.0  # le quota ZeroGPU se reconstitue progressivement
        if m := _QUOTA_RE.search(text):
            h, mi, s = (int(x) for x in m.groups())
            retry = max(retry, float(h * 3600 + mi * 60 + s))
        # Quota ZeroGPU commun à tous les Spaces : on les met tous en pause d'un coup.
        return ProviderError("Quota GPU gratuit épuisé", ErrorKind.QUOTA, retry_after=retry,
                             scope=Scope.PROVIDER)
    return ProviderError(text[:200], ErrorKind.SERVER)


def _video_url(result: Any, base_url: str) -> str:
    """URL de la vidéo dans la réponse Gradio ; uniquement sur le domaine du Space."""
    item = result[0] if isinstance(result, list) and result else result
    if isinstance(item, dict) and "video" in item:
        item = item["video"]
    url = item.get("url") if isinstance(item, dict) else None
    if not isinstance(url, str) or not url.startswith(base_url + "/"):
        raise ProviderError("Réponse vidéo inattendue", ErrorKind.SERVER)
    return url


async def _pollinations_image(model: ModelInfo, prompt: str,
                              params: dict[str, Any]) -> MediaOutput:
    """Pollinations (sans clé) : service parfois instable → 2 essais (graine différente), chacun
    limité à 45 s : mieux vaut basculer ou renoncer vite que laisser l'utilisateur attendre."""
    url = pollinations.IMAGE_URL + urllib.parse.quote(prompt, safe="")
    last: ProviderError | None = None
    for attempt in range(2):
        q = {"width": str(params.get("width", 1024)), "height": str(params.get("height", 1024)),
             "nologo": "true", "private": "true"}
        if model.model_id != "auto":
            q["model"] = model.model_id
        seed = params.get("seed")
        q["seed"] = str(seed if seed is not None and attempt == 0 else int(time.time()) + attempt)
        try:
            resp = await http.client().get(url, params=q, timeout=45.0)
        except httpx.HTTPError as exc:
            last = ProviderError(type(exc).__name__, ErrorKind.NETWORK)
        else:
            mime = resp.headers.get("content-type", "").split(";")[0]
            if resp.status_code < 400 and mime.startswith("image/") and resp.content:
                return MediaOutput(resp.content, mime)
            last = (classify_error(resp.status_code, resp.text, dict(resp.headers))
                    if resp.status_code >= 400 else
                    ProviderError("Réponse non image", ErrorKind.SERVER))
            if last.kind in (ErrorKind.RATE_LIMIT, ErrorKind.QUOTA, ErrorKind.AUTH):
                break                      # inutile d'insister : on laisse la bascule agir
        await asyncio.sleep(1.5 * (attempt + 1))
    raise last or ProviderError("Aucune image", ErrorKind.SERVER)


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
    if exe is None or os.environ.get("PROJIA_PLATFORM") == "android":
        # L'application lira le texte avec la voix du système.
        return MediaOutput(text.encode(), "text/plain", text=text, local_tts=True)
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "speech.wav"
        if exe == "piper":
            voice = params.get("piper_model") or os.environ.get("PROJIA_PIPER_MODEL")
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
