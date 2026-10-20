"""Course couverte d'un flux (P1.2) : on lance le meilleur modèle ; s'il n'a rien dit après
`hedge_after` secondes (ou s'il échoue), le suivant démarre EN PARALLÈLE sans arrêter le premier.
Le premier qui produit un élément gagne, l'autre est annulé. Le délai avant le premier mot passe
ainsi de « le délai d'abandon du premier modèle » (30 à 90 s) à quelques secondes, sans rien
perdre en qualité : le meilleur modèle garde sa chance de répondre le premier.

Fonction pure et testable : aucune dépendance au routeur."""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator, Callable
from typing import Any

Factory = Callable[[], AsyncIterator[dict[str, Any]]]
OnFailure = Callable[[int, BaseException], None]


async def _first(gen: AsyncIterator[dict[str, Any]]) -> dict[str, Any]:
    return await gen.__anext__()


async def _close(gen: AsyncIterator[dict[str, Any]] | None) -> None:
    aclose = getattr(gen, "aclose", None)
    if aclose is not None:
        with contextlib.suppress(BaseException):
            await aclose()


async def race_streams(factories: list[Factory], hedge_after: float,
                       on_failure: OnFailure | None = None
                       ) -> AsyncIterator[tuple[int, dict[str, Any]]]:
    """Rend (index de la source, élément). L'index est constant après le premier élément.
    Si toutes les sources lancées échouent avant de parler, l'exception de la première est levée
    (le routeur passe alors à la suite de sa chaîne, comme sans course)."""
    n = len(factories)
    gens: dict[int, AsyncIterator[dict[str, Any]]] = {}
    tasks: dict[asyncio.Task[dict[str, Any]], int] = {}
    errors: dict[int, BaseException] = {}
    started = 0

    def launch() -> None:
        nonlocal started
        i = started
        started += 1
        gens[i] = factories[i]()
        tasks[asyncio.create_task(_first(gens[i]))] = i

    launch()
    winner: int | None = None
    first_item: dict[str, Any] | None = None
    try:
        while winner is None:
            timeout = hedge_after if started < n else None
            done, _ = await asyncio.wait(set(tasks), timeout=timeout,
                                         return_when=asyncio.FIRST_COMPLETED)
            if not done:                       # le premier se tait : on couvre avec le suivant
                launch()
                continue
            for task in done:
                i = tasks.pop(task)
                try:
                    item = task.result()
                except StopAsyncIteration:
                    item = None                # source finie sans rien dire : traitée comme muette
                    errors[i] = RuntimeError("flux vide")
                except Exception as exc:
                    errors[i] = exc
                    item = None
                if item is not None and winner is None:
                    winner, first_item = i, item
            if winner is None and not tasks:
                if started < n:
                    launch()                   # tout a échoué : on lance le suivant
                else:
                    raised = 0 if 0 in errors else next(iter(errors))
                    for i, err in errors.items():
                        if i != raised and on_failure:   # la source 0 est traitée par l'appelant
                            on_failure(i, err)
                    raise errors[raised]
        losers = list(tasks)
        for task in losers:
            task.cancel()
        await asyncio.gather(*losers, return_exceptions=True)  # l'annulation est menée à terme
        tasks.clear()
        for i, gen in gens.items():
            if i != winner:
                await _close(gen)
        assert first_item is not None
        for i, err in errors.items():
            if on_failure:
                on_failure(i, err)  # sources tombées avant que l'autre ne parle
        yield winner, first_item
        async for item in gens[winner]:
            yield winner, item
    finally:
        for task in tasks:
            task.cancel()
        for gen in gens.values():
            await _close(gen)
