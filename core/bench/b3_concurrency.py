"""E1c — charge concurrente : nombreux tours en parallèle (avec pannes de fournisseurs
aléatoires), puis cohérence des conversations (ordre, alternance, aucun message perdu)."""

import asyncio
import random
import sys

from bench.harness import Timer, core, drain, rss_mb
from tontolo.providers.base import ErrorKind, ProviderError

N = int(sys.argv[1]) if len(sys.argv) > 1 else 40
TURNS = int(sys.argv[2]) if len(sys.argv) > 2 else 6
random.seed(7)


async def main() -> None:
    async with core() as (c, fake, home):
        fake.chunk_delay = 0.002
        # pannes aléatoires : le routeur doit basculer sur un autre modèle
        for mid in ("coder-pro", "chatty", "vision-x"):
            for _ in range(15):
                fake.fail(mid, ProviderError("quota", ErrorKind.RATE_LIMIT, status=429,
                                             retry_after=1))
        t = Timer()
        cids = [await c.db.create_conversation(f"Charge {i}") for i in range(N)]
        errors: list[str] = []

        async def user(i: int) -> None:
            cid = cids[i]
            for k in range(TURNS):
                evs = await drain(c.chat.send(cid, f"Question {k} de l'utilisateur {i}"))
                kinds = [e["type"] for e in evs]
                if "done" not in kinds:
                    errors.append(f"{i}/{k}: pas de réponse ({[e for e in evs if e['type'] == 'error']})")
                await asyncio.sleep(random.random() * 0.01)

        with t(f"{N} utilisateurs x {TURNS} tours en parallèle"):
            await asyncio.gather(*[user(i) for i in range(N)])
        await asyncio.sleep(0.5)
        bad = 0
        for i, cid in enumerate(cids):
            msgs = await c.db.get_messages(cid)
            roles = [m["role"] for m in msgs]
            seqs = [m["_meta"]["seq"] for m in msgs]
            if roles != ["user", "assistant"] * TURNS or seqs != list(range(1, len(msgs) + 1)):
                bad += 1
                if bad <= 3:
                    print(f"  incohérent {i}: {roles[:8]} seq={seqs[:8]}")
            texts = [m["content"] for m in msgs if m["role"] == "user"]
            if texts != [f"Question {k} de l'utilisateur {i}" for k in range(TURNS)]:
                bad += 1
                print(f"  messages mêlés entre discussions : {i}")
        print(f"  erreurs de tour : {len(errors)} ; discussions incohérentes : {bad} ; RSS {rss_mb():.0f} Mo")
        for e in errors[:5]:
            print("   ", e)
        t.report()


asyncio.run(main())
