"""Reconnaît une demande de fichier (« génère un fichier Word… », « fais-moi une carte
mentale… », « exporte en PDF… ») et son format. Il faut un verbe de création ou une
tournure de format (« en PDF », « au format CSV ») : « explique ce PDF » reste du chat."""

from __future__ import annotations

import re

from tontolo.creator.textfile import SAFE_EXT

_VERB = (r"(g[ée]n[èe]re|g[ée]n[ée]rer|cr[ée]e|cr[ée]er|fais|faire|fabrique|r[ée]dige|r[ée]diger|"
         r"pr[ée]pare|pr[ée]parer|exporte|exporter|convertis|convertir|compile|compiler|donne|"
         r"produis|[ée]cris|[ée]crire|dessine|construis|make|create|generate|write|export|build|"
         r"draw|prepare|produce|give me|manaova|mamorona|ataovy|soraty|omeo)")
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


def detect(text: str) -> str | None:
    t = (text or "").lower()
    if len(t) > 4000:
        t = t[:4000]
    has_verb = re.search(rf"\b{_VERB}\b", t) is not None
    as_format = re.search(r"\b(en|au format|in|as|sous forme d['e]|version)\s+"
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
