"""Frontières des références médias : provenance, erreurs et changements de sujet."""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import HTTPException

from tontolo.catalog.models import Category
from tontolo.router.classifier import classify
from tontolo.server.app import _first_image, _image_source, _media_history, _media_prompt
from tontolo.storage.db import Database


@pytest.mark.parametrize("text", ["anime-la", "animate it", "ampihetsiho"])
def test_attached_image_animation_is_video(text: str) -> None:
    content = [{"type": "text", "text": text},
               {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}}]
    assert classify([{"role": "user", "content": content}]).category == Category.VIDEO_GEN


async def test_image_reference_cannot_cross_discussions_or_skip_failed_image(
        db: Database, tmp_path: Any) -> None:
    own = await db.create_conversation("ici")
    other = await db.create_conversation("ailleurs")
    image = tmp_path / "image.png"
    image.write_bytes(b"PNG ORIGINAL")
    core = SimpleNamespace(db=db, media=SimpleNamespace(dir=tmp_path))
    await db.upsert_job({"id": "aa", "kind": "image_gen", "status": "done",
                         "prompt": "chat", "conversation_id": other,
                         "result_path": str(image)})
    await db.add_message(own, {"role": "assistant", "content": "[média:aa]"})
    assert await _image_source(core, own) == (None, None)
    history = await _media_history(core, own)
    assert "_media_kind" not in history[0]
    await db.upsert_job({"id": "bb", "kind": "image_gen", "status": "done",
                         "prompt": "baobab", "conversation_id": own,
                         "result_path": str(image)})
    await db.add_message(own, {"role": "assistant", "content": "[média:bb]"})
    assert await _image_source(core, own) == (b"PNG ORIGINAL", "bb")
    await db.upsert_job({"id": "cc", "kind": "image_gen", "status": "failed",
                         "prompt": "nouvelle image", "conversation_id": own})
    await db.add_message(own, {"role": "assistant", "content": "[média:cc]"})
    assert await _image_source(core, own) == (None, None)


async def test_short_new_prompt_does_not_inherit_unrelated_request(db: Database) -> None:
    cid = await db.create_conversation("Fil")
    core = SimpleNamespace(db=db)
    await db.add_message(cid, {"role": "user", "content": "Résous un exercice de mathématiques"})
    await db.add_message(cid, {"role": "user", "content": "Dessine un baobab"})
    assert await _media_prompt(core, cid, "Dessine un baobab") == "Dessine un baobab"


def test_invalid_image_is_reported() -> None:
    with pytest.raises(HTTPException) as error:
        _first_image([{"type": "image_url", "image_url": {"url": "data:image/png;base64,???"}}])
    assert error.value.status_code == 400
