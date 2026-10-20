"""Noms et descriptions des fournisseurs intégrés en anglais et en malgache (le français est
dans leur définition). L'application choisit selon sa langue ; la liste en ligne
(`freeapis`) fournit ses propres descriptions, en anglais."""

from __future__ import annotations

from typing import Any

PROVIDER_TEXT: dict[str, dict[str, dict[str, str]]] = {
    "openrouter": {
        "en": {"description": "Aggregator: many “:free” models with a free key."},
        "mg": {"description": "Mpanangona: modely « :free » maro miaraka amin'ny fanalahidy "
                              "maimaim-poana."},
    },
    "local": {
        "en": {"name": "Device", "description": "System speech synthesis, no quota."},
        "mg": {"name": "Fitaovana", "description": "Feo avy amin'ny rafitra, tsy misy fetra."},
    },
    "pollinations": {
        "en": {"description": "Text and images without a key (rate limited)."},
        "mg": {"description": "Lahatsoratra sy sary tsy mila fanalahidy (voafetra ny "
                              "hafainganana)."},
    },
    "hf_spaces": {
        "en": {"name": "Hugging Face Spaces",
               "description": "Video without a key through public Spaces (shared GPU, "
                              "daily quota)."},
        "mg": {"name": "Spaces Hugging Face",
               "description": "Horonan-tsary tsy mila fanalahidy amin'ny Spaces ho an'ny daholobe "
                              "(GPU iombonana, fetra isan'andro)."},
    },
    "ollama_local": {
        "en": {"name": "Ollama (on this device)",
               "description": "Models installed with Ollama: work without Internet."},
        "mg": {"name": "Ollama (amin'ity fitaovana ity)",
               "description": "Modely napetraka tamin'ny Ollama: mandeha tsy misy Internet."},
    },
    "llamacpp_local": {
        "en": {"name": "llama.cpp (on this device)",
               "description": "GGUF model served by llama-server: works without Internet."},
        "mg": {"name": "llama.cpp (amin'ity fitaovana ity)",
               "description": "Modely GGUF atolotry ny llama-server: mandeha tsy misy Internet."},
    },
    # Gratuits avec clé
    "groq": {
        "en": {"description": "Very fast. Permanent free tier (rate limited)."},
        "mg": {"description": "Haingana dia haingana. Maimaim-poana mandrakariva (voafetra)."},
    },
    "cerebras": {
        "en": {"description": "Among the fastest. Permanent free tier (rate limited)."},
        "mg": {"description": "Anisan'ny haingana indrindra. Maimaim-poana mandrakariva "
                              "(voafetra)."},
    },
    "sambanova": {
        "en": {"description": "Large open models, fast. Free tier (rate limited)."},
        "mg": {"description": "Modely misokatra lehibe, haingana. Maimaim-poana (voafetra)."},
    },
    "github": {
        "en": {"description": "GPT, Llama, DeepSeek, Mistral… with a GitHub token (“models: "
                              "read” permission). Free, rate limited."},
        "mg": {"description": "GPT, Llama, DeepSeek, Mistral… miaraka amin'ny token GitHub "
                              "(alalana « models: read »). Maimaim-poana, voafetra."},
    },
    "together": {
        "en": {"description": "“Free” models are free; the others are paid (not used)."},
        "mg": {"description": "Maimaim-poana ny modely « Free »; mandoa vola ny hafa (tsy "
                              "ampiasaina)."},
    },
    "mistral": {
        "en": {"description": "Free “Experiment” tier: all Mistral models, rate limited."},
        "mg": {"description": "Tolotra « Experiment » maimaim-poana: ny modely Mistral rehetra, "
                              "voafetra."},
    },
    "gemini": {
        "en": {"description": "Gemini Flash and Pro with a free Google AI Studio key."},
        "mg": {"description": "Gemini Flash sy Pro miaraka amin'ny fanalahidy Google AI Studio "
                              "maimaim-poana."},
    },
    "nvidia": {
        "en": {"description": "Dozens of open models, free for development."},
        "mg": {"description": "Modely misokatra am-polony, maimaim-poana ho an'ny fampandrosoana."},
    },
    "huggingface": {
        "en": {"description": "Inference router: free monthly credits."},
        "mg": {"description": "Mpitari-dalana: crédit maimaim-poana isam-bolana."},
    },
    # Payants directs
    "openai": {
        "en": {"description": "GPT-5, GPT-4.1, o3… Billed per use by OpenAI."},
        "mg": {"description": "GPT-5, GPT-4.1, o3… Aloa araka ny fampiasana amin'ny OpenAI."},
    },
    "anthropic": {
        "en": {"description": "Claude Opus, Sonnet, Haiku. Billed per use by Anthropic."},
        "mg": {"description": "Claude Opus, Sonnet, Haiku. Aloa araka ny fampiasana amin'ny "
                              "Anthropic."},
    },
    "deepseek": {
        "en": {"description": "Very cheap, excellent at code and maths."},
        "mg": {"description": "Mora dia mora, tena mahay kaody sy matematika."},
    },
    "xai": {
        "en": {"description": "Grok models. Billed per use by xAI."},
        "mg": {"description": "Modely Grok. Aloa araka ny fampiasana amin'ny xAI."},
    },
    "moonshot": {
        "en": {"description": "Kimi models: long context, good at agents. Billed per use."},
        "mg": {"description": "Modely Kimi: votoaty lava, mahay amin'ny agent. Aloa araka ny "
                              "fampiasana."},
    },
    "qwen": {
        "en": {"description": "Qwen Max, Plus, Coder… Billed per use by Alibaba Cloud."},
        "mg": {"description": "Qwen Max, Plus, Coder… Aloa araka ny fampiasana amin'ny "
                              "Alibaba Cloud."},
    },
    "perplexity": {
        "en": {"description": "Answers with web search and sources. Billed per use."},
        "mg": {"description": "Valiny miaraka amin'ny fikarohana an-tranonkala sy loharano. "
                              "Aloa araka ny fampiasana."},
    },
}

_CUSTOM = {
    "en": {"description": "Custom provider (advanced mode)."},
    "mg": {"description": "Mpamatsy manokana (fomba mandroso)."},
}


def texts(pid: str, provider: dict[str, Any]) -> dict[str, dict[str, str]]:
    """Traductions d'un fournisseur ({"en": {...}, "mg": {...}}), vide si inconnu."""
    if provider.get("custom"):
        return _CUSTOM
    return PROVIDER_TEXT.get(pid, {})
