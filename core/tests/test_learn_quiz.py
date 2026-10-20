"""Mode Apprendre : un quiz ou des fiches sont TOUJOURS livrés en bloc interactif."""

from __future__ import annotations

import json
from typing import Any

from projia.agent.loop import ChatService, has_study_block, parse_study_json, study_kind
from projia.config import Settings
from projia.providers.fake import FakeProvider
from projia.router.engine import Router
from projia.storage.db import Database

QUIZ = {"title": "Vecteurs", "questions": [
    {"q": "Coordonnées de $\\vec{BH}$ ?", "choices": ["(-1,1,1)", "(1,-1,1)"], "answer": 0,
     "explain": "H = (0,1,1), B = (1,0,0)."}]}


def test_detection_and_validation() -> None:
    assert study_kind("crée un quizz de 10 questions basés sur ce fichier.") == "quiz"
    assert study_kind("fais-moi un QCM") == "quiz"
    assert study_kind("prépare des fiches de révision") == "flashcards"
    assert study_kind("explique les vecteurs") is None
    assert parse_study_json(json.dumps(QUIZ), "quiz")["questions"][0]["answer"] == 0
    bad = {"questions": [{"q": "x", "choices": ["a"], "answer": 3}]}
    assert parse_study_json(json.dumps(bad), "quiz") is None
    assert has_study_block(f"Voici :\n```quiz\n{json.dumps(QUIZ)}\n```", "quiz")
    assert not has_study_block("1. Question ? A. … B. …", "quiz")


async def test_text_quiz_is_converted_to_an_interactive_block(
        settings: Settings, db: Database, router: Router, fake: FakeProvider) -> None:
    settings.task_planning = False
    seen: list[str] = []

    def act(model: Any, messages: list[dict[str, Any]]) -> dict[str, Any]:
        system = " ".join(str(m.get("content")) for m in messages if m["role"] == "system")
        seen.append(system)
        if "Convertis ce quiz" in system:
            return {"role": "assistant", "content": json.dumps(QUIZ)}
        return {"role": "assistant", "content": (
            "# Quiz : Vecteurs\n\n1. Coordonnées de BH ?\n- A. (-1,1,1)\n- B. (1,-1,1)")}

    for mid in ("coder-pro", "chatty", "small", "vision-x", "paid-genius"):
        fake.behaviors[mid] = act
    chat = ChatService(settings, db, router)
    cid = await db.create_conversation("cours")
    await db.set_mode(cid, "learn:lycee")
    events = [ev async for ev in chat.send(cid, "crée un quizz de 10 questions basés sur ce "
                                               "fichier.", use_tools=False)]
    done = next(e for e in events if e["type"] == "done")
    content = done["message"]["content"]
    assert has_study_block(content, "quiz") and content.startswith("Quiz : Vecteurs")
    assert any("La demande est un QUIZ" in s for s in seen)  # consigne ferme envoyée
    stored = await db.get_messages(cid)
    assert has_study_block(stored[-1]["content"], "quiz")  # c'est bien ce qui est gardé
