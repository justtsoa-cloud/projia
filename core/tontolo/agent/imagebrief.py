"""Brief d'image tiré de la discussion : « génère une image par rapport à la discussion ».

Un générateur d'images ne lit pas la discussion : il reçoit UN prompt. Quand la demande ne dit
pas de quoi il s'agit (« fais-en une image »), ce module le compose à partir du fil :

1. `digest` : sujet (première demande) + dernières réponses, nettoyés (Markdown, LaTeX, code,
   liens) et bornés ;
2. un petit modèle gratuit rédige un prompt anglais visuel (éléments concrets, composition,
   style, couleurs ; PAS de formules ni de paragraphes : un générateur ne sait pas les écrire) ;
3. `clean` vérifie le résultat (longueur, refus, injection de consignes, liens) ;
4. repli SANS modèle (`fallback`) si le modèle tarde, échoue ou répond n'importe quoi : sujet
   + style d'affiche pédagogique. Jamais d'échec, jamais de blocage (délai borné).
"""

from __future__ import annotations

import asyncio
import re
import unicodedata
from collections.abc import Awaitable, Callable
from typing import Any

MAX_DIGEST = 3500
MAX_PROMPT = 700
BRIEF_TIMEOUT = 20.0

SYSTEM = (
    "You write ONE prompt for an AI image generator that visually summarizes a conversation. "
    "Rules: English only, 40 to 90 words, one paragraph, no lists. Describe concrete visual "
    "elements that express the main ideas (diagrams, shapes, objects, icons, a central "
    "metaphor), the composition, the style and the colors. Image generators cannot spell: use "
    "NO sentences, NO formulas, NO equations, NO code, NO title: the picture must contain no "
    "text at all. Respect the user's style wishes (beautiful, compact, detailed, colors). "
    "Reply with ONLY the prompt wrapped in <prompt></prompt> tags: no preamble, no reasoning.")

STYLE = ("modern educational infographic poster, clean flat vector illustration, deep navy "
         "background with cyan, mint and white accents, balanced composition with a central "
         "diagram and small icons, crisp lines, high detail, absolutely no text, no letters, no "
         "words, no numbers")

_BAD = re.compile(r"\b(i can(?:'|no)t|i cannot|sorry|as an ai|je ne peux pas|désolé)\b", re.I)
_URL = re.compile(r"https?://\S+")
_FENCE = re.compile(r"```.*?```", re.S)
_MATH = re.compile(r"\$\$.*?\$\$|\$[^$\n]{1,200}\$|\\\[.*?\\\]|\\\(.*?\\\)", re.S)
_MD = re.compile(r"[#*_`>|]+")

_TAGGED = re.compile(r"<prompt>(.*?)</prompt>", re.S | re.I)
# Un modèle « à réflexion » laisse parfois son raisonnement dans la réponse : jamais un prompt.
_META = re.compile(
    r"^(?:the user|the conversation|we need|we are|i need|i should|let me|let's|okay|ok,|"
    r"first,|hmm|thinking|here(?:'s| is)|sure)\b", re.I)

Ask = Callable[[list[dict[str, Any]], Callable[[str], bool]], Awaitable[str | None]]


def extract(raw: str | None) -> str | None:
    """Prompt entre balises <prompt>…</prompt> (le dernier), vérifié ; None sinon : sans
    balises, la réponse est un raisonnement tronqué et non un prompt."""
    found = _TAGGED.findall(raw or "")
    return clean(found[-1]) if found else None


def _plain(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(str(p.get("text", "")) for p in content if isinstance(p, dict))
    return ""


def _tidy(text: str, limit: int) -> str:
    text = _FENCE.sub(" ", text)
    text = _MATH.sub(" ", text)
    text = _URL.sub(" ", text)
    text = _MD.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()[:limit]


def digest(history: list[dict[str, Any]]) -> tuple[str, str]:
    """(sujet, résumé) du fil : le sujet est la première demande ; le résumé reprend les
    dernières réponses de l'assistant (les plus récentes comptent le plus)."""
    usable = [m for m in history if m.get("role") in ("user", "assistant")
              and not re.fullmatch(r"\[média:[0-9a-f]+\]", str(m.get("content", "")).strip())]
    topic = next((_tidy(_plain(m.get("content")), 200) for m in usable
                  if m.get("role") == "user" and _tidy(_plain(m.get("content")), 200)), "")
    parts: list[str] = []
    budget = MAX_DIGEST
    for m in reversed(usable):
        if m.get("role") != "assistant":
            continue
        t = _tidy(_plain(m.get("content")), 1200)
        if len(t) < 40:
            continue
        parts.append(t[:budget])
        budget -= len(parts[-1])
        if budget < 300 or len(parts) >= 3:
            break
    return topic, "\n\n".join(reversed(parts))


def clean(raw: str | None) -> str | None:
    """Prompt prêt à l'emploi, ou None si la réponse du modèle est inutilisable."""
    if not raw:
        return None
    text = _URL.sub(" ", raw.strip().strip("\"'`“”«» "))
    text = re.sub(r"^(?:prompt|image prompt)\s*:\s*", "", text, flags=re.I)
    text = re.sub(r"\s+", " ", _FENCE.sub(" ", text)).strip()
    if len(text) < 25 or _BAD.search(text[:200]) or _META.match(text):
        return None
    return text[:MAX_PROMPT]


_WISHES = (
    (r"\b(beau|belle|beaux|magnifique|joli\w*|esth[ée]tique|beautiful|stunning|gorgeous)\b",
     "beautiful, polished"),
    (r"\b(compact\w*|dense|compact)\b", "compact, well organised"),
    (r"\b(d[ée]taill\w*|detailed|pr[ée]cis\w*|riche)\b", "highly detailed"),
    (r"\b(color[ée]\w*|vif|vifs|colorful|vibrant)\b", "colorful, vibrant"),
    (r"\b(minimalist\w*|simple|[ée]pur[ée]\w*|clean)\b", "minimalist, clean"),
    (r"\b(r[ée]aliste\w*|photor[ée]alist\w*|realistic)\b", "realistic"),
    (r"\b(noir et blanc|black and white|monochrome)\b", "black and white"),
    (r"\b(sombre|dark|nuit)\b", "dark theme"),
    (r"\b(clair|light|lumineu\w*|bright)\b", "bright, light theme"),
    (r"\b(aquarelle|watercolou?r)\b", "watercolor style"),
    (r"\b(dessin[ée]?|cartoon|bd|manga)\b", "hand-drawn cartoon style"),
)


def style_wishes(request: str) -> str:
    """Souhaits de style de la demande, en anglais (« très beau, compact » → « beautiful,
    polished, compact… »). Le reste de la phrase (reproches, tournures) n'entre jamais dans le
    prompt : un générateur d'images l'afficherait ou le dessinerait."""
    found = [en for rx, en in _WISHES if re.search(rx, request or "", re.I)]
    return ", ".join(dict.fromkeys(found))


_LEAD = frozenset([
    "peux", "pouvez", "pourrais", "pourriez", "tu", "vous", "me", "moi", "nous", "je", "veux",
    "voudrais", "souhaite", "aimerais", "que", "explique", "expliquez", "expliquer", "decris",
    "decrivez", "decrire", "dis", "dites", "parle", "parles", "parlez", "parler", "raconte",
    "racontes", "montre", "montrez", "presente", "presentez", "resume", "resumez", "de", "d",
    "du", "des", "en", "et", "ou", "pour", "sur", "au", "aux", "sil", "plait", "svp", "stp",
    "facon", "maniere", "tres", "simple", "simplement", "mathematiquement", "clairement",
    "rapidement", "bien", "un", "peu", "can", "could", "you", "please", "explain", "describe",
    "tell", "about", "simply", "briefly",
])
_TAIL = re.compile(r"\s+(?:en|in)\s+(?:math[ée]matiques|maths|physique|chimie)\s*$", re.I)


def subject_of(topic: str) -> str:
    """Sujet d'une première demande, sans la tournure (« peux tu me décrire … la théorie de la
    représentation en mathématiques » → « la théorie de la représentation »)."""
    words = (topic or "").replace("'", "' ").replace("’", "’ ").split()
    i = 0
    while i < len(words) - 1:
        bare = re.sub(r"[^a-z]", "", "".join(
            c for c in unicodedata.normalize("NFKD", words[i].lower())
            if not unicodedata.combining(c)))
        if bare not in _LEAD:
            break
        i += 1
    subject = " ".join(words[i:]).replace("' ", "'").replace("’ ", "’")
    subject = _TAIL.sub("", subject).strip(" .,;:?!")
    return subject[:140] or (topic or "")[:140]


def fallback(topic: str, wishes: str = "") -> str:
    """Prompt sans modèle : le sujet de la discussion et un style d'affiche pédagogique."""
    subject = subject_of(topic) or "the subject of the conversation"
    extra = f", {wishes.strip()[:160]}" if wishes.strip() else ""
    return f"Educational infographic poster about {subject}. {STYLE}{extra}"[:MAX_PROMPT]


async def build(history: list[dict[str, Any]], request: str, ask: Ask,
                limit: float = BRIEF_TIMEOUT) -> tuple[str, str]:
    """(prompt, source) : source = « model » ou « fallback »."""
    topic, summary = digest(history)
    wishes = style_wishes(request)
    if not (topic or summary):
        return request, "request"  # fil vide : la demande telle quelle
    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": (
            f"Conversation topic: {topic}\n\nLatest answers:\n{summary}\n\n"
            f"Style wishes of the user: {wishes or 'none'}")},
    ]
    try:
        async with asyncio.timeout(limit):
            prompt = extract(await ask(messages, lambda t: extract(t) is not None))
    except Exception:  # panne, délai, modèle absent : le repli prend le relais
        prompt = None
    return (prompt, "model") if prompt else (fallback(topic, wishes), "fallback")
