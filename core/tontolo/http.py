"""Client HTTP partagé : connexions réutilisées, compression, délais raisonnables."""

from __future__ import annotations

import asyncio

import httpx

from tontolo import __version__

USER_AGENT = f"Tontolo/{__version__} (+https://github.com/raantss18/tontolo)"

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
