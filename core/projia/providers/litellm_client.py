"""Client LiteLLM optionnel (Linux) : `pip install projia[litellm]` et
`PROJIA_USE_LITELLM=1`. Même contrat que l'adaptateur httpx ; le routage,
les replis et les temps de refroidissement restent gérés par Projia, car ils
dépendent du catalogue gratuit en ligne et non d'une liste fixe."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import litellm  # ImportError si l'extra n'est pas installé

from projia import secrets
from projia.catalog.models import ModelInfo
from projia.providers.base import ChatResult, ErrorKind, ProviderError, accumulate
from projia.providers.openai_compat import classify_error


class LiteLLMClient:
    def __init__(self, provider: dict[str, Any]) -> None:
        self.provider = provider
        self.pid: str = provider["id"]

    def _kwargs(self, model: ModelInfo, params: dict[str, Any]) -> dict[str, Any]:
        kw: dict[str, Any] = {
            "model": f"openai/{model.model_id}",
            "api_base": self.provider["base_url"],
            "api_key": secrets.get_key(self.pid) or "none",
        }
        for k in ("temperature", "max_tokens", "top_p", "stop", "tool_choice"):
            if params.get(k) is not None:
                kw[k] = params[k]
        return kw

    @staticmethod
    def _error(exc: Exception) -> ProviderError:
        status = getattr(exc, "status_code", None)
        return classify_error(status, str(exc), {}) if status else ProviderError(
            str(exc), ErrorKind.NETWORK)

    async def chat(
        self, model: ModelInfo, messages: list[dict[str, Any]], *,
        tools: list[dict[str, Any]] | None = None, **params: Any,
    ) -> ChatResult:
        try:
            resp = await litellm.acompletion(messages=messages, tools=tools or None,
                                             **self._kwargs(model, params))
        except Exception as exc:
            raise self._error(exc) from exc
        msg = resp.choices[0].message.model_dump(exclude_none=True)
        usage = resp.usage.model_dump() if getattr(resp, "usage", None) else {}
        return ChatResult(msg, usage, resp.choices[0].finish_reason)

    async def stream(
        self, model: ModelInfo, messages: list[dict[str, Any]], *,
        tools: list[dict[str, Any]] | None = None, **params: Any,
    ) -> AsyncIterator[dict[str, Any]]:
        message: dict[str, Any] = {"role": "assistant", "content": ""}
        try:
            resp = await litellm.acompletion(messages=messages, tools=tools or None,
                                             stream=True, **self._kwargs(model, params))
            async for chunk in resp:
                delta = chunk.choices[0].delta.model_dump(exclude_none=True)
                accumulate(message, delta)
                yield {"delta": delta}
        except Exception as exc:
            raise self._error(exc) from exc
        yield {"_result": ChatResult(message)}
