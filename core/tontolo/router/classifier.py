"""Classification de la tâche (section 4.1) : catégorie, modalité et besoins.

Étage 1 : heuristiques rapides (blocs de code, LaTeX, pièces jointes, longueur,
mots-clés français, anglais et malgache). Étage 2 optionnel : si le résultat est
ambigu, un petit modèle gratuit répond en JSON (`llm_classify`).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from tontolo.catalog.models import Category

# Mots-clés pondérés par catégorie (fr / en / mg). Les expressions sont des regex.
_KEYWORDS: dict[Category, tuple[tuple[str, float], ...]] = {
    Category.IMAGE_GEN: (
        (r"\b(dessine|dessiner|illustre|illustration|peins|peindre)\b", 3),
        (r"\b(g[ée]n[èe]re|cr[ée]e|fais|fabrique|produis)[- ]?(moi )?(une |un )?"
         r"(image|photo|dessin|logo|affiche|illustration|ic[ôo]ne)", 4),
        (r"\b(draw|paint|sketch)\b", 3),
        (r"\b(generate|create|make)( me)? (an? )?(image|picture|photo|logo|poster|icon)", 4),
        (r"\b(manaova|mamorona) sary\b|\bsary\b.*\b(manaova|mamorona)\b", 4),
    ),
    Category.IMAGE_EDIT: (
        (r"\b(modifie|retouche|[ée]dite|change|recadre|enl[èe]ve|supprime|ajoute)\b.*"
         r"\b(image|photo|fond|arri[èe]re-plan)\b", 4),
        (r"\b(edit|retouch|remove|replace)\b.*\b(image|photo|background)\b", 4),
        (r"\bovay ny sary\b", 4),
    ),
    Category.VIDEO_GEN: (
        (r"\b(vid[ée]o|clip|anime cette image|animation)\b", 3),
        (r"\b(video|animate)\b", 3),
        (r"\bhoronan-?tsary\b", 4),
    ),
    Category.TTS: (
        (r"\b(lis|lire|dis|prononce)\b.*\b([àa] (voix|haute voix)|[àa] l'oral|audio)\b", 4),
        (r"\bvoix haute\b|\bsynth[èe]se vocale\b", 4),
        (r"\b(read (it |this )?(aloud|out loud)|text[- ]to[- ]speech|say it out loud)\b", 4),
        (r"\bvakio mafy\b", 4),
    ),
    Category.STT: (
        (r"\b(transcris|transcrire|transcription|retranscris)\b", 4),
        (r"\b(transcribe|transcription|speech[- ]to[- ]text)\b", 4),
        (r"\bsoraty ny feo\b", 4),
    ),
    Category.MUSIC_SFX: (
        (r"\b(musique|chanson|m[ée]lodie|bruitage|effet sonore|jingle)\b", 3),
        (r"\b(music|song|melody|sound effect|sfx|jingle)\b", 3),
        (r"\bhira\b", 3),
    ),
    Category.CODE: (
        (r"```", 3),
        (r"\b(python|javascript|typescript|java|rust|golang|kotlin|dart|flutter|c\+\+|sql|"
         r"bash|regex|html|css|react|django|fastapi|docker)\b", 2),
        (r"\b(code|coder|fonction|function|bug|d[ée]bogue|debug|compile|script|classe|"
         r"m[ée]thode|api|refactor|stack ?trace|exception|traceback)\b", 1.5),
        (r"\b(def |class |import |#include|console\.log|public static)", 3),
        (r"\bkaody\b|\bprogramma\b", 2),
    ),
    Category.MATH: (
        (r"\$[^$]+\$|\\\(|\\\[|\\frac|\\int|\\sum|\\sqrt", 3),
        (r"\b([ée]quation|int[ée]grale|d[ée]riv[ée]e|th[ée]or[èe]me|d[ée]montre|"
         r"d[ée]monstration|matrice|probabilit[ée]|limite|polyn[ôo]me|calcule|r[ée]sous)\b", 2),
        (r"\b(equation|integral|derivative|theorem|prove|proof|matrix|probability|solve|"
         r"calculate|compute)\b", 2),
        (r"\d+\s*[-+*/^]\s*\d+", 1),
        (r"\b(kajy|fitoviana|porofo)\b", 2),
        (r"\b(latex|tikz|calcul diff[ée]rentiel|calculus|alg[èe]bre|analyse r[ée]elle)\b", 2),
    ),
    Category.TRANSLATION: (
        (r"\b(tradui[st]|traduction|traduire|en anglais|en fran[çc]ais|en malgache)\b", 4),
        (r"\b(translate|translation|in english|in french)\b", 4),
        (r"\b(adikao|dikao|amin'ny teny)\b", 4),
    ),
    Category.WRITING: (
        (r"\b(r[ée]dige|[ée]cris|po[èe]me|lettre|histoire|conte|article|discours|"
         r"dissertation|r[ée]sum[ée]|slogan|courriel|e-?mail)\b", 2),
        (r"\b(write|poem|letter|story|essay|article|speech|summar(y|ize)|email)\b", 2),
        (r"\b(soraty|tantara|tononkalo|taratasy)\b", 2),
        (r"\b(dossier|manuel|cours|rapport|m[ée]moire|document|chapitres?)\b", 1.5),
    ),
    Category.SEARCH: (
        (r"\b(actualit[ée]s?|aujourd'hui|derni[èe]res? (nouvelles|infos)|cette semaine|"
         r"en ce moment|m[ée]t[ée]o|cours (du|de l')|prix actuel|r[ée]cemment|qui a gagn[ée])\b",
         3),
        (r"\b(news|today|latest|this week|right now|weather|current price|recently|"
         r"who won)\b", 3),
        (r"\b(vaovao|androany|toetr'andro)\b", 3),
        (r"\b(cherche|recherche|trouve)\b.*\b(sur (le )?web|en ligne|internet|sources?)\b", 3),
        (r"\b(search|look up|google)\b", 2),
    ),
    Category.REASONING: (
        (r"\b(pourquoi|analyse|compare|raisonne|logique|[ée]nigme|strat[ée]gie|"
         r"avantages et inconv[ée]nients|[ée]tape par [ée]tape)\b", 1.5),
        (r"\b(why|analy[sz]e|compare|reason|logic|puzzle|riddle|strategy|pros and cons|"
         r"step by step)\b", 1.5),
        (r"\b(nahoana|hazavao)\b", 1.5),
    ),
}

_MEDIA_OUT = {Category.IMAGE_GEN: "image", Category.IMAGE_EDIT: "image",
              Category.VIDEO_GEN: "video", Category.TTS: "audio", Category.MUSIC_SFX: "audio"}
_COMPILED = {cat: [(re.compile(p, re.I), w) for p, w in pats] for cat, pats in _KEYWORDS.items()}
LONG_CONTEXT_TOKENS = 32_000
AMBIGUITY_MARGIN = 1.0


@dataclass
class TaskProfile:
    category: Category = Category.CHAT
    modality_in: list[str] = field(default_factory=lambda: ["text"])
    modality_out: str = "text"
    needs_tools: bool = False
    needs_vision: bool = False
    min_context: int = 0
    latency_pref: str = "normal"       # « fast » pour les échanges courts
    force_search: bool = False
    confidence: float = 1.0
    scores: dict[str, float] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "category": self.category.value, "modality_in": self.modality_in,
            "modality_out": self.modality_out, "needs_tools": self.needs_tools,
            "needs_vision": self.needs_vision, "min_context": self.min_context,
            "latency_pref": self.latency_pref, "force_search": self.force_search,
            "confidence": round(self.confidence, 2),
        }


def estimate_tokens(messages: list[dict[str, Any]]) -> int:
    total = 0
    for m in messages:
        c = m.get("content")
        if isinstance(c, str):
            total += len(c)
        elif isinstance(c, list):
            for part in c:
                if part.get("type") == "text":
                    total += len(part.get("text", ""))
                else:
                    total += 1000  # image ou audio : forfait prudent
        for tc in m.get("tool_calls") or []:
            total += len(json.dumps(tc))
    return int(total / 3.5) + 4 * len(messages)


def _text_and_parts(message: dict[str, Any]) -> tuple[str, set[str]]:
    c = message.get("content")
    if isinstance(c, str):
        return c, set()
    kinds: set[str] = set()
    texts: list[str] = []
    for part in c or []:
        t = part.get("type", "")
        if t == "text":
            texts.append(part.get("text", ""))
        elif t in ("image_url", "input_image"):
            kinds.add("image")
        elif t in ("input_audio", "audio_url"):
            kinds.add("audio")
        elif t in ("file", "video_url"):
            kinds.add("video" if t == "video_url" else "file")
    return "\n".join(texts), kinds


def classify(
    messages: list[dict[str, Any]], *, tools_available: bool = False,
    forced: Category | str | None = None,
) -> TaskProfile:
    last_user = next((m for m in reversed(messages) if m.get("role") == "user"), None)
    text, parts = _text_and_parts(last_user) if last_user else ("", set())
    scores: dict[Category, float] = {}
    for cat, pats in _COMPILED.items():
        s = sum(w for rx, w in pats if rx.search(text))
        if s:
            scores[cat] = s
    if "image" in parts:
        if scores.get(Category.IMAGE_EDIT) or scores.get(Category.IMAGE_GEN):
            scores[Category.IMAGE_EDIT] = scores.get(Category.IMAGE_EDIT, 0) + 4
            scores.pop(Category.IMAGE_GEN, None)
        else:
            scores[Category.VISION] = scores.get(Category.VISION, 0) + 5
    if "audio" in parts:
        scores[Category.STT] = scores.get(Category.STT, 0) + (5 if len(text) < 200 else 2)
    if "video" in parts:
        scores[Category.VISION] = scores.get(Category.VISION, 0) + 3

    tokens = estimate_tokens(messages)
    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    if forced:
        category, confidence = Category(forced), 1.0
    elif ranked:
        category = ranked[0][0]
        second = ranked[1][1] if len(ranked) > 1 else 0.0
        confidence = min(1.0, (ranked[0][1] - second) / 3 + 0.4)
    else:
        category, confidence = Category.CHAT, 0.5
    if tokens > LONG_CONTEXT_TOKENS and category in (Category.CHAT, Category.WRITING,
                                                       Category.REASONING):
        category = Category.LONG_CONTEXT

    profile = TaskProfile(
        category=category,
        modality_in=["text", *sorted(parts)],
        modality_out=_MEDIA_OUT.get(category, "text"),
        needs_vision="image" in parts and category not in (Category.IMAGE_EDIT,),
        min_context=int(tokens * 1.2) + 1024,
        latency_pref="fast" if len(text) < 80 and category == Category.CHAT else "normal",
        force_search=category == Category.SEARCH,
        confidence=confidence,
        scores={c.value: s for c, s in ranked},
    )
    profile.needs_tools = profile.force_search or (tools_available and category in (
        Category.AGENTIC, Category.SEARCH))
    if profile.force_search:
        profile.category = Category.SEARCH
    return profile


def is_ambiguous(profile: TaskProfile) -> bool:
    return profile.confidence < 0.5


CLASSIFIER_PROMPT = (
    "Classe la demande de l'utilisateur. Réponds uniquement en JSON : "
    '{"category": one of [' + ", ".join(f'"{c.value}"' for c in Category) + "]}"
)


def parse_llm_category(text: str) -> Category | None:
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return None
    try:
        return Category(json.loads(m.group(0)).get("category"))
    except (ValueError, AttributeError, TypeError):
        return None
