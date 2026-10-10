"""Fournisseur simulé pour les tests (quotas, bascule, retour) et la démonstration."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from typing import Any

from tontolo.catalog.models import ModelInfo
from tontolo.providers.base import ChatResult, ProviderError

Behavior = Callable[[ModelInfo, list[dict[str, Any]]], dict[str, Any] | ProviderError]


@dataclass
class FakeProvider:
    """Répond « [modèle] réponse » ou lève l'erreur programmée pour un modèle."""

    behaviors: dict[str, Behavior] = field(default_factory=dict)
    errors: dict[str, list[ProviderError]] = field(default_factory=dict)
    calls: list[tuple[str, int]] = field(default_factory=list)
    fail_mid_stream: set[str] = field(default_factory=set)

    def fail(self, model_id: str, *errors: ProviderError) -> None:
        self.errors.setdefault(model_id, []).extend(errors)

    def _answer(self, model: ModelInfo, messages: list[dict[str, Any]]) -> dict[str, Any]:
        self.calls.append((model.model_id, len(messages)))
        queue = self.errors.get(model.model_id)
        if queue:
            raise queue.pop(0)
        if model.model_id in self.behaviors:
            out = self.behaviors[model.model_id](model, messages)
            if isinstance(out, ProviderError):
                raise out
            return out
        last = next((m for m in reversed(messages) if m["role"] == "user"), {"content": ""})
        content = last["content"] if isinstance(last["content"], str) else "…"
        return {"role": "assistant", "content": f"[{model.model_id}] {content}"}

    async def chat(
        self, model: ModelInfo, messages: list[dict[str, Any]], *,
        tools: list[dict[str, Any]] | None = None, **params: Any,
    ) -> ChatResult:
        msg = self._answer(model, messages)
        return ChatResult(msg, {"prompt_tokens": 10, "completion_tokens": 5}, "stop")

    async def stream(
        self, model: ModelInfo, messages: list[dict[str, Any]], *,
        tools: list[dict[str, Any]] | None = None, **params: Any,
    ) -> AsyncIterator[dict[str, Any]]:
        if model.model_id in self.fail_mid_stream:
            self.fail_mid_stream.discard(model.model_id)
            yield {"delta": {"content": "réponse parti"}}
            from tontolo.providers.base import ErrorKind

            raise ProviderError("coupure", ErrorKind.RATE_LIMIT, status=429, retry_after=30)
        msg = self._answer(model, messages)
        text = msg.get("content") or ""
        for i in range(0, len(text), 8):
            yield {"delta": {"content": text[i:i + 8]}}
        if msg.get("tool_calls"):
            yield {"delta": {"tool_calls": [dict(tc, index=i)
                                            for i, tc in enumerate(msg["tool_calls"])]}}
        yield {"_result": ChatResult(msg, {"prompt_tokens": 10, "completion_tokens": 5},
                                     "stop")}
