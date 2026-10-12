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


def wants_summary(text: str) -> bool:
    """« Résume ce document », « fintino ity rakitra ity », « summarize this »…"""
    return bool(_SUMMARY.search(text or ""))


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
    import logging

    logging.getLogger("pypdf").setLevel(logging.ERROR)  # polices incomplètes : sans bruit
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


# --- Fiche compacte d'un long document ---------------------------------------------------------
# Un livre entier ne tient pas dans une demande : la discussion garde une version LÉGÈRE (plan,
# définitions, exemples, code et phrases clés de chaque section), calculée sur l'appareil sans
# modèle ni quota. Les créations (Beamer, PowerPoint, Word…) partent de cette fiche et des
# passages les plus utiles à la demande, au lieu des seules premières pages.

LONG_DOC = 20_000            # au-delà, fiche compacte + passages choisis
DIGEST_CHARS = 14_000        # taille de la fiche
_HEADING_KW = re.compile(
    r"^\s*(?:chapitre|chapter|partie|part|section|leçon|lesson|toko|lohahevitra)\s+"
    r"[\dIVXLC]+\b.{0,80}$", re.I)
# Titres numérotés « 1.2 Titre » ou « 3 Titre court » ; jamais une note de bas de page
# (« 1. Phrase longue… ») : 8 mots au plus, sans ponctuation finale.
_HEADING_NUM = re.compile(r"^\s*(?:\d{1,2}(?:\.\d{1,2}){1,2}|\d{1,2})\s+[A-ZÀ-Ý][^\n.,;:!?]{1,60}"
                          r"\s*$|^\s*[A-ZÀ-Ý][A-ZÀ-Ý0-9 '’,:-]{5,70}\s*$")
_RUNNING = re.compile(r"\s+\d{1,4}\s*$")  # numéro de page collé à un en-tête courant


def _is_heading(line: str) -> bool:
    text = _RUNNING.sub("", line.strip())
    return (len(text) <= 90 and len(text.split()) <= 10
            and bool(_HEADING_KW.match(text) or _HEADING_NUM.match(text)))


_KEY = re.compile(r"\b(définition|on appelle|est un|est une|théorème|propriété|exemple|"
                  r"par exemple|remarque|méthode|attention|definition|theorem|example|"
                  r"for example|note that|famaritana|ohatra)\b", re.I)
_CODE_LINE = re.compile(r"^\s*(def |class |import |from \w+ import|#include|public |"
                        r"function |for \(|for \w+ in |while |if \(|return |print\(|\w+\s*=)")
_LEADERS = re.compile(r"(\.\s?){4,}|\.{4,}")  # points de conduite (table des matières, index)
_SENT = re.compile(r"(?<=[.!?])\s+(?=[A-ZÀ-Ý0-9«(])")


def _sections(pages: list[str]) -> list[tuple[str, int, list[str]]]:
    """(titre, page, lignes) ; sans titres détectés : une section toutes les ~10 pages."""
    out: list[tuple[str, int, list[str]]] = []
    seen: set[str] = set()

    def bare(title: str) -> str:  # « 4 Principes de base 12 » → « principes de base »
        return re.sub(r"^\d+\s+", "", _norm(_RUNNING.sub("", title)))

    # En-têtes courants (titre du chapitre repris en haut de chaque page, avec son numéro de
    # page) : seule la première occurrence compte, c'est le vrai titre du chapitre.
    for number, page in enumerate(pages, 1):
        for line in page.splitlines():
            title = line.strip()
            if _is_heading(line):
                if bare(title) in seen:
                    continue  # en-tête courant répété : ni titre ni texte
                seen.add(bare(title))
                out.append((title, number, []))
            elif out:
                out[-1][2].append(line)
            else:
                out.append(("Début", number, [line]))
    if len(out) < 3:
        out = []
        for start in range(0, len(pages), 10):
            lines = "\n".join(pages[start:start + 10]).splitlines()
            out.append((f"Pages {start + 1}–{min(start + 10, len(pages))}", start + 1, lines))
    # Sections minuscules (titres de table des matières) : fusionnées avec la suivante.
    merged: list[tuple[str, int, list[str]]] = []
    for title, first_page, lines in out:
        if merged and sum(len(x) for x in merged[-1][2]) < 200:
            prev = merged.pop()
            merged.append((prev[0] if len(prev[2]) else title, prev[1], prev[2] + lines))
        else:
            merged.append((title, first_page, lines))
    return merged


def _group(sections: list[tuple[str, int, list[str]]], n: int
           ) -> list[tuple[str, int, list[str]]]:
    """Au plus `n` groupes de taille comparable : tout le livre est couvert, du début à la
    fin, même avec des centaines de sous-sections."""
    if len(sections) <= n:
        return sections
    total = sum(sum(len(x) for x in lines) for _, _, lines in sections) or 1
    target = total / n
    groups: list[tuple[str, int, list[str]]] = []
    acc: list[tuple[str, int, list[str]]] = []
    size = 0
    for sec in sections:
        acc.append(sec)
        size += sum(len(x) for x in sec[2])
        if size >= target:
            groups.append((" · ".join(t for t, _, _ in acc[:2]) + (" …" if len(acc) > 2 else ""),
                           acc[0][1], [x for _, _, lines in acc for x in lines]))
            acc, size = [], 0
    if acc:
        groups.append((" · ".join(t for t, _, _ in acc[:2]) + (" …" if len(acc) > 2 else ""),
                       acc[0][1], [x for _, _, lines in acc for x in lines]))
    return groups


def digest(pages: list[str], budget: int = DIGEST_CHARS) -> str:
    """Fiche compacte : plan avec pages, puis l'essentiel de chaque section (phrases les plus
    porteuses, définitions, exemples, un extrait de code)."""
    sections = _sections(pages)
    if not sections:
        return ""
    vocab = Counter(w for p in pages for w in _WORD.findall(_norm(p)) if w not in _STOP)
    # Plan : les titres de premier et deuxième niveau (60 au plus), pour garder de la place.
    main = [(t, p) for t, p, _ in sections if not re.match(r"^\d+\.\d+\.\d", t)]
    toc = "\n".join(f"- {t} (p. {p})" for t, p in main[:60])
    head = (f"Fiche compacte du document ({len(pages)} pages, {len(sections)} parties).\n"
            f"Plan :\n{toc}\n")
    groups = _group(sections, 30)
    per = max(250, (budget - len(head)) // max(1, len(groups)) - 60)
    body: list[str] = []
    for title, page, lines in groups:
        text = re.sub(r"\s+", " ", " ".join(x for x in lines if not _CODE_LINE.match(x)))
        sentences = [x.strip() for x in _SENT.split(text) if 30 <= len(x.strip()) <= 400
                     and not _LEADERS.search(x)]

        def score(sentence: str) -> float:
            words = [w for w in _WORD.findall(_norm(sentence)) if w not in _STOP]
            base = sum(math.log(1 + vocab[w]) for w in words) / (len(words) + 4)
            return base + (2.0 if _KEY.search(sentence) else 0.0)

        ranked = sorted(range(len(sentences)), key=lambda i: -score(sentences[i]))
        keep: list[int] = []
        seen: set[str] = set()
        used = 0
        for i in ranked:
            key = _norm(sentences[i])[:80]
            if key in seen or used + len(sentences[i]) > per:
                continue  # jamais deux fois la même phrase
            seen.add(key)
            keep.append(i)
            used += len(sentences[i])
        code = [x.rstrip()[:100] for x in lines if _CODE_LINE.match(x)][:4]
        part = f"## {title} (p. {page})\n" + " ".join(sentences[i] for i in sorted(keep))
        if code:
            part += "\nCode :\n" + "\n".join(code)
        body.append(part)
    out = head + "\n" + "\n\n".join(body)
    if len(out) > budget:  # chaque partie raccourcie d'autant : la fin du livre reste là
        excess = len(out) - budget
        cut = excess // max(1, len(body)) + 1
        body = [b[:max(120, len(b) - cut)] for b in body]
        out = head + "\n" + "\n\n".join(body)
    return out[:budget]
