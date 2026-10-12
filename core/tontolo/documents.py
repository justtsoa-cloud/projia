"""Documents joints à une conversation (PDF, texte, Markdown, HTML) : extraction du texte,
découpage en extraits numérotés par page, puis sélection des extraits utiles à chaque question
pour que le modèle réponde en citant ses sources (« [nom, p. 3] »).

Aucun service en ligne pour l'extraction : tout se fait localement (pypdf, pur Python)."""

from __future__ import annotations

import html
import io
import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass

MAX_PAGES = 500
MAX_CHARS = 2_000_000
CHUNK_CHARS = 1200
TOP_CHUNKS = 6

_WORD = re.compile(r"[a-z0-9]{3,}")
_SUMMARY = re.compile(r"\b(r[ée]sum|synth[èe]s|summar|fintin|de quoi parle|what is (this|it) about|"
                      r"points? cl[ée]s|key points|plan du|structure)", re.I)
_STOP = frozenset([
    "les", "des", "une", "est", "pour", "que", "qui", "dans", "par", "sur", "avec", "pas",
    "plus", "son", "ses", "aux", "cette", "ces", "mais", "ont", "sont", "comme", "tout",
    "elle", "ils", "nous", "vous", "leur", "entre", "the", "and", "for", "that", "with",
    "this", "from", "are", "was", "were", "have", "has", "not", "but", "which", "their",
    "there", "what", "when", "your", "ary", "amin", "ny", "izay", "sy", "fa", "dia", "ho",
])


class DocumentError(ValueError):
    """Fichier illisible ou non pris en charge (message destiné à l'utilisateur)."""


@dataclass
class Chunk:
    page: int
    text: str


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in text if not unicodedata.combining(c))


def extract_pages(name: str, data: bytes) -> list[str]:
    """Texte par page (une seule « page » pour les formats sans pagination). Tous les formats
    pris en charge : voir `tontolo.attachments`."""
    from tontolo.attachments import extract_any

    pages = [p[:MAX_CHARS] for p in extract_any(name, data)]
    if not any(p.strip() for p in pages):
        raise DocumentError("Le document ne contient pas de texte.")
    return pages


def _pdf_pages(data: bytes) -> list[str]:
    try:
        from pypdf import PdfReader
        from pypdf.errors import PdfReadError
    except ImportError as exc:  # installation minimale sans pypdf
        raise DocumentError("Lecture des PDF indisponible sur cette installation.") from exc
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise DocumentError("Ce PDF est protégé par un mot de passe.")
        pages: list[str] = []
        total = 0
        for page in reader.pages[:MAX_PAGES]:
            text = page.extract_text() or ""
            total += len(text)
            pages.append(text)
            if total > MAX_CHARS:
                break
    except DocumentError:
        raise
    except (PdfReadError, ValueError, KeyError, TypeError) as exc:
        raise DocumentError("PDF illisible.") from exc
    if not any(p.strip() for p in pages):
        raise DocumentError("Ce PDF ne contient pas de texte (document scanné ?). Envoyez plutôt "
                            "les pages en photo.")
    return pages


def html_to_text(text: str) -> str:
    text = re.sub(r"(?is)<(script|style|noscript|svg|head)[^>]*>.*?</\1>", " ", text)
    text = re.sub(r"(?i)<br\s*/?>|</(p|div|li|h[1-6]|tr)>", "\n", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    return re.sub(r"[ \t]+", " ", re.sub(r"\n\s*\n+", "\n\n", text)).strip()


def chunk_pages(pages: list[str]) -> list[Chunk]:
    chunks: list[Chunk] = []
    for number, page in enumerate(pages, 1):
        text = re.sub(r"\s+", " ", page).strip()
        for start in range(0, len(text), CHUNK_CHARS):
            part = text[start:start + CHUNK_CHARS].strip()
            if part:
                chunks.append(Chunk(number, part))
    return chunks


def select(chunks: list[Chunk], question: str, k: int = TOP_CHUNKS) -> list[Chunk]:
    """Extraits les plus pertinents (pondération de type BM25 simplifiée). Pour une demande de
    résumé, des extraits répartis sur tout le document."""
    if not chunks:
        return []
    if _SUMMARY.search(question) or len(chunks) <= k:
        step = max(1, len(chunks) // k)
        return chunks[::step][:k]
    terms = [w for w in _WORD.findall(_norm(question)) if w not in _STOP]
    if not terms:
        return chunks[:k]
    docs = [Counter(_WORD.findall(_norm(c.text))) for c in chunks]
    n = len(docs)
    df = Counter(t for d in docs for t in set(d) if t in terms)
    scores = []
    for i, d in enumerate(docs):
        length = sum(d.values()) or 1
        s = 0.0
        for t in terms:
            if d[t]:
                idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
                s += idf * d[t] * 2.2 / (d[t] + 1.2 * (0.25 + 0.75 * length / 180))
        scores.append((s, i))
    best = [i for s, i in sorted(scores, reverse=True)[:k] if s > 0] or list(range(min(k, n)))
    return [chunks[i] for i in sorted(best)]


def context_block(documents: list[tuple[str, list[Chunk]]]) -> str:
    """Texte des extraits pour le message système (les citations reprennent nom et page)."""
    parts = []
    for name, chunks in documents:
        for c in chunks:
            parts.append(f"[{name}, p. {c.page}]\n{c.text}")
    return "\n\n".join(parts)
