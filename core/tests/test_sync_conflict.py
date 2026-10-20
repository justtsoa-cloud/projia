"""Synchronisation par compte : le dernier qui écrit gagne, mais jamais au prix de messages
écrits ailleurs. Deux appareils qui continuent la même discussion hors ligne ne perdent rien."""

from __future__ import annotations

import asyncio

from projia.storage.db import Database


async def _talk(db: Database, cid: str, *texts: str) -> None:
    for i, t in enumerate(texts):
        await db.add_message(cid, {"role": "user" if i % 2 == 0 else "assistant", "content": t})
        await asyncio.sleep(0.002)  # horodatages distincts


async def _sync(src: Database, dst: Database) -> list[bool]:
    return [await dst.replace_conversation(c) for c in await src.export_conversations(0)]


async def _texts(db: Database, cid: str) -> list[str]:
    return [str(m["content"]) for m in await db.get_messages(cid)]


async def _all_titles(db: Database) -> dict[str, list[str]]:
    return {c["id"]: await _texts(db, c["id"]) for c in await db.list_conversations(limit=100)}


async def test_two_devices_continue_the_same_chat_offline_nothing_is_lost() -> None:
    a, b = await Database(":memory:").open(), await Database(":memory:").open()
    cid = await a.create_conversation("Révision")
    await _talk(a, cid, "Q1", "R1")
    await _sync(a, b)                      # b reçoit la discussion
    await _talk(a, cid, "Q2 (téléphone)", "R2 (téléphone)")
    await asyncio.sleep(0.01)
    await _talk(b, cid, "Q2 (bureau)", "R2 (bureau)")   # b écrit plus tard : il gagnera
    await _sync(b, a)
    texts = await _all_titles(a)
    flat = [t for msgs in texts.values() for t in msgs]
    assert "Q2 (bureau)" in flat and "R2 (bureau)" in flat      # la version la plus récente
    assert "Q2 (téléphone)" in flat and "R2 (téléphone)" in flat  # et rien de perdu
    assert len(texts) == 2                                       # copie de l'autre appareil
    titles = [c["title"] for c in await a.list_conversations(limit=100)]
    assert any("Révision" in t and t != "Révision" for t in titles)
    await _sync(a, b)                      # la copie revient sur b : les deux appareils convergent
    assert sorted(map(str, (await _all_titles(b)).values())) == sorted(map(str, texts.values()))
    await a.close()
    await b.close()


async def test_regeneration_elsewhere_does_not_create_copies() -> None:
    """Une réponse régénérée sur l'autre appareil remplace l'ancienne : pas de doublon."""
    a, b = await Database(":memory:").open(), await Database(":memory:").open()
    cid = await a.create_conversation("Chat")
    await _talk(a, cid, "Q", "R ancienne")
    await _sync(a, b)
    await asyncio.sleep(0.01)
    last = (await b.get_messages(cid))[-1]["_meta"]["seq"]
    await b.truncate_after(cid, last - 1)               # b supprime la réponse…
    await _talk(b, cid, "R régénérée")                  # …et en écrit une nouvelle
    # (le message écrit par add_message a le rôle « user » ici : peu importe pour ce test)
    await _sync(b, a)
    assert len(await a.list_conversations(limit=100)) == 1
    assert "R ancienne" not in await _texts(a, cid)
    await a.close()
    await b.close()


async def test_deleted_elsewhere_stays_deleted_even_with_local_edits() -> None:
    a, b = await Database(":memory:").open(), await Database(":memory:").open()
    cid = await a.create_conversation("À supprimer")
    await _talk(a, cid, "Q", "R")
    await _sync(a, b)
    await _talk(a, cid, "Question de plus")             # a continue…
    await asyncio.sleep(0.01)
    await b.delete_conversation(cid)                    # …mais b supprime ensuite
    await _sync(b, a)
    assert not [c for c in await a.list_conversations(limit=100)]  # supprimée, aucune copie
    await a.close()
    await b.close()


async def test_older_remote_never_overwrites_newer_local() -> None:
    a, b = await Database(":memory:").open(), await Database(":memory:").open()
    cid = await a.create_conversation("Chat")
    await _talk(a, cid, "Q", "R")
    await _sync(a, b)
    await asyncio.sleep(0.01)
    await _talk(b, cid, "Plus récent")
    assert not any(await _sync(a, b))                   # a est plus ancien : rien n'est appliqué
    assert "Plus récent" in await _texts(b, cid)
    await a.close()
    await b.close()


async def test_large_volume_syncs_completely_and_quickly() -> None:
    """E5 : 150 discussions de 40 messages (6 000 messages) passent d'un appareil à l'autre."""
    import time

    a, b = await Database(":memory:").open(), await Database(":memory:").open()
    for i in range(150):
        cid = await a.create_conversation(f"Discussion {i}")
        for j in range(40):
            await a.add_message(cid, {"role": "user" if j % 2 == 0 else "assistant",
                                      "content": f"message {i}-{j} " + "x" * 200})
    started = time.monotonic()
    batch = await a.export_conversations(0)
    applied = [await b.replace_conversation(c) for c in batch]
    elapsed = time.monotonic() - started
    assert len(batch) == 150 and all(applied)
    assert sum([await b.count_messages(c["id"]) for c in batch]) == 6000
    assert elapsed < 20, f"synchro de 6 000 messages : {elapsed:.1f} s"
    assert not any(await _sync(a, b))        # deuxième passage : rien à refaire, aucun doublon
    assert len(await b.list_conversations(limit=500)) == 150
    await a.close()
    await b.close()
