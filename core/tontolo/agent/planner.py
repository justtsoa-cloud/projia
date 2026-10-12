"""Découpage des tâches complexes (plan visible, gardé dans le fil de la discussion).

Deux façons de mener un plan, choisies par le planificateur :
- « parallel » : sous-tâches indépendantes confiées en même temps à plusieurs modèles
  (de familles différentes si possible), puis assemblées par le modèle principal ;
- « steps » : livraison pas à pas ; chaque réponse traite une étape, l'utilisateur passe à
  la suivante avec « Continuer ».
Le plan est enregistré avec la discussion et rappelé au modèle à chaque tour : changer de
modèle ou d'appareil ne fait pas perdre le fil.
"""

from __future__ import annotations

import json
import re
from typing import Any

MAX_STEPS = 6
SUBTASK_MAX_TOKENS = 3000
SUBTASK_TIMEOUT = 150.0

_KEYWORDS = re.compile(
    r"\b(projet complet|cours complet|rapport complet|application compl[èe]te|site complet|"
    r"livre|plan d[ée]taill[ée]|[ée]tape par [ée]tape|plusieurs parties|en plusieurs [ée]tapes|"
    r"toutes les questions|tous les exercices|analyse compl[èe]te|[ée]tude compl[èe]te|"
    r"compare[rz]? .{3,40} et .{3,40} et |complete (course|project|report|app)|step by step|"
    r"several parts|all (the )?exercises|in depth|lesona feno|dingana tsikelikely)\b", re.I)
_CONTINUE = re.compile(
    r"^\s*(continue[rz]?|continuons|la suite|suite|[ée]tape suivante|next( step)?|go on|"
    r"keep going|tohizo|manohiza|ok,? continue[rz]?|vas-y,? continue|ok)\s*[.!]*\s*$", re.I)

PLAN_PROMPT = """Tu es le planificateur de Tontolo. Décide si la demande est une tâche \
complexe qui gagne à être découpée. Réponds UNIQUEMENT en JSON :
{"complex": true|false, "mode": "parallel"|"steps", "goal": "objectif en une phrase", \
"steps": [{"title": "titre court", "task": "consigne précise et autonome"}]}
Règles : complex = false pour une question simple ou une réponse qui tient en une fois. \
2 à 6 étapes, précises, sans recouvrement, dans l'ordre logique. mode = "parallel" si les \
étapes sont INDÉPENDANTES (parties qu'on peut rédiger séparément puis assembler : plusieurs \
exercices, comparaisons, sections distinctes) ; mode = "steps" si chaque étape dépend de la \
précédente ou si le résultat est très long (livre, cours, projet construit progressivement). \
Écris dans la langue de la demande."""

SUBTASK_PROMPT = """Tu es un membre d'une équipe de modèles. Réalise UNIQUEMENT la \
sous-tâche demandée, complètement et précisément (Markdown, maths en LaTeX $…$), sans \
introduction ni conclusion générale : un autre modèle assemblera les parties. Réponds dans la \
langue de la demande."""


def looks_complex(text: str) -> bool:
    """Filtre rapide (sans appel de modèle) avant de demander un plan."""
    t = (text or "").strip()
    if len(t) < 60 or wants_continue(t):
        return False
    items = len(re.findall(r"(?m)^\s*(\d+[.)]|[-*•])\s+\S", t))
    return (items >= 3 and len(t) > 150) or bool(_KEYWORDS.search(t))


def wants_continue(text: str) -> bool:
    return bool(_CONTINUE.match(text or ""))


def parse_plan(text: str) -> dict[str, Any] | None:
    m = re.search(r"\{.*\}", text or "", re.S)
    try:
        data = json.loads(m.group(0)) if m else None
    except ValueError:
        return None
    if not isinstance(data, dict) or data.get("complex") is not True:
        return None
    steps = [{"title": str(s.get("title") or "")[:80].strip(),
              "task": str(s.get("task") or s.get("title") or "")[:600].strip()}
             for s in data.get("steps") or [] if isinstance(s, dict)]
    steps = [s for s in steps if s["title"] and s["task"]][:MAX_STEPS]
    if len(steps) < 2:
        return None
    mode = "parallel" if data.get("mode") == "parallel" else "steps"
    return {"mode": mode, "goal": str(data.get("goal") or "")[:300], "steps": steps,
            "current": 0, "results": [], "status": "active"}


def plan_block(plan: dict[str, Any]) -> dict[str, Any]:
    """Rappel du plan au modèle (priorité juste après le fil de la discussion)."""
    steps = plan["steps"]
    lines = [f"{i + 1}. {s['title']} — {s['task']}" for i, s in enumerate(steps)]
    head = f"Plan de la tâche en cours dans CETTE discussion (objectif : {plan['goal']}) :\n"
    if plan["mode"] == "parallel":
        parts = "\n\n".join(
            f"### Partie {i + 1} — {steps[i]['title']} ({r.get('model') or '?'})\n"
            f"{r.get('text') or '(non faite : réalise-la toi-même)'}"
            for i, r in enumerate(plan.get("results") or []))
        tail = ("\nLes parties ont été rédigées en parallèle par plusieurs modèles. Assemble-les "
                "en UNE réponse cohérente et complète : vérifie-les, corrige les erreurs, "
                "complète les manques, harmonise le style, sans annoncer les parties.\n\n"
                + parts)
    else:
        k = int(plan.get("current") or 0)
        delivered = plan.get("delivered") or {}
        recap = "".join(
            f"\n- Étape {int(i) + 1} livrée (texte complet : task_read id={d['ref']}) : "
            f"{d['head'][:300]}…" for i, d in sorted(delivered.items(), key=lambda x: int(x[0]))
            if int(i) < k)
        tail = ((f"\nÉtapes déjà livrées (résumé ; le fil peut avoir été compacté) :{recap}"
                 if recap else "")
                + f"\nLivraison pas à pas : réponds maintenant UNIQUEMENT à l'étape {k + 1}/"
                f"{len(steps)} ({steps[k]['title']}), complètement. Appuie-toi sur les étapes "
                "déjà livrées dans le fil. "
                + (f"Termine par une ligne qui annonce l'étape suivante ({steps[k + 1]['title']})"
                   " et dis que l'utilisateur peut écrire « continuer »." if k + 1 < len(steps)
                   else "C'est la dernière étape : termine par un court bilan de l'ensemble.")
                + " Si la dernière demande de l'utilisateur ne concerne pas ce plan, réponds-y "
                "normalement.")
    return {"role": "system", "content": head + "\n".join(lines) + tail}


def public(plan: dict[str, Any] | None) -> dict[str, Any] | None:
    """Vue envoyée à l'application (sans le texte des sous-tâches)."""
    if not plan:
        return None
    return {"mode": plan["mode"], "goal": plan["goal"], "current": plan.get("current", 0),
            "status": plan.get("status", "active"),
            "steps": [{"title": s["title"]} for s in plan["steps"]],
            "results": [{"model": r.get("model"), "ok": bool(r.get("text") or r.get("ref")),
                         "ref": r.get("ref")} for r in plan.get("results") or []],
            "delivered": {k: {"ref": v.get("ref")} for k, v in
                          (plan.get("delivered") or {}).items()}}
