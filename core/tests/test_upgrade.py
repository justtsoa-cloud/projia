"""Saut de versions : une base créée par la 0.2.0 s'ouvre avec le code actuel, sans perte."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from tontolo.storage.db import Database

FIXTURE = Path(__file__).parent / "data" / "db_v0_2_0.sql"


async def test_database_from_v0_2_0(tmp_path: Path) -> None:
    path = tmp_path / "tontolo.db"
    con = sqlite3.connect(path)
    con.executescript(FIXTURE.read_text())
    con.close()
    db = await Database(str(path)).open()
    try:
        convs = await db.list_conversations()
        assert [c["title"] for c in convs] == ["Ancienne discussion"]
        msgs = await db.get_messages(convs[0]["id"])
        assert [m["content"] for m in msgs] == ["Bonjour depuis 0.2.0", "Salut !"]
        # Les fonctions plus récentes marchent sur l'ancienne base.
        await db.pin_conversation(convs[0]["id"], True)
        new = await db.create_conversation("Nouvelle")
        assert await db.conversation_exists(new)
    finally:
        await db.close()
