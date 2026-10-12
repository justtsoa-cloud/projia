"""Reconnaît une demande de fichier (« génère un fichier Word… », « fais-moi une carte
mentale… », « exporte en PDF… ») et son format. Il faut un verbe de création ou une
tournure de format (« en PDF », « au format CSV ») : « explique ce PDF » reste du chat."""

from __future__ import annotations

import re

from tontolo.creator.textfile import SAFE_EXT

_VERB = (r"(g[ée]n[èe]re|g[ée]n[ée]rer|cr[ée]e|cr[ée]er|fais|faire|fabrique|r[ée]dige|r[ée]diger|"
         r"pr[ée]pare|pr[ée]parer|exporte|exporter|convertis|convertir|compile|compiler|donne|"
         r"produis|[ée]cris|[ée]crire|dessine|construis|make|create|generate|write|export|build|"
         r"draw|prepare|produce|give me|manaova|mamorona|ataovy|soraty|omeo|manorata|amboary|"
         r"vokary|avoahy)")
_FORMATS: list[tuple[str, str]] = [
    ("mindmap", r"carte[s]? (mentale|heuristique)|mind ?-?maps?|sch[ée]ma heuristique|"
                r"carte conceptuelle|sarintsaina|sarin-kevitra"),
    ("pptx", r"power ?point|pptx|diaporama|diapositives?|slides?|pr[ée]sentation (pptx|"
             r"powerpoint|en diapos?)"),
    ("xlsx", r"excel|xlsx|tableur|feuille de calcul|spreadsheet|classeur"),
    ("docx", r"\bdocx\b|\bword\b|fichier word|document word"),
    ("latex", r"\blatex\b|\bfichier \.?tex\b"),
    ("pdf", r"\bpdf\b"),
    ("chart", r"graphique|histogramme|camembert|diagramme (en|circulaire|en barres|"
              r"en b[âa]tons)|courbe de|bar chart|pie chart|line chart|\bchart\b"),
    ("diagram", r"organigramme|logigramme|flowchart|frise chronologique|timeline|"
                r"diagramme de (gantt|s[ée]quence|classes?|flux)|sch[ée]ma (de|du|des|d')"),
]
_TEXT_EXT = re.compile(r"(?:fichier|file|format|en|in|as|au format)\s+\.?(csv|json|html|svg|"
                       r"markdown|md|txt|texte|python|py|javascript|js|sql|xml|yaml|ics|"
                       r"calendrier|css|java|c\+\+|cpp|dart|kotlin|bash|sh)\b", re.I)
_EXT_ALIASES = {"markdown": "md", "texte": "txt", "python": "py", "javascript": "js",
                "calendrier": "ics", "c++": "cpp", "kotlin": "kt", "bash": "sh"}


_BUNDLE = re.compile(
    r"\b(zip|archive (zip|compress[ée]e)|plusieurs fichiers|several files|multiple files|"
    r"multi-?fichiers?|"
    r"rakitra maromaro|arborescence|un fichier par (chapitre|section|module|page|partie)|"
    r"one file per (chapter|section|module|page)|(chaque|each) (chapitre|chapter|module) "
    r"(dans|in) (un|a|its own) (fichier|file)|(dossier|projet|folder|project) (complet |"
    r"structur[ée] |latex |de code |python |web )*(en|avec|with|in) (plusieurs|multiple|"
    r"several) fichiers|structur[ée] en (plusieurs )?fichiers)\b")


def detect(text: str) -> str | None:
    t = (text or "").lower()
    if len(t) > 4000:
        t = t[:4000]
    has_verb = re.search(rf"\b{_VERB}\b", t) is not None
    if _BUNDLE.search(t) and has_verb:
        return "bundle"  # plusieurs fichiers : livrés ensemble dans une archive .zip
    from tontolo.creator.book import asks_for_book, wants_book

    if (has_verb and wants_book(t)) or asks_for_book(t):
        return "book"  # livre / long document : plan puis chapitres, livré en PDF
    as_format = re.search(r"\b(en|au format|in|as|sous forme d['e]|version|amin'ny)\s+"
                          r"(pdf|docx|word|excel|xlsx|pptx|powerpoint|latex)\b", t)
    for kind, pattern in _FORMATS:
        if re.search(pattern, t) and (has_verb or as_format):
            return kind
    m = _TEXT_EXT.search(t)
    if m and has_verb:
        ext = _EXT_ALIASES.get(m.group(1).lower(), m.group(1).lower())
        if SAFE_EXT.match(ext):
            return f"text:{ext}"
    return None


def valid(kind: str) -> bool:
    from tontolo.creator.pipeline import KINDS

    return kind in KINDS or (kind.startswith("text:") and bool(SAFE_EXT.match(kind[5:])))


_REVISION = re.compile(
    r"\b(ajoute|rajoute|ajouter|rajouter|compl[èe]te|d[ée]taille|d[ée]veloppe|enrichis|"
    r"modifie|change|corrige|am[ée]liore|remplace|enl[èe]ve|supprime|retire|raccourcis|"
    r"allonge|simplifie|traduis|mets|plus de|davantage|moins de|"
    r"add|more|expand|extend|update|fix|improve|include|remove|shorten|simplify|translate|"
    r"ampio|ampiana|ovay|ahitsio|hatsarao|esory)\b", re.I)


# Retour sur le fichier qui vient d'être livré, sans verbe de modification :
# « excellent mais des vraies citations », « plus court », « trop long », « en couleur ».
_PRAISE = (r"(excellent|parfait|super|bien|bravo|g[ée]nial|top|ok|oui|great|good|nice|"
           r"perfect|thanks)")
_BUT = r"(mais|sauf|par contre|cependant|but)"
_STARTS = (r"(mais|plut[ôo]t|sauf|il manque|il faudrait|trop|pas assez|encore|aussi|en plus|"
           r"avec|sans|plus |moins |en couleur|en fran[çc]ais|en anglais|but |more |less |"
           r"too |also |instead|with |without )")
_QUALITY = r"(vrai(e)?s?|r[ée]el(le)?s?|exact(e)?s?|pr[ée]cis(e)?s?|real|actual|authentic|accurate)"
_FEEDBACK = re.compile(rf"\b{_PRAISE}\b.{{0,12}}\b{_BUT}\b|^\s*{_STARTS}|\b{_QUALITY}\b", re.I)
# Pas une demande de modification : simple politesse ou question de compréhension.
_NOT_A_REVISION = re.compile(
    r"^\s*(merci|ok|d'accord|super|parfait|bien|top|bravo|thanks|thank you|great|"
    r"misaotra)\s*[.!]*\s*$|\b(comprends|compris|explique|pourquoi|comment|c'est quoi|"
    r"qu'est-ce|que signifie|why|how|what is|what does|explain)\b", re.I)


def is_revision(text: str) -> bool:
    """Demande de modification du fichier qui vient d'être créé (et non une question)."""
    t = (text or "").strip()
    if not t or len(t) >= 600 or t.endswith("?") or _NOT_A_REVISION.search(t):
        return False
    return bool(_REVISION.search(t)) or (len(t) <= 240 and bool(_FEEDBACK.search(t)))
