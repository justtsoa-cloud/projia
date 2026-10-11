"""Serveurs payants directs : rapprochement avec les prix OpenRouter, jamais sans prix."""

from __future__ import annotations

from tontolo.catalog.models import ModelInfo
from tontolo.catalog.sources import paid


def _or(mid: str, price: float, free: bool = False) -> ModelInfo:
    return ModelInfo(provider="openrouter", model_id=mid, name=f"Anthropic: {mid.split('/')[1]}",
                     is_free=free, price_in=price / 2, price_out=price,
                     metrics={"aa.intelligence": 60.0})


def test_match_uses_openrouter_price_and_alias() -> None:
    ref = [_or("anthropic/claude-sonnet-4.5", 1.5e-5), _or("anthropic/claude-haiku-4.5", 5e-6),
           _or("openai/gpt-5-mini", 2e-6), _or("anthropic/claude-x:free", 0, free=True)]
    listed = ["claude-sonnet-4-5-20250929", "claude-sonnet-4-5", "claude-haiku-4-5-20251001",
              "claude-unknown-9"]
    out = {m.model_id: m for m in paid.match("anthropic", listed, ref)}
    assert set(out) == {"claude-sonnet-4-5", "claude-haiku-4-5-20251001"}
    m = out["claude-sonnet-4-5"]
    assert m.provider == "anthropic" and not m.is_free and m.price_out == 1.5e-5
    assert m.metrics == {"aa.intelligence": 60.0} and m.name == "claude-sonnet-4.5"


def test_norm() -> None:
    assert paid.norm("gpt-5-mini-2025-08-07") == paid.norm("openai/gpt-5-mini")
    assert paid.norm("grok-4-latest") == paid.norm("x-ai/grok-4")
