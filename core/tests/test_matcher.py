"""Appariement de modèles entre sources, sur des noms réels relevés le 2026-10-10."""

import pytest

from projia.catalog.matcher import Matcher, canonical, family


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("google/gemma-4-31b-it:free", "gemma-4-31b"),
        ("Google: Gemma 4 31B (free)", "gemma-4-31b"),
        ("claude-opus-5.5-high", "claude-opus-5-5"),
        ("anthropic/claude-opus-5.5", "claude-opus-5-5"),
        ("mistral-large-2512", "mistral-large"),
        ("deepseek-v4.1-flash-max", "deepseek-4-1-flash-max"),
        ("DeepSeek V4.1 Flash Max", "deepseek-4-1-flash-max"),
        ("@cf/meta/llama-3.3-70b-instruct-fp8-fast", "llama-3-3-70b"),
        ("muse-spark-1.2 (xHigh)", "muse-spark-1-2"),
    ],
)
def test_canonical(raw: str, expected: str) -> None:
    assert canonical(raw) == expected


@pytest.fixture
def matcher() -> Matcher:
    m = Matcher()
    m.add("gemma4-31b", ["gemma-4-31b-it", "Gemma 4 31B"])
    m.add("gemma4-26b", ["gemma-4-26b-a4b-it"])
    m.add("nemotron-super", ["NVIDIA Nemotron 3 Super"])
    m.add("gpt-5.4", ["gpt-5.4"])
    m.add("gpt-5.4-mini", ["gpt-5.4-mini"])
    m.add("opus-4.5", ["claude-opus-4-5-20251101-high-32k"])
    m.add("qwen3.8-27b", ["qwen3.8-27b"])
    return m


@pytest.mark.parametrize(
    ("names", "expected"),
    [
        (("google/gemma-4-31b-it:free", "Google: Gemma 4 31B (free)"), "gemma4-31b"),
        (("google/gemma-4-26b-a4b-it:free",), "gemma4-26b"),
        (("nvidia/nemotron-3-super-120b-a12b:free",), "nemotron-super"),
        (("openai/gpt-5.4",), "gpt-5.4"),
        (("openai/gpt-5.4-mini",), "gpt-5.4-mini"),
        (("anthropic/claude-opus-4.5",), "opus-4.5"),
        (("qwen/qwen3.8-27b",), "qwen3.8-27b"),
    ],
)
def test_match_real_cases(matcher: Matcher, names: tuple[str, ...], expected: str) -> None:
    res = matcher.match(*names)
    assert res is not None and res.key == expected


@pytest.mark.parametrize(
    "names",
    [
        ("google/gemma-4-12b-it",),     # taille différente
        ("openai/gpt-5.4-nano",),       # gamme différente
        ("openai/gpt-5.5",),            # version différente
        ("anthropic/claude-opus-4.6",),
        ("qwen/qwen3.8-max",),
    ],
)
def test_no_false_positive(matcher: Matcher, names: tuple[str, ...]) -> None:
    assert matcher.match(*names) is None


def test_family() -> None:
    assert family("google/gemma-4-31b-it:free") == "gemma-4"
    assert family("nvidia/nemotron-3-super-120b-a12b") == "nemotron-3"


def test_keyless_providers_from_live_data() -> None:
    """Données réelles du 2026-10-10 : Kilo Code, LLM7 et OVHcloud sont accessibles sans clé."""
    import json
    from pathlib import Path

    from projia.catalog.sources.freeapis import parse

    data = json.loads((Path(__file__).parent / "fixtures" / "freeapis.json").read_text())
    models, providers = parse(data)
    keyless = {pid for pid, p in providers.items() if p["keyless"]}
    assert {"kilo", "llm7", "ovh"} <= keyless
    assert "gemini" not in keyless and "groq" not in keyless
    assert all(not m.needs_key for m in models if m.provider in keyless)
