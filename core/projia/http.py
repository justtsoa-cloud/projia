"""Client HTTP partagé : connexions réutilisées, compression, délais raisonnables."""

from __future__ import annotations

import asyncio

import httpx

from projia import __version__

USER_AGENT = f"Projia/{__version__} (+https://github.com/justtsoa-cloud/projia)"

_client: httpx.AsyncClient | None = None
_loop: asyncio.AbstractEventLoop | None = None


def client() -> httpx.AsyncClient:
    """Client partagé, recréé si la boucle d'événements a changé."""
    global _client, _loop
    try:
        loop: asyncio.AbstractEventLoop | None = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if _client is None or _client.is_closed or loop is not _loop:
        _loop = loop
        _client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, connect=10.0),
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )
    return _client


async def aclose() -> None:
    global _client
    if _client is not None:
        try:
            current = asyncio.get_running_loop()
        except RuntimeError:
            current = None
        if _loop is current and _loop is not None and not _loop.is_closed():
            await _client.aclose()
        _client = None


async def reset() -> None:
    """Abandonne les connexions persistantes (après une coupure réseau, elles sont mortes)."""
    await aclose()


async def is_online(limit: float = 3.0) -> bool:
    """Vrai si Internet répond (n'importe quelle réponse HTTP d'un hébergeur très disponible).

    Client dédié : le client partagé peut garder des connexions mortes après une coupure."""
    urls = ("https://www.gstatic.com/generate_204", "https://cloudflare.com/cdn-cgi/trace")

    async def one(url: str) -> bool:
        try:
            async with httpx.AsyncClient(timeout=limit, headers={"User-Agent": USER_AGENT}) as c:
                await c.get(url)
            return True
        except httpx.HTTPError:
            return False

    tasks = [asyncio.create_task(one(u)) for u in urls]
    try:
        for fut in asyncio.as_completed(tasks):
            if await fut:
                return True
        return False
    finally:
        for t in tasks:
            t.cancel()
