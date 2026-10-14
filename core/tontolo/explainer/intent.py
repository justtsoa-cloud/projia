"""« Fais-moi une vidéo qui explique les fractions » : détecter la demande et la COMPLÉTER.

Le grand public n'écrit pas de prompt parfait. Ce module décide, sans appel de modèle :
- `resolve` : est-ce une demande de vidéo explicative (et non d'une vidéo générée ou d'une
  question sur une vidéo jointe) ? Le sujet est-il dans la phrase ou dans la discussion ?
- `complete` : tout ce que la personne n'a pas dit, choisi par défaut (niveau, durée, langue,
  structure pédagogique), pour que le scénario soit bon sans question en retour.
Entrée bornée à 500 caractères, expressions sans répétition imbriquée.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

MAX_CHARS = 500

_VIDEO = (r"(?:vid[ée]os?|animations?|clips?|films?|videos?|horonan-?tsary|sarimihetsika)")
_KIND = (r"(?:explicati(?:f|ve)s?|p[ée]dagogiques?|didactiques?|educational|explainer|"
         r"explanatory|tutorial|tuto|fampianarana|manim)")
_EXPLAIN_VERB = (r"(?:explique\w*|expliquer|montre\w*|illustre\w*|enseigne\w*|apprend\w*|"
                 r"explain\w*|show\w*|teach\w*|hazavao|asehoy|ampianaro)")
# « vidéo explicative », « vidéo pédagogique », « manim », « vidéo qui explique… »
_EXPLICIT = re.compile(
    rf"\bmanim\b|\b{_VIDEO}\s+(?:{_KIND}|(?:qui|pour|to|that)\s+(?:m')?{_EXPLAIN_VERB})\b|"
    rf"\b{_KIND}\s+{_VIDEO}\b|\b(?:animation|animer)\s+(?:p[ée]dagogique|explicative)\b|"
    rf"\b{_EXPLAIN_VERB}(?:-moi|-nous)?\b.{{0,60}}\b(?:en|avec une|with an?|in an?|as an?)\s+"
    rf"{_VIDEO}\b", re.I)
# Une création de vidéo quelconque (suffit en mode Apprendre : un modèle de vidéo générative ne
# sait ni écrire une formule ni tenir un raisonnement)
_MAKE_VIDEO = re.compile(
    rf"\b(?:fais|faire|cr[ée]e\w*|g[ée]n[èe]re\w*|produis\w*|r[ée]alise\w*|pr[ée]pare\w*|"
    rf"montre-moi|donne-moi|make|create|generate|produce|manaova|mamorona|ataovy)\b"
    rf"(?:-moi|-nous)?(?:\s+\S{{1,14}}){{0,4}}?\s+{_VIDEO}\b", re.I)
# « une vidéo sur la guerre froide », « vidéo : les temps du passé » (sans verbe)
_BARE_VIDEO = re.compile(
    rf"^\s*(?:(?:une?|a|an)\s+)?(?:(?:courte?|petite?|short|quick)\s+)?{_VIDEO}\s*"
    rf"(?::|sur|[àa] propos de|about|on|momba)", re.I)
_ABOUT_EXISTING = re.compile(
    rf"\b(?:cette|cet|la|ma|ta|sa|this|the|ity)\s+{_VIDEO}\s+(?:jointe|que|est|dit|montre|"
    rf"attached)\b|\b(?:que (?:montre|dit)|what (?:does|is)|r[ée]sume|d[ée]cris)\b", re.I)
_DEICTIC = re.compile(
    r"\b(?:[çc]a|cela|ceci|tout (?:[çc]a|cela)|la discussion|cette discussion|notre [ée]change|"
    r"cette (?:explication|notion|le[çc]on)|ce sujet|ce chapitre|ci-dessus|all this|this|that|"
    r"izany)\b", re.I)
_LEAD = re.compile(
    rf"^\s*(?:(?:peux|pouvez|pourrais|pourriez)[- ](?:tu|vous)\s+|je (?:veux|voudrais|souhaite|"
    rf"aimerais)\s+|(?:s'il (?:te|vous) pla[iî]t[, ]*)|(?:fais|faire|cr[ée]e\w*|g[ée]n[èe]re\w*|"
    rf"produis\w*|r[ée]alise\w*|pr[ée]pare\w*|montre|donne|make|create|can you|please|"
    rf"ataovy|manaova|mamorona|"
    rf"{_EXPLAIN_VERB})"
    rf"(?:-moi|[- ]nous)?\s+|(?:une?|des|a|an)\s+|(?:courte?|petite?|longue?|belle|simple|"
    rf"short|quick|nice|ny|ireo)\s+|{_VIDEO}(?:\s*:\s*|\s+)|{_KIND}\s+|(?:qui|pour|that|to)\s+(?:m'|nous\s+)?"
    rf"{_EXPLAIN_VERB}\s+|(?:sur|[àa] propos de|about|on|momba)\s+|(?:comment|how)\s+)+", re.I)
_TAIL = re.compile(rf"\s+(?:en|avec une|with an?|in an?|as an?)\s+{_VIDEO}(?:\s+\S+)?\s*$", re.I)
_TRAIL = re.compile(
    r"(?:\s+(?:(?:tr[èe]s|plus)\s+)?(?:courte?|rapide|express|longue?|d[ée]taill\w*|short|quick|"
    r"long|detailed|simple)|\s+(?:de|en|d'environ|of)\s+\d{1,3}\s*(?:min(?:ute)?s?|mn|s|"
    r"sec(?:ondes?|onds?)?))+\s*$", re.I)
_BROAD = re.compile(
    r"^(?:les?\s+|la\s+|l')?(?:maths?|math[ée]matiques|physique|chimie|biologie|svt|histoire|"
    r"g[ée]ographie|fran[çc]ais|anglais|informatique|sciences?|économie|philosophie|"
    r"geometry|algebra|science|history|biology|physics|chemistry)\s*$", re.I)
_MINUTES = re.compile(r"\b(\d{1,2})\s*(?:min(?:ute)?s?|mn)\b", re.I)
_SECONDS = re.compile(r"\b(\d{2,3})\s*(?:s|sec(?:ondes?|onds?)?)\b", re.I)
_SHORT = re.compile(r"\b(?:courte?|rapide|express|short|quick|fohy)\b", re.I)
_LONG = re.compile(r"\b(?:longue?|d[ée]taill\w*|approfondi\w*|long|detailed|lava)\b", re.I)


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in text if not unicodedata.combining(c))


@dataclass(frozen=True)
class ExplainerIntent:
    active: bool = False
    from_context: bool = False  # le sujet est la discussion, pas la phrase
    topic: str = ""             # sujet extrait de la phrase (peut être vide)


def resolve(text: str, *, learn_mode: bool = False) -> ExplainerIntent:
    t = (text or "").strip()[:MAX_CHARS]
    if not t:
        return ExplainerIntent()
    explicit = _EXPLICIT.search(t) is not None
    if not explicit and not (learn_mode and (_MAKE_VIDEO.search(t) or _BARE_VIDEO.search(t))):
        return ExplainerIntent()
    if _ABOUT_EXISTING.search(t) and not _MAKE_VIDEO.search(t) and not explicit:
        return ExplainerIntent()
    topic = _TAIL.sub("", _LEAD.sub("", t)).strip(" .,;:?!")
    topic = _TRAIL.sub("", topic).strip(" .,;:?!")
    words = [w for w in re.findall(r"[a-z0-9]{3,}", _norm(topic))]
    deictic = _DEICTIC.search(t) is not None
    return ExplainerIntent(True, deictic or len(words) < 1, topic[:200])


LEVELS = {
    "college": "collégien (11-15 ans)", "lycee": "lycéen (15-18 ans)",
    "superieur": "étudiant", "adulte": "adulte débutant, sans prérequis",
}


@dataclass
class Brief:
    """Demande complétée : tout ce que le scénario doit respecter."""
    topic: str
    level: str = "lycee"
    language: str = "fr"
    duration_s: int = 75
    broad: bool = False
    notes: list[str] = field(default_factory=list)  # choix faits à la place de l'utilisateur

    @property
    def scenes(self) -> int:
        return max(4, min(8, round(self.duration_s / 11)))

    def directive(self) -> str:
        """Consigne complète pour le rédacteur (sans question en retour)."""
        who = LEVELS.get(self.level, LEVELS["lycee"])
        lines = [
            f"Sujet : {self.topic or 'la notion centrale de la discussion'}.",
            f"Public : {who}. Langue des textes : {self.language}. Durée visée : "
            f"{self.duration_s} secondes, {self.scenes} scènes.",
            "Plan imposé : 1) accroche (une question ou une situation concrète), 2) l'idée "
            "centrale en une phrase simple, 3) UN exemple concret déroulé pas à pas (un calcul "
            "chiffré pour les maths et les sciences ; pour l'histoire, les langues, la "
            "littérature, la géographie ou l'économie : un cas réel, une date clé, une phrase "
            "ou un document analysé, JAMAIS une opération artificielle), 4) l'erreur fréquente "
            "ou l'idée reçue à corriger, 5) récapitulation en 3 points.",
            "Pas de jargon sans l'expliquer ; une idée par scène ; phrases courtes ; vérifie "
            "chaque calcul et chaque affirmation (rien d'inventé).",
        ]
        if self.broad:
            lines.append("Le sujet est trop vaste pour une vidéo courte : choisis UNE notion "
                         "centrale, concrète et adaptée au public, et annonce-la dans le titre.")
        return "\n".join(lines)


def complete(text: str, *, level: str = "lycee", language: str = "fr",
             topic: str = "") -> Brief:
    """Complète une demande vague. `topic` : sujet déduit de la discussion (si la phrase n'en
    porte pas). Les choix faits par défaut sont notés, pour être dits à l'utilisateur."""
    t = (text or "")[:MAX_CHARS]
    intent = resolve(t, learn_mode=True)
    subject = (intent.topic or topic).strip() or topic.strip()
    notes: list[str] = []
    duration = 75
    if m := _MINUTES.search(t):
        duration = int(m.group(1)) * 60
    elif m := _SECONDS.search(t):
        duration = int(m.group(1))
    elif _SHORT.search(t):
        duration = 45
    elif _LONG.search(t):
        duration = 120
    else:
        notes.append("durée d'environ 1 min 15")
    duration = max(30, min(180, duration))
    broad = bool(_BROAD.match(subject)) or len(subject.split()) == 0
    if broad:
        notes.append("une seule notion centrale choisie")
    if level not in LEVELS:
        level = "lycee"
    return Brief(subject, level, language if language in ("fr", "en", "mg") else "fr",
                 duration, broad, notes)
