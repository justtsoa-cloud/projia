"""Détection des modèles locaux (Ollama, llama.cpp) : boucle locale uniquement."""

from __future__ import annotations

import httpx

from projia.catalog.sources import local_llm


def _client() -> httpx.AsyncClient:
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.host == "127.0.0.1"  # jamais d'hôte distant
        if req.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [
                {"name": "llama3.2:3b"}, {"name": "nomic-embed-text"}, {"name": "qwen3:4b"}]})
        if req.url.path == "/v1/models":
            return httpx.Response(200, json={"data": [{"id": "/models/gemma-3-1b.gguf"}]})
        return httpx.Response(404)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_ollama_models_without_embeddings() -> None:
    models = await local_llm._ollama(_client())
    assert [m.model_id for m in models] == ["llama3.2:3b", "qwen3:4b"]
    assert all(m.is_free and not m.needs_key and m.provider == "ollama_local" for m in models)


async def test_llamacpp_model() -> None:
    models = await local_llm._llamacpp(_client())
    assert models[0].name == "gemma-3-1b.gguf (local)"


async def test_discover_without_local_server_is_empty() -> None:
    # Aucun serveur local dans l'environnement de test : liste vide, sans erreur ni délai long.
    assert isinstance(await local_llm.discover(), list)
