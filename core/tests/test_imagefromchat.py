"""« Génère une image par rapport à la discussion » : intention, brief tiré du fil, poster."""

from __future__ import annotations

import json
import time
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tontolo.agent import imagebrief
from tontolo.catalog.models import Category
from tontolo.catalog.service import CatalogService
from tontolo.config import Settings
from tontolo.creator import intent as file_intent
from tontolo.providers.fake import FakeProvider
from tontolo.providers.registry import ProviderRegistry
from tontolo.router.classifier import classify
from tontolo.router.imageintent import resolve
from tontolo.server.app import create_app

PDF_REQUESTS = [  # les trois phrases de la discussion d'origine
    ("transforme tout cela en un poster détaillé, sans faute et bien compact mais aussi très "
     "beau à regarder", "poster"),
    ("je veux ça en image", "illustration"),
    ("je demande de générer une image et ça me donne deux fois du texte", "illustration"),
]


@pytest.mark.parametrize(("text", "kind"), PDF_REQUESTS)
def test_the_original_requests_are_understood(text: str, kind: str) -> None:
    intent = resolve(text)
    assert intent.kind == kind and intent.from_context


@pytest.mark.parametrize("text", [
    "je demande de générer une image par rapport à la discussion", "mets ça en infographie",
    "make an image of all this", "peux-tu illustrer cela ?", "Mamorona sary momba izany",
    "fais-en une illustration", "sous forme d'image s'il te plaît",
])
def test_context_images(text: str) -> None:
    assert resolve(text).kind != "none" and resolve(text).from_context


@pytest.mark.parametrize("text", [
    "décris cette image", "que montre ce poster ?", "Explique la photosynthèse", "Merci !",
    "écris un site web avec une image", "fais un résumé de la discussion", "",
])
def test_no_false_positive(text: str) -> None:
    assert resolve(text).kind == "none"


def test_an_explicit_subject_stays_the_subject() -> None:
    intent = resolve("génère une image d'un chat qui danse sur la lune")
    assert intent.kind == "illustration" and not intent.from_context


def test_classifier_and_file_intent_follow_the_resolver() -> None:
    cat = classify([{"role": "user", "content": "je veux ça en image"}]).category
    assert cat == Category.IMAGE_GEN
    assert file_intent.detect(PDF_REQUESTS[0][0]) == "poster"
    assert file_intent.detect("je veux ça en image") is None  # illustration : pas un document
    assert file_intent.valid("poster")


def test_the_resolver_cannot_be_stalled() -> None:
    nasty = ("génère " + "une image " * 3000) + "x" * 100_000
    started = time.perf_counter()
    for _ in range(20):
        resolve(nasty)
        resolve("fais " + "a " * 4000 + " image")
    assert time.perf_counter() - started < 1.0


def _thread() -> list[dict[str, Any]]:
    return [
        {"role": "user", "content": "peux tu me décrire mathématiquement et simplement la "
                                    "théorie de la représentation des groupes"},
        {"role": "assistant", "content": (
            "La théorie de la représentation étudie des groupes en les faisant agir par des "
            "matrices. **Définition** : $\\rho : G \\to GL(V)$ est un morphisme. Exemple : le "
            "groupe cyclique $\\mathbb{Z}/4\\mathbb{Z}$ agit par rotations de 90 degrés, avec "
            "des matrices 2x2. ```python\nprint(1)\n``` Voir https://exemple.org/x")},
        {"role": "user", "content": "je veux ça en image"},
    ]


def test_digest_keeps_the_subject_and_drops_the_noise() -> None:
    topic, summary = imagebrief.digest(_thread()[:-1])
    assert "théorie de la représentation" in topic
    assert "rotations" in summary and "$" not in summary and "print" not in summary
    assert "https" not in summary and "**" not in summary


def test_extract_needs_the_tags_and_drops_reasoning() -> None:
    raw = ("The user wants a prompt... <prompt>draft</prompt> Final: "
           "<prompt>A glowing lattice of linked nodes on a navy background, cyan and gold</prompt>")
    assert imagebrief.extract(raw) == (
        "A glowing lattice of linked nodes on a navy background, cyan and gold")
    assert imagebrief.extract("The user wants a prompt for an image generator.") is None
    assert imagebrief.extract("<prompt>The user wants something here today</prompt>") is None


def test_clean_rejects_unusable_model_output() -> None:
    assert imagebrief.clean("I'm sorry, I cannot help with that request at all.") is None
    assert imagebrief.clean("ok") is None and imagebrief.clean(None) is None
    good = imagebrief.clean('"Prompt: A glowing cyclic diagram of rotating squares on navy"')
    assert good is not None and good.startswith("A glowing") and "http" not in good
    assert len(imagebrief.clean("x " * 2000) or "") <= imagebrief.MAX_PROMPT


async def test_brief_uses_the_model_then_falls_back_without_it() -> None:
    history = _thread()[:-1]

    async def good(messages: list[dict[str, Any]], accept: Any) -> str:
        assert "représentation" in messages[1]["content"]
        assert "very beautiful, compact" not in messages[1]["content"]
        return ("<prompt>A luminous diagram of a square rotating through four positions, navy "
                "and gold</prompt>")

    prompt, source = await imagebrief.build(history, "très beau et compact", good)
    assert source == "model" and "square" in prompt

    async def broken(messages: list[dict[str, Any]], accept: Any) -> str:
        raise RuntimeError("panne")

    prompt, source = await imagebrief.build(history, "très beau et compact", broken)
    assert source == "fallback" and "représentation" in prompt
    assert "beautiful" in prompt and "compact" in prompt  # les souhaits de style, traduits

    async def slow(messages: list[dict[str, Any]], accept: Any) -> str:
        import asyncio

        await asyncio.sleep(5)
        return "never"

    t = time.perf_counter()
    _, source = await imagebrief.build(history, "belle image", slow, limit=0.2)
    assert source == "fallback" and time.perf_counter() - t < 2

    async def junk(messages: list[dict[str, Any]], accept: Any) -> str:
        return "Sorry, I cannot do that."

    async def reasoning(messages: list[dict[str, Any]], accept: Any) -> str:
        # Un modèle à réflexion laisse son raisonnement (sans balises) : jamais un prompt.
        return "The user wants a prompt for an AI image generator that visually summarizes it."

    assert (await imagebrief.build(history, "", reasoning))[1] == "fallback"

    assert (await imagebrief.build(history, "", junk))[1] == "fallback"
    assert (await imagebrief.build([], "je veux ça en image", good))[1] == "request"


def test_complaints_never_reach_the_image_prompt() -> None:
    prompt = imagebrief.fallback("group theory", imagebrief.style_wishes(
        "je demande de générer une image et ça me donne deux fois du texte, très beau"))
    assert "texte" not in prompt and "demande" not in prompt and "beautiful" in prompt


@pytest.fixture
def client(settings: Settings, catalog_service: CatalogService, fake: FakeProvider,
           monkeypatch: pytest.MonkeyPatch) -> Any:
    async def fake_load(self: CatalogService) -> Any:
        self.catalog = catalog_service.catalog
        return self.catalog

    monkeypatch.setattr(CatalogService, "load", fake_load)
    app = create_app(settings, registry=ProviderRegistry(lambda p: fake), refresh=False)
    with TestClient(app, base_url="http://127.0.0.1") as c:
        yield c


def test_the_job_prompt_comes_from_the_discussion(client: TestClient,
                                                  monkeypatch: pytest.MonkeyPatch) -> None:
    from tontolo.media.service import MediaService

    submitted: list[tuple[str, str]] = []

    async def submit(self: Any, kind: str, prompt: str = "", **kw: Any) -> dict[str, Any]:
        submitted.append((kind, prompt))
        return {"id": "j1", "kind": kind, "status": "queued", "params": {}}

    async def wait(self: Any, job_id: str, *a: Any, **k: Any) -> dict[str, Any]:
        return {"id": "j1", "kind": "image_gen", "status": "done", "params": {}, "model": "x"}

    monkeypatch.setattr(MediaService, "submit", submit)
    monkeypatch.setattr(MediaService, "wait", wait)
    snap = {"snapshot_name": "Groupes", "chat_messages": [
        {"sender": "human", "content": [{"type": "text", "text": _thread()[0]["content"]}]},
        {"sender": "assistant", "content": [{"type": "text", "text": _thread()[1]["content"]}]}]}
    cid = client.post("/tontolo/import", json={"data": json.dumps(snap)}).json()[
        "conversations"][0]["id"]
    with client.stream("POST", "/tontolo/chat", json={
            "conversation_id": cid, "content": "je veux ça en image"}) as r:
        events = [json.loads(x[5:]) for x in r.iter_lines() if x.startswith("data:")]
    assert any(e.get("step") == "image_brief" for e in events)
    kind, prompt = submitted[-1]
    assert kind == "image_gen"
    assert "veux" not in prompt and ("représentation" in prompt or "group" in prompt.lower())
    # Un sujet explicite reste inchangé.
    with client.stream("POST", "/tontolo/chat", json={
            "conversation_id": cid, "content": "dessine un baobab au coucher du soleil"}) as r:
        list(r.iter_lines())
    assert "baobab" in submitted[-1][1].lower()


async def test_quick_calls_survive_a_model_that_requires_sign_in(
        router: Any, fake: FakeProvider, monkeypatch: pytest.MonkeyPatch) -> None:
    """Régression : `quick` (résumés de fil, mémoire, brief d'image) n'essayait qu'UN modèle ;
    un modèle gratuit qui exige une connexion le faisait échouer en silence."""
    from tontolo.providers.base import ErrorKind, ProviderError

    calls: list[str] = []

    def behave(model: Any, messages: list[dict[str, Any]]) -> dict[str, Any]:
        calls.append(model.model_id)
        if len(calls) == 1:
            raise ProviderError("You need to sign in to use this model.", ErrorKind.AUTH, 401)
        return {"role": "assistant", "content": "A glowing diagram of four rotating squares."}

    for mid in ["coder-pro", "chatty", "small", "vision-x", "paid-genius"]:
        fake.behaviors[mid] = behave
    out = await router.quick([{"role": "user", "content": "hello"}])
    assert out is not None and "squares" in out and len(calls) >= 2
