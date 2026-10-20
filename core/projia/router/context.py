"""Adaptation de l'historique au modèle cible (section 5.3).

- Contexte plus petit : on garde les messages système et les derniers tours ;
  les tours plus anciens sont remplacés par un résumé (produit par un modèle
  gratuit et conservé en base). Sans résumé possible : troncature signalée.
- Modèle sans appel d'outils natif : les messages d'outils sont dégradés en texte.
- Modèle sans vision : les images sont remplacées par une mention textuelle.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

from projia.catalog.models import ModelInfo
from projia.router.classifier import estimate_tokens

Summarizer = Callable[[list[dict[str, Any]]], Awaitable[str | None]]


def strip_meta(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{k: v for k, v in m.items() if not k.startswith("_")} for m in messages]


def degrade_tools(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for m in messages:
        if m.get("role") == "assistant" and m.get("tool_calls"):
            calls = "; ".join(
                f"{tc['function']['name']}({tc['function'].get('arguments', '')})"
                for tc in m["tool_calls"]
            )
            text = (m.get("content") or "") + f"\n[Appel d'outil : {calls}]"
            out.append({"role": "assistant", "content": text.strip()})
        elif m.get("role") == "tool":
            out.append({"role": "user",
                        "content": f"[Résultat de l'outil {m.get('name', '')}]\n"
                                   f"{_as_text(m.get('content'))}"})
        else:
            out.append(m)
    return out


def degrade_images(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for m in messages:
        c = m.get("content")
        if isinstance(c, list):
            parts = []
            for p in c:
                if p.get("type") == "text":
                    parts.append(p.get("text", ""))
                else:
                    parts.append(f"[pièce jointe {p.get('type', 'fichier')} non lisible par "
                                 "ce modèle]")
            out.append({**m, "content": "\n".join(parts)})
        else:
            out.append(m)
    return out


def _as_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    return json.dumps(content, ensure_ascii=False)


def budget_for(model: ModelInfo) -> int:
    ctx = model.context_length or 8192
    reserve = min(8192, max(1024, ctx // 4))
    return max(1024, ctx - reserve)


def _split_turns(messages: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Découpe en tours commençant par un message utilisateur (outils rattachés)."""
    turns: list[list[dict[str, Any]]] = []
    for m in messages:
        if m.get("role") == "user" or not turns:
            turns.append([m])
        else:
            turns[-1].append(m)
    return turns


async def fit(
    messages: list[dict[str, Any]],
    model: ModelInfo,
    *,
    summary: str | None = None,
    summarizer: Summarizer | None = None,
) -> tuple[list[dict[str, Any]], str | None, int]:
    """Renvoie (messages adaptés, nouveau résumé éventuel, nb de messages résumés)."""
    msgs = strip_meta(messages)
    if not model.supports_tools:
        msgs = degrade_tools(msgs)
    if not model.supports_vision:
        msgs = degrade_images(msgs)
    budget = budget_for(model)
    if estimate_tokens(msgs) <= budget:
        return msgs, None, 0

    system = [m for m in msgs if m.get("role") == "system"]
    rest = [m for m in msgs if m.get("role") != "system"]
    turns = _split_turns(rest)
    kept: list[list[dict[str, Any]]] = []
    used = estimate_tokens(system) + 600  # place pour le résumé
    for turn in reversed(turns):
        t = estimate_tokens(turn)
        if kept and used + t > budget:
            break
        kept.insert(0, turn)
        used += t
    dropped = [m for turn in turns[: len(turns) - len(kept)] for m in turn]
    new_summary = None
    if dropped:
        if summarizer is not None:
            to_sum = ([{"role": "system", "content": f"Résumé précédent : {summary}"}]
                      if summary else []) + dropped
            new_summary = await summarizer(to_sum)
        note = new_summary or summary
        header = (f"Résumé des échanges précédents : {note}" if note else
                  "Note : les échanges les plus anciens ont été retirés pour tenir dans le "
                  "contexte de ce modèle.")
        system = [*system, {"role": "system", "content": header}]
    flat = [m for turn in kept for m in turn]
    # Si un seul tour dépasse encore le budget, on tronque son texte.
    out = [*system, *flat]
    while estimate_tokens(out) > budget and flat:
        last = flat[-1]
        if isinstance(last.get("content"), str) and len(last["content"]) > 2000:
            last["content"] = last["content"][: len(last["content"]) // 2] + "\n[…tronqué]"
        else:
            break
        out = [*system, *flat]
    return out, new_summary, len(dropped)


SUMMARY_PROMPT = (
    "Résume fidèlement cette conversation en français, en 10 lignes maximum : faits, "
    "décisions, préférences de l'utilisateur et questions en suspens. Ne rajoute rien."
)
