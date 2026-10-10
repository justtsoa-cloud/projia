"""Sélection du client pour un fournisseur donné."""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

from tontolo.providers.base import ProviderClient
from tontolo.providers.openai_compat import OpenAICompatClient

ClientFactory = Callable[[dict[str, Any]], ProviderClient]


def default_factory(provider: dict[str, Any]) -> ProviderClient:
    # LiteLLM n'est utilisé que s'il est installé et demandé (Linux uniquement).
    if os.environ.get("TONTOLO_USE_LITELLM") == "1":
        try:
            from tontolo.providers.litellm_client import LiteLLMClient

            return LiteLLMClient(provider)
        except ImportError:
            pass
    return OpenAICompatClient(provider)


class ProviderRegistry:
    def __init__(self, factory: ClientFactory = default_factory) -> None:
        self.factory = factory
        self._clients: dict[str, ProviderClient] = {}

    def get(self, provider: dict[str, Any]) -> ProviderClient:
        pid = provider["id"]
        if pid not in self._clients:
            self._clients[pid] = self.factory(provider)
        return self._clients[pid]

    def reset(self) -> None:
        self._clients.clear()
