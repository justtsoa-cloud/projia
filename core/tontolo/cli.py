"""Interface en ligne de commande.

    tontolo catalog list --free --category code
    tontolo catalog refresh
    tontolo changes
    tontolo route "Écris une fonction Python"
    tontolo chat "Bonjour !"
    tontolo keys set openrouter
    tontolo serve [--host 0.0.0.0 --port 8765]
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import logging
import sys
from datetime import datetime
from typing import Any

from tontolo import __version__, secrets
from tontolo.app_state import Core
from tontolo.catalog.models import Category


def _fmt_ts(ts: float | None) -> str:
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M") if ts else "—"


async def cmd_catalog_list(args: argparse.Namespace) -> int:
    core = await Core.start(refresh=False)
    try:
        if args.refresh:
            await core.catalog.refresh()
        elif core.catalog._task is not None:
            # Premier lancement : attendre les classements (chargés en arrière-plan).
            await core.catalog._task
        usable = core.catalog.usable_providers()
        models = core.catalog.catalog.filter(category=args.category, free_only=args.free,
                                             usable=usable if args.usable else None)
        cat = args.category or "chat"
        print(f"{'#':>3}  {'score':>5}  {'clé':<58} {'contexte':>9}  notes")
        for i, m in enumerate(models[: args.limit], 1):
            notes = []
            if m.provider not in usable:
                notes.append("clé requise")
            if m.provisional:
                notes.append("provisoire")
            if m.supports_tools:
                notes.append("outils")
            if m.supports_vision:
                notes.append("vision")
            if not m.is_free:
                notes.append("payant")
            print(f"{i:>3}  {m.quality.get(cat, 0):>5.2f}  {m.key[:58]:<58} "
                  f"{m.context_length:>9}  {', '.join(notes)}")
        print(f"\nCatalogue du {_fmt_ts(core.catalog.catalog.updated_at)} — sources : "
              + ", ".join(f"{k} {v}" for k, v in core.catalog.catalog.sources.items()))
        print("Classements : Artificial Analysis (artificialanalysis.ai), LMArena (CC BY 4.0).")
    finally:
        await core.stop()
    return 0


async def cmd_catalog_refresh(args: argparse.Namespace) -> int:
    core = await Core.start(refresh=False)
    try:
        changes = await core.catalog.refresh(force=True)
        print(f"{len(core.catalog.catalog.models)} modèles, {len(changes)} changement(s).")
        for c in changes[:30]:
            print(f"  {c['kind']:<22} {c['model_id']}")
    finally:
        await core.stop()
    return 0


async def cmd_changes(args: argparse.Namespace) -> int:
    core = await Core.start(refresh=False)
    try:
        for c in await core.db.list_changes(args.limit):
            print(f"{_fmt_ts(c['ts'])}  {c['kind']:<22} {c['model_id']}")
    finally:
        await core.stop()
    return 0


async def cmd_route(args: argparse.Namespace) -> int:
    core = await Core.start(refresh=False)
    try:
        d = await core.router.decide([{"role": "user", "content": args.prompt}],
                                     model=args.model)
        print(f"Catégorie : {d.profile.category.value} (confiance "
              f"{d.profile.confidence:.2f})")
        for i, c in enumerate(d.chain[:8], 1):
            r = c.reason(d.profile.category)
            print(f"{i}. {c.model.key}  score={r['score']} qualité={r['quality']} "
                  f"vitesse={r['speed']} fiabilité={r['reliability']}"
                  + ("  [préféré]" if c.preferred else ""))
        if not d.chain:
            print("Aucun modèle éligible (ajoutez une clé : tontolo keys set openrouter).")
    finally:
        await core.stop()
    return 0


async def cmd_chat(args: argparse.Namespace) -> int:
    core = await Core.start(refresh=False)
    code = 0
    try:
        forced = Category(args.category) if args.category else None
        async for ev in core.chat.send(args.conversation, args.prompt, model=args.model,
                                       forced=forced, use_tools=not args.no_tools,
                                       auto_approve=args.yes):
            t = ev["type"]
            if t == "route":
                print(f"[{ev['name']} — {ev['reason']['category']}]", file=sys.stderr)
            elif t == "delta" and ev.get("content"):
                print(ev["content"], end="", flush=True)
            elif t == "model_switched":
                print(f"\n[bascule → {ev['to_name']} : {ev['reason']}]", file=sys.stderr)
            elif t == "stream_reset":
                print("\n[réponse partielle abandonnée]", file=sys.stderr)
            elif t == "web_search":
                print(f"[recherche web : {ev['query']}]", file=sys.stderr)
            elif t == "tool_call":
                print(f"\n[outil {ev['name']}]", file=sys.stderr)
            elif t == "tool_confirmation":
                print(f"\n[confirmation requise : {[c['name'] for c in ev['calls']]} — "
                      "relancez avec --yes]", file=sys.stderr)
            elif t == "conversation":
                print(f"[conversation {ev['id']}]", file=sys.stderr)
            elif t == "error":
                print(f"\nErreur : {ev['message']}", file=sys.stderr)
                code = 1
            elif t == "paid_confirmation":
                print(f"\nConfirmation requise pour un modèle payant ({ev['name']}, "
                      f"≈ {ev['estimated_cost_usd']} $).", file=sys.stderr)
                code = 2
        print()
    finally:
        await core.stop()
    return code


def cmd_keys(args: argparse.Namespace) -> int:
    if args.action == "set":
        value = args.value or getpass.getpass(f"Clé {args.provider} : ")
        secrets.set_key(args.provider, value.strip())
        print(f"Clé enregistrée pour {args.provider}.")
    elif args.action == "delete":
        secrets.delete_key(args.provider)
        print(f"Clé supprimée pour {args.provider}.")
    else:
        print("présente" if secrets.has_key(args.provider) else "absente")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="tontolo", description="Hub d'IA libre et gratuit.")
    p.add_argument("--version", action="version", version=f"tontolo {__version__}")
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)

    cat = sub.add_parser("catalog", help="catalogue des modèles").add_subparsers(
        dest="sub", required=True)
    lst = cat.add_parser("list", help="classement des modèles")
    lst.add_argument("--free", action="store_true", help="modèles gratuits seulement")
    lst.add_argument("--usable", action="store_true", help="seulement ceux utilisables")
    lst.add_argument("--category", choices=[c.value for c in Category])
    lst.add_argument("--limit", type=int, default=20)
    lst.add_argument("--refresh", action="store_true")
    lst.set_defaults(func=cmd_catalog_list)
    cat.add_parser("refresh", help="mise à jour forcée").set_defaults(func=cmd_catalog_refresh)

    ch = sub.add_parser("changes", help="fil des nouveautés")
    ch.add_argument("--limit", type=int, default=50)
    ch.set_defaults(func=cmd_changes)

    rt = sub.add_parser("route", help="montre le modèle choisi et pourquoi")
    rt.add_argument("prompt")
    rt.add_argument("--model")
    rt.set_defaults(func=cmd_route)

    c = sub.add_parser("chat", help="envoie un message")
    c.add_argument("prompt")
    c.add_argument("--model")
    c.add_argument("--conversation")
    c.add_argument("--category", choices=[c.value for c in Category])
    c.add_argument("--no-tools", action="store_true")
    c.add_argument("--yes", action="store_true", help="approuve les outils à effet de bord")
    c.set_defaults(func=cmd_chat)

    k = sub.add_parser("keys", help="clés API personnelles")
    k.add_argument("action", choices=["set", "delete", "check"])
    k.add_argument("provider")
    k.add_argument("value", nargs="?")
    k.set_defaults(func=cmd_keys)

    s = sub.add_parser("serve", help="lance le serveur compatible OpenAI")
    s.add_argument("--host")
    s.add_argument("--port", type=int)
    s.set_defaults(func=None)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                        format="%(levelname)s %(name)s: %(message)s")
    secrets.load_dotenv()
    if args.cmd == "serve":
        from tontolo.server.app import run

        run(args.host, args.port)
        return 0
    func: Any = args.func
    if asyncio.iscoroutinefunction(func):
        return int(asyncio.run(func(args)))
    return int(func(args))


if __name__ == "__main__":
    sys.exit(main())
