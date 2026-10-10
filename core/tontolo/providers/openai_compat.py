"""Adaptateur minimal compatible OpenAI, en `httpx` pur (Linux et Android).

LiteLLM est trop lourd pour l'APK (dépendances natives tiktoken/tokenizers,
aiohttp…) ; ce client couvre tous les fournisseurs gratuits qui exposent
`/chat/completions` au format OpenAI, ce qui est le cas de tous ceux du catalogue.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import AsyncIterator
from typing import Any

import httpx

from tontolo import http, secrets
from tontolo.catalog.models import ModelInfo
from tontolo.providers.base import ChatResult, ErrorKind, ProviderError, Scope, accumulate

_DAILY = re.compile(r"per[- ]day|daily|free-models-per-day|quota|exceeded your current", re.I)
_CONTEXT = re.compile(r"context|too long|maximum.*tokens|token limit", re.I)


def classify_error(status: int | None, body: str, headers: dict[str, str]) -> ProviderError:
    retry_after: float | None = None
    if ra := headers.get("retry-after"):
        try:
            retry_after = float(ra)
        except ValueError:
            retry_after = None
    msg = body[:500]
    try:
        data = json.loads(body)
        err = data.get("error", data)
        if isinstance(err, dict):
            msg = str(err.get("message") or msg)
            meta = err.get("metadata") or {}
            if isinstance(meta, dict) and meta.get("raw"):
                msg += f" ({str(meta['raw'])[:200]})"
    except (ValueError, AttributeError):
        pass
    scope = Scope.MODEL
    if status == 429 or (status is None and "rate" in msg.lower()):
        kind = ErrorKind.QUOTA if _DAILY.search(msg) else ErrorKind.RATE_LIMIT
        if "free-models-per" in msg:
            scope = Scope.FREE_POOL
    elif status == 402:
        kind, scope = ErrorKind.QUOTA, Scope.PROVIDER
    elif status in (401, 403):
        kind, scope = ErrorKind.AUTH, Scope.PROVIDER
    elif status == 404:
        kind = ErrorKind.UNAVAILABLE
    elif status in (400, 413, 422):
        kind = ErrorKind.CONTEXT if _CONTEXT.search(msg) else ErrorKind.BAD_REQUEST
    elif status is not None and status >= 500:
        kind = ErrorKind.SERVER
    else:
        kind = ErrorKind.SERVER
    return ProviderError(msg, kind, status=status, retry_after=retry_after, scope=scope,
                         headers=headers)


class OpenAICompatClient:
    def __init__(self, provider: dict[str, Any]) -> None:
        self.provider = provider
        self.pid: str = provider["id"]

    def _base_url(self) -> str:
        base: str = self.provider["base_url"]
        if "{account_id}" in base:
            account = os.environ.get("CLOUDFLARE_ACCOUNT_ID") or secrets.get_key(
                "cloudflare-account")
            if not account:
                raise ProviderError("Identifiant de compte Cloudflare manquant", ErrorKind.AUTH,
                                    scope=Scope.PROVIDER)
            base = base.replace("{account_id}", account)
        return base.rstrip("/")

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        key = secrets.get_key(self.pid)
        if key:
            headers["Authorization"] = f"Bearer {key}"
        elif not self.provider.get("keyless"):
            raise ProviderError(f"Aucune clé pour {self.pid}", ErrorKind.AUTH,
                                scope=Scope.PROVIDER)
        if self.pid == "openrouter":
            headers["HTTP-Referer"] = "https://github.com/raantss18/tontolo"
            headers["X-Title"] = "Tontolo"
        return headers

    def _payload(
        self, model: ModelInfo, messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None, stream: bool, params: dict[str, Any],
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"model": model.model_id, "messages": messages,
                                   "stream": stream}
        if tools:
            payload["tools"] = tools
        for k in ("temperature", "max_tokens", "top_p", "stop", "response_format",
                  "tool_choice", "seed"):
            if params.get(k) is not None:
                payload[k] = params[k]
        if stream and self.pid == "openrouter":
            payload["usage"] = {"include": True}
        return payload

    async def chat(
        self, model: ModelInfo, messages: list[dict[str, Any]], *,
        tools: list[dict[str, Any]] | None = None, **params: Any,
    ) -> ChatResult:
        url = f"{self._base_url()}/chat/completions"
        payload = self._payload(model, messages, tools, False, params)
        try:
            resp = await http.client().post(url, json=payload, headers=self._headers(),
                                            timeout=params.get("timeout", 120.0))
        except httpx.HTTPError as exc:
            raise ProviderError(type(exc).__name__, ErrorKind.NETWORK) from exc
        headers = {k.lower(): v for k, v in resp.headers.items()}
        if resp.status_code >= 400:
            raise classify_error(resp.status_code, resp.text, headers)
        try:
            data = resp.json()
        except ValueError as exc:
            raise ProviderError("Réponse illisible", ErrorKind.SERVER) from exc
        if "error" in data and not data.get("choices"):
            err = data["error"]
            code = err.get("code") if isinstance(err, dict) else None
            raise classify_error(code if isinstance(code, int) else None, json.dumps(data),
                                 headers)
        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message") or {"role": "assistant", "content": ""}
        message.setdefault("role", "assistant")
        clean = {k: v for k, v in message.items()
                 if k in ("role", "content", "tool_calls", "reasoning") and v}
        clean.setdefault("content", message.get("content") or "")
        return ChatResult(clean, data.get("usage") or {}, choice.get("finish_reason"), headers)

    async def stream(
        self, model: ModelInfo, messages: list[dict[str, Any]], *,
        tools: list[dict[str, Any]] | None = None, **params: Any,
    ) -> AsyncIterator[dict[str, Any]]:
        url = f"{self._base_url()}/chat/completions"
        payload = self._payload(model, messages, tools, True, params)
        message: dict[str, Any] = {"role": "assistant", "content": ""}
        usage: dict[str, int] = {}
        finish: str | None = None
        try:
            async with http.client().stream(
                "POST", url, json=payload, headers=self._headers(),
                timeout=params.get("timeout", 120.0),
            ) as resp:
                headers = {k.lower(): v for k, v in resp.headers.items()}
                if resp.status_code >= 400:
                    body = (await resp.aread()).decode("utf-8", "replace")
                    raise classify_error(resp.status_code, body, headers)
                async for line in resp.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data_str = line[5:].strip()
                    if data_str == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_str)
                    except ValueError:
                        continue
                    if "error" in chunk and not chunk.get("choices"):
                        err = chunk["error"]
                        code = err.get("code") if isinstance(err, dict) else None
                        raise classify_error(code if isinstance(code, int) else None,
                                             json.dumps(chunk), headers)
                    if chunk.get("usage"):
                        usage = chunk["usage"]
                    for choice in chunk.get("choices") or []:
                        delta = choice.get("delta") or {}
                        accumulate(message, delta)
                        finish = choice.get("finish_reason") or finish
                        if delta:
                            yield {"delta": delta}
        except httpx.HTTPError as exc:
            raise ProviderError(type(exc).__name__, ErrorKind.NETWORK) from exc
        clean = {k: v for k, v in message.items() if v or k == "content"}
        yield {"_result": ChatResult(clean, usage, finish, headers)}
