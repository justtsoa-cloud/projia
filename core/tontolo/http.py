"""Client HTTP partagé : connexions réutilisées, compression, délais raisonnables."""

from __future__ import annotations

import httpx

from tontolo import __version__

USER_AGENT = f"Tontolo/{__version__} (+https://github.com/raantss18/tontolo)"

_client: httpx.AsyncClient | None = None


def client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
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
        await _client.aclose()
        _client = None
