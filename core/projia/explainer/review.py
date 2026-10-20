"""Relecture du scénario (X10) et contrôle de la langue (C2).

- `language_ok` : sans modèle, vérifie que les textes sont dans la langue demandée (un petit modèle
  répond parfois en anglais à une demande en français) ;
- `review` : un SECOND modèle gratuit (autre appel, autre candidat) relit les calculs et les faits
  du scénario et répond {ok, issues} ; s'il trouve des erreurs, le rédacteur corrige une fois.
Rien ne bloque : si la relecture est indisponible, la vidéo est livrée (marquée « non relue »)."""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from typing import Any

from projia.explainer.writer import extract_json

Ask = Callable[[list[dict[str, Any]], Callable[[str], bool]], Awaitable[str]]

_WORDS = {
    "fr": frozenset([
        "le", "la", "les", "un", "une", "des", "du", "de", "et", "est", "sont", "pour",
        "avec", "dans", "que", "qui", "sur", "pas", "plus", "ce", "cette", "ces", "nous",
        "vous", "il", "elle", "on", "au", "aux", "par", "comme", "mais", "ou", "donc",
        "car",
    ]),
    "en": frozenset([
        "the", "a", "an", "and", "is", "are", "of", "to", "in", "for", "with", "that",
        "this", "on", "as", "be", "it", "by", "from", "at", "or", "not", "but", "we", "you",
        "they", "your", "can", "will",
    ]),
    "mg": frozenset([
        "ny", "sy", "amin", "dia", "ho", "an", "ary", "na", "izay", "izany", "ireo", "no",
        "fa", "mba", "ao", "eo", "ka", "tsy", "misy", "izy", "ahy", "anao", "azy", "raha",
        "satria",
    ]),
}


def _texts(story: dict[str, Any]) -> str:
    parts: list[str] = []
    for s in story.get("scenes", []):
        parts += [str(s.get("narration") or ""), str(s.get("title") or s.get("text") or ""),
                  str(s.get("caption") or "")]
        parts += [str(i) for i in s.get("items") or []]
    return " ".join(parts).lower()


def language_ok(story: dict[str, Any], language: str) -> bool:
    """Vrai si la langue demandée domine (ou si le texte est trop court pour trancher)."""
    words = re.findall(r"[a-zàâçéèêëîïôûùüÿœ']+", _texts(story))
    if len(words) < 25 or language not in _WORDS:
        return True
    score = {k: sum(w in v for w in words) for k, v in _WORDS.items()}
    best = max(score, key=lambda k: score[k])
    return best == language or score[language] >= 0.8 * score[best]


REVIEW_SYSTEM = (
    "You review the storyboard of a short educational video for ERRORS only: wrong arithmetic, "
    "wrong formulas, wrong dates or facts, claims that are made up. Do not judge style. Reply "
    'with ONLY one JSON object: {"ok": true|false, "issues": ["short, precise description of '
    'each error and the correct value"]}. If everything is correct reply '
    '{"ok": true, "issues": []}.')


def _digest(story: dict[str, Any]) -> str:
    lines = [f"Title: {story.get('title')}"]
    for i, s in enumerate(story.get("scenes", []), 1):
        bits = [str(s.get(k)) for k in ("title", "text", "latex", "caption", "expr") if s.get(k)]
        bits += [str(x) for x in s.get("items") or []]
        bits += [f"{x.get('text', '')} {x.get('latex', '')}".strip() for x in s.get("steps") or []
                 if isinstance(x, dict)]
        lines.append(f"{i}. [{s.get('type')}] " + " | ".join(bits)
                     + f" || {s.get('narration', '')}")
    return "\n".join(lines)[:6000]


def _parse(raw: str) -> dict[str, Any] | None:
    try:
        data = extract_json(raw)
    except Exception:  # réponse non JSON : relecture inutilisable
        return None
    return data if isinstance(data, dict) and isinstance(data.get("ok"), bool) else None


async def review(story: dict[str, Any], ask: Ask) -> list[str] | None:
    """Liste d'erreurs signalées ([] : rien à corriger) ; None si la relecture est indisponible."""
    messages = [{"role": "system", "content": REVIEW_SYSTEM},
                {"role": "user", "content": _digest(story)}]
    try:
        raw = await ask(messages, lambda t: _parse(t) is not None)
    except Exception:  # aucun relecteur disponible : la vidéo part quand même
        return None
    data = _parse(raw)
    if data is None:
        return None
    issues = [str(i)[:300] for i in (data.get("issues") or []) if str(i).strip()][:6]
    return [] if data["ok"] and not issues else issues
