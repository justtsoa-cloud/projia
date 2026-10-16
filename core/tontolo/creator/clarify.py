"""Questions à choix AVANT une création longue (« écris un rapport », « fais un livre ») :
quand le public ou la longueur ne sont pas précisés, on les demande d'abord — questions fixes,
sans appel de modèle (instantané, toujours bien formé), dans la langue de la demande.
La réponse de l'utilisateur relance ensuite la création avec la demande complétée."""

from __future__ import annotations

import re
from typing import Any

ASK_ID = "create-ask"
ASKED_KINDS = frozenset({"book", "docx", "pdf", "pptx", "bundle"})
MAX_WORDS = 25  # au-delà, la demande est déjà détaillée : on ne la retarde pas

_AUDIENCE = re.compile(
    r"\b(pour (les |des |mes |un |une )?|for |ho an'?n?y? ?)?(élèves?|eleves?|lycéens?|collégiens?|"
    r"étudiants?|etudiants?|enfants?|adultes?|débutants?|experts?|professionnels?|pros?|"
    r"enseignants?|profs?|parents?|clients?|équipe|jury|grand public|primaire|collège|lycée|"
    r"licence|master|terminale|seconde|première|students?|kids?|children|beginners?|"
    r"teachers?|team|managers?|mpianatra|ankizy|mpampianatra|ray aman-dreny|"
    r"sixi[èe]mes?|cinqui[èe]mes?|quatri[èe]mes?|troisi[èe]mes?|[3-6]\s?[eè](?:me)?|"
    r"cp|ce[12]|cm[12]|maternelle|bts|iut|prépa|prepa|primary|secondary|high school|"
    r"middle school|grade\s?\d{1,2}|\d{1,2}(?:st|nd|rd|th) grade|year \d{1,2}|"
    r"kilasy|zokiolona|olon-dehibe)\b", re.I)
_NUM = (r"(?:\d{1,4}|un|une|deux|trois|quatre|cinq|six|sept|huit|neuf|dix|douze|quinze|vingt|"
        r"one|two|three|four|five|six|seven|eight|nine|ten|twelve|fifteen|twenty|"
        r"iray|roa|telo|efatra|dimy|enina|fito|valo|sivy|folo)")
_LENGTH = re.compile(rf"\b{_NUM}[\s-]*(pages?|p\.|pejy|diapos?|slides?|mots|words|teny|"
                     r"chapitres?|chapters?|lignes?|lines?|minutes?|mn)\b|"
                     r"\bpejy\s+" + _NUM + r"\b|\b(court|courte|bref|brève|short|"
                     r"long|longue|détaillé|détaillée|detailed|fohy|lava|une page|one page)\b",
                     re.I)
# Transformation d'une matière existante (« convertis ce HTML en PDF », « mets ce texte en
# Word ») : tout est déjà donné, on ne demande rien.
_TRANSFORM = re.compile(r"\b(convert\w*|transform\w*|mets?|exporte\w*|tradui\w*|translate|"
                        r"résume\w*|summari[sz]e|reformule\w*|corrige\w*|ce|cet|cette|ces|"
                        r"this|these|ity|ireo)\b", re.I)
_FR = re.compile(r"\b(le|la|les|un|une|des|du|sur|pour|avec|écris|ecris|fais|rédige|redige|"
                 r"crée|cree|génère|genere|rapport|livre|exposé|expose)\b", re.I)
_EN = re.compile(r"\b(the|write|make|create|about|for|report|book|please|an?)\b", re.I)
_MG = re.compile(r"\b(ny|sy|amin'?ny|momba|azafady|manorata|mamorona|boky|tatitra|ho an'?ny)\b",
                 re.I)

_TEXT = {
    "fr": {"who": "Pour quel public ?", "who_o": ["Élèves", "Étudiants", "Professionnels",
                                                   "Grand public"],
           "len": "Quelle longueur ?", "len_o": ["Courte (1-2 pages)", "Moyenne (5 pages)",
                                                 "Longue (10 pages et plus)"],
           "len_b": "Combien de pages ?", "len_bo": ["10 pages", "20 pages", "50 pages"]},
    "en": {"who": "Who is it for?", "who_o": ["Pupils", "Students", "Professionals",
                                               "General public"],
           "len": "How long?", "len_o": ["Short (1-2 pages)", "Medium (5 pages)",
                                         "Long (10+ pages)"],
           "len_b": "How many pages?", "len_bo": ["10 pages", "20 pages", "50 pages"]},
    "mg": {"who": "Ho an'iza?", "who_o": ["Mpianatra", "Mpianatra oniversite", "Matihanina",
                                           "Besinimaro"],
           "len": "Halavany?", "len_o": ["Fohy (pejy 1-2)", "Antonony (pejy 5)",
                                        "Lava (pejy 10 mahery)"],
           "len_b": "Pejy firy?", "len_bo": ["Pejy 10", "Pejy 20", "Pejy 50"]},
}


def language_of(text: str, default: str = "fr") -> str:
    """Langue de la demande (les questions et les réponses doivent la suivre, sinon le document
    risque d'être écrit dans la langue de l'interface)."""
    scores = {"fr": len(_FR.findall(text)), "en": len(_EN.findall(text)),
              "mg": len(_MG.findall(text))}
    best = max(scores.values())
    if best == 0:
        return default if default in _TEXT else "fr"
    leaders = [k for k, v in scores.items() if v == best]
    return default if default in leaders else leaders[0]


def questions_for(kind: str, text: str, default_lang: str = "fr") -> list[dict[str, Any]]:
    """Questions à poser avant de créer (vide : la demande est assez précise)."""
    if kind not in ASKED_KINDS or len(text.split()) > MAX_WORDS or _TRANSFORM.search(text):
        return []
    t = _TEXT[language_of(text, default_lang)]
    out: list[dict[str, Any]] = []
    if not _AUDIENCE.search(text):
        out.append({"question": t["who"], "options": t["who_o"], "multiple": False})
    if not _LENGTH.search(text):
        book = kind == "book"
        out.append({"question": t["len_b" if book else "len"],
                    "options": t["len_bo" if book else "len_o"], "multiple": False})
    return out


def ask_messages(kind: str, request: str, questions: list[dict[str, Any]]
                 ) -> list[dict[str, Any]]:
    """Messages enregistrés dans le fil (même forme qu'un appel `ask_user` du modèle) : la carte
    revient à la réouverture, et la réponse sait quelle création reprendre."""
    import json

    args = json.dumps({"questions": questions, "create": {"kind": kind, "request": request}},
                      ensure_ascii=False)
    return [
        {"role": "assistant", "content": "", "tool_calls": [{
            "id": ASK_ID, "type": "function",
            "function": {"name": "ask_user", "arguments": args}}]},
        {"role": "tool", "tool_call_id": ASK_ID, "name": "ask_user",
         "content": "Questions affichées ; la création reprendra avec les réponses."},
    ]


def pending_creation(recent: list[dict[str, Any]]) -> tuple[str, str] | None:
    """(format, demande) si le dernier échange est une question de création sans réponse."""
    import json

    for m in reversed(recent):
        role = m.get("role")
        if role == "tool":
            continue
        if role != "assistant":
            return None
        for call in m.get("tool_calls") or []:
            if call.get("id") == ASK_ID:
                try:
                    create = json.loads(call["function"]["arguments"]).get("create") or {}
                except (ValueError, KeyError, TypeError, AttributeError):
                    return None
                kind, request = str(create.get("kind") or ""), str(create.get("request") or "")
                return (kind, request) if kind and request else None
        return None
    return None
