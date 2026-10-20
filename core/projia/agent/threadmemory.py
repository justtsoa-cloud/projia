"""Mémoire du fil d'une discussion : rien d'important ne doit se perdre, même après une heure
d'échanges et quel que soit le modèle qui répond.

Trois mécanismes, tous locaux et sans appel de modèle :
- `recall` : retrouve dans les messages ANTÉRIEURS à la fenêtre envoyée mot pour mot ceux qui
  répondent à la demande en cours (un chiffre, un nom, une consigne que le résumé a pu
  raccourcir) ;
- `search_query` : une demande courte (« et la suite ? », « explique le 2 ») est complétée
  par les demandes précédentes, pour retrouver les bons extraits des documents joints ;
- `CONTINUITY` : consigne de continuité, pour qu'un changement de modèle ne se remarque pas.
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from typing import Any

_WORD = re.compile(r"[a-z0-9]{3,}")
_STOP = frozenset([
    "les", "des", "une", "est", "pour", "que", "qui", "dans", "par", "sur", "avec", "pas",
    "plus", "son", "ses", "aux", "cette", "ces", "mais", "ont", "sont", "comme", "tout", "elle",
    "ils", "nous", "vous", "leur", "entre", "the", "and", "for", "that", "with", "this", "from",
    "are", "was", "were", "have", "has", "not", "but", "which", "their", "there", "what",
    "when", "your", "ary", "amin", "ny", "izay", "sy", "fa", "dia", "ho", "peux", "veux",
    "fais", "faire", "dis", "donne", "moi", "toi", "encore", "aussi", "alors", "donc", "voici",
    "voila", "oui", "non", "merci", "bonjour",
])

CONTINUITY = (
    "Continuité : cette discussion est déjà engagée et a pu être menée par d'autres modèles "
    "avant toi. Poursuis-la exactement dans le même ton (tutoiement ou vouvoiement), la même "
    "langue, la même mise en forme et le même niveau de détail que tes réponses précédentes "
    "ci-dessous. Ne te présente pas, n'annonce jamais un changement de modèle, ne recommence "
    "pas ce qui a déjà été fait, et tiens compte de tout ce qui a été dit, joint ou décidé "
    "dans ce fil (messages, résumé, documents).")

RECENT_VERBATIM = 18  # messages envoyés mot pour mot : on ne les redit pas
MAX_SCAN = 600        # messages anciens examinés (borne le coût par tour)
SNIPPET = 700


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in text if not unicodedata.combining(c))


def _terms(text: str) -> list[str]:
    return [w for w in _WORD.findall(_norm(text)) if w not in _STOP]


def _plain(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(str(p.get("text", "")) for p in content if isinstance(p, dict))
    return ""


def search_query(history: list[dict[str, Any]], question: str) -> str:
    """Demande complétée par les deux précédentes si elle est trop courte pour se suffire."""
    if len(_terms(question)) >= 4:
        return question
    earlier = [_plain(m.get("content"))[:300] for m in history[:-1]
               if m.get("role") == "user" and _plain(m.get("content")).strip()]
    return " ".join([*earlier[-2:], question])


def recall(history: list[dict[str, Any]], question: str, k: int = 3) -> str | None:
    """Passages anciens du fil qui répondent à `question` (BM25 simplifié), ou None."""
    old = history[: max(0, len(history) - RECENT_VERBATIM)][-MAX_SCAN:]
    items = [(i, m) for i, m in enumerate(old)
             if m.get("role") in ("user", "assistant")
             and len(_plain(m.get("content")).strip()) > 20]
    terms = list(dict.fromkeys(_terms(question)))
    if not items or len(terms) < 1:
        return None
    docs = [Counter(_terms(_plain(m.get("content")))) for _, m in items]
    n = len(docs)
    df = Counter(t for d in docs for t in set(d) if t in terms)
    scored: list[tuple[float, int]] = []
    for idx, d in enumerate(docs):
        length = sum(d.values()) or 1
        hits = [t for t in terms if d[t]]
        if len(hits) < min(2, len(terms)):  # deux mots en commun (un seul si demande brève)
            continue
        s = 0.0
        for t in hits:
            idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
            s += idf * d[t] * 2.2 / (d[t] + 1.2 * (0.25 + 0.75 * length / 120))
        scored.append((s, idx))
    best = sorted(scored, reverse=True)[:k]
    if not best:
        return None
    lines = []
    for _, idx in sorted(best, key=lambda x: x[1]):
        pos, m = items[idx]
        who = "Utilisateur" if m.get("role") == "user" else "Projia"
        text = re.sub(r"\s+", " ", _plain(m.get("content"))).strip()
        lines.append(f"[message {pos + 1} — {who}] {text[:SNIPPET]}")
    return "\n".join(lines)
