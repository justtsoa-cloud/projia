"""Fusion des réponses des sous-tâches (orchestration optionnelle).

Stratégie selon la complexité :
- low : concaténation Markdown (titres par sous-tâche), instantanée ;
- medium : petit modèle gratuit rapide (celui des résumés), qui relie et uniformise ;
- high : meilleur modèle gratuit disponible pour l'écriture.
Toujours un repli sur la concaténation : une fusion ratée ne perd jamais les réponses.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

SYNTH_TIMEOUT = 90.0
SYNTH_PROMPT = (
    "Tu reçois une demande et les réponses de plusieurs assistants, une par partie. Rédige UNE "
    "réponse finale cohérente, dans la langue de la demande : garde tout le contenu utile (le "
    "code tel quel, les chiffres exacts), supprime les répétitions, relie les parties. "
    "N'invente rien qui ne figure pas dans les réponses.")


@dataclass
class PartResult:
    title: str
    text: str
    model: str = ""
    ok: bool = True


Ask = Callable[[list[dict[str, Any]]], Awaitable[tuple[str, str]]]  # → (texte, clé du modèle)


class ResponseSynthesizer:
    def __init__(self, quick: Ask | None = None, best: Ask | None = None) -> None:
        self.quick = quick   # petit modèle gratuit (medium)
        self.best = best     # meilleur modèle gratuit (high)

    @staticmethod
    def concatenate(parts: list[PartResult]) -> str:
        if len(parts) == 1:
            return parts[0].text
        return "\n\n".join(f"### {p.title}\n\n{p.text}" for p in parts)

    async def merge(self, request: str, parts: list[PartResult], complexity: str
                    ) -> tuple[str, str, str]:
        """(réponse, stratégie utilisée, modèle de fusion)."""
        plain = self.concatenate(parts)
        if complexity == "high":
            askers = [self.best]
        elif complexity == "medium":
            # Petit modèle d'abord ; s'il raccourcit trop (contenu perdu), modèle d'écriture.
            askers = [self.quick, self.best]
        else:
            askers = []
        if len(parts) < 2 or not all(p.ok for p in parts):
            return plain, "concat", ""
        messages = [
            {"role": "system", "content": SYNTH_PROMPT},
            {"role": "user", "content": f"Demande :\n{request[:6000]}\n\nRéponses :\n"
                                        f"{plain[:40_000]}"},
        ]
        for ask in (a for a in askers if a is not None):
            try:
                async with asyncio.timeout(SYNTH_TIMEOUT):
                    text, model = await ask(messages)
            except Exception:
                continue
            # Une fusion bien plus courte que les parties a sans doute perdu du contenu.
            if text.strip() and len(text) >= 0.4 * len(plain):
                return text, complexity, model
        return plain, "concat", ""
