"""E1a — très longue discussion : coût d'un tour selon la taille du fil."""

import asyncio
import os
import sys

from bench.harness import Timer, core, drain, rss_mb

PAUSE = float(os.environ.get("PAUSE", "0.5"))
SIZES = [int(x) for x in (sys.argv[1:] or ["200", "1000", "3000", "8000"])]


async def main() -> None:
    async with core() as (c, fake, home):
        t = Timer()
        cid = await c.db.create_conversation("Longue discussion")
        done = 0
        for target in SIZES:
            # remplissage direct en base (rapide) : alternance question / réponse, avec des
            # médias et quelques gros messages
            for i in range(done, target):
                if i % 2 == 0:
                    body: object = f"Question {i} " + "mot " * 40
                    if i % 40 == 0:
                        body = [{"type": "text", "text": f"Photo {i}"},
                                {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}}]
                    await c.db.add_message(cid, {"role": "user", "content": body})
                else:
                    if i % 17 == 0:
                        jid = f"{i:032x}"
                        await c.db.upsert_job({"id": jid, "kind": "image_gen", "status": "done",
                                               "prompt": f"image {i}", "params": {},
                                               "result_path": None, "conversation_id": cid})
                        content = f"[média:{jid}]"
                    else:
                        content = f"Réponse {i} " + "texte " * 120
                    await c.db.add_message(cid, {"role": "assistant", "content": content})
            done = target
            for rep in range(3):
                with t(f"{target:>5} messages : tour {rep + 1}"):
                    await drain(c.chat.send(cid, f"Nouvelle question {target}-{rep}"))
                await asyncio.sleep(PAUSE)  # l'utilisateur lit : les tâches de fond se terminent
            await asyncio.sleep(0.2)
            print(f"  [{target} messages] RSS {rss_mb():.0f} Mo ; appels (modèle, nb messages) : "
                  f"{fake.calls[-6:]}")
            fake.calls.clear()
        t.report()


asyncio.run(main())
