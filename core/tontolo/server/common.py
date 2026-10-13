"""Éléments partagés par les routeurs du serveur : corps de requête validés, limites,
aides (historique, fichiers, médias), concentrateur d'événements."""

from __future__ import annotations

import asyncio
import base64
import contextlib
import ipaddress
import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from fastapi import HTTPException, Request, UploadFile, WebSocket
from pydantic import BaseModel, Field, field_validator, model_validator

from tontolo import (
    documents,
    importer,
)
from tontolo.app_state import Core
from tontolo.catalog.models import Category
from tontolo.router.classifier import _is_followup, classify
from tontolo.router.refusal import mentions_image
from tontolo.security import (
    key_allowed,
)

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


KEYFRAMES = 4  # images clés d'une vidéo jointe, décrites par un modèle à vision


async def _keyframes(data: bytes, count: int = KEYFRAMES) -> list[tuple[float, bytes]]:
    """Images clés réparties sur la vidéo (ffmpeg, sur l'appareil), réduites à 640 px de
    large en JPEG. Liste vide sans ffmpeg ou si la vidéo est illisible."""
    import shutil
    import tempfile

    exe, probe = shutil.which("ffmpeg"), shutil.which("ffprobe")
    if exe is None or probe is None:
        return []
    frames: list[tuple[float, bytes]] = []
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "in"
        src.write_bytes(data)

        async def run(*args: str, limit: float = 30) -> bytes | None:
            proc = await asyncio.create_subprocess_exec(
                *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
            try:
                out, _ = await asyncio.wait_for(proc.communicate(), limit)
            except TimeoutError:
                proc.kill()
                return None
            return out if proc.returncode == 0 else None

        raw = await run(probe, "-v", "error", "-show_entries", "format=duration", "-of",
                        "default=noprint_wrappers=1:nokey=1", str(src))
        try:
            duration = float((raw or b"").strip() or 0)
        except ValueError:
            duration = 0.0
        if duration <= 0:
            return []
        for i in range(count):
            at = duration * (i + 0.5) / count
            out = Path(tmp) / f"{i}.jpg"
            done = await run(exe, "-nostdin", "-loglevel", "error", "-ss", f"{at:.2f}", "-i",
                             str(src), "-frames:v", "1", "-vf", "scale='min(640,iw)':-2",
                             "-q:v", "5", str(out))
            if done is not None and out.exists() and out.stat().st_size > 0:
                frames.append((at, out.read_bytes()))
    return frames


def _clock(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else \
        f"{s // 60}:{s % 60:02d}"


async def _describe_keyframes(core: Core, name: str, data: bytes) -> str:
    """Ce qu'on voit dans la vidéo (diapositives, tableau, schémas, gestes…), image clé par
    image clé, par un modèle à vision. Chaîne vide si impossible : la transcription suffit."""
    frames = await _keyframes(data)
    if not frames:
        return ""
    content: list[dict[str, Any]] = [{"type": "text", "text": (
        f"Voici {len(frames)} images clés d'une vidéo, dans l'ordre, aux instants "
        + ", ".join(_clock(t) for t, _ in frames)
        + ". Pour chacune, une ligne « [instant] description » : ce qu'on voit, tout texte, "
        "formule ou schéma lisible à l'écran (formules en LaTeX). Factuel, sans "
        "interprétation ni introduction.")}]
    content += [{"type": "image_url", "image_url": {
        "url": "data:image/jpeg;base64," + base64.b64encode(jpg).decode()}} for _, jpg in frames]
    try:
        text, _, _ = await core.creator.ask([{"role": "user", "content": content}],
                                            category=Category.VISION, limit=90)
    except Exception:  # images clés facultatives : jamais bloquantes
        return ""
    text = text.strip()[:6000]
    return f"Images clés de la vidéo « {name} » (décrites par un modèle à vision) :\n{text}" \
        if text else ""


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


def settings_json(core: Core) -> dict[str, Any]:
    """Réglages renvoyés à l'application : jamais le jeton du serveur."""
    data = core.settings.model_dump(mode="json")
    data["server"].pop("token", None)
    return data


def core_of(request: Request | WebSocket) -> Core:
    c: Core = request.app.state.core
    return c


def _local_only(request: Request, core: Core, what: str = "Espace de travail") -> None:
    if not (request.client is not None and request.client.host in ("127.0.0.1", "::1")
            and core.settings.server.host in LOOPBACK):
        raise HTTPException(403, f"{what} : configuration locale uniquement")


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
