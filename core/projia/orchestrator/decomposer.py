"""Découpage rapide d'une demande en sous-tâches (orchestration optionnelle).

Heuristiques par expressions régulières (aucun appel de modèle) :
- coupure sur les listes (« 1. », « - »), les points-virgules, « puis / ensuite / then /
  avy eo », « + », et les « et explique / and explain » entre deux actions ;
- type de chaque sous-tâche par le classifieur existant du routeur (code, maths, écriture…) ;
- dépendance : une sous-tâche qui renvoie à une précédente (« explique-le », « ce code »,
  « le résultat », « it », « izany ») passe APRÈS, avec les résultats déjà obtenus.

Si la demande est longue mais qu'aucune coupure n'est trouvée, un modèle local (Ollama), s'il
est installé, peut proposer le découpage ; sinon la demande reste d'un seul tenant.
"""

from __future__ import annotations

import json
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from projia.catalog.models import Category
from projia.router.classifier import classify

MAX_SUBTASKS = 6
LOW_CHARS = 220           # une seule tâche courte : orchestration inutile (complexité faible)
LONG_UNSPLIT = 400        # au-delà, sans coupure trouvée : découpage proposé par le modèle local

_LIST_ITEM = re.compile(r"^\s*(?:\d{1,2}[.)]|[-*•])\s+", re.M)
_SPLIT = re.compile(
    r"\s*;\s*|\s+\+\s+|\n+|"
    r"[,.]?\s+(?:puis|ensuite|après quoi|enfin|then|afterwards|finally|avy eo|aorian'izay)\s+|"
    r"[,.]?\s+(?:et|and|ary)\s+(?=(?:explique|expliquer|commente|documente|résume|traduis|"
    r"teste|explain|comment|document|summari[sz]e|translate|test|hazavao|adikao|fintino)\w*)",
    re.I)
_DEPENDS = re.compile(
    r"\b(?:explique-le|explique-la|explique-les|commente-le|teste-le|traduis-le|résume-le|"
    r"ce code|cette fonction|ce script|ce texte|ce programme|le résultat|les résultats|"
    r"ci-dessus|précédent\w*|celui-ci|celle-ci|explain it|test it|translate it|"
    r"summari[sz]e it|this code|that code|the result|the code above|above|previous|"
    r"izany|io kaody io|ilay kaody)\b|^(?:explique|commente|teste|explain|test|hazavao)\w*$",
    re.I)
_VERB = re.compile(r"\w{3,}")
_ACTION = re.compile(
    r"^(?:explique|expliquer|commente|documente|résume|traduis|teste|écris|calcule|donne|"
    r"fais|crée|liste|compare|corrige|explain|comment|document|summari[sz]e|translate|test|"
    r"write|calculate|give|make|create|list|compare|fix|hazavao|adikao|fintino|soraty|"
    r"kajio|omeo|ataovy)", re.I)

SPLIT_PROMPT = (
    "Découpe la demande en 2 à 6 sous-tâches autonomes. Réponds uniquement en JSON : "
    '{"subtasks": ["…", "…"]}. Garde la langue de la demande.')


@dataclass
class Subtask:
    index: int
    text: str
    category: Category
    depends: bool = False  # utilise le résultat des sous-tâches précédentes


@dataclass
class Plan:
    request: str
    subtasks: list[Subtask] = field(default_factory=list)
    complexity: str = "low"   # low | medium | high
    source: str = "regex"     # regex | local_llm | single

    @property
    def parallel(self) -> list[Subtask]:
        return [s for s in self.subtasks if not s.depends]

    @property
    def sequential(self) -> list[Subtask]:
        return [s for s in self.subtasks if s.depends]


def _clean(part: str) -> str:
    return _LIST_ITEM.sub("", part).strip(" \t,.;:-")


class TaskDecomposer:
    """`local_split` : appel optionnel à un modèle local (texte → réponse brute) pour les
    demandes longues sans coupure évidente."""

    def __init__(self, local_split: Callable[[str], Awaitable[str | None]] | None = None) -> None:
        self.local_split = local_split

    def split(self, request: str) -> list[str]:
        text = (request or "").strip()
        parts = [_clean(p) for p in _SPLIT.split(text) if p and _clean(p)]
        # Morceaux trop courts pour être une tâche (« ok », « merci ») : rattachés au précédent.
        merged: list[str] = []
        for p in parts:
            if merged and len(_VERB.findall(p)) < 2 and not _ACTION.match(p):
                merged[-1] = f"{merged[-1]} {p}"
            else:
                merged.append(p)
        return merged[:MAX_SUBTASKS] or [text]

    @staticmethod
    def complexity(parts: list[str], request: str) -> str:
        if len(parts) <= 1:
            return "low" if len(request) <= LOW_CHARS else "medium"
        return "high" if len(parts) > 3 or len(request) > 1500 else "medium"

    def build(self, request: str, parts: list[str], source: str) -> Plan:
        subtasks = []
        for i, p in enumerate(parts):
            cat = classify([{"role": "user", "content": p}]).category
            subtasks.append(Subtask(i, p, cat, depends=i > 0 and bool(_DEPENDS.search(p))))
        return Plan(request, subtasks, self.complexity(parts, request),
                    source if len(parts) > 1 else "single")

    async def decompose(self, request: str) -> Plan:
        parts = self.split(request)
        if len(parts) == 1 and len(request) > LONG_UNSPLIT and self.local_split is not None:
            # NOTE: Choix autonome - modèle local seulement s'il est installé (gratuit, privé) ;
            # toute erreur ou réponse illisible laisse la demande d'un seul tenant.
            try:
                raw = await self.local_split(request)
                data = json.loads(re.search(r"\{.*\}", raw or "", re.S).group(0))  # type: ignore[union-attr]
                proposed = [str(x).strip() for x in data.get("subtasks", []) if str(x).strip()]
                if 2 <= len(proposed) <= MAX_SUBTASKS:
                    return self.build(request, proposed, "local_llm")
            except Exception:
                pass
        return self.build(request, parts, "regex")
