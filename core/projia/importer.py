"""Importer une discussion venue d'un autre assistant pour la continuer dans Projia.

Sources prises en charge :
- lien de partage Claude (claude.ai/share/…) : les données sont servies derrière une
  protection anti-robots ; le cœur essaie l'API publique, sinon l'application l'ouvre dans
  une vue web (vrai navigateur) et renvoie le JSON obtenu (`parse_any`) ;
- lien de partage ChatGPT (chatgpt.com/share/…) : données incluses dans la page ;
- lien de partage Gemini : extrait par la vue web de l'application (texte des bulles) ;
- export JSON (instantané Claude, export de données Claude/ChatGPT) ou texte collé
  (« Human: / Assistant: », « You said: / ChatGPT said: », « Vous : / Claude : »…).

Seules des adresses construites à partir d'un identifiant validé sont téléchargées (pas de
requête vers une adresse arbitraire fournie par l'utilisateur)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

import httpx

from projia import http

MAX_MESSAGES = 500
MAX_TEXT = 100_000
MAX_DATA = 4_000_000
NOT_FOUND = "Discussion introuvable ou supprimée."
BROWSER_UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/130.0 Safari/537.36")

_CLAUDE_SHARE = re.compile(r"https?://(?:www\.)?claude\.ai/share/([0-9a-f-]{36})", re.I)
_CLAUDE_PRIVATE = re.compile(r"https?://(?:www\.)?claude\.ai/chat/[0-9a-f-]{36}", re.I)
_CHATGPT_SHARE = re.compile(
    r"https?://(?:www\.)?(?:chatgpt\.com|chat\.openai\.com)/share/([0-9a-f-]{36})", re.I)
_GEMINI_SHARE = re.compile(
    r"https?://(?:gemini\.google\.com/share|g\.co/gemini/share)/([0-9A-Za-z_-]{6,64})", re.I)
_PRIVATE_USE = re.compile("[-]")

# Script exécuté dans la vue web pour Gemini : texte des questions et des réponses.
GEMINI_SCRIPT = (
    "JSON.stringify(Array.from(document.querySelectorAll('user-query, model-response'))"
    ".map(e => ({role: e.tagName.toLowerCase() === 'user-query' ? 'user' : 'assistant', "
    "text: e.innerText})))")


class ConversationImportError(ValueError):
    """Import impossible ; `code` est traduit par l'application."""

    def __init__(self, code: str, message: str, **extra: Any) -> None:
        super().__init__(message)
        self.code = code
        self.extra = extra


@dataclass
class Imported:
    source: str
    title: str
    messages: list[dict[str, str]] = field(default_factory=list)


def find_link(text: str) -> tuple[str, str] | None:
    """(type, adresse) du premier lien de discussion reconnu dans un texte."""
    for kind, rx in (("claude", _CLAUDE_SHARE), ("chatgpt", _CHATGPT_SHARE),
                     ("gemini", _GEMINI_SHARE), ("claude_private", _CLAUDE_PRIVATE)):
        m = rx.search(text or "")
        if m:
            return kind, m.group(0)
    return None


def _clean(text: Any) -> str:
    return _PRIVATE_USE.sub("", str(text or "")).strip()[:MAX_TEXT]


def _finish(source: str, title: str, messages: list[dict[str, Any]]) -> Imported:
    out: list[dict[str, str]] = []
    for m in messages:
        text = _clean(m.get("text"))
        role = m.get("role")
        if not text or role not in ("user", "assistant"):
            continue
        if out and out[-1]["role"] == role:  # deux messages de suite du même auteur : fusion
            out[-1]["text"] = (out[-1]["text"] + "\n\n" + text)[:MAX_TEXT]
        else:
            out.append({"role": role, "text": text})
    if not out:
        raise ConversationImportError("import_empty", "Aucun message trouvé dans cette discussion.")
    title = _clean(title)[:60] or out[0]["text"][:60]
    return Imported(source, title, out[:MAX_MESSAGES])


# --- Claude -----------------------------------------------------------------------------

def _claude_text(msg: dict[str, Any]) -> str:
    parts = msg.get("content")
    if isinstance(parts, list) and parts:
        return "\n\n".join(str(p.get("text", "")) for p in parts
                           if isinstance(p, dict) and p.get("type") == "text")
    return str(msg.get("text", ""))


def parse_claude(data: dict[str, Any]) -> Imported:
    msgs = [{"role": "user" if m.get("sender") == "human" else "assistant",
             "text": _claude_text(m)}
            for m in data.get("chat_messages") or [] if isinstance(m, dict)]
    return _finish("claude", str(data.get("snapshot_name") or data.get("name") or ""), msgs)


def claude_api_url(share_url: str) -> str:
    m = _CLAUDE_SHARE.search(share_url)
    if not m:
        raise ConversationImportError("import_unsupported", "Lien Claude non reconnu.")
    return (f"https://claude.ai/api/chat_snapshots/{m.group(1).lower()}"
            "?rendering_mode=messages&render_all_tools=true")


# --- ChatGPT ----------------------------------------------------------------------------

def _turbo_decode(flat: list[Any]) -> Any:
    """Décode le format « turbo-stream » (React Router) : objets {"_i": j} où i et j sont des
    indices dans le tableau à plat (clé = flat[i], valeur = flat[j])."""

    def r(i: Any, depth: int = 0) -> Any:
        if not isinstance(i, int) or i < 0 or i >= len(flat) or depth > 80:
            return None
        v = flat[i]
        if isinstance(v, dict):
            out: dict[str, Any] = {}
            for k, x in v.items():
                try:
                    out[str(flat[int(k[1:])])] = r(x, depth + 1)
                except (ValueError, IndexError):
                    continue
            return out
        if isinstance(v, list):
            return [r(x, depth + 1) for x in v]
        return v

    return r


def parse_chatgpt_html(page: str) -> Imported:
    chunks = re.findall(r'streamController\.enqueue\(("(?:[^"\\]|\\.)*")\)', page)
    for chunk in chunks:
        try:
            flat = json.loads(json.loads(chunk))
        except (ValueError, TypeError, RecursionError):
            continue
        if not isinstance(flat, list) or "linear_conversation" not in flat:
            continue
        decode = _turbo_decode(flat)
        key = flat.index("linear_conversation")
        title_key = flat.index("title") if "title" in flat else -1
        for v in flat:
            if isinstance(v, dict) and f"_{key}" in v:
                nodes = decode(v[f"_{key}"]) or []
                title = decode(v.get(f"_{title_key}")) if title_key >= 0 else ""
                msgs = []
                for n in nodes:
                    msg = (n or {}).get("message") or {}
                    role = (msg.get("author") or {}).get("role")
                    content = msg.get("content") or {}
                    if content.get("content_type") != "text":
                        continue
                    text = "\n".join(p for p in content.get("parts") or [] if isinstance(p, str))
                    msgs.append({"role": role, "text": text})
                return _finish("chatgpt", title if isinstance(title, str) else "", msgs)
    raise ConversationImportError("import_empty", "Discussion ChatGPT introuvable dans la page.")


def parse_chatgpt_export(conv: dict[str, Any]) -> Imported:
    """Une conversation de l'export de données ChatGPT (conversations.json)."""
    mapping = conv.get("mapping") or {}
    node_id = conv.get("current_node")
    chain: list[dict[str, Any]] = []
    while node_id and node_id in mapping and len(chain) < 5000:
        chain.append(mapping[node_id])
        node_id = mapping[node_id].get("parent")
    msgs = []
    for n in reversed(chain):
        msg = n.get("message") or {}
        content = msg.get("content") or {}
        if content.get("content_type") == "text":
            msgs.append({"role": (msg.get("author") or {}).get("role"),
                         "text": "\n".join(p for p in content.get("parts") or []
                                           if isinstance(p, str))})
    return _finish("chatgpt", str(conv.get("title") or ""), msgs)


# --- Texte collé ------------------------------------------------------------------------

_SPEAKER = re.compile(
    r"^\s*(?:\*\*)?(human|user|utilisateur|vous|you|moi|me|you said|vous avez dit|"
    r"assistant|claude|chatgpt|gpt|gemini|ia|ai|chatgpt said|claude said|projia)"
    r"(?:\*\*)?\s*[:：]\s*(?:\*\*)?", re.I | re.M)
_USER_NAMES = {"human", "user", "utilisateur", "vous", "you", "moi", "me", "you said",
               "vous avez dit"}


def parse_text(text: str) -> Imported:
    marks = list(_SPEAKER.finditer(text))
    if len(marks) < 2:
        # Pas de locuteurs reconnaissables : tout le texte devient le contexte de départ.
        body = text.strip()
        if not body:
            raise ConversationImportError("import_empty", "Texte vide.")
        return _finish("text", "", [
            {"role": "user", "text": "Voici une discussion que j'avais commencée ailleurs ; "
                                     "continuons à partir de là.\n\n" + body},
            {"role": "assistant", "text": "D'accord, j'ai lu la discussion. Continuons."}])
    msgs = []
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        role = "user" if m.group(1).lower() in _USER_NAMES else "assistant"
        msgs.append({"role": role, "text": text[m.end():end]})
    return _finish("text", "", msgs)


# --- Point d'entrée ---------------------------------------------------------------------

def parse_any(data: str) -> list[Imported]:
    """JSON (instantané Claude, export Claude/ChatGPT, liste de messages) ou texte."""
    if len(data) > MAX_DATA:
        raise ConversationImportError("import_too_big", "Données trop volumineuses.")
    stripped = data.strip()
    if stripped[:1] in "[{":
        try:
            obj = json.loads(stripped)
        except (ValueError, RecursionError):  # JSON invalide ou imbriqué à l'excès
            obj = None
        if obj is not None:
            try:
                return _parse_json(obj)
            except (TypeError, AttributeError, KeyError, OverflowError, RecursionError) as exc:
                raise ConversationImportError(
                    "import_empty", "Structure de discussion invalide.") from exc
    return [parse_text(data)]


def _parse_json(obj: Any) -> list[Imported]:
    if isinstance(obj, dict):
        if "chat_messages" in obj:
            return [parse_claude(obj)]
        if "mapping" in obj:
            return [parse_chatgpt_export(obj)]
        if isinstance(obj.get("messages"), list):
            return _parse_json(obj["messages"])
    if isinstance(obj, list) and obj:
        if all(isinstance(x, dict) and ("chat_messages" in x or "mapping" in x) for x in obj):
            out = []
            for x in obj[:200]:
                try:
                    out.extend(_parse_json(x))
                except ConversationImportError:
                    continue
            if out:
                return out
        elif all(isinstance(x, dict) for x in obj):  # [{role, text|content}]
            msgs = [{"role": "assistant" if str(x.get("role")) in ("assistant", "model", "bot")
                     else "user", "text": x.get("text") or x.get("content") or ""} for x in obj]
            return [_finish("json", "", msgs)]
    raise ConversationImportError("import_empty", "Format de discussion non reconnu.")


async def fetch(url: str) -> Imported:
    """Télécharge et décode un lien de partage. Lève ConversationImportError (code
    `import_browser` quand l'application doit passer par une vue web)."""
    found = find_link(url)
    if found is None:
        raise ConversationImportError("import_unsupported", "Lien non reconnu.")
    kind, link = found
    headers = {"User-Agent": BROWSER_UA, "Accept-Language": "fr,en;q=0.8"}
    if kind == "claude_private":
        raise ConversationImportError("import_private", "Ce lien Claude est privé.")
    if kind == "claude":
        api = claude_api_url(link)
        try:
            r = await http.client().get(api, headers={**headers, "Accept": "application/json"},
                                        timeout=20)
            if r.status_code == 200 and r.headers.get("content-type", "").startswith(
                    "application/json"):
                return parse_claude(r.json())
            if r.status_code == 404:
                raise ConversationImportError("import_not_found", NOT_FOUND)
        except httpx.HTTPError:
            pass
        raise ConversationImportError("import_browser", "Ouverture dans un navigateur nécessaire.",
                           page_url=link, api_url=api, extract="fetch_json")
    if kind == "chatgpt":
        share_id = link.rsplit("/", 1)[1].lower()
        try:
            r = await http.client().get(f"https://chatgpt.com/share/{share_id}",
                                        headers=headers, timeout=25)
        except httpx.HTTPError as exc:
            raise ConversationImportError("import_network", "Lien injoignable.") from exc
        if r.status_code == 404:
            raise ConversationImportError("import_not_found", NOT_FOUND)
        if r.status_code == 200:
            try:
                return parse_chatgpt_html(r.text[:MAX_DATA * 3])
            except ConversationImportError:
                pass
        raise ConversationImportError("import_browser", "Ouverture dans un navigateur nécessaire.",
                           page_url=link, extract="page_text")
    # Gemini : rendu côté navigateur uniquement.
    raise ConversationImportError("import_browser", "Ouverture dans un navigateur nécessaire.",
                       page_url=link, extract="script", script=GEMINI_SCRIPT)
