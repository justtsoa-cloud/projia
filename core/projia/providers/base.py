"""Interface commune des fournisseurs (`ProviderClient`) et erreurs normalisées."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol

from projia.catalog.models import ModelInfo


class ErrorKind(StrEnum):
    RATE_LIMIT = "rate_limit"      # 429 temporaire
    QUOTA = "quota"                # quota journalier / crédits épuisés
    AUTH = "auth"                  # clé absente ou invalide
    CONTEXT = "context"            # historique trop long pour le modèle
    UNAVAILABLE = "unavailable"    # modèle retiré / introuvable
    SERVER = "server"              # 5xx fournisseur
    NETWORK = "network"            # délai, coupure
    BAD_REQUEST = "bad_request"    # requête refusée (paramètre non supporté…)


class Scope(StrEnum):
    MODEL = "model"
    PROVIDER = "provider"
    FREE_POOL = "free_pool"        # quota partagé par tous les modèles gratuits d'un fournisseur


@dataclass
class ProviderError(Exception):
    message: str
    kind: ErrorKind
    status: int | None = None
    retry_after: float | None = None
    scope: Scope = Scope.MODEL
    headers: dict[str, str] = field(default_factory=dict)

    def __str__(self) -> str:
        return f"{self.kind}: {self.message}"


@dataclass
class ChatResult:
    """Réponse complète au format OpenAI canonique."""

    message: dict[str, Any]
    usage: dict[str, int] = field(default_factory=dict)
    finish_reason: str | None = None
    headers: dict[str, str] = field(default_factory=dict)


class ProviderClient(Protocol):
    async def chat(
        self, model: ModelInfo, messages: list[dict[str, Any]], *,
        tools: list[dict[str, Any]] | None = None, **params: Any,
    ) -> ChatResult: ...

    def stream(
        self, model: ModelInfo, messages: list[dict[str, Any]], *,
        tools: list[dict[str, Any]] | None = None, **params: Any,
    ) -> AsyncIterator[dict[str, Any]]:
        """Produit des morceaux OpenAI (`choices[0].delta`) puis un dernier
        élément `{"_result": ChatResult}` avec le message assemblé."""
        ...


def accumulate(message: dict[str, Any], delta: dict[str, Any]) -> None:
    """Assemble un delta de streaming (texte et appels d'outils) dans `message`."""
    if content := delta.get("content"):
        message["content"] = (message.get("content") or "") + content
    if reasoning := delta.get("reasoning") or delta.get("reasoning_content"):
        message["reasoning"] = (message.get("reasoning") or "") + reasoning
    for tc in delta.get("tool_calls") or []:
        calls = message.setdefault("tool_calls", [])
        idx = tc.get("index", len(calls))
        while len(calls) <= idx:
            calls.append({"id": "", "type": "function", "function": {"name": "", "arguments": ""}})
        cur = calls[idx]
        if tc.get("id"):
            cur["id"] = tc["id"]
        fn = tc.get("function") or {}
        if fn.get("name"):
            cur["function"]["name"] += fn["name"]
        if fn.get("arguments"):
            cur["function"]["arguments"] += fn["arguments"]
