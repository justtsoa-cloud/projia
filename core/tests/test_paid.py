"""Serveurs payants directs : rapprochement avec les prix OpenRouter, jamais sans prix."""

from __future__ import annotations

from projia.catalog.models import ModelInfo
from projia.catalog.sources import paid


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


def test_static_provider_uses_openrouter_ids(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Perplexity n'a pas de liste de modèles : ceux d'OpenRouter (prix connu) servent."""
    import asyncio

    from projia import secrets

    monkeypatch.setattr(secrets, "get_key", lambda pid: "k" if pid == "perplexity" else None)
    ref = [_or("perplexity/sonar-pro", 1.5e-5), _or("perplexity/sonar", 1e-6),
           _or("perplexity/unpriced", 0)]
    out = asyncio.run(paid.discover(None, 0, ref))  # type: ignore[arg-type]
    assert {m.model_id for m in out} == {"sonar-pro", "sonar"}  # jamais sans prix
    assert all(m.provider == "perplexity" and not m.is_free for m in out)


def test_keyed_free_providers_parse_every_shape() -> None:
    from projia.catalog.sources import keyed

    openai_shape = {"data": [{"id": "llama-3.3-70b"}, {"id": "whisper-large-v3"},
                             {"id": "text-embedding-3"}, {"id": "qwen-2.5-vl-72b"}]}
    got = {m.model_id: m for m in keyed.parse("cerebras", openai_shape)}
    assert set(got) == {"llama-3.3-70b", "qwen-2.5-vl-72b"}  # ni audio ni embeddings
    assert got["qwen-2.5-vl-72b"].supports_vision and got["llama-3.3-70b"].is_free
    together = [{"id": "meta-llama/Llama-3.3-70B-Instruct-Turbo-Free", "type": "chat",
                 "context_length": 131072},
                {"id": "meta-llama/Llama-3.3-70B-Instruct-Turbo", "type": "chat"},
                {"id": "BAAI/bge-large", "type": "embedding"}]
    t = keyed.parse("together", together)
    assert [m.model_id for m in t] == ["meta-llama/Llama-3.3-70B-Instruct-Turbo-Free"]
    assert t[0].context_length == 131072  # seuls les modèles « Free » (le reste est payant)
    github = [{"id": "openai/gpt-4.1", "name": "GPT-4.1", "limits": {"max_input_tokens": 1000}}]
    g = keyed.parse("github", github)
    assert g[0].name == "GPT-4.1" and g[0].context_length == 1000
    assert keyed.parse("groq", "pas du json attendu") == []


def test_builtin_addresses_win_over_the_online_list() -> None:
    """Une liste en ligne compromise ne peut pas détourner la clé d'un fournisseur intégré."""
    from projia import security
    from projia.catalog.sources import keyed

    for pid, p in [*keyed.PROVIDERS.items(), *paid.PROVIDERS.items()]:
        assert pid in security.BUILTIN_PROVIDERS
        assert p["base_url"].startswith("https://")
    assert security.key_allowed("groq", "http://api.groq.com/openai/v1") is False  # HTTPS


async def test_online_list_cannot_redirect_a_builtin_provider(monkeypatch, settings) -> None:  # type: ignore[no-untyped-def]
    from projia.catalog import service as svc
    from projia.catalog.models import ModelInfo

    async def evil(*_a, **_k):  # type: ignore[no-untyped-def]
        return ([ModelInfo(provider="groq", model_id="m", is_free=True)],
                {"groq": {"id": "groq", "name": "Groq", "base_url": "https://evil.example/v1"}})

    async def empty(*_a, **_k):  # type: ignore[no-untyped-def]
        return []

    monkeypatch.setattr(svc.freeapis, "fetch", evil)
    for name in ("fetch_models",):
        monkeypatch.setattr(svc.openrouter, name, empty)
        monkeypatch.setattr(svc.pollinations, name, empty)
    monkeypatch.setattr(svc.local_llm, "discover", empty)
    service = svc.CatalogService(settings)
    await service._build(svc.SourceCache(service.cache_dir, offline=True), record=False,
                         quick=True)
    assert service.catalog.providers["groq"]["base_url"] == "https://api.groq.com/openai/v1"


def test_every_builtin_provider_is_translated() -> None:
    from projia.catalog import service
    from projia.catalog.i18n import PROVIDER_TEXT
    from projia.catalog.sources import keyed, local_llm

    ids = {*service.BUILTIN_PROVIDERS, *local_llm.PROVIDERS, *keyed.PROVIDERS, *paid.PROVIDERS}
    for pid in ids:
        assert PROVIDER_TEXT.get(pid, {}).get("en", {}).get("description"), pid
        assert PROVIDER_TEXT[pid].get("mg", {}).get("description"), pid
