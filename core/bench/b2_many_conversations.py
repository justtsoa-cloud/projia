"""E1b — beaucoup de discussions : liste, recherche, dossiers, export de synchro."""

import asyncio
import sys

from bench.harness import Timer, core, rss_mb

N = int(sys.argv[1]) if len(sys.argv) > 1 else 500
M = int(sys.argv[2]) if len(sys.argv) > 2 else 30


async def main() -> None:
    async with core() as (c, fake, home):
        t = Timer()
        with t(f"création de {N} discussions x {M} messages"):
            for i in range(N):
                cid = await c.db.create_conversation(f"Discussion {i} sujet {i % 17}")
                if i % 10 == 0:
                    await c.db.set_folder(cid, f"Dossier {i % 5}")
                for j in range(M):
                    role = "user" if j % 2 == 0 else "assistant"
                    await c.db.add_message(cid, {"role": role, "content":
                                                 f"Message {j} de {i} : probabilités et lois "
                                                 f"normales, sujet {i % 17} " + "texte " * 30})
        with t("liste 50 premières"):
            await c.db.list_conversations(50, 0, None, None)
        with t("liste page 400 (offset 20000)"):
            await c.db.list_conversations(50, 400, None, None)
        with t("recherche plein texte « lois normales »"):
            r = await c.db.list_conversations(50, 0, "lois normales", None)
        print(f"  (résultats : {len(r)})")
        with t("dossiers"):
            await c.db.list_folders()
        with t("export synchro depuis 0 (toutes les discussions)"):
            exp = await c.db.export_conversations(0)
        print(f"  (conversations exportées : {len(exp)})")
        with t("export synchro depuis 0, JSON"):
            import json
            blob = json.dumps(exp)
        print(f"  (taille JSON : {len(blob) // 1024 // 1024} Mo ; RSS {rss_mb():.0f} Mo)")
        with t("recherche globale (messages)"):
            await c.db.search_messages("normales", 30) if hasattr(c.db, "search_messages") else None
        t.report()


asyncio.run(main())
