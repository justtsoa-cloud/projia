"""Rédaction du scénario par un modèle : JSON strict, validé, une réparation, jamais de code."""

from __future__ import annotations

import json
import re
from collections.abc import Awaitable, Callable
from typing import Any

from tontolo.explainer import storyboard
from tontolo.explainer.intent import Brief

Ask = Callable[[list[dict[str, Any]], Callable[[str], bool]], Awaitable[str]]

SYSTEM = """You are an excellent teacher writing the storyboard of a SHORT explainer video, in \
the spirit of 3Blue1Brown: simple, visual, one idea per scene. Reply with ONLY one JSON object, \
no commentary, no code fences.

Schema:
{"title": "...", "scenes": [ SCENE, ... ]}
SCENE is one of:
 {"type":"title","text":"...","subtitle":"...","narration":"..."}
 {"type":"bullets","title":"...","items":["...","..."],"narration":"..."}        (max 4 items)
 {"type":"equation","latex":"\\\\frac{1}{2}+\\\\frac{1}{3}=\\\\frac{5}{6}","caption":"...","narration":"..."}
 {"type":"steps","title":"...","steps":[{"text":"...","latex":"..."},{"text":"..."}],"narration":"..."}
 {"type":"plot","title":"...","expr":"x**2","xmin":-3,"xmax":3,"caption":"...","narration":"..."}
 {"type":"bars","title":"...","labels":["A","B"],"values":[3,5],"narration":"..."}
 {"type":"recap","title":"...","items":["...","...","..."],"narration":"..."}

Rules:
- Follow the plan and the audience given by the user. First scene: type "title". Last scene: \
"recap". 4 to 8 scenes.
- "narration" is what a friendly voice says over the scene: 2 or 3 short, natural sentences (about \
25 to 40 words, so the video reaches the requested length), in the requested language. On-screen texts are even shorter (under 70 characters).
- Fill the screen: a "bullets" scene has 2 to 4 items (never one); put a key formula in an "equation" scene; prefer "steps" for the worked example.
- Include ONE worked example, shown with "steps" or "equation". Maths and sciences: real numbers \
(and a "plot" when a function helps); check every calculation twice. History, languages, \
literature, geography, economy: a real case, a key date, a sentence or a quoted extract analysed \
step by step, never a made-up calculation. Use "bars" ONLY for real, well-known figures; never \
invent numbers or a ranking. Never invent facts.
- LaTeX: plain ASCII only (\\\\frac, \\\\sqrt, ^, _, \\\\cdot, \\\\times, \\\\pi, \\\\text{words}); no \\\\def, \\\\input, \\\\usepackage, no \
accented letters inside LaTeX.
- "expr" for plots: x, numbers, + - * / **, sin cos tan exp log sqrt abs, pi.
- Write all on-screen text and narration in the language requested. For language lessons, use the real grammar terms of the language taught (e.g. \
"simple past", never a French term for an English tense) and keep the examples in that language."""

_LANG = {"fr": "French", "en": "English", "mg": "Malagasy"}


def extract_json(raw: str) -> Any:
    """Premier objet JSON équilibré de la réponse (le modèle peut ajouter du texte autour)."""
    s = re.sub(r"```(?:json)?", "", raw or "")
    start = s.find("{")
    if start < 0:
        raise storyboard.StoryboardError("aucun objet JSON dans la réponse")
    depth, in_str, esc = 0, False, False
    for i in range(start, len(s)):
        c = s[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        elif c == '"':
            in_str = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(s[start:i + 1])
                except ValueError as exc:
                    raise storyboard.StoryboardError(f"JSON invalide : {exc}") from exc
    raise storyboard.StoryboardError("objet JSON incomplet (réponse coupée ?)")


def _user(brief: Brief, context: str) -> str:
    out = [brief.directive(), f"Requested language: {_LANG.get(brief.language, 'French')}."]
    if context.strip():
        out.append("Conversation so far (use it to stay consistent; do not repeat it):\n"
                   + context.strip()[:3500])
    return "\n\n".join(out)


def _valid(raw: str, language: str) -> bool:
    try:
        storyboard.validate(extract_json(raw), language=language)
        return True
    except storyboard.StoryboardError:
        return False


async def write(brief: Brief, ask: Ask, context: str = "") -> dict[str, Any]:
    """Scénario validé. `ask` reçoit un critère d'acceptation : seuls les JSON qui passent la
    validation comptent (plusieurs modèles peuvent courir ; le premier valide gagne). Une
    réparation si le premier jet est invalide ; StoryboardError sinon."""
    messages = [{"role": "system", "content": SYSTEM},
                {"role": "user", "content": _user(brief, context)}]

    def accept(text: str) -> bool:
        return _valid(text, brief.language)

    raw = await ask(messages, accept)
    try:
        return storyboard.validate(extract_json(raw), language=brief.language)
    except storyboard.StoryboardError as first:
        messages += [{"role": "assistant", "content": (raw or "")[:6000]},
                     {"role": "user", "content": (
                         f"Your JSON was rejected: {first}. Fix exactly that and reply with the "
                         "complete corrected JSON object only.")}]
        return storyboard.validate(extract_json(await ask(messages, accept)),
                                   language=brief.language)
