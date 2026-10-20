"""« Fais-en une image », « transforme tout cela en poster » : l'intention de produire une
image à partir de la discussion en cours.

Trois décisions, toutes sans appel de modèle, déterministes et bornées (entrée tronquée à
500 caractères, expressions régulières sans répétition imbriquée : pas de blocage possible) :

1. `kind` : « none » (autre chose), « illustration » (une image de modèle générateur) ou
   « poster » (un document dense à texte et formules EXACTS : un modèle d'image ne sait pas
   écrire une formule sans faute, un poster LaTeX si) ;
2. `from_context` : la demande ne dit pas de quoi il s'agit (« ça », « tout cela », « je veux
   ça en image », « par rapport à la discussion ») : le sujet est le fil de la discussion ;
3. jamais de faux positif sur une question sur une image existante (« décris cette image »).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

MAX_CHARS = 500


@dataclass(frozen=True)
class ImageIntent:
    kind: str = "none"          # none | illustration | poster
    from_context: bool = False  # le sujet est la discussion, pas la phrase


NONE = ImageIntent()

_FORM = (r"(?:images?|illustrations?|dessins?|visuels?|posters?|affiches?|infographies?|"
         r"infographics?|pictures?|photos?|sary|sarin-kevitra|pictogrammes?)")
_ASK = (r"(?:g[ée]n[èe]re\w*|cr[ée]e\w*|fais\w*|faire|dessine\w*|produis\w*|r[ée]alise\w*|"
        r"illustre\w*|visualise\w*|transforme\w*|mets|mettre|convertis\w*|donne\w*|montre\w*|"
        r"veux|voudrais|souhaite\w*|demande\w*|besoin|aimerais|make|create|generate|draw|"
        r"illustrate|turn|convert|want|need|give|show|manaova|mamorona|ataovy|tiako|omeo)")
# « en image », « sous forme de poster », « as a picture »
_AS_FORM = re.compile(
    rf"\b(?:en\s+|sous (?:la )?forme\s+(?:d['’]|de\s+|du\s+)?|in\s+|as\s+)"
    rf"(?:an?\s+|une?\s+|un\s+)?{_FORM}\b", re.I)
_MAKE_FORM = re.compile(
    rf"\b{_ASK}\b(?:\s+\S{{1,14}}){{0,4}}?\s+(?:une?\s+|des\s+|d'|l'|the\s+|an?\s+|ny\s+)?"
    rf"{_FORM}\b", re.I)
_VERB_ONLY = re.compile(
    r"\b(?:illustre\w*|illustrer|visualise\w*|dessine\w*|dessiner|draw|illustrate|visuali[sz]e)\b",
    re.I)
# Parler d'une image existante : jamais une création.
_ABOUT = re.compile(
    r"\b(?:d[ée]cris\w*|explique\w*|analyse\w*|lis|lire|que (?:montre|dit|repr[ée]sente)|"
    r"qu'est-ce que|c'est quoi|what (?:does|is)|describe|explain|read|hazavao|inona no)\b", re.I)
_CREATE = re.compile(
    r"\b(?:g[ée]n[èe]re\w*|cr[ée]e\w*|dessine\w*|produis\w*|fabrique\w*|generate|create|draw|"
    r"make|mamorona|manaova|transforme\w*|convertis\w*|mets|fais\w*|veux|demande\w*)\b", re.I)
# Le sujet est « ça » : la discussion
_DEICTIC = re.compile(
    r"\b(?:[çc]a|cela|ceci|tout (?:[çc]a|cela|ceci)|ci-dessus|ci dessus|"
    r"la discussion|cette discussion|notre (?:[ée]change|discussion|conversation)|"
    r"cette (?:explication|conversation|r[ée]ponse)|ce sujet|le sujet|ce que (?:tu|vous) "
    r"(?:viens|venez) de|par rapport [àa] (?:la|cette|notre|[çc]a|cela)|"
    r"based on (?:this|that|our|the) (?:chat|discussion|conversation)|all (?:of )?this|"
    r"this|that|everything above|above|izany|ity rehetra)\b", re.I)
# Texte exact exigé : un poster document plutôt qu'une image de modèle générateur
_POSTER = re.compile(r"\b(?:posters?|affiches?|infographies?|infographics?|fiche visuelle)\b", re.I)
_EXACT = re.compile(
    r"\b(?:d[ée]taill\w*|compact\w*|sans (?:faute|erreur)s?|pr[ée]cis\w*|exact\w*|complet\w*|"
    r"formules?|texte|lisible|tout le contenu|rigoureu\w*|detailed|accurate|no (?:mistakes|errors)|"
    r"error-free|text|formulas?|complete|thorough)\b", re.I)
_STOP = frozenset([
    "une", "un", "des", "les", "le", "la", "l", "de", "du", "d", "en", "et", "ou", "pour",
    "sur", "par", "avec", "dans", "ce", "cet", "cette", "ces", "je", "tu", "il", "elle", "on",
    "nous", "vous", "me", "te", "moi", "toi", "veux", "voudrais", "demande", "besoin", "peux",
    "peut", "aimerais", "souhaite", "faire", "fais", "genere", "generer", "cree", "creer",
    "dessine", "dessiner", "produis", "realise", "illustre", "visualise", "transforme",
    "transformer", "mets", "mettre", "convertis", "donne", "montre", "image", "images",
    "illustration", "illustrations", "dessin", "dessins", "visuel", "visuels", "poster",
    "posters", "affiche", "affiches", "infographie", "infographies", "sous", "forme", "tres",
    "bien", "beau", "belle", "plus", "encore", "aussi", "svp", "stp", "please", "make",
    "create", "generate", "draw", "want", "need", "give", "show", "the", "and", "for", "with",
    "this", "that", "picture", "photo", "pictures", "sary",
])


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in text if not unicodedata.combining(c))


def _content_words(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9]{3,}", _norm(text)) if w not in _STOP]


def resolve(text: str) -> ImageIntent:
    """Intention d'image d'un message utilisateur (voir le module)."""
    t = (text or "").strip()[:MAX_CHARS]
    if not t:
        return NONE
    wants = _AS_FORM.search(t) is not None or _MAKE_FORM.search(t) is not None
    if not wants:
        # « Illustre cela », « peux-tu dessiner ça ? » : le verbe seul suffit si « ça » est dit.
        if _VERB_ONLY.search(t) and _DEICTIC.search(t):
            return ImageIntent("illustration", True)
        return NONE
    if _ABOUT.search(t) and not _CREATE.search(t):
        return NONE  # « décris cette image », « que montre ce poster ? »
    deictic = _DEICTIC.search(t) is not None
    # Sans sujet propre (« je veux ça en image », « génère une image ») : le fil en tient lieu.
    from_context = deictic or len(_content_words(t)) <= 2
    kind = "poster" if (_POSTER.search(t) and _EXACT.search(t)) else "illustration"
    return ImageIntent(kind, from_context)
