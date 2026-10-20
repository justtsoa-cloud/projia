"""Pistes de discussion de l'accueil.

Principe : pas un simple « Bonjour », mais une invitation précise liée à ce que la personne fait
vraiment. Tout est local et sans appel de modèle (instantané, hors ligne, gratuit) :

1. `interests` : thèmes récents tirés des titres de discussion, pondérés par la récence ; les
   sujets sensibles (santé, argent, intime, deuil…) ne sont JAMAIS proposés ;
2. `build` : une piste principale + deux secondaires, de natures variées (aller plus loin, quiz,
   fait surprenant, petit projet) choisies selon le jour pour ne pas se répéter ; la discussion
   récente à reprendre reste proposée à part par l'application ;
3. « pas pour moi » écarte un thème pour deux semaines (`DISMISS_DAYS`).
"""

from __future__ import annotations

import re
import time
import unicodedata
from typing import Any

DISMISS_DAYS = 14
MAX_TOPIC = 60
KINDS = ("deeper", "quiz", "fact", "project")

_SENSITIVE = re.compile(
    r"\b(sant[ée]|m[ée]dic\w*|maladie|douleur|d[ée]pressi\w*|suicid\w*|anxi\w*|th[ée]rapie|"
    r"diagnostic|sympt[oô]me\w*|argent|dette|cr[ée]dit|imp[oô]ts?|salaire|banque|divorce|"
    r"deuil|d[ée]c[èe]s|sexe|sexuel\w*|intime|amoureu\w*|avocat|proc[èe]s|police|"
    r"health|medical|disease|pain|depress\w*|suicide|anxiety|therapy|symptom\w*|money|debt|"
    r"loan|tax(?:es)?|salary|bank|divorce|grief|death|sex\w*|lawyer|lawsuit|"
    r"aretina|marary|fahasoavana|vola|trosa|fahafatesana|sarotra ny fiainana)\b", re.I)
_STOP = frozenset(re.findall(r"\S+", (
    "bonjour salut hello hi coucou merci test essai le la les un une des du de d l et ou en "
    "sur pour par avec sans dans comme que qui quoi est sont fais fait faire peux peut tu vous "
    "me moi mon ma mes nous explique expliquer decris dis donne donner cree creer ecris ecrire "
    "aide aider montre propose voudrais veux aimerais svp stp please the a an of to for and or "
    "on in with about how what can you me my is are make give write explain show help i ny sy "
    "amin momba ho an ao ary na nouvelle conversation discussion sans titre "
)))


def plain(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s.lower())
                   if not unicodedata.combining(c))


def clean_topic(title: str) -> str:
    """Titre de discussion → thème court et lisible (« Peux-tu m'expliquer la photosynthèse ? »
    → « la photosynthèse »)."""
    from projia.agent.imagebrief import subject_of

    t = re.sub(r"\s+", " ", str(title or "")).strip(" .,;:?!\"'«»")
    t = re.sub(r"^(?:peux|pouvez|pourrais|pourriez)[- ](?:tu|vous)\s+", "", t, flags=re.I)
    t = re.sub(r"^(?:m'|m’|me |nous )", "", t, flags=re.I)
    t = subject_of(t) if t else ""
    return t[:MAX_TOPIC].strip(" .,;:?!\"'«»")


def interests(conversations: list[dict[str, Any]], now: float | None = None,
              limit: int = 5) -> list[str]:
    """Thèmes (courts) des discussions récentes, le plus récent et le plus répété d'abord.
    `conversations` : lignes `list_conversations` (title, updated_at, mode)."""
    now = now or time.time()
    scores: dict[str, float] = {}
    shown: dict[str, str] = {}
    for c in conversations:
        topic = clean_topic(c.get("title") or "")
        words = [w for w in re.findall(r"[a-z0-9]{3,}", plain(topic)) if w not in _STOP]
        if not topic or len(words) < 1 or _SENSITIVE.search(str(c.get("title") or "")):
            continue
        age_days = max(0.0, (now - float(c.get("updated_at") or now)) / 86400)
        weight = 0.5 ** (age_days / 7)           # demi-vie d'une semaine
        weight *= 1.3 if str(c.get("mode") or "").startswith("learn") else 1.0
        key = " ".join(sorted(words))
        scores[key] = scores.get(key, 0.0) + weight
        shown.setdefault(key, topic)
    ranked = sorted(scores, key=lambda k: scores[k], reverse=True)
    return [shown[k] for k in ranked[:limit]]


_T: dict[str, dict[str, tuple[str, str]]] = {
    "fr": {
        "deeper": ("Aller plus loin : {t}",
                   "Je veux aller plus loin sur « {t} » : propose-moi trois pistes que je n'ai "
                   "pas encore explorées, avec une question pour commencer."),
        "quiz": ("Un quiz sur {t}",
                 "Fais-moi un quiz de 5 questions sur « {t} », une question à la fois."),
        "fact": ("Le saviez-vous ? {t}",
                 "Raconte-moi un fait surprenant et vérifiable sur « {t} », en trois phrases."),
        "project": ("Un petit projet autour de {t}",
                    "Propose-moi une idée de petit projet concret autour de « {t} », "
                    "faisable en une heure."),
    },
    "en": {
        "deeper": ("Go further: {t}",
                   "I want to go further on “{t}”: suggest three angles I haven't explored "
                   "yet, with a question to start."),
        "quiz": ("A quiz on {t}",
                 "Give me a 5-question quiz on “{t}”, one question at a time."),
        "fact": ("Did you know? {t}",
                 "Tell me a surprising, verifiable fact about “{t}” in three sentences."),
        "project": ("A small project about {t}",
                    "Suggest a small concrete project about “{t}” that I can do in an hour."),
    },
    "mg": {
        "deeper": ("Handroso: {t}",
                   "Te handroso bebe kokoa amin'ny « {t} » aho: manaova tolo-kevitra telo mbola "
                   "tsy nodinihiko, miaraka amin'ny fanontaniana iray hanombohana."),
        "quiz": ("Fanontaniana fitsapana: {t}",
                 "Manaova fanontaniana fitsapana 5 momba ny « {t} », iray isaky ny fotoana."),
        "fact": ("Fantatrao ve? {t}",
                 "Tantarao ahy zava-misy mahagaga sy azo hamarinina momba ny « {t} », "
                 "amin'ny fehezanteny telo."),
        "project": ("Tetikasa kely momba ny {t}",
                    "Atolory ahy hevitra tetikasa kely tena izy momba ny « {t} » azo atao ao "
                    "anatin'ny ora iray."),
    },
}


def active_dismissals(raw: dict[str, float] | None, now: float | None = None) -> set[str]:
    now = now or time.time()
    return {k for k, ts in (raw or {}).items() if now - float(ts) < DISMISS_DAYS * 86400}


def build(conversations: list[dict[str, Any]], language: str = "fr",
          dismissed: dict[str, float] | None = None, now: float | None = None,
          count: int = 3) -> list[dict[str, Any]]:
    """Pistes du jour ([] sans historique exploitable : l'application garde ses idées
    générales). Variées : un thème et une nature différents pour chaque piste ; le choix change
    chaque jour mais reste stable pendant la journée."""
    now = now or time.time()
    lang = language if language in _T else "fr"
    gone = active_dismissals(dismissed, now)
    topics = [t for t in interests(conversations, now) if plain(t) not in gone]
    if not topics:
        return []
    day = int(now // 86400)
    out: list[dict[str, Any]] = []
    for i, topic in enumerate(topics[:count]):
        kind = KINDS[(day + i) % len(KINDS)]
        title, prompt = _T[lang][kind]
        out.append({"id": f"{kind}:{plain(topic)}", "kind": kind, "topic": topic,
                    "title": title.format(t=topic), "prompt": prompt.format(t=topic)})
    # Un seul thème : on varie quand même la nature des pistes secondaires.
    if len(out) == 1 and count > 1:
        for j in (1, 2):
            kind = KINDS[(day + j) % len(KINDS)]
            title, prompt = _T[lang][kind]
            out.append({"id": f"{kind}:{plain(topics[0])}", "kind": kind, "topic": topics[0],
                        "title": title.format(t=topics[0]), "prompt": prompt.format(t=topics[0])})
    return out
