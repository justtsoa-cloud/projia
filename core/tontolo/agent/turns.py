"""Tours de conversation détachés de la connexion du client.

Une génération ne doit jamais être perdue parce que l'utilisateur quitte l'écran :
chaque tour tourne dans une tâche de fond qui enregistre ses messages en base ;
ses événements sont conservés dans un tampon que les clients lisent (rejeu depuis
le début, puis suite en direct). Se déconnecter ne l'annule pas ; seul un arrêt
explicite (`stop`) le fait.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger(__name__)

KEEP_FINISHED = 120.0  # secondes de conservation d'un tour terminé (rattachement tardif)


@dataclass
class Turn:
    conversation_id: str
    events: list[dict[str, Any]] = field(default_factory=list)
    done: bool = False
    finished_at: float = 0.0
    task: asyncio.Task[None] | None = None
    changed: asyncio.Event = field(default_factory=asyncio.Event)
    started_at: float = field(default_factory=time.time)

    def progress(self) -> dict[str, Any]:
        """Avancement résumé (suivi en direct sur les autres appareils) : dernière étape et
        fin du texte déjà produit."""
        text, step = "", ""
        for ev in self.events:
            kind = ev.get("type")
            if kind == "delta" and ev.get("content"):
                text += str(ev["content"])
            elif kind in ("stream_reset", "media_switch"):
                text = ""
            elif kind == "step":
                step = str(ev.get("step") or "")
            elif kind == "tool_call":
                step = f"tool:{ev.get('name')}"
            elif kind == "job":
                step = f"job:{ev.get('kind')}:{ev.get('status')}"
            elif kind == "tool_confirmation":
                step = "waiting_confirmation"
        return {"conversation_id": self.conversation_id, "started_at": self.started_at,
                "step": step, "partial": text[-400:], "chars": len(text)}

    def push(self, event: dict[str, Any]) -> None:
        self.events.append(event)
        self.changed.set()

    async def follow(self) -> AsyncIterator[dict[str, Any]]:
        """Rejoue les événements déjà produits puis suit le direct jusqu'à la fin."""
        i = 0
        while True:
            while i < len(self.events):
                yield self.events[i]
                i += 1
            if self.done:
                return
            self.changed.clear()
            if i < len(self.events) or self.done:
                continue
            await self.changed.wait()


def _awaits_user(ev: dict[str, Any]) -> str:
    """Pourquoi le tour attend l'utilisateur : « tool » (confirmation d'outil), « paid »
    (accord pour un modèle payant), « question » (la réponse du modèle se termine par une
    question) ; « » sinon."""
    kind = ev.get("type")
    if kind == "tool_confirmation":
        return "tool"
    if kind == "paid_confirmation":
        return "paid"
    if kind == "done" and not ev.get("job"):
        msg = ev.get("message") or {}
        text = str(msg.get("content") or "").rstrip()
        if text.endswith(("?", "？")) and not msg.get("tool_calls"):
            return "question"
    return ""


class TurnManager:
    def __init__(self) -> None:
        self.turns: dict[str, Turn] = {}
        # Discussions qui attendent une réponse de l'utilisateur (jusqu'à son prochain message).
        self.waiting: dict[str, str] = {}

    def active(self, conversation_id: str) -> Turn | None:
        turn = self.turns.get(conversation_id)
        return turn if turn is not None and not turn.done else None

    def running(self) -> list[Turn]:
        return [t for t in self.turns.values() if not t.done]

    def get(self, conversation_id: str) -> Turn | None:
        self._cleanup()
        return self.turns.get(conversation_id)

    def start(self, conversation_id: str, events: AsyncIterator[dict[str, Any]]) -> Turn:
        """Lance un tour (un seul actif par conversation)."""
        current = self.active(conversation_id)
        if current is not None:
            return current
        self._cleanup()  # sans cela, les tours terminés (et tous leurs événements) s'accumulent
        turn = Turn(conversation_id)
        self.turns[conversation_id] = turn
        self.waiting.pop(conversation_id, None)  # un nouveau tour : l'utilisateur a répondu

        async def run() -> None:
            try:
                async for ev in events:
                    turn.push(ev)
                    reason = _awaits_user(ev)
                    if reason:
                        self.waiting[conversation_id] = reason
            except Exception as exc:  # une erreur inattendue ne doit pas rester muette
                log.exception("Tour en échec")
                turn.push({"type": "error", "message": f"Erreur interne : {type(exc).__name__}"})

        def finalize(task: asyncio.Task[None]) -> None:
            # Appelé dans tous les cas, y compris une annulation avant le premier démarrage.
            if task.cancelled():
                turn.push({"type": "stopped"})
            turn.done = True
            turn.finished_at = time.time()
            turn.changed.set()

        turn.task = asyncio.create_task(run())
        turn.task.add_done_callback(finalize)
        return turn

    async def stop(self, conversation_id: str) -> bool:
        turn = self.active(conversation_id)
        if turn is None or turn.task is None:
            return False
        turn.task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await turn.task
        await asyncio.sleep(0)   # laisse le rappel de fin s'exécuter
        return True

    def _cleanup(self) -> None:
        now = time.time()
        for cid, t in list(self.turns.items()):
            if t.done and now - t.finished_at > KEEP_FINISHED:
                del self.turns[cid]
