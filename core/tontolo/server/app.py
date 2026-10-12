"""Serveur FastAPI : API compatible OpenAI (`/v1/*`), API native (`/tontolo/*`) et
WebSocket d'événements (bascules, nouveautés, jobs médias).

Le même serveur tourne embarqué dans l'application (127.0.0.1, mode local)
ou sur une machine Linux (mode client-serveur, jeton obligatoire).
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import contextlib
import hmac
import ipaddress
import json
import re
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile, WebSocket
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, Field, field_validator, model_validator

from tontolo import __version__, attachments, documents, importer, secrets, security
from tontolo.agent import planner
from tontolo.agent.loop import dumps
from tontolo.agent.mcp_client import MAX_SERVERS as MCP_MAX_SERVERS
from tontolo.agent.mcp_client import check_server as check_mcp_server
from tontolo.agent.mcp_client import load_config, save_config
from tontolo.agent.workspace import is_desktop
from tontolo.app_state import Core
from tontolo.catalog.i18n import texts as provider_texts
from tontolo.catalog.models import Category, ModelInfo
from tontolo.config import CustomProvider, Settings, load_settings, save_settings
from tontolo.creator import clarify
from tontolo.creator import intent as file_intent
from tontolo.memory import name_from
from tontolo.providers.registry import ProviderRegistry
from tontolo.router.classifier import _is_followup, classify
from tontolo.router.quota import QuotaManager
from tontolo.router.refusal import looks_like_image_refusal, mentions_image
from tontolo.security import (
    LOOPBACK_NAMES,
    assert_public_url,
    host_of,
    key_allowed,
    origin_allowed,
)
from tontolo.storage import space
from tontolo.update import check_update, download_update

LOOPBACK = {"127.0.0.1", "::1", "localhost"}
MAX_TASK_VIEW = 200_000
ACTIVE_MIMES = {"text/html", "application/xhtml+xml", "image/svg+xml", "text/xml",
                "application/xml", "text/javascript", "application/javascript"}
_SAFE_MIME = re.compile(r"^(image|audio|video|text|application)/[\w.+-]{1,60}(; ?charset=[\w-]+)?$")


def safe_mime(value: Any) -> str:
    """Type de contenu d'une création : forme valide, sinon binaire neutre."""
    mime = str(value or "").strip().lower()
    return mime if _SAFE_MIME.match(mime) else "application/octet-stream"
SYNC_CREATION_MAX = 1_000_000  # créations synchronisées entre appareils (octets)
MEDIA_TURN_KINDS = {"image_gen", "image_edit", "tts", "music_sfx", "video_gen"}
REVIEWED_TOPICS = {"math", "code", "reasoning"}  # réponses vérifiées par un second modèle


MAX_UPLOAD_BYTES = 25 * 1024 * 1024


async def _read_limited(file: UploadFile, limit: int = 0) -> bytes:
    limit = limit or MAX_UPLOAD_BYTES
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(413, f"Fichier trop volumineux ({limit // 1024 // 1024} Mo maximum)")
    return data


MAX_VIDEO_BYTES = 100 * 1024 * 1024  # avec ffmpeg (piste son extraite) ; sinon 25 Mo


async def _audio_track(name: str, data: bytes) -> tuple[str, bytes]:
    """Piste son d'une vidéo (ffmpeg, s'il est installé) : bien plus légère à transcrire.
    Sans ffmpeg, la vidéo est envoyée telle quelle (les services vocaux acceptent mp4/webm)."""
    import shutil
    import tempfile

    exe = shutil.which("ffmpeg")
    if exe is None:
        return name, data
    with tempfile.TemporaryDirectory() as tmp:
        src, out = Path(tmp) / "in", Path(tmp) / "out.mp3"
        src.write_bytes(data)
        proc = await asyncio.create_subprocess_exec(
            exe, "-nostdin", "-loglevel", "error", "-i", str(src), "-vn", "-ac", "1", "-ar",
            "16000", "-b:a", "48k", "-t", "3600", str(out),
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
        try:
            await asyncio.wait_for(proc.wait(), 300)
        except TimeoutError:
            proc.kill()
            return name, data
        if proc.returncode == 0 and out.exists() and out.stat().st_size > 0:
            return Path(name).stem + ".mp3", out.read_bytes()
    return name, data


def _text_of(content: Any) -> str:
    if isinstance(content, str):
        return content
    return " ".join(str(p.get("text", "")) for p in content if isinstance(p, dict)
                    and p.get("type") == "text")


def _references_image(text: str) -> bool:
    """Une référence explicite, pas une nouvelle scène texte → vidéo."""
    return bool(re.search(
        r"\b(anime[- ](?:la|le|les)|animate (?:it|this)|bring it to life|make it move|"
        r"ampihetsiho|ampihetseho|(?:cette|cet|la|l['’]|this|that|the)\s*"
        r"(?:image|photo|picture)|(?:transforme|convertis|mets)[- ](?:la|le)|"
        r"fais[- ](?:la|le|les)[- ]bouger|donne[- ]lui vie)\b", text, re.I))


async def _media_history(core: Core, cid: str,
                         history: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """Modalité réelle des résultats du fil ; les marqueurs étrangers sont ignorés."""
    out = []
    for message in history if history is not None else await core.db.get_messages(cid):
        item = dict(message)
        match = re.fullmatch(r"\[média:([0-9a-f]+)\]", str(item.get("content", "")))
        if item.get("role") == "assistant" and match:
            job = await core.db.get_job(match.group(1))
            if job and job.get("conversation_id") == cid:
                item["_media_kind"] = job["kind"]
        out.append(item)
    return out


async def _media_prompt(core: Core, cid: str, text: str) -> str:
    """Hérite uniquement pour une relance ou une référence explicite à l'image."""
    if not (_is_followup(text) or _references_image(text)):
        return text
    history = await core.db.get_messages(cid)
    # Le message courant est déjà enregistré, y compris lors d'une régénération.
    for message in reversed(history[:-1]):
        match = re.fullmatch(r"\[média:([0-9a-f]+)\]", str(message.get("content", "")))
        if message.get("role") == "assistant" and match:
            job = await core.db.get_job(match.group(1))
            if job and job.get("conversation_id") == cid and job["kind"] in (
                    "image_gen", "image_edit", "video_gen"):
                return f"{job['prompt']}. {text}"
        if message.get("role") == "user":
            prior = _text_of(message["content"])
            if classify([message]).category.value in MEDIA_TURN_KINDS:
                return f"{prior}. {text}"
            if not _is_followup(prior):
                break
    return text


_NON_ENGLISH = re.compile(
    r"[àâçéèêëîïôûùüÿœ]|\b(une?|des|les|du|de la|dans|avec|sur|qui|et|est|"
    r"manaova|mamorona|sary|ny|amin|izay|sy|ary|horonan)\b", re.I)

ENGLISH_PROMPT = (
    "Rewrite the user's request as one concise English prompt for an image or video "
    "generator: preserve the subject, scene, style, mood, requested motion, camera movement, "
    "duration and constraints on changes to the input image. Translate from any "
    "language (French, Malagasy…), keeping compound nouns whole (Malagasy « tilikambo jiro » "
    "is a lighthouse, « sambo » a boat, « vorona » a bird). Output only the prompt, nothing "
    "else.")


async def _english_prompt(core: Core, text: str) -> str:
    """Les générateurs d'images et de vidéos suivent mal le français et le malgache :
    reformulation en anglais par un petit modèle gratuit (texte d'origine en cas d'échec)."""
    if not _NON_ENGLISH.search(text):
        return text
    messages = [{"role": "system", "content": ENGLISH_PROMPT},
                {"role": "user", "content": text[:1500]}]
    out: str | None = None
    try:
        # Meilleur modèle de traduction (le malgache demande un bon modèle), délai borné.
        async with asyncio.timeout(25):
            async for ev in core.router.run(messages, stream=False, forced=Category.TRANSLATION,
                                            params={"max_tokens": 300, "temperature": 0.2}):
                if ev["type"] == "done":
                    out = str(ev["message"].get("content") or "")
    except Exception:  # délai dépassé ou erreur : la traduction ne bloque jamais la création
        out = None
    if not out:
        try:
            async with asyncio.timeout(10):
                out = await core.router.quick(messages)
        except Exception:
            out = None
    out = (out or "").strip().strip('"').strip()
    return out[:900] if 3 <= len(out.split()) <= 160 else text


async def _last_file(core: Core, cid: str) -> tuple[str, str] | None:
    """(format, source) du fichier créé par la DERNIÈRE réponse de la conversation."""
    # Le dernier fichier LIVRÉ : une correction qui a échoué n'efface pas la version précédente
    # (« excellent mais plus court » après un échec doit encore partir de la dernière version).
    job: dict[str, Any] | None = None
    for m in reversed(await core.db.get_window(cid, 12)):
        if m.get("role") != "assistant":
            continue
        mt = re.match(r"^\[média:([0-9a-f]+)\]$", str(m.get("content") or "").strip())
        if not mt:
            return None  # la discussion a continué en texte : on ne corrige plus un fichier
        found = await core.db.get_job(mt.group(1))
        if (not found or found.get("conversation_id") != cid
                or found.get("kind") != "file_gen"):
            return None
        if found.get("status") == "done":
            job = found
            break  # échec : on remonte à la version précédente
    if job is None:
        return None
    params = job.get("params") or {}
    src = params.get("source_path") or job.get("result_path")
    path = Path(str(src or ""))
    text = ""
    if path.is_file() and path.resolve().is_relative_to(core.media.dir.resolve()):
        raw = path.read_bytes()
        text = raw.decode("utf-8", "replace") if params.get("source_path") or str(
            params.get("mime", "")).startswith("text/") else ""
    return str(params.get("format") or ""), text


async def _file_material(core: Core, cid: str, skip_last: bool = False,
                         request: str = "") -> str:
    """Contenu à convertir pour une création de fichier : documents joints puis source du
    dernier fichier créé dans la discussion. Un long document (livre) est transmis sous forme
    de fiche compacte (plan, notions, exemples, code de chaque partie) plus les passages les
    plus utiles à la demande, et non ses seules premières pages."""
    parts: list[str] = []
    for d in (await core.db.list_documents(cid, with_pages=True))[-3:]:
        pages = [str(p) for p in d.get("pages") or []]
        text = "\n".join(pages)
        if not text.strip():
            continue
        if len(text) <= documents.LONG_DOC:
            parts.append(f"Document joint « {d.get('name')} » (contenu à utiliser) :\n" + text)
            continue
        digest = str(d.get("digest") or "") or documents.digest(pages)
        picked = documents.select(documents.chunk_pages(pages), request or "résumé", k=10)
        excerpts = "\n\n".join(f"[p. {c.page}] {c.text}" for c in picked)
        parts.append(f"Document joint « {d.get('name')} » ({len(pages)} pages) — fiche "
                     f"compacte de TOUT le document (à suivre) :\n{digest}\n\nPassages "
                     f"détaillés les plus utiles à la demande :\n{excerpts}")
    prev = None if skip_last else await _last_file(core, cid)
    if prev and prev[1].strip():
        parts.append(f"Source du dernier fichier créé ({prev[0]}) :\n{prev[1][:15000]}")
    return "\n\n".join(parts)[-36000:]


def _keep_draft(core: Core, cid: str, job: dict[str, Any]) -> None:
    """Chaque version d'un fichier créé (source LaTeX, Markdown, code…) est gardée parmi les
    résultats intermédiaires de la discussion."""
    params = job.get("params") or {}
    if job.get("status") != "done":
        return
    src = Path(str(params.get("source_path") or job.get("result_path") or ""))
    if not params.get("source_path") and not str(params.get("mime", "")).startswith("text/"):
        return
    with contextlib.suppress(OSError, ValueError):
        text = src.read_text(encoding="utf-8", errors="replace")
        if text.strip():
            core.chat.tasks.put(cid, "draft", f"{params.get('filename') or src.name} "
                                f"({time.strftime('%H:%M')})", text)


async def _image_source(core: Core, cid: str) -> tuple[bytes | None, str | None]:
    """Dernière image du fil. Une image échouée interdit le retour à une ancienne."""
    for m in reversed(await core.db.get_messages(cid)):
        if m.get("role") == "user":
            image = _first_image(m.get("content"))
            if image is not None:
                return image, None
        mt = re.fullmatch(r"\[média:([0-9a-f]+)\]", str(m.get("content", "")).strip())
        if m.get("role") != "assistant" or not mt:
            continue
        job = await core.db.get_job(mt.group(1))
        if not job or job.get("conversation_id") != cid:
            continue
        if job["kind"] not in ("image_gen", "image_edit"):
            continue
        if job.get("status") != "done" or not job.get("result_path"):
            return None, None
        path = Path(job["result_path"])
        if (path.is_file() and path.resolve().is_relative_to(core.media.dir.resolve())
                and path.stat().st_size <= MAX_UPLOAD_BYTES):
            return path.read_bytes(), job["id"]
        return None, None
    return None, None


async def _last_image(core: Core, cid: str) -> bytes | None:
    image, _ = await _image_source(core, cid)
    return image


def _wants_image(text: str) -> bool:
    """La demande porte sur une image (mot « image », ou « draw / dessine… » détecté)."""
    return mentions_image(text) or classify([{"role": "user", "content": text}]).category in (
        Category.IMAGE_GEN, Category.IMAGE_EDIT)


def _first_image(content: Any) -> bytes | None:
    """Première image jointe (data URL) d'un message, pour l'édition d'image."""
    if not isinstance(content, list):
        return None
    for part in content:
        image = part.get("image_url") if isinstance(part, dict) else None
        url = image.get("url", "") if isinstance(image, dict) else ""
        if isinstance(url, str) and url.startswith("data:") and "," in url:
            encoded = url.split(",", 1)[1]
            if len(encoded) > (MAX_UPLOAD_BYTES + 2) // 3 * 4:
                raise HTTPException(413, "Image trop volumineuse (25 Mo maximum)")
            try:
                data = base64.b64decode(encoded, validate=True)
            except ValueError as exc:
                raise HTTPException(400, "Image jointe invalide") from exc
            if len(data) > MAX_UPLOAD_BYTES:
                raise HTTPException(413, "Image trop volumineuse (25 Mo maximum)")
            return data
    return None


def _clean(value: Any) -> Any:
    """Retire les demi-paires de substitution Unicode (« \\ud800 » isolé) : elles font échouer
    l'enregistrement et l'envoi aux modèles ; tout le reste du texte est conservé."""
    if isinstance(value, str):
        return value.encode("utf-8", "replace").decode("utf-8")
    if isinstance(value, list):
        return [_clean(v) for v in value]
    if isinstance(value, dict):
        return {_clean(k): _clean(v) for k, v in value.items()}
    return value


class SafeModel(BaseModel):
    """Corps de requête : textes assainis avant toute validation."""

    @model_validator(mode="before")
    @classmethod
    def _sanitize(cls, data: Any) -> Any:
        return _clean(data)


MAX_CONTENT_CHARS = 1_500_000
MAX_PARTS = 24


def _check_content(value: Any) -> Any:
    if isinstance(value, str):
        if len(value) > MAX_CONTENT_CHARS:
            raise ValueError("message trop long (1,5 million de caractères au maximum)")
        return value
    if not isinstance(value, list) or not value or len(value) > MAX_PARTS:
        raise ValueError("contenu invalide")
    total = 0
    for part in value:
        if not isinstance(part, dict) or not isinstance(part.get("type"), str):
            raise ValueError("partie de message invalide")
        if part["type"] == "text":
            if not isinstance(part.get("text"), str):
                raise ValueError("texte invalide")
            total += len(part["text"])
        elif part["type"] == "image_url":
            image = part.get("image_url")
            if not isinstance(image, dict) or not isinstance(image.get("url"), str):
                raise ValueError("image invalide")
        else:
            raise ValueError(f"type de partie inconnu : {part['type'][:30]}")
    if total > MAX_CONTENT_CHARS:
        raise ValueError("message trop long")
    return value


class ChatBody(SafeModel):
    conversation_id: str | None = Field(default=None, max_length=64)
    content: str | list[dict[str, Any]]
    model: str | None = Field(default=None, max_length=200)
    category: str | None = Field(default=None, max_length=40)
    strict: bool = False
    use_tools: bool = True
    # « general » ou « learn » (mode Apprendre) ; `level` : primaire, college, lycee…
    mode: str | None = Field(default=None, pattern="^(general|learn|agent)$")
    level: str | None = Field(default=None, pattern="^[a-z]{1,20}$")
    # Mode agent : « auto », « researcher », « developer », « writer », « analyst ».
    agent: str | None = Field(default=None, pattern="^[a-z]{1,20}$")
    # Orchestration multi-modèles (sous-tâches en parallèle puis fusion) : désactivée par
    # défaut ; une demande simple (complexité faible) suit toujours le flux normal.
    orchestrate: bool = False

    @field_validator("content")
    @classmethod
    def _content(cls, v: Any) -> Any:
        return _check_content(v)

    @field_validator("category")
    @classmethod
    def _category(cls, v: str | None) -> str | None:
        if v is None or v.startswith("file:"):
            return v
        try:
            Category(v)
        except ValueError as exc:
            raise ValueError("catégorie inconnue") from exc
        return v


class WorkspaceBody(SafeModel):
    path: str | None = Field(default=None, max_length=1024)


class LocalMediaBody(SafeModel):
    conversation_id: str | None = None
    content: str | list[dict[str, Any]]
    result_b64: str
    mime: str = "image/jpeg"
    kind: str = "image_edit"
    note: str = ""
    model_name: str = "Retouche locale (sur l'appareil)"


class EditBody(SafeModel):
    seq: int
    content: str
    model: str | None = None


class PinBody(SafeModel):
    pinned: bool


class MemoryBody(SafeModel):
    text: str
    kind: str = "fact"


class ResumeBody(SafeModel):
    approved: bool
    model: str | None = None
    avoid_model: str | None = Field(default=None, max_length=200)  # « autre modèle » après 👎


class FeedbackBody(SafeModel):
    uid: str = Field(min_length=8, max_length=64, pattern=r"^[0-9a-f]+$")
    rating: int = Field(ge=-1, le=1)
    reason: str = Field(default="", max_length=40,
                        pattern=r"^(|inexact|off_topic|too_long|too_short|language|other)$")


class ImportBody(SafeModel):
    url: str | None = Field(default=None, max_length=500)
    data: str | None = Field(default=None, max_length=importer.MAX_DATA)
    folder: str | None = Field(default=None, max_length=60)


class FolderShareBody(SafeModel):
    folder: str = Field(min_length=1, max_length=60)
    share: bool


class RenameBody(SafeModel):
    title: str | None = None
    folder: str | None = None


class PrefBody(SafeModel):
    scope: str = "global"            # global | conversation | category
    scope_key: str = ""
    model: str | None = None         # None ou « auto » : retour en Auto
    strict: bool = False


class CustomProviderBody(SafeModel):
    name: str = Field(min_length=1, max_length=60)
    base_url: str = Field(min_length=8, max_length=300)
    free: bool = True
    needs_key: bool = True
    price_in_per_m: float = Field(default=0.0, ge=0, le=1000)
    price_out_per_m: float = Field(default=0.0, ge=0, le=1000)
    key: str | None = Field(default=None, max_length=500)


class KeyBody(SafeModel):
    key: str
    persist: bool = True
    validate_key: bool = True   # l'application renvoie ses clés au démarrage sans revalider


class MediaBody(SafeModel):
    kind: str
    prompt: str = ""
    model: str | None = None
    conversation_id: str | None = None
    params: dict[str, Any] = {}


class RateLimiter:
    """Fenêtre glissante par clé (adresse du client) : au plus `limit` événements par
    `window` secondes. Mémoire bornée (les clés inactives sont oubliées)."""

    def __init__(self, limit: int, window: float) -> None:
        self.limit, self.window = limit, window
        self.hits: dict[str, list[float]] = {}

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        if len(self.hits) > 1000:
            self.hits = {k: v for k, v in self.hits.items() if v and now - v[-1] < self.window}
        recent = [t for t in self.hits.get(key, []) if now - t < self.window]
        if len(recent) >= self.limit:
            self.hits[key] = recent
            return False
        recent.append(now)
        self.hits[key] = recent
        return True


WS_MAX_CLIENTS = 16             # clients d'événements simultanés
WS_CONNECTS_PER_MINUTE = 30     # tentatives de connexion par adresse
TERM_MAX_MESSAGE = 64 * 1024    # octets par message vers le terminal
TERM_MESSAGES_PER_SECOND = 200  # saisie (collage compris) et redimensionnements


class Hub:
    """Diffusion des événements aux clients WebSocket."""

    def __init__(self) -> None:
        self.queues: set[asyncio.Queue[dict[str, Any]]] = set()

    def publish(self, event: dict[str, Any]) -> None:
        for q in list(self.queues):
            if q.qsize() < 200:
                q.put_nowait(event)


def create_app(
    settings: Settings | None = None, *, registry: ProviderRegistry | None = None,
    refresh: bool = True,
) -> FastAPI:
    hub = Hub()
    ws_connects = RateLimiter(WS_CONNECTS_PER_MINUTE, 60.0)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        core = await Core.start(settings, registry=registry, refresh=refresh)
        app.state.core = core
        core.catalog.on_changes(lambda ch: hub.publish({"type": "catalog_changes",
                                                        "changes": ch}))
        core.media.on_event(hub.publish)
        yield
        await core.stop()

    app = FastAPI(title="Tontolo", version=__version__, lifespan=lifespan)
    app.state.hub = hub

    def core_of(request: Request | WebSocket) -> Core:
        c: Core = request.app.state.core
        return c

    @app.middleware("http")
    async def auth(request: Request, call_next: Any) -> Response:
        core: Core | None = getattr(request.app.state, "core", None)
        token = core.settings.server.token if core else None
        # Anti-CSRF : une page web ne peut pas piloter le serveur local.
        if not origin_allowed(request.headers.get("origin")):
            return JSONResponse({"error": {"message": "Origine refusée"}}, status_code=403)
        # Anti-DNS rebinding : en écoute locale, seul un Host de boucle locale est accepté.
        bind = core.settings.server.host if core else "127.0.0.1"
        if bind in LOOPBACK and host_of(request.headers.get("host", "")) not in LOOPBACK_NAMES:
            return JSONResponse({"error": {"message": "Hôte refusé"}}, status_code=403)
        if token and request.url.path not in ("/health",):
            given = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
            if not hmac.compare_digest(given, token):
                return JSONResponse({"error": {"message": "Jeton invalide"}}, status_code=401)
        response: Response = await call_next(request)
        return response

    # --- Santé -----------------------------------------------------------

    @app.get("/health")
    async def health(request: Request) -> dict[str, Any]:
        core = core_of(request)
        return {"status": "ok", "version": __version__,
                "models": len(core.catalog.catalog.models),
                "catalog_updated_at": core.catalog.catalog.updated_at}

    # --- API compatible OpenAI -------------------------------------------

    @app.get("/v1/models")
    async def v1_models(request: Request) -> dict[str, Any]:
        core = core_of(request)
        usable = core.catalog.usable_providers()
        data = [{"id": "auto", "object": "model", "created": 0, "owned_by": "tontolo"}]
        for m in core.catalog.catalog.models.values():
            if m.provider in usable and (m.is_free or core.settings.paid.fallback != "off"):
                data.append({"id": m.key, "object": "model", "created": int(m.created or 0),
                             "owned_by": m.provider})
        return {"object": "list", "data": data}

    @app.post("/v1/chat/completions")
    async def v1_chat(request: Request) -> Any:
        core = core_of(request)
        body = await request.json()
        messages = body.get("messages") or []
        if not messages:
            raise HTTPException(400, "messages requis")
        stream = bool(body.get("stream"))
        params = {k: body[k] for k in ("temperature", "max_tokens", "top_p", "stop",
                                       "response_format", "tool_choice", "seed") if k in body}
        gen = core.router.run(messages, tools=body.get("tools"), stream=stream,
                              model=body.get("model"), params=params)
        cid = f"chatcmpl-{uuid.uuid4().hex[:24]}"
        created = int(time.time())
        if not stream:
            final: dict[str, Any] | None = None
            switches = []
            async for ev in gen:
                if ev["type"] == "done":
                    final = ev
                elif ev["type"] == "model_switched":
                    switches.append(ev)
                elif ev["type"] in ("error", "paid_confirmation"):
                    return JSONResponse({"error": {"message": ev.get("message")
                                                   or "Confirmation de paiement requise",
                                                   "type": ev["type"]}}, status_code=503)
            if final is None:
                raise HTTPException(503, "Aucun modèle disponible")
            return {
                "id": cid, "object": "chat.completion", "created": created,
                "model": final["model"],
                "choices": [{"index": 0, "message": final["message"],
                             "finish_reason": final.get("finish_reason") or (
                                 "tool_calls" if final["message"].get("tool_calls")
                                 else "stop")}],
                "usage": final.get("usage") or {},
                "tontolo": {"switches": switches, "profile": final.get("profile")},
            }

        async def sse() -> AsyncIterator[str]:
            model = "auto"
            async for ev in gen:
                t = ev["type"]
                if t == "route":
                    model = ev["model"]
                    yield f": tontolo route {model}\n\n"
                elif t == "delta":
                    delta = {k: v for k, v in ev.items() if k != "type"}
                    chunk = {"id": cid, "object": "chat.completion.chunk", "created": created,
                             "model": model, "choices": [{"index": 0, "delta": delta,
                                                          "finish_reason": None}]}
                    yield f"data: {dumps(chunk)}\n\n"
                elif t in ("model_switched", "stream_reset", "model_returned"):
                    if t == "model_switched":
                        model = ev["to"]
                    yield f"data: {dumps({'id': cid, 'object': 'tontolo.event', **ev})}\n\n"
                elif t == "done":
                    fr = "tool_calls" if ev["message"].get("tool_calls") else "stop"
                    chunk = {"id": cid, "object": "chat.completion.chunk", "created": created,
                             "model": ev["model"], "choices": [{"index": 0, "delta": {},
                                                                "finish_reason": fr}],
                             "usage": ev.get("usage") or None}
                    yield f"data: {dumps(chunk)}\n\n"
                elif t in ("error", "paid_confirmation"):
                    err = {"error": {"message": ev.get("message") or
                                     "Confirmation de paiement requise", "type": t}}
                    yield f"data: {dumps(err)}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(sse(), media_type="text/event-stream")

    @app.post("/v1/images/generations")
    async def v1_images(request: Request) -> Any:
        core = core_of(request)
        body = await request.json()
        job = await core.media.submit("image_gen", body.get("prompt", ""),
                                      model=body.get("model"),
                                      params={k: body[k] for k in ("size", "seed",
                                                                   "aspect_ratio") if k in body})
        done = await core.media.wait(job["id"])
        if not done or done["status"] != "done":
            return JSONResponse({"error": {"message": (done or {}).get("error")}},
                                status_code=503)
        data = Path(done["result_path"]).read_bytes()
        return {"created": int(time.time()), "model": done["model"],
                "data": [{"b64_json": base64.b64encode(data).decode(),
                          "media_type": done["params"].get("mime")}]}

    # --- Documents joints ---------------------------------------------------

    @app.post("/tontolo/documents")
    async def upload_document(request: Request, file: UploadFile = File(...),
                              conversation_id: str | None = Form(None)) -> dict[str, Any]:
        """Joint une pièce (PDF, bureautique, texte, code, archive, son, vidéo…) à une
        conversation (créée si besoin) : son texte sert à répondre en citant les pages."""
        import shutil

        core = core_of(request)
        name = Path(file.filename or "document").name[:120] or "document"
        kind = attachments.media_kind(name)
        big = kind == "video" and shutil.which("ffmpeg") is not None
        data = await _read_limited(file, MAX_VIDEO_BYTES if big else 0)
        if kind is not None:
            # Son ou vidéo : transcription par le service vocal (modèle gratuit routé).
            audio_name, audio = await _audio_track(name, data) if kind == "video" else (name, data)
            if len(audio) > MAX_UPLOAD_BYTES:
                raise HTTPException(413, "Vidéo trop longue à transcrire sur cet appareil "
                                         "(25 Mo maximum sans ffmpeg).")
            job = await core.media.submit("stt", input_bytes=audio, input_name=audio_name)
            done = await core.media.wait(job["id"])
            text = str(((done or {}).get("params") or {}).get("text") or "").strip()
            if not done or done["status"] != "done" or not text:
                raise HTTPException(422, "Transcription impossible pour l'instant : "
                                         + str((done or {}).get("error") or "aucun texte"))
            what = "de la vidéo" if kind == "video" else "de l'enregistrement"
            pages = [f"Transcription {what} « {name} » :\n{text}"]
        else:
            try:
                pages = await asyncio.to_thread(documents.extract_pages, name, data)
            except documents.DocumentError as exc:
                raise HTTPException(422, str(exc)) from exc
        cid = conversation_id
        if not cid or not await core.db.conversation_exists(cid):
            cid = await core.db.create_conversation(name[:60])
        doc_id = uuid.uuid4().hex
        # Long document (livre…) : fiche compacte calculée une fois, sur l'appareil.
        digest = (await asyncio.to_thread(documents.digest, pages)
                  if sum(len(p) for p in pages) > documents.LONG_DOC else "")
        await core.db.add_document(cid, doc_id, name, pages, digest)
        return {"id": doc_id, "conversation_id": cid, "name": name, "pages": len(pages),
                "chars": sum(len(p) for p in pages)}

    @app.get("/tontolo/conversations/{cid}/documents")
    async def list_documents(request: Request, cid: str) -> list[dict[str, Any]]:
        return await core_of(request).db.list_documents(cid)

    @app.delete("/tontolo/conversations/{cid}/documents/{doc_id}")
    async def delete_document(request: Request, cid: str, doc_id: str) -> dict[str, bool]:
        await core_of(request).db.delete_document(cid, doc_id)
        return {"ok": True}

    @app.post("/v1/audio/transcriptions")
    async def v1_transcribe(request: Request, file: UploadFile = File(...),
                            model: str = Form("auto"), language: str | None = Form(None)) -> Any:
        core = core_of(request)
        job = await core.media.submit("stt", model=model, input_bytes=await _read_limited(file),
                                      input_name=file.filename or "audio.wav",
                                      params={"language": language} if language else {})
        done = await core.media.wait(job["id"])
        if not done or done["status"] != "done":
            return JSONResponse({"error": {"message": (done or {}).get("error")}},
                                status_code=503)
        return {"text": done["params"].get("text", "")}

    @app.post("/v1/audio/speech")
    async def v1_speech(request: Request) -> Any:
        core = core_of(request)
        body = await request.json()
        job = await core.media.submit("tts", body.get("input", ""), model=body.get("model"),
                                      params={"voice": body.get("voice", "alloy")})
        done = await core.media.wait(job["id"])
        if not done or done["status"] != "done":
            return JSONResponse({"error": {"message": (done or {}).get("error")}},
                                status_code=503)
        if done["params"].get("local_tts"):
            return JSONResponse({"local_tts": True, "text": done["params"].get("text")},
                                status_code=200)
        return FileResponse(done["result_path"], media_type=done["params"].get("mime"))

    # --- API native : conversations ---------------------------------------


    async def _prefixed(first: list[dict[str, Any]],
                        gen: AsyncIterator[dict[str, Any]]) -> AsyncIterator[dict[str, Any]]:
        for ev in first:
            yield ev
        async for ev in gen:
            yield ev

    def _turn(core: Core, cid: str, gen: AsyncIterator[dict[str, Any]],
              first: list[dict[str, Any]] | None = None) -> StreamingResponse:
        """Lance un tour détaché (survit à la déconnexion du client) et diffuse son flux."""
        if core.turns.active(cid) is not None:
            raise HTTPException(409, "Une réponse est déjà en cours dans cette conversation")
        turn = core.turns.start(cid, _prefixed(first or [], gen))
        return _sse(turn.follow())

    def _sse(gen: AsyncIterator[dict[str, Any]]) -> StreamingResponse:
        async def run() -> AsyncIterator[str]:
            async for ev in gen:
                if ev["type"] in ("model_switched", "model_returned"):
                    hub.publish(ev)
                yield f"data: {dumps(ev)}\n\n"
            yield "data: {\"type\": \"end\"}\n\n"

        return StreamingResponse(run(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache",
                                          "X-Accel-Buffering": "no"})

    @app.post("/tontolo/chat")
    async def chat(request: Request, body: ChatBody) -> StreamingResponse:
        core = core_of(request)
        _first_image(body.content)  # valider avant de démarrer un tour détaché
        if body.conversation_id is None:
            core.catalog.refresh_in_background()  # veille « à chaque utilisation »
        file_kind = (body.category[5:] if body.category and body.category.startswith("file:")
                     else None)
        if file_kind is not None and not file_intent.valid(file_kind):
            raise HTTPException(400, "format de fichier inconnu")
        category = Category(body.category) if body.category and file_kind is None else None
        base_source: str | None = None
        if file_kind is None and body.category is None:
            # Avec ou sans photo : « traite l'exercice de la photo, rends la réponse en pdf ».
            file_kind = file_intent.detect(_text_of(body.content))
            if file_kind is None and body.conversation_id and not _first_image(body.content):
                # « Rajoute des détails », « traduis-la »… juste après un fichier créé :
                # on modifie CE fichier (même format, version précédente reprise).
                prev = await _last_file(core, body.conversation_id)
                if prev is not None and file_intent.is_revision(_text_of(body.content)):
                    file_kind, base_source = prev
        completed: str | None = None
        if (file_kind is None and body.category is None and body.conversation_id
                and not _first_image(body.content)):
            # Réponse aux questions posées avant une création : la création reprend, avec la
            # demande d'origine complétée par les choix (« Pour qui ? → Lycéens »).
            answer = _text_of(body.content)
            pend = clarify.pending_creation(await core.db.get_window(body.conversation_id, 6))
            if pend is not None and ("→" in answer or len(answer.split()) <= 12):
                file_kind, completed = pend[0], f"{pend[1]}\n{answer}"
        if file_kind is not None:
            category = None
        elif category is None:
            # Modalité détectée automatiquement (« dessine… », « crée la photo », « vas-y »
            # après une demande d'image…) : aucun mode à choisir pour l'utilisateur.
            prior: list[dict[str, Any]] = []
            if body.conversation_id and await core.db.conversation_exists(body.conversation_id):
                prior = await _media_history(core, body.conversation_id)
            detected = classify([*prior, {"role": "user", "content": body.content}]).category
            if detected.value in MEDIA_TURN_KINDS:
                category = detected
        # La conversation est créée d'abord : le tour lui est rattaché dès le départ.
        cid = body.conversation_id
        first: list[dict[str, Any]] = []
        if not cid or not await core.db.conversation_exists(cid):
            text = body.content if isinstance(body.content, str) else next(
                (p.get("text", "") for p in body.content if p.get("type") == "text"), "")
            cid = await core.db.create_conversation(text[:60].strip(), cid)
            first.append({"type": "conversation", "id": cid})
        body.conversation_id = cid
        if body.mode is not None:
            await core.db.set_mode(cid, f"learn:{body.level or 'lycee'}" if body.mode == "learn"
                                   else f"agent:{body.agent or 'auto'}" if body.mode == "agent"
                                   else "")
        if file_kind is not None and completed is None and base_source is None and (
                body.mode != "learn" and not _first_image(body.content)):
            questions = clarify.questions_for(file_kind, _text_of(body.content),
                                              core.settings.language)
            if questions:
                return _turn(core, cid, _ask_turn(core, cid, body, file_kind, questions), first)
        if file_kind is not None:
            return _turn(core, cid, _file_turn(core, body, file_kind, base_source, completed),
                         first)
        if ((body.orchestrate or core.settings.orchestrate) and core.orchestrator is not None
                and category is None
                and not _first_image(body.content) and body.mode != "learn"):
            plan = await core.orchestrator.decomposer.decompose(_text_of(body.content))
            # NOTE: Choix autonome - complexité faible : aucune orchestration (zéro latence
            # ajoutée, le découpage par expressions régulières prend moins d'une milliseconde).
            if plan.complexity != "low":
                return _turn(core, cid, _orchestrated_turn(core, cid, body, plan), first)
        if category is not None and category.value in MEDIA_TURN_KINDS:
            return _turn(core, cid, _media_turn(core, body, category), first)
        return _turn(core, cid, _text_turn(core, body, cid, category), first)

    async def _text_turn(core: Core, body: ChatBody, cid: str,
                         category: Category | None) -> AsyncIterator[dict[str, Any]]:
        """Tour de texte avec **bascule automatique** : si le modèle répond qu'il ne sait pas
        générer d'image alors que l'utilisateur en demandait une, on passe à la génération."""
        text = _text_of(body.content)
        user_seq = 0
        switch = False
        topic = ""
        final: dict[str, Any] | None = None
        async for ev in core.chat.send(cid, body.content, model=body.model, forced=category,
                                       strict=body.strict, use_tools=body.use_tools):
            if ev["type"] == "route":
                topic = str((ev.get("profile") or {}).get("category") or "")
            if ev["type"] == "done":
                final = ev
            if ev["type"] == "user_saved":
                user_seq = int(ev.get("seq") or 0)
            if (ev["type"] == "done" and _wants_image(text)
                    and looks_like_image_refusal(str((ev.get("message") or {}).get("content")))):
                switch = True
                break                     # on ne montre pas le refus
            yield ev
        answer = str(((final or {}).get("message") or {}).get("content") or "")
        if (not switch and final is not None and core.settings.team_review
                and topic in REVIEWED_TOPICS and len(answer) > 80
                and not (final.get("message") or {}).get("tool_calls")):
            # Équipe de modèles : un second modèle d'une autre famille vérifie la réponse.
            yield {"type": "step", "step": "answer_reviewing"}
            # Le relecteur voit ce que le rédacteur a vu : documents joints et fin du fil (sans
            # quoi il prend le contenu d'un fichier joint pour une invention).
            doc = await core.chat._documents_block(cid, text)
            recent = await core.db.get_window(cid, 8)
            thread = "\n".join(f"[{m['role']}] {_text_of(m.get('content') or '')[:1500]}"
                               for m in recent[:-2] if m.get("role") in ("user", "assistant"))
            context = (str(doc["content"]) if doc else "") + ("\n\n" + thread if thread else "")
            verdict = await core.creator.review_answer(text, answer, str(final.get("model")),
                                                       context=context)
            yield {"type": "review", **verdict} if verdict else {"type": "step",
                                                                 "step": "doc_done"}
        if switch and user_seq:
            await core.db.truncate_after(cid, user_seq)
            yield {"type": "media_switch"}
            kind = Category.IMAGE_EDIT if _first_image(body.content) else Category.IMAGE_GEN
            async for ev in _media_turn(core, body, kind, add_user=False):
                yield ev

    async def _orchestrated_turn(core: Core, cid: str, body: ChatBody, plan: Any
                                 ) -> AsyncIterator[dict[str, Any]]:
        """Demande composée : sous-tâches en parallèle (puis dépendantes), fusion, mesures."""
        recent = await core.db.get_window(cid, 6)
        context = "\n".join(f"[{m['role']}] {_text_of(m.get('content') or '')[:1000]}"
                            for m in recent if m.get("role") in ("user", "assistant"))
        user = await core.db.add_message(cid, {"role": "user", "content": body.content})
        yield {"type": "user_saved", "uid": user["uid"], "seq": user["seq"]}
        yield {"type": "orchestration", "complexity": plan.complexity,
               "subtasks": [{"index": s.index, "text": s.text[:200],
                             "category": s.category.value, "depends": s.depends}
                            for s in plan.subtasks]}
        if core.orchestrator is None:
            return
        out = await core.orchestrator.run(plan, context)
        msg = {"role": "assistant", "content": out["text"]}
        saved = await core.db.add_message(cid, msg, model=out["model"] or None)
        model = core.router.catalog.catalog.get(out["model"]) if out["model"] else None
        yield {"type": "done", "message": msg, "model": out["model"],
               "name": model.name if model else out["model"], "metrics": out["metrics"],
               "uid": saved["uid"], "conversation_id": cid}

    async def _ask_turn(core: Core, cid: str, body: ChatBody, kind: str,
                        questions: list[dict[str, Any]]) -> AsyncIterator[dict[str, Any]]:
        """Création longue mal précisée : questions à choix d'abord (aucun appel de modèle)."""
        await core.db.add_message(cid, {"role": "user", "content": body.content})
        for m in clarify.ask_messages(kind, _text_of(body.content), questions):
            await core.db.add_message(cid, m)
        yield {"type": "question", "conversation_id": cid, "questions": questions}

    async def _file_turn(core: Core, body: ChatBody, kind: str, base_source: str | None = None,
                         request: str | None = None) -> AsyncIterator[dict[str, Any]]:
        """Création d'un fichier (DOCX, PDF, carte mentale…) par l'équipe de modèles :
        rédaction, vérification, correction ; le résultat est une carte « fichier »."""
        cid = str(body.conversation_id)
        text = request or _text_of(body.content)
        history = await core.db.get_window(cid, 12)
        context = "\n\n".join(
            f"[{m['role']}] {_text_of(m['content'])[:3000]}" for m in history[-6:]
            if m["role"] in ("user", "assistant") and not str(m["content"]).startswith("[média:")
        )[-9000:]
        # Matière à transformer (« convertis ce HTML en PDF », « mets ce document en Word ») :
        # documents joints à la discussion et source du dernier fichier créé, en entier.
        material = await _file_material(core, cid, skip_last=base_source is not None,
                                        request=text)
        if material:
            context = f"{material}\n\n{context}"
        await core.db.add_message(cid, {"role": "user", "content": body.content})
        done: dict[str, Any] = {}
        images = [str((p.get("image_url") or {}).get("url"))
                  for p in (body.content if isinstance(body.content, list) else [])
                  if isinstance(p, dict) and p.get("type") == "image_url"][:3]
        async for ev in core.creator.create(kind, text, conversation_id=cid, context=context,
                                            base=base_source, images=images):
            if ev["type"] == "job":
                done = ev
            yield ev
        job = {k: v for k, v in done.items() if k != "type"}
        _keep_draft(core, cid, job)
        note = f"[média:{job['id']}]"
        msg = await core.db.add_message(cid, {"role": "assistant", "content": note},
                                        model=job.get("model"))
        yield {"type": "done", "message": {"role": "assistant", "content": note},
               "model": job.get("model"), "uid": msg["uid"], "conversation_id": cid,
               "name": (job.get("params") or {}).get("model_name"), "job": job}

    async def _media_turn(core: Core, body: ChatBody, category: Category,
                          add_user: bool = True) -> AsyncIterator[dict[str, Any]]:
        """Tour de conversation dont le résultat est un média (image, voix, vidéo)."""
        text = _text_of(body.content)
        cid = body.conversation_id
        if not cid or not await core.db.conversation_exists(cid):
            cid = await core.db.create_conversation(text[:60])
            yield {"type": "conversation", "id": cid}
        if add_user:
            await core.db.add_message(cid, {"role": "user", "content": body.content})
        image = _first_image(body.content)
        source_job_id = None
        needs_image = category == Category.IMAGE_EDIT or (
            category == Category.VIDEO_GEN and _references_image(text))
        if image is None and needs_image:
            image, source_job_id = await _image_source(core, cid)
            if image is None:
                yield {"type": "error", "code": "media_reference_missing",
                       "message": "Aucune image disponible dans cette discussion. "
                                  "Joignez une image ou régénérez la création échouée."}
                return
        prompt = await _media_prompt(core, cid, text)
        if category in (Category.IMAGE_GEN, Category.VIDEO_GEN, Category.IMAGE_EDIT):
            prompt = await _english_prompt(core, prompt)
        job = await core.media.submit(category.value, prompt, conversation_id=cid,
                                      model=body.model, input_bytes=image,
                                      params={"source_job_id": source_job_id,
                                              "input_mode": "image" if image else "text"},
                                      input_name="image.png")
        yield {"type": "job", **job}
        done = await core.media.wait(job["id"]) or job
        yield {"type": "job", **done}
        note = f"[média:{done['id']}]"      # l'état (réussi ou échec) est lu dans le job
        msg = await core.db.add_message(cid, {"role": "assistant", "content": note},
                                        model=done.get("model"))
        yield {"type": "done", "message": {"role": "assistant", "content": note},
               "model": done.get("model"), "uid": msg["uid"], "conversation_id": cid,
               "name": (done.get("params") or {}).get("model_name"),
               "job": done}


    @app.post("/tontolo/chat/{cid}/resume")
    async def resume(request: Request, cid: str, body: ResumeBody) -> StreamingResponse:
        core = core_of(request)
        return _turn(core, cid, core.chat.resume(cid, approved=body.approved, model=body.model))

    @app.post("/tontolo/chat/{cid}/regenerate")
    async def regenerate(request: Request, cid: str, body: ResumeBody | None = None
                         ) -> StreamingResponse:
        core = core_of(request)
        if core.turns.active(cid) is not None:
            raise HTTPException(409, "Une réponse est déjà en cours dans cette conversation")
        history = await core.db.get_messages(cid)
        last_user = next((m for m in reversed(history) if m["role"] == "user"), None)
        if last_user is not None:
            earlier = await _media_history(core, cid, history[:history.index(last_user)])
            kind = classify([*earlier, {"role": "user", "content": last_user["content"]}]).category
            if kind.value in MEDIA_TURN_KINDS:
                # Une demande d'image/voix se relance comme un média, pas comme du texte.
                await core.db.truncate_after(cid, last_user["_meta"]["seq"])
                media_body = ChatBody(conversation_id=cid, content=last_user["content"],
                                      model=body.model if body else None)
                return _turn(core, cid, _media_turn(core, media_body, kind, add_user=False))
        avoid = frozenset({body.avoid_model}) if body and body.avoid_model else frozenset()
        return _turn(core, cid, core.chat.regenerate(cid, model=body.model if body else None,
                                                     avoid=avoid))

    @app.post("/tontolo/chat/{cid}/edit")
    async def edit_message(request: Request, cid: str, body: EditBody) -> StreamingResponse:
        core = core_of(request)
        if core.turns.active(cid) is not None:
            raise HTTPException(409, "Une réponse est déjà en cours dans cette conversation")
        history = await core.db.get_messages(cid)
        target = next((m for m in history if m["_meta"]["seq"] == body.seq), None)
        if target is not None and target["role"] == "user":
            earlier = await _media_history(core, cid,
                                          [m for m in history if m["_meta"]["seq"] < body.seq])
            kind = classify([*earlier, {"role": "user", "content": body.content}]).category
            if kind.value in MEDIA_TURN_KINDS:
                # Message modifié en demande d'image/vidéo/voix : média, pas texte.
                await core.db.edit_message(cid, body.seq, {"role": "user", "content": body.content})
                await core.db.truncate_after(cid, body.seq)
                media_body = ChatBody(conversation_id=cid, content=body.content, model=body.model)
                return _turn(core, cid, _media_turn(core, media_body, kind, add_user=False))
        return _turn(core, cid, core.chat.edit_and_resend(cid, body.seq, body.content,
                                                          model=body.model))

    @app.get("/tontolo/chat/{cid}/stream")
    async def follow_turn(request: Request, cid: str) -> StreamingResponse:
        """Se rattacher au tour en cours (ou tout juste terminé) d'une conversation."""
        turn = core_of(request).turns.get(cid)

        async def empty() -> AsyncIterator[dict[str, Any]]:
            return
            yield {}

        return _sse(turn.follow() if turn is not None else empty())

    @app.post("/tontolo/chat/{cid}/stop")
    async def stop_turn(request: Request, cid: str) -> dict[str, bool]:
        return {"stopped": await core_of(request).turns.stop(cid)}

    @app.post("/tontolo/chat/local-media")
    async def local_media(request: Request, body: LocalMediaBody) -> dict[str, Any]:
        """Enregistre dans la conversation une retouche **faite sur l'appareil** (la photo n'a
        été envoyée à aucun service) : message, fichier, entrée de la galerie."""
        core = core_of(request)
        if len(body.result_b64) > 34_000_000:
            raise HTTPException(413, "Image trop volumineuse (25 Mo maximum)")
        try:
            data = base64.b64decode(body.result_b64, validate=True)
        except ValueError as exc:
            raise HTTPException(400, "Image invalide") from exc
        if body.kind not in ("image_edit", "image_gen"):
            raise HTTPException(400, "type invalide")
        text = _text_of(body.content)
        cid = body.conversation_id
        if not cid or not await core.db.conversation_exists(cid):
            cid = await core.db.create_conversation(text[:60].strip(), cid)
        await core.db.add_message(cid, {"role": "user", "content": body.content})
        job_id = uuid.uuid4().hex
        from tontolo.media.providers import ext_for

        path = core.media.dir / body.kind / f"{job_id}.{ext_for(body.mime)}"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        job = {"id": job_id, "kind": body.kind, "status": "done", "model": "local:retouche",
               "prompt": text, "result_path": str(path), "conversation_id": cid,
               "created_at": time.time(),
               "params": {"mime": body.mime, "warning": body.note,
                          "model_name": body.model_name}}
        await core.db.upsert_job(job)
        msg = await core.db.add_message(cid, {"role": "assistant",
                                              "content": f"[média:{job_id}]"},
                                        model="local:retouche")
        await core.media.purge()
        return {"conversation_id": cid, "job": job, "uid": msg["uid"]}

    @app.post("/tontolo/chat/{cid}/approve-paid")
    async def approve_paid(request: Request, cid: str) -> dict[str, bool]:
        core_of(request).router.approve_paid(cid)
        return {"ok": True}

    @app.get("/tontolo/conversations")
    async def conversations(request: Request, q: str | None = None, limit: int = 50,
                            offset: int = 0, folder: str | None = None) -> list[dict[str, Any]]:
        core = core_of(request)
        rows = await core.db.list_conversations(min(limit, 500), offset, q, folder)
        for c in rows:  # pastilles : en cours sur cet appareil / attend une réponse
            c["running"] = core.turns.active(c["id"]) is not None
            c["waiting"] = core.turns.waiting.get(c["id"], "")
        return rows

    @app.get("/tontolo/conversations/{cid}")
    async def conversation(request: Request, cid: str, after: int = 0,
                           limit: int | None = None, tail: int | None = None,
                           before: int | None = None) -> dict[str, Any]:
        """`tail=N` : les N derniers messages ; `before=seq&tail=N` : les N précédents (début
        d'un long fil chargé à la demande). `total` : nombre de messages du fil."""
        db = core_of(request).db
        if not await db.conversation_exists(cid):
            raise HTTPException(404, "Conversation introuvable")
        summary, covered = await db.get_summary(cid)
        messages = (await db.get_window(cid, tail, before) if tail
                    else await db.get_messages(cid, after, limit))
        return {"id": cid, "messages": messages, "total": await db.count_messages(cid),
                "feedback": await db.feedback_of(cid),
                "mode": await db.get_mode(cid), "summary": summary, "summary_covered": covered,
                "plan": planner.public(await db.get_plan(cid)),
                "active": core_of(request).turns.active(cid) is not None}

    @app.delete("/tontolo/conversations/{cid}/plan")
    async def drop_plan(request: Request, cid: str) -> dict[str, bool]:
        """Abandonner le plan en cours (la discussion continue normalement)."""
        await core_of(request).db.set_plan(cid, None)
        return {"ok": True}

    @app.post("/tontolo/conversations/{cid}/compact")
    async def compact_conversation(request: Request, cid: str) -> dict[str, Any]:
        """Compactage manuel : fiche structurée du début du fil (messages conservés)."""
        core = core_of(request)
        if not await core.db.conversation_exists(cid):
            raise HTTPException(404, "Conversation introuvable")
        ok = await core.chat.compact(cid)
        summary, covered = await core.db.get_summary(cid)
        return {"ok": ok, "summary": summary, "summary_covered": covered}


    @app.patch("/tontolo/conversations/{cid}")
    async def rename(request: Request, cid: str, body: RenameBody) -> dict[str, bool]:
        db = core_of(request).db
        if body.title is not None:
            await db.rename_conversation(cid, body.title)
        if body.folder is not None:
            await db.set_folder(cid, body.folder)
        return {"ok": True}

    @app.post("/tontolo/import")
    async def import_conversation(request: Request, body: ImportBody) -> dict[str, Any]:
        """Importe une discussion (lien de partage Claude/ChatGPT/Gemini, JSON ou texte) pour
        la continuer ici. Erreur 422 `{code, message, …}` ; `import_browser` demande à
        l'application d'ouvrir le lien dans une vue web puis de renvoyer `data`."""
        db = core_of(request).db
        try:
            if body.data:
                found = importer.parse_any(body.data)
            elif body.url:
                found = [await importer.fetch(body.url)]
            else:
                raise importer.ConversationImportError("import_empty", "Rien à importer.")
        except importer.ConversationImportError as exc:
            raise HTTPException(422, {"code": exc.code, "message": str(exc), **exc.extra}
                                ) from exc
        out = []
        for conv in found:
            cid = await db.create_conversation(conv.title)
            for m in conv.messages:
                await db.add_message(cid, {"role": m["role"], "content": m["text"]},
                                     model=f"import:{conv.source}" if m["role"] == "assistant"
                                     else None)
            if body.folder:
                await db.set_folder(cid, body.folder)
            out.append({"id": cid, "title": conv.title, "count": len(conv.messages),
                        "source": conv.source})
        return {"conversations": out}

    @app.get("/tontolo/folders")
    async def folders(request: Request) -> list[dict[str, Any]]:
        core = core_of(request)
        shared = set(core.settings.shared_folders)
        return [{**f, "shared": f["folder"] in shared} for f in await core.db.list_folders()]

    @app.put("/tontolo/folders/share")
    async def share_folder(request: Request, body: FolderShareBody) -> dict[str, bool]:
        """Active ou coupe le partage de contexte entre les discussions d'un dossier."""
        core = core_of(request)
        shared = [f for f in core.settings.shared_folders if f != body.folder]
        if body.share:
            shared.append(body.folder)
        core.settings.shared_folders = shared
        save_settings(core.settings)
        return {"ok": True}

    @app.put("/tontolo/conversations/{cid}/pin")
    async def pin(request: Request, cid: str, body: PinBody) -> dict[str, bool]:
        await core_of(request).db.pin_conversation(cid, body.pinned)
        return {"ok": True}

    @app.get("/tontolo/conversations/{cid}/export")
    async def export(request: Request, cid: str) -> Response:
        """Export Markdown d'une conversation (partage, archivage)."""
        db = core_of(request).db
        if not await db.conversation_exists(cid):
            raise HTTPException(404, "Conversation introuvable")
        convs = {c["id"]: c for c in await db.list_conversations(limit=10_000)}
        title = convs.get(cid, {}).get("title") or "Conversation"
        lines = [f"# {title}", ""]
        for m in await db.get_messages(cid):
            if m["role"] not in ("user", "assistant"):
                continue
            content = m.get("content")
            if isinstance(content, list):
                content = "\n".join(p.get("text", "[image]") for p in content)
            if not content:
                continue
            who = "**Vous**" if m["role"] == "user" else f"**Tontolo** · _{m['_meta']['model']}_"
            lines += [who, "", str(content), ""]
        return Response("\n".join(lines), media_type="text/markdown; charset=utf-8")

    @app.delete("/tontolo/conversations/{cid}")
    async def delete_conv(request: Request, cid: str) -> dict[str, bool]:
        core = core_of(request)
        await core.db.delete_conversation(cid)
        with contextlib.suppress(OSError, ValueError):
            core.chat.tasks.delete(cid)  # résultats intermédiaires effacés avec la discussion
        return {"ok": True}

    @app.get("/tontolo/conversations/{cid}/tasks")
    async def task_items(request: Request, cid: str) -> list[dict[str, Any]]:
        """Résultats intermédiaires de la tâche (parties, étapes, sorties, brouillons)."""
        try:
            return core_of(request).chat.tasks.items(cid)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.get("/tontolo/conversations/{cid}/tasks/{item_id}")
    async def task_item(request: Request, cid: str, item_id: str) -> dict[str, Any]:
        store = core_of(request).chat.tasks
        try:
            item = store.get(cid, item_id)
            text = store.read(cid, item_id, 0, MAX_TASK_VIEW)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        if item is None or text is None:
            raise HTTPException(404, "Élément introuvable")
        return {**item, "content": text}

    @app.get("/tontolo/cloud/tasks")
    async def cloud_tasks(request: Request, since: float = 0) -> dict[str, Any]:
        """Résultats intermédiaires modifiés depuis `since`, avec leur contenu (chiffrés par
        l'application avant envoi)."""
        store = core_of(request).chat.tasks
        out, until = [], since
        for cid, item in store.changed_since(since):
            until = max(until, float(item.get("updated") or 0))
            out.append({**item, "conversation_id": cid,
                        "content": store.read(cid, item["id"], 0, 1_000_000) or ""})
        return {"items": out, "until": until}

    @app.post("/tontolo/cloud/tasks")
    async def cloud_tasks_import(request: Request) -> dict[str, int]:
        store = core_of(request).chat.tasks
        body = await request.json()
        applied = 0
        for it in (body.get("items") or [])[:50]:
            try:
                cid, iid = str(it["conversation_id"]), str(it["id"])
                mine = store.get(cid, iid)
                if mine is not None and float(mine.get("updated") or 0) >= float(it["updated"]):
                    continue
                store.put(cid, str(it["kind"]), str(it.get("title") or ""),
                          str(it.get("content") or ""), item_id=iid,
                          created=float(it.get("created") or 0) or None,
                          updated=float(it["updated"]))
                applied += 1
            except (KeyError, TypeError, ValueError, OSError):
                continue
        return {"applied": applied}

    # --- Catalogue, nouveautés, préférences --------------------------------

    def _model_json(m: ModelInfo, usable: set[str],
                    quota: QuotaManager | None = None) -> dict[str, Any]:
        return {
            "key": m.key, "id": m.model_id, "provider": m.provider, "name": m.name,
            "family": m.family, "max_output": m.max_output,
            "inputs": m.input_modalities, "outputs": m.output_modalities,
            # Agentique : sait appeler des outils (recherche, fichiers, calcul…).
            "agentic": m.supports_tools and m.is_text,
            "free": m.is_free, "usable": m.provider in usable, "tools": m.supports_tools,
            "vision": m.supports_vision, "context": m.context_length, "media": m.media,
            "quality": m.quality, "speed": m.speed, "provisional": m.provisional,
            "rate_limit": m.rate_limit, "created": m.created,
            "price_in": m.price_in, "price_out": m.price_out,
            "available_at": quota.available_at(m) if quota is not None else 0.0,
            **_quota_json(m, quota),
        }

    def _quota_json(m: ModelInfo, quota: QuotaManager | None) -> dict[str, Any]:
        if quota is None:
            return {"status": "available"}
        st = quota.status_of(m)
        return {"status": st.status, "wait_reason": st.reason}

    @app.get("/tontolo/catalog")
    async def catalog(request: Request, category: str | None = None, free: bool = True,
                      usable: bool = False, q: str | None = None,
                      limit: int = 100) -> dict[str, Any]:
        core = core_of(request)
        usable_set = core.catalog.usable_providers()
        if category is not None:
            try:
                Category(category)
            except ValueError as exc:
                raise HTTPException(400, "catégorie inconnue") from exc
        models = core.catalog.catalog.filter(category=category, free_only=free,
                                             usable=usable_set if usable else None)
        if q:
            ql = q.lower()
            models = [m for m in models if ql in m.key.lower() or ql in m.name.lower()]
        return {"updated_at": core.catalog.catalog.updated_at,
                "sources": core.catalog.catalog.sources,
                "models": [_model_json(m, usable_set, core.router.quota)
                           for m in models[:limit]]}

    @app.get("/tontolo/generators")
    async def generators(request: Request) -> dict[str, Any]:
        """Générateurs d'images, de vidéos et de sons, par type : prêts d'abord (gratuits
        puis payants), puis ceux qui demandent une clé."""
        core = core_of(request)
        usable_set = core.catalog.usable_providers()
        out: dict[str, list[dict[str, Any]]] = {}
        for kind in ("image_gen", "image_edit", "video_gen", "tts", "stt", "music_sfx"):
            models = core.catalog.catalog.filter(category=kind)
            models.sort(key=lambda m: (m.provider not in usable_set, not m.is_free))
            out[kind] = [_model_json(m, usable_set, core.router.quota) for m in models[:40]]
        return {"kinds": out}

    @app.post("/tontolo/catalog/refresh")
    async def refresh_catalog(request: Request) -> dict[str, Any]:
        changes = await core_of(request).catalog.refresh(force=True)
        return {"changes": len(changes)}

    @app.get("/tontolo/online")
    async def online(request: Request) -> dict[str, bool]:
        return {"online": await core_of(request).router.probe()}

    @app.get("/tontolo/health")
    async def model_health(request: Request) -> dict[str, Any]:
        return await core_of(request).router.health()

    @app.get("/tontolo/status")
    async def status(request: Request) -> dict[str, Any]:
        core = core_of(request)
        return {"quotas": core.router.quota.snapshot(),
                "usable_providers": sorted(core.catalog.usable_providers()),
                "catalog_updated_at": core.catalog.catalog.updated_at,
                "sources": core.catalog.catalog.sources,
                "mcp_errors": core.mcp.errors}

    @app.post("/tontolo/route")
    async def route_preview(request: Request) -> dict[str, Any]:
        """« Pourquoi ce modèle ? » : décision sans appel au fournisseur."""
        core = core_of(request)
        body = await request.json()
        d = await core.router.decide(body.get("messages") or [],
                                     conversation_id=body.get("conversation_id"),
                                     model=body.get("model"))
        return {"profile": d.profile.as_dict(),
                "chain": [dict(c.reason(d.profile.category), model=c.model.key,
                               name=c.model.name) for c in d.chain[:10]]}

    @app.get("/tontolo/changes")
    async def changes(request: Request, limit: int = 100) -> list[dict[str, Any]]:
        return await core_of(request).db.list_changes(limit)

    @app.post("/tontolo/changes/seen")
    async def changes_seen(request: Request) -> dict[str, bool]:
        await core_of(request).db.mark_changes_seen()
        return {"ok": True}

    @app.get("/tontolo/preferences")
    async def get_prefs(request: Request) -> list[dict[str, Any]]:
        return await core_of(request).db.get_preferences()


    @app.put("/tontolo/preferences")
    async def put_pref(request: Request, body: PrefBody) -> dict[str, bool]:
        if body.scope not in ("global", "conversation", "category"):
            raise HTTPException(400, "portée invalide")
        model = None if body.model in (None, "", "auto") else body.model
        await core_of(request).db.set_preference(body.scope, body.scope_key, model,
                                                 body.strict)
        return {"ok": True}

    # --- Fournisseurs et clés (BYOK) --------------------------------------

    @app.get("/tontolo/providers")
    async def providers(request: Request) -> list[dict[str, Any]]:
        core = core_of(request)
        counts: dict[str, int] = {}
        paid_counts: dict[str, int] = {}
        for m in core.catalog.catalog.models.values():
            target = counts if m.is_free else paid_counts
            target[m.provider] = target.get(m.provider, 0) + 1
        return [{**{k: v for k, v in p.items() if k not in ("base_url", "or_prefix")},
                 "has_key": secrets.has_key(pid), "free_models": counts.get(pid, 0),
                 "paid_models": paid_counts.get(pid, 0), "i18n": provider_texts(pid, p)}
                for pid, p in sorted(core.catalog.catalog.providers.items())]


    @app.put("/tontolo/keys/{provider}")
    async def put_key(request: Request, provider: str, body: KeyBody) -> dict[str, Any]:
        core = core_of(request)
        ok, detail = (await _validate_key(core, provider, body.key.strip())
                      if body.validate_key else (True, "Clé chargée"))
        if ok:
            secrets.set_key(provider, body.key.strip(), persist=body.persist)
            core.router.registry.reset()
            core.catalog.refresh_in_background()
        return {"valid": ok, "detail": detail}

    @app.delete("/tontolo/keys/{provider}")
    async def delete_key(request: Request, provider: str) -> dict[str, bool]:
        secrets.delete_key(provider)
        core_of(request).router.registry.reset()
        return {"ok": True}

    # --- Réglages ----------------------------------------------------------

    @app.get("/tontolo/settings")
    async def get_settings(request: Request) -> dict[str, Any]:
        data = core_of(request).settings.model_dump(mode="json")
        data["server"].pop("token", None)
        return data

    @app.put("/tontolo/settings")
    async def put_settings(request: Request) -> dict[str, Any]:
        core = core_of(request)
        patch = await request.json()
        patch.pop("server", None)  # jamais modifiable à distance
        patch.pop("custom_providers", None)  # points d'accès dédiés, sur l'appareil seulement
        if isinstance(patch.get("agent"), dict):
            patch["agent"].pop("workdir", None)  # dossier des outils fichiers : local seulement
        merged = core.settings.model_dump(mode="json")
        for k, v in patch.items():
            if isinstance(v, dict) and isinstance(merged.get(k), dict):
                merged[k].update(v)
            else:
                merged[k] = v
        new = Settings.model_validate(merged)
        for field_name in type(new).model_fields:
            setattr(core.settings, field_name, getattr(new, field_name))
        save_settings(core.settings)
        return await get_settings(request)

    # --- Médias -----------------------------------------------------------


    @app.post("/tontolo/media")
    async def media_submit(request: Request, body: MediaBody) -> dict[str, Any]:
        try:
            return await core_of(request).media.submit(
                body.kind, body.prompt, params=body.params, model=body.model,
                conversation_id=body.conversation_id)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post("/tontolo/media/upload")
    async def media_upload(request: Request, kind: str = Form(...), prompt: str = Form(""),
                           model: str | None = Form(None),
                           file: UploadFile = File(...)) -> dict[str, Any]:
        return await core_of(request).media.submit(
            kind, prompt, model=model, input_bytes=await _read_limited(file),
            input_name=file.filename or "fichier")

    @app.get("/tontolo/media")
    async def media_list(request: Request, kind: str | None = None,
                         status: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        return await core_of(request).db.list_jobs(limit, status, kind)

    @app.get("/tontolo/media/{job_id}")
    async def media_get(request: Request, job_id: str) -> dict[str, Any]:
        job = await core_of(request).db.get_job(job_id)
        if not job:
            raise HTTPException(404, "Job introuvable")
        return job

    @app.get("/tontolo/media/{job_id}/file")
    async def media_file(request: Request, job_id: str) -> FileResponse:
        core = core_of(request)
        job = await core.db.get_job(job_id)
        if not job or not job.get("result_path") or not Path(job["result_path"]).exists():
            raise HTTPException(404, "Fichier introuvable")
        path = Path(job["result_path"]).resolve()
        if not path.is_relative_to(core.media.dir.resolve()):
            raise HTTPException(403, "Accès refusé")
        mime = safe_mime(job["params"].get("mime"))
        headers = {"X-Content-Type-Options": "nosniff",
                   "Content-Security-Policy": "sandbox; default-src 'none'"}
        if mime in ACTIVE_MIMES:  # page, SVG, XML : téléchargés, jamais affichés par le cœur
            headers["Content-Disposition"] = f'attachment; filename="{path.name}"'
            mime = "application/octet-stream"
        return FileResponse(path, media_type=mime, headers=headers)

    @app.delete("/tontolo/media/{job_id}")
    async def media_delete(request: Request, job_id: str) -> dict[str, bool]:
        core = core_of(request)
        job = await core.db.get_job(job_id)
        if job and job.get("result_path"):
            Path(job["result_path"]).unlink(missing_ok=True)
        await core.db.delete_job(job_id)
        return {"ok": True}

    # --- Dépenses, synchronisation, MCP, mise à jour ---------------------

    @app.post("/tontolo/feedback")
    async def feedback(request: Request, body: FeedbackBody) -> dict[str, Any]:
        """👍 / 👎 sur une réponse (0 : annuler). Renvoie le modèle et le type de demande, que
        l'application peut partager anonymement (jamais le texte)."""
        out = await core_of(request).chat.rate(body.uid, body.rating, body.reason)
        if out is None:
            raise HTTPException(404, "Réponse introuvable")
        return out

    @app.put("/tontolo/feedback/global")
    async def feedback_global(request: Request) -> dict[str, int]:
        """Notes collectives anonymes (fonction Supabase `model_scores`), relayées par l'app."""
        core = core_of(request)
        body = await request.json()
        rows = body.get("scores") if isinstance(body, dict) else None
        kept = core.router.set_global_scores(rows if isinstance(rows, list) else [])
        await core.db.kv_set("global_scores", json.dumps(
            [{"model": m, "category": c, "score": v, "devices": 999}
             for (m, c), v in core.router.reliability.global_scores.items()]))
        return {"kept": kept}

    @app.get("/tontolo/answers")
    async def answers_info(request: Request) -> dict[str, Any]:
        """Réponses déjà données gardées sur l'appareil (cache sémantique)."""
        core = core_of(request)
        return {"enabled": core.settings.answer_cache, "count": await core.db.count_answers()}

    @app.delete("/tontolo/answers")
    async def answers_clear(request: Request) -> dict[str, int]:
        core = core_of(request)
        removed = await core.db.delete_answers()
        core.chat.answers.invalidate()
        return {"removed": removed}

    @app.get("/tontolo/memory")
    async def memory_list(request: Request) -> dict[str, Any]:
        core = core_of(request)
        return {"enabled": core.settings.memory_enabled,
                "items": await core.db.list_memories()}

    @app.post("/tontolo/memory")
    async def memory_add(request: Request, body: MemoryBody) -> dict[str, bool]:
        ok = await core_of(request).chat.memory.remember(
            body.text, "instruction" if body.kind == "instruction" else "fact", "manuel")
        if not ok:
            raise HTTPException(400, "Souvenir refusé (vide ou contenant un secret)")
        return {"ok": True}

    @app.delete("/tontolo/memory/{mem_id}")
    async def memory_delete(request: Request, mem_id: int) -> dict[str, bool]:
        await core_of(request).chat.memory.delete(mem_id)
        return {"ok": True}

    @app.delete("/tontolo/memory")
    async def memory_clear(request: Request) -> dict[str, bool]:
        await core_of(request).chat.memory.delete(None)
        return {"ok": True}

    @app.post("/tontolo/memory/compact")
    async def memory_compact(request: Request) -> dict[str, int]:
        return {"count": await core_of(request).chat.memory.maybe_compact(force=True)}

    @app.get("/tontolo/spend")
    async def spend(request: Request) -> dict[str, Any]:
        db = core_of(request).db
        now = time.time()
        return {"today": await db.spend_since(now - now % 86400),
                "month": await db.spend_since(now - 31 * 86400),
                "entries": await db.list_spend()}

    @app.get("/tontolo/cloud/export")
    async def cloud_export(request: Request, since: float = 0) -> dict[str, Any]:
        """Conversations modifiées depuis `since` (entières) pour la synchronisation par
        compte ; l'application les chiffre avant de les envoyer."""
        db = core_of(request).db
        until = time.time()
        return {"conversations": await db.export_conversations(since), "until": until}

    @app.post("/tontolo/cloud/import")
    async def cloud_import(request: Request) -> dict[str, int]:
        body = await request.json()
        db = core_of(request).db
        applied = 0
        for conv in (body.get("conversations") or [])[:5000]:
            try:
                applied += await db.replace_conversation(conv)
            except (KeyError, TypeError, ValueError):
                continue  # élément illisible : ignoré, les autres sont appliqués
        return {"applied": applied}

    @app.get("/tontolo/cloud/creations")
    async def cloud_creations(request: Request, since: float = 0) -> dict[str, Any]:
        """Créations terminées (images, audio, fichiers…) de 1 Mo au plus, modifiées depuis
        `since`, avec leur contenu : l'application les chiffre avant envoi. `until` : date de
        la dernière vue (les plus lourdes restent sur l'appareil, mais avancent le curseur)."""
        core = core_of(request)
        out: list[dict[str, Any]] = []
        until = since
        for job in await core.db.jobs_since(since):
            until = max(until, float(job.get("updated_at") or 0))
            path = Path(str(job.get("result_path") or ""))
            try:
                if not path.is_file() or path.stat().st_size > SYNC_CREATION_MAX:
                    continue
                data = path.read_bytes()
            except OSError:
                continue
            item = {k: job.get(k) for k in ("id", "kind", "status", "model", "prompt", "params",
                                            "conversation_id", "created_at", "updated_at")}
            item.update(name=path.name, data_b64=base64.b64encode(data).decode())
            out.append(item)
        return {"creations": out, "until": until}

    @app.post("/tontolo/cloud/creations")
    async def cloud_creation_import(request: Request) -> dict[str, int]:
        """Création venue d'un autre appareil : fichier écrit dans le dossier des médias puis
        enregistrée (jamais d'écrasement d'une création locale)."""
        core = core_of(request)
        body = await request.json()
        applied = 0
        for item in (body.get("creations") or [])[:50]:
            try:
                job_id = str(item["id"])
                if not re.fullmatch(r"[0-9a-f]{8,64}", job_id) or await core.db.get_job(job_id):
                    continue
                data = base64.b64decode(str(item["data_b64"]), validate=True)
                if len(data) > SYNC_CREATION_MAX:
                    continue
                name = re.sub(r"[^\w.\-]", "_", Path(str(item.get("name") or job_id)).name)[:120]
                folder = core.settings.data_dir / "media" / "synced"
                folder.mkdir(parents=True, exist_ok=True)
                path = folder / (name if name.startswith(job_id) else f"{job_id}-{name}")
                path.write_bytes(data)
                params = item.get("params") if isinstance(item.get("params"), dict) else {}
                params.pop("source_path", None)  # chemin d'un autre appareil : sans objet
                params["mime"] = safe_mime(params.get("mime"))
                await core.db.upsert_job({
                    "id": job_id, "kind": str(item.get("kind") or "image_gen")[:20],
                    "status": "done", "model": item.get("model"),
                    "prompt": str(item.get("prompt") or "")[:4000], "params": params,
                    "result_path": str(path), "conversation_id": item.get("conversation_id"),
                    "created_at": float(item.get("created_at") or time.time())})
                applied += 1
            except (KeyError, TypeError, ValueError, binascii.Error, OSError):
                continue
        return {"applied": applied}

    @app.get("/tontolo/activity")
    async def activity(request: Request) -> dict[str, Any]:
        """Tâches en cours sur cet appareil (suivi en direct depuis les autres appareils)."""
        core = core_of(request)
        items = []
        for turn in core.turns.running():
            p = turn.progress()
            p["title"] = await core.db.get_title(turn.conversation_id) or ""
            items.append(p)
        waiting = [{"conversation_id": cid, "reason": reason,
                    "title": await core.db.get_title(cid) or ""}
                   for cid, reason in core.turns.waiting.items()]
        return {"tasks": items, "waiting": waiting, "at": time.time()}

    @app.get("/tontolo/sync")
    async def sync_export(request: Request, since: float = 0) -> dict[str, Any]:
        return await core_of(request).db.export_since(since)

    @app.post("/tontolo/sync")
    async def sync_import(request: Request) -> dict[str, int]:
        try:
            return {"applied": await core_of(request).db.import_sync(await request.json())}
        except (KeyError, TypeError, ValueError) as exc:
            raise HTTPException(400, "Lot de synchronisation invalide") from exc

    @app.get("/tontolo/mcp")
    async def mcp_get(request: Request) -> dict[str, Any]:
        core = core_of(request)
        return {"servers": load_config(core.mcp.config_path), "errors": core.mcp.errors,
                "tools": [t.name for t in core.mcp.tools]}

    @app.put("/tontolo/mcp")
    async def mcp_put(request: Request) -> dict[str, bool]:
        core = core_of(request)
        raw = await request.body()
        if len(raw) > 64 * 1024:
            raise HTTPException(413, "Configuration MCP trop volumineuse")
        body = json.loads(raw or b"{}")
        if not isinstance(body, dict) or not isinstance(body.get("servers", []), list):
            raise HTTPException(400, "Liste de serveurs attendue")
        servers = [s for s in body.get("servers", []) if isinstance(s, dict)]
        if len(servers) > MCP_MAX_SERVERS:
            raise HTTPException(400, f"{MCP_MAX_SERVERS} serveurs MCP au plus")
        client_local = (request.client is not None
                        and request.client.host in ("127.0.0.1", "::1"))
        if any(s.get("transport") == "stdio" for s in servers) and not (
                client_local and core.settings.server.host in LOOPBACK):
            # Un serveur stdio lance un programme : jamais configurable à distance.
            raise HTTPException(403, "Serveurs MCP stdio : configuration locale uniquement")
        for srv in servers:
            if problem := check_mcp_server(srv):
                raise HTTPException(400, f"Serveur MCP « {srv.get('name')} » : {problem}")
        if not (client_local and core.settings.server.host in LOOPBACK):
            # Depuis un autre appareil : seulement des serveurs HTTPS publics (pas d'accès au
            # réseau interne de la machine par ce biais).
            for srv in servers:
                if srv.get("transport", "http") != "stdio":
                    try:
                        if not str(srv.get("url", "")).startswith("https://"):
                            raise PermissionError("HTTPS requis")
                        await assert_public_url(str(srv["url"]))
                    except PermissionError as exc:
                        raise HTTPException(403, f"Serveur MCP « {srv.get('name')} » : "
                                                 f"{exc}") from exc
        if any(s.get("transport") == "stdio" for s in servers) and not (
                client_local and core.settings.server.host in LOOPBACK):
            # Un serveur stdio lance un programme : jamais configurable à distance.
            raise HTTPException(403, "Serveurs MCP stdio : configuration locale uniquement")
        save_config(core.mcp.config_path, servers)
        await core.mcp.close()
        return {"ok": True}

    # --- Navigateur intégré -------------------------------------------------------

    @app.get("/tontolo/browser")
    async def browser_status(request: Request) -> dict[str, Any]:
        chat = core_of(request).chat
        cdp = chat.browser_cdp
        return {"desktop": cdp is not None, "executable": cdp.executable if cdp else None,
                "tabs": len(cdp.tabs) if cdp else 0, "panel": chat.browser_bridge.available}

    @app.get("/tontolo/browser/next")
    async def browser_next(request: Request, wait: float = 25) -> dict[str, Any]:
        """Tablette : prochaine commande à exécuter dans le panneau WebView (attente longue)."""
        core = core_of(request)
        _local_only(request, core)
        cmd = await core.chat.browser_bridge.next(max(0.0, min(wait, 25.0)))
        return {"command": cmd}

    @app.post("/tontolo/browser/result")
    async def browser_result(request: Request) -> dict[str, bool]:
        core = core_of(request)
        _local_only(request, core)
        body = await request.json()
        data = body.get("data") if isinstance(body.get("data"), dict) else {}
        return {"ok": core.chat.browser_bridge.result(str(body.get("id") or ""), data)}

    # --- Espace de travail du bureau (fichiers et commandes, avec garde-fous) ---------

    def _local_only(request: Request, core: Core, what: str = "Espace de travail") -> None:
        if not (request.client is not None and request.client.host in ("127.0.0.1", "::1")
                and core.settings.server.host in LOOPBACK):
            raise HTTPException(403, f"{what} : configuration locale uniquement")

    # --- Mode avancé : fournisseurs personnalisés, export / import des réglages ----------

    @app.get("/tontolo/custom-providers")
    async def custom_list(request: Request) -> list[dict[str, Any]]:
        core = core_of(request)
        counts: dict[str, int] = {}
        for m in core.catalog.catalog.models.values():
            counts[m.provider] = counts.get(m.provider, 0) + 1
        return [{**cp.model_dump(), "has_key": secrets.has_key(cp.id),
                 "models": counts.get(cp.id, 0)} for cp in core.settings.custom_providers]

    @app.post("/tontolo/custom-providers")
    async def custom_add(request: Request, body: CustomProviderBody) -> dict[str, Any]:
        core = core_of(request)
        _local_only(request, core, "Fournisseurs personnalisés")
        if len(core.settings.custom_providers) >= 20:
            raise HTTPException(400, "20 fournisseurs personnalisés au plus")
        base = body.base_url.strip().rstrip("/")
        problem = await _custom_url_problem(base, body.needs_key)
        if problem:
            raise HTTPException(400, problem)
        if not body.free and (body.price_in_per_m <= 0 or body.price_out_per_m <= 0):
            raise HTTPException(400, "Fournisseur payant : indiquez ses prix (sinon le plafond "
                                     "de dépense ne peut pas être garanti)")
        key = (body.key or "").strip()
        if body.needs_key and not key:
            raise HTTPException(400, "Clé requise")
        slug = re.sub(r"[^a-z0-9]+", "-", body.name.lower()).strip("-")[:30] or "fournisseur"
        pid, n = f"custom-{slug}", 2
        taken = {cp.id for cp in core.settings.custom_providers} | set(
            core.catalog.catalog.providers)
        while pid in taken:
            pid, n = f"custom-{slug}-{n}", n + 1
        cp = CustomProvider(id=pid, name=body.name.strip()[:60], base_url=base, free=body.free,
                            needs_key=body.needs_key, price_in_per_m=body.price_in_per_m,
                            price_out_per_m=body.price_out_per_m)
        found = await _custom_probe(cp, key)
        if isinstance(found, str):
            raise HTTPException(400, found)
        security.pins().reset(pid)
        if key:
            if not key_allowed(pid, base):  # épingle l'hôte maintenant
                raise HTTPException(400, "Adresse refusée pour une clé (HTTPS requis)")
            secrets.set_key(pid, key)
        core.settings.custom_providers.append(cp)
        save_settings(core.settings)
        core.router.registry.reset()
        await core.catalog.refresh()
        return {"id": pid, "models": found}

    @app.delete("/tontolo/custom-providers/{pid}")
    async def custom_delete(request: Request, pid: str) -> dict[str, bool]:
        core = core_of(request)
        _local_only(request, core, "Fournisseurs personnalisés")
        before = len(core.settings.custom_providers)
        core.settings.custom_providers = [cp for cp in core.settings.custom_providers
                                          if cp.id != pid]
        if len(core.settings.custom_providers) == before:
            raise HTTPException(404, "Fournisseur inconnu")
        save_settings(core.settings)
        secrets.delete_key(pid)
        security.pins().reset(pid)
        core.router.registry.reset()
        await core.catalog.refresh()
        return {"ok": True}

    @app.get("/tontolo/settings/export")
    async def settings_export(request: Request) -> dict[str, Any]:
        """Réglages à sauvegarder ou copier sur un autre appareil : jamais de clé ni de jeton."""
        data = core_of(request).settings.model_dump(mode="json")
        data.pop("server", None)
        return {"tontolo_settings": 1, "settings": data}

    @app.post("/tontolo/settings/import")
    async def settings_import(request: Request) -> dict[str, Any]:
        core = core_of(request)
        _local_only(request, core, "Import des réglages")
        body = await request.json()
        data = body.get("settings") if isinstance(body, dict) else None
        if not isinstance(data, dict) or body.get("tontolo_settings") != 1:
            raise HTTPException(400, "Fichier de réglages Tontolo attendu")
        data.pop("server", None)
        if isinstance(data.get("agent"), dict):
            data["agent"].pop("workdir", None)
        merged = core.settings.model_dump(mode="json")
        merged.update(data)
        try:
            new = Settings.model_validate(merged)
        except ValueError as exc:
            raise HTTPException(400, f"Réglages invalides : {str(exc)[:300]}") from exc
        for cp in new.custom_providers:  # mêmes garde-fous qu'à l'ajout manuel
            if await _custom_url_problem(cp.base_url, cp.needs_key):
                raise HTTPException(400, f"Adresse refusée : {cp.name}")
        for field_name in type(new).model_fields:
            if field_name != "server":
                setattr(core.settings, field_name, getattr(new, field_name))
        save_settings(core.settings)
        core.router.registry.reset()
        core.catalog.refresh_in_background()
        return await get_settings(request)

    def _workspace_json(core: Core) -> dict[str, Any]:
        ws = core.chat.workspace
        return {"path": str(ws.root) if ws else None, "desktop": is_desktop(),
                "commands": bool(ws) and is_desktop(),
                "history": [{k: e.get(k) for k in ("rel", "action", "at")}
                            for e in (ws.journal() if ws else [])][-20:][::-1]}

    @app.get("/tontolo/workspace")
    async def workspace_get(request: Request) -> dict[str, Any]:
        return _workspace_json(core_of(request))

    @app.put("/tontolo/workspace")
    async def workspace_put(request: Request, body: WorkspaceBody) -> dict[str, Any]:
        core = core_of(request)
        _local_only(request, core)
        try:
            root = core.chat.set_workdir(body.path)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        core.settings.agent.workdir = str(root) if root else None
        save_settings(core.settings)
        return _workspace_json(core)

    @app.post("/tontolo/workspace/undo")
    async def workspace_undo(request: Request) -> dict[str, Any]:
        core = core_of(request)
        _local_only(request, core)
        if core.chat.workspace is None:
            raise HTTPException(400, "Aucun dossier de travail choisi")
        return {"message": core.chat.workspace.undo(), **_workspace_json(core)}

    @app.get("/tontolo/update")
    async def update(request: Request, target: str | None = None,
                     arch: str | None = None) -> dict[str, Any]:
        return await check_update(target=target, arch=arch)

    @app.post("/tontolo/update/download")
    async def update_download(request: Request, target: str,
                              arch: str | None = None) -> dict[str, Any]:
        if target not in ("linux", "android"):
            raise HTTPException(400, "cible invalide")
        core = core_of(request)
        result = await download_update(space.cache_dir(core.settings.data_dir, "updates"),
                                       target, arch)
        if result.get("ok"):
            space.keep_only(Path(result["path"]).parent, Path(result["path"]))
        return result

    @app.get("/tontolo/home")
    async def home(request: Request) -> dict[str, Any]:
        """Accueil d'une nouvelle discussion : prénom (réglage, sinon mémoire) et sujets
        récents pour des suggestions personnalisées."""
        core = core_of(request)
        name = core.settings.user_name.strip()
        if not name and core.settings.memory_enabled:
            name = name_from([str(m.get("text") or "") for m in await core.db.list_memories()])
        recent = [{"id": c["id"], "title": c["title"]}
                  for c in await core.db.list_conversations(6, 0, None, None)
                  if str(c.get("title") or "").strip()][:4]
        return {"name": name, "name_from": "settings" if core.settings.user_name.strip()
                else ("memory" if name else ""), "recent": recent}

    @app.get("/tontolo/storage")
    async def storage(request: Request) -> dict[str, Any]:
        """Place occupée : données (discussions, créations, tâches…) et cache unique."""
        data = core_of(request).settings.data_dir
        return await asyncio.to_thread(space.report, data)

    @app.post("/tontolo/storage/clear-cache")
    async def storage_clear(request: Request) -> dict[str, Any]:
        core = core_of(request)
        freed = await asyncio.to_thread(space.clear_cache, core.settings.data_dir)
        return {"freed": freed, **await asyncio.to_thread(space.report,
                                                          core.settings.data_dir)}

    @app.get("/tontolo/about")
    async def about() -> dict[str, Any]:
        return {"version": __version__, "license": "Apache-2.0",
                "attributions": ATTRIBUTIONS}

    # --- WebSocket d'événements ------------------------------------------

    @app.websocket("/tontolo/ws")
    async def ws(websocket: WebSocket) -> None:
        core = core_of(websocket)
        token = core.settings.server.token
        if token and not hmac.compare_digest(websocket.query_params.get("token", ""), token):
            await websocket.close(code=4401)
            return
        if not origin_allowed(websocket.headers.get("origin")):
            await websocket.close(code=4403)
            return
        peer = websocket.client.host if websocket.client else "?"
        if len(hub.queues) >= WS_MAX_CLIENTS or not ws_connects.allow(f"ws:{peer}"):
            await websocket.close(code=4429)  # trop de connexions : débit limité
            return
        await websocket.accept()
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        hub.queues.add(q)
        try:
            while True:
                ev = await q.get()
                await websocket.send_text(json.dumps(ev, ensure_ascii=False, default=str))
        except Exception:
            pass
        finally:
            hub.queues.discard(q)

    # --- Terminal du bureau (une session par discussion) -----------------------------

    @app.websocket("/tontolo/terminal/{cid}/ws")
    async def terminal_ws(websocket: WebSocket, cid: str) -> None:
        """Affichage et saisie du terminal d'une discussion. Accès à un shell : application
        locale uniquement (aucune page web, aucun client distant)."""
        core = core_of(websocket)
        token = core.settings.server.token
        local = (websocket.client is not None and websocket.client.host in ("127.0.0.1", "::1")
                 and core.settings.server.host in LOOPBACK)
        # Un shell : jeton OBLIGATOIRE (sans jeton, n'importe quel processus local pourrait
        # s'y connecter), application locale seulement, aucune origine web.
        if (core.chat.terminals is None or not local or not token
                or websocket.headers.get("origin")
                or not re.fullmatch(r"[\w-]{1,64}", cid)
                or not hmac.compare_digest(websocket.query_params.get("token", ""), token)):
            await websocket.close(code=4403)
            return
        if not ws_connects.allow(f"term:{cid}"):
            await websocket.close(code=4429)
            return
        await websocket.accept()
        session = core.chat.terminals.get(cid, core.chat.terminal_cwd())
        typed = RateLimiter(TERM_MESSAGES_PER_SECOND, 1.0)
        q: asyncio.Queue[bytes] = asyncio.Queue()
        session.listeners.add(q)

        async def pump() -> None:
            await websocket.send_bytes(bytes(session.buffer))
            while True:
                await websocket.send_bytes(await q.get())

        sender = asyncio.create_task(pump())
        try:
            while True:
                raw = await websocket.receive_text()
                if len(raw) > TERM_MAX_MESSAGE or not typed.allow("in"):
                    await websocket.close(code=1009 if len(raw) > TERM_MAX_MESSAGE else 4429)
                    break
                msg = json.loads(raw)
                if not isinstance(msg, dict):
                    continue
                if isinstance(msg.get("input"), str):
                    session.write(msg["input"].encode())
                if isinstance(msg.get("resize"), list) and len(msg["resize"]) == 2:
                    session.resize(int(msg["resize"][0]), int(msg["resize"][1]))
                if msg.get("restart"):
                    session.close()
                    session.listeners.discard(q)
                    session = core.chat.terminals.get(cid, core.chat.terminal_cwd())
                    session.listeners.add(q)
                    await websocket.send_bytes(bytes(session.buffer))
        except Exception:
            pass
        finally:
            sender.cancel()
            session.listeners.discard(q)

    return app


ATTRIBUTIONS = [
    {"name": "Artificial Analysis", "url": "https://artificialanalysis.ai/",
     "use": "Indices d'intelligence, de code, de maths et de vitesse"},
    {"name": "LMArena", "url": "https://lmarena.ai/",
     "use": "Classements ELO par catégorie (jeu de données CC BY 4.0)"},
    {"name": "OpenRouter", "url": "https://openrouter.ai/",
     "use": "Catalogue des modèles, prix et capacités"},
    {"name": "awesome-free-llm-apis", "url": "https://github.com/mnfst/awesome-free-llm-apis",
     "use": "Découverte des fournisseurs gratuits (CC0)"},
    {"name": "Pollinations", "url": "https://pollinations.ai/",
     "use": "Texte et images sans clé"},
]


async def _custom_url_problem(base: str, needs_key: bool) -> str | None:
    """Adresse d'un fournisseur personnalisé : HTTPS public, ou serveur local en HTTP sans clé.
    Jamais d'adresse de métadonnées ni de schéma exotique."""
    parts = urlsplit(base)
    if parts.scheme not in ("https", "http") or not parts.hostname or parts.username:
        return "Adresse http(s) attendue, sans identifiants dans l'URL"
    host = parts.hostname
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None
    if ip is not None and (ip.is_link_local or ip.is_multicast or ip.is_reserved
                           or ip.is_unspecified):
        return "Adresse réservée refusée"
    if host.endswith((".internal", "metadata.google.internal")):
        return "Adresse interne refusée"
    if parts.scheme == "http":
        local = host in LOOPBACK or host.endswith(".local") or (ip is not None and ip.is_private)
        if not local:
            return "HTTPS obligatoire (HTTP seulement pour un serveur du réseau local)"
        if needs_key:
            return "Une clé n'est jamais envoyée en HTTP : utilisez HTTPS ou « sans clé »"
    return None


async def _custom_probe(cp: Any, key: str) -> int | str:
    """Test de connexion : nombre de modèles de discussion listés, ou message d'erreur."""
    from tontolo import http
    from tontolo.catalog.service import custom_models

    headers = {"Authorization": f"Bearer {key}"} if key else {}
    try:
        resp = await http.client().get(f"{cp.base_url}/models", headers=headers, timeout=15,
                                       follow_redirects=False)
    except Exception as exc:
        return f"Connexion impossible : {type(exc).__name__}"
    if resp.status_code in (401, 403):
        return "Clé refusée par le fournisseur"
    if resp.status_code != 200:
        return f"Réponse inattendue ({resp.status_code}) : est-ce une API compatible OpenAI ?"
    try:
        data = resp.json()
    except ValueError:
        return "Réponse illisible : est-ce une API compatible OpenAI ?"
    found = len(custom_models(cp, data))
    return found if found else "Aucun modèle de discussion trouvé à cette adresse"


async def _validate_key(core: Core, provider: str, key: str) -> tuple[bool, str]:
    """Validation immédiate de la clé (aucun appel de génération, aucun quota consommé)."""
    from tontolo import http

    if provider == "artificial-analysis":
        url, headers = ("https://artificialanalysis.ai/api/v2/data/llms/models",
                        {"x-api-key": key})
    else:
        p = core.catalog.catalog.providers.get(provider)
        if p is None or not p.get("base_url"):
            return False, "Fournisseur inconnu"
        base = p["base_url"]
        if not key_allowed(provider, base):
            return False, "Adresse du fournisseur non fiable (HTTPS requis, hôte épinglé)"
        url = (f"{base}/key" if provider == "openrouter"
               else p.get("models_url") or f"{base}/models")
        headers = {"Authorization": f"Bearer {key}"}
        if provider == "anthropic":
            headers |= {"x-api-key": key, "anthropic-version": "2023-06-01"}
    try:
        resp = await http.client().get(url, headers=headers, timeout=20)
    except Exception as exc:
        return False, f"Réseau : {type(exc).__name__}"
    if resp.status_code == 200:
        return True, "Clé valide"
    if resp.status_code in (401, 403):
        return False, "Clé refusée par le fournisseur"
    return False, f"Réponse inattendue ({resp.status_code})"


def run(host: str | None = None, port: int | None = None) -> None:
    import uvicorn

    settings = load_settings()
    host = host or settings.server.host
    port = port or settings.server.port
    if host not in LOOPBACK and not settings.server.token:
        raise SystemExit("Un jeton (server.token ou TONTOLO_TOKEN) est obligatoire pour "
                         "écouter hors de la boucle locale.")
    settings.server.host, settings.server.port = host, port
    uvicorn.run(create_app(settings), host=host, port=port, log_level="info")
