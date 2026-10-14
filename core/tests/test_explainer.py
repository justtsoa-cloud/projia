"""Vidéos explicatives du mode Apprendre : intention, complétion, scénario, sécurité, route."""

from __future__ import annotations

import base64
import json
import time
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tontolo.catalog.service import CatalogService
from tontolo.config import Settings
from tontolo.explainer import manim_render, storyboard, writer
from tontolo.explainer.intent import complete, resolve
from tontolo.providers.fake import FakeProvider
from tontolo.providers.registry import ProviderRegistry
from tontolo.server.app import create_app

GOOD = {"title": "Additionner des fractions", "scenes": [
    {"type": "title", "text": "Additionner des fractions", "narration": "Bonjour."},
    {"type": "bullets", "title": "L'idée", "items": ["Même dénominateur", "On additionne"],
     "narration": "Il faut le même dénominateur."},
    {"type": "steps", "title": "Exemple", "steps": [
        {"text": "Dénominateur commun", "latex": "\\frac{1}{2}=\\frac{3}{6}"},
        {"text": "On additionne", "latex": "\\frac{3}{6}+\\frac{2}{6}=\\frac{5}{6}"}],
     "narration": "Trois sixièmes plus deux sixièmes."},
    {"type": "plot", "title": "Courbe", "expr": "x^2", "xmin": -3, "xmax": 3,
     "caption": "Le carré", "narration": "La courbe."},
    {"type": "recap", "title": "À retenir", "items": ["a", "b", "c"], "narration": "Fin."}]}


@pytest.mark.parametrize(("text", "learn", "active", "ctx"), [
    ("fais-moi une vidéo qui explique les fractions", True, True, False),
    ("fais une vidéo sur la photosynthèse", True, True, False),
    ("une vidéo explicative sur les probabilités", False, True, False),
    ("explique-moi les dérivées en vidéo", False, True, False),
    ("fais-moi une vidéo de ça", True, True, True),
    ("make an educational video about black holes", False, True, False),
    ("fais une vidéo manim sur les vecteurs", False, True, False),
    ("crée une courte vidéo sur les maths", True, True, False),
    ("fais une vidéo d'un chat qui danse", False, False, False),  # génération, hors cours
    ("que montre cette vidéo jointe ?", True, False, False),
    ("Explique la photosynthèse", True, False, False),
    ("", True, False, False),
])
def test_intent(text: str, learn: bool, active: bool, ctx: bool) -> None:
    got = resolve(text, learn_mode=learn)
    assert got.active is active and (not active or got.from_context is ctx)


def test_naive_requests_are_completed() -> None:
    brief = complete("fais-moi une vidéo sur les maths", level="college")
    assert brief.broad and brief.duration_s == 75 and brief.level == "college"
    assert "UNE notion" in brief.directive() and "collégien" in brief.directive()
    assert complete("une courte vidéo sur la loi d'Ohm").duration_s == 45
    assert complete("vidéo explicative de 2 minutes sur la loi d'Ohm").duration_s == 120
    assert complete("une vidéo détaillée sur Ohm").duration_s == 120
    assert complete("une vidéo de 20 minutes sur Ohm").duration_s == 180  # borné
    assert complete("une vidéo sur Ohm", level="inconnu").level == "lycee"
    assert 4 <= complete("une vidéo sur Ohm").scenes <= 8
    # Sujet pris dans la discussion quand la phrase n'en dit rien.
    assert "accroche" in complete("une vidéo sur Ohm").directive()


def test_the_storyboard_is_validated_and_bounded() -> None:
    story = storyboard.validate(GOOD)
    assert story["seconds"] > 10 and len(story["scenes"]) == 5
    plot = story["scenes"][3]
    assert len(plot["points"]) > 30 and plot["points"][0][1] == pytest.approx(9.0)
    with pytest.raises(storyboard.StoryboardError, match="type inconnu"):
        storyboard.validate({"title": "x", "scenes": [{"type": "script", "code": "1"}] * 3})
    with pytest.raises(storyboard.StoryboardError, match="au moins 3"):
        storyboard.validate({"title": "x", "scenes": GOOD["scenes"][:2]})
    big = {"title": "t", "scenes": [{"type": "title", "text": "x" * 500, "narration": "y" * 900}
                                     for _ in range(30)]}
    out = storyboard.validate(big)
    assert len(out["scenes"]) == storyboard.MAX_SCENES
    assert all(len(s["text"]) <= storyboard.MAX_TEXT and len(s["narration"]) <= 320
               for s in out["scenes"])


def test_a_single_bullet_becomes_a_big_centered_sentence() -> None:
    story = storyboard.validate({"title": "t", "scenes": [
        {"type": "bullets", "title": "Accroche", "items": ["Imagine une pizza."],
         "narration": "n"}, GOOD["scenes"][1], GOOD["scenes"][4]]})
    first = story["scenes"][0]
    assert first["type"] == "title" and first["text"] == "Imagine une pizza."
    assert first["subtitle"] == "Accroche"


@pytest.mark.parametrize("bad", [
    "\\input{/etc/passwd}", "\\write18{rm -rf /}", "\\def\\x{y}", "\\usepackage{x}",
    "\\frac{1}{2", "x\u00e9", "\\href{http://x}{y}", "\\catcode`\\@=11",
    "\\immediate\\write", "`ls`", "a" * 400,
])
def test_dangerous_latex_is_refused(bad: str) -> None:
    scene = {"type": "equation", "latex": bad, "narration": "x"}
    with pytest.raises(storyboard.StoryboardError):
        storyboard.validate({"title": "t", "scenes": [GOOD["scenes"][0], scene, GOOD["scenes"][4]]})


def test_plot_expressions_are_a_whitelist() -> None:
    assert len(storyboard.plot_points("sin(x)+x/2", -3, 3)) > 30
    assert storyboard.plot_points("sqrt(x)", -2, 4)  # racines négatives ignorées
    for bad in ["__import__('os').system('ls')", "open('/etc/passwd')", "x.__class__",
                "[i for i in range(9**9)]", "lambda: 1", "x**999", "9**9**9", "1e9*x",
                "eval('1')", "sin(x)(2)", "x if x else 1", "exec"]:
        with pytest.raises(storyboard.StoryboardError):
            storyboard.plot_points(bad, -1, 1)
    start = time.perf_counter()
    for _ in range(50):
        storyboard.plot_points("x**2+sin(x)*cos(x)/(1+x**2)", -50, 50)
    assert time.perf_counter() - start < 1.0


def test_json_extraction_and_one_repair() -> None:
    raw = "Voici : ```json\n" + json.dumps(GOOD) + "\n``` et du texte après."
    assert writer.extract_json(raw)["title"] == "Additionner des fractions"
    with pytest.raises(storyboard.StoryboardError):
        writer.extract_json("rien")
    with pytest.raises(storyboard.StoryboardError):
        writer.extract_json('{"title": "coupé", "scenes": [')


async def test_writer_repairs_once_then_gives_up() -> None:
    brief = complete("une vidéo sur les fractions")
    calls: list[list[dict[str, Any]]] = []

    async def flaky(messages: list[dict[str, Any]], accept: Any) -> str:
        calls.append(messages)
        return "pas du json" if len(calls) == 1 else json.dumps(GOOD)

    story = await writer.write(brief, flaky, context="discussion")
    assert story["title"] == "Additionner des fractions" and len(calls) == 2
    assert "rejected" in calls[1][-1]["content"]

    async def hopeless(messages: list[dict[str, Any]], accept: Any) -> str:
        return "toujours pas"

    with pytest.raises(storyboard.StoryboardError):
        await writer.write(brief, hopeless)


def test_fallback_builds_a_simple_video_from_an_explanation() -> None:
    text = ("Une fraction représente une part d'un tout partagé en parts égales. Le dénominateur "
            "dit en combien de parts on coupe le tout. Le numérateur dit combien de parts on "
            "prend. Pour additionner deux fractions, il faut le même dénominateur. Ensuite on "
            "additionne seulement les numérateurs et on garde le dénominateur.")
    story = storyboard.fallback_from_text("les fractions", text)
    assert story is not None and story["scenes"][0]["type"] == "title"
    assert story["scenes"][-1]["type"] == "recap"
    assert storyboard.fallback_from_text("x", "trop court") is None


def test_manim_script_is_a_fixed_template_with_data_never_code() -> None:
    evil = {"title": "x'; import os; os.system('id') #", "scenes": [
        {"type": "title", "text": "\"\"\"; __import__('os').system('id'); \"\"\"",
         "narration": "a\\'b"}] * 3}
    story = storyboard.validate(evil)
    script = manim_render.build_script(story, tex=True)
    assert "os.system" not in script and "__import__" not in script and "import os" not in script
    data = script.split('base64.b64decode("')[1].split('"')[0]
    assert json.loads(base64.b64decode(data))["scenes"][0]["text"].startswith('"""')
    assert script.count("DATA = ") == 1
    clean = manim_render.build_script(storyboard.validate(GOOD), tex=False)
    assert "class Explainer(Scene)" in clean
    compile(clean, "scene.py", "exec")  # le gabarit est du Python valide


def test_status_and_render_without_manim(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(manim_render, "_manim_python", lambda: None)
    assert manim_render.status()["manim"] is False
    import asyncio

    with pytest.raises(manim_render.RenderError, match="pas installé"):
        asyncio.run(manim_render.render(storyboard.validate(GOOD)))


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


def _chat(client: TestClient, body: dict[str, Any]) -> list[dict[str, Any]]:
    with client.stream("POST", "/tontolo/chat", json=body) as r:
        return [json.loads(x[5:]) for x in r.iter_lines() if x.startswith("data:")]


def test_learn_mode_request_becomes_an_explainer_block(client: TestClient,
                                                       fake: FakeProvider) -> None:
    seen: list[list[dict[str, Any]]] = []

    def reply(model: Any, messages: list[dict[str, Any]]) -> dict[str, Any]:
        seen.append(messages)
        return {"role": "assistant", "content": json.dumps(GOOD)}

    for mid in [*fake.behaviors, "coder-pro", "chatty", "small", "vision-x", "paid-genius"]:
        fake.behaviors[mid] = reply
    events = _chat(client, {"content": "fais-moi une courte vidéo sur les fractions",
                            "mode": "learn", "level": "college"})
    assert any(e.get("step") == "explainer_plan" for e in events)
    done = next(e for e in events if e["type"] == "done")
    content = done["message"]["content"]
    assert content.startswith("Voici une vidéo explicative") and "```explainer" in content
    block = json.loads(content.split("```explainer\n")[1].split("\n```")[0])
    assert block["scenes"][0]["type"] == "title" and len(block["scenes"]) == 5
    assert "collégien" in str(seen[-1][-1]["content"])  # le niveau du mode Apprendre
    assert "45 secondes" in str(seen[-1][-1]["content"])  # « courte » → 45 s
    # Hors mode Apprendre, une vidéo « normale » reste une génération de vidéo.
    plain = _chat(client, {"content": "fais une vidéo d'un chat qui danse"})
    assert not any(e.get("step") == "explainer_plan" for e in plain)


def test_if_the_model_fails_the_user_still_gets_an_answer(client: TestClient,
                                                          fake: FakeProvider) -> None:
    def junk(model: Any, messages: list[dict[str, Any]]) -> dict[str, Any]:
        return {"role": "assistant", "content": "désolé, pas de JSON ici"}

    for mid in [*fake.behaviors, "coder-pro", "chatty", "small", "vision-x", "paid-genius"]:
        fake.behaviors[mid] = junk
    done = next(e for e in _chat(client, {"content": "fais une vidéo sur les fractions",
                                          "mode": "learn"}) if e["type"] == "done")
    content = done["message"]["content"]
    assert "pas réussi" in content or "```explainer" in content


def test_render_endpoint_validates_and_reports_capabilities(client: TestClient) -> None:
    caps = client.get("/tontolo/explainer/capabilities").json()
    assert set(caps) >= {"manim", "ffmpeg", "latex", "sandbox", "mp4"}
    bad = client.post("/tontolo/explainer/render", json={"story": {"scenes": [{"type": "x"}]}})
    assert bad.status_code == 400
    evil = client.post("/tontolo/explainer/render", json={"story": {
        "title": "t", "scenes": [{"type": "equation", "latex": "\\input{/etc/passwd}"}] * 3}})
    assert evil.status_code == 400
    huge = client.post("/tontolo/explainer/render", content=b"x" * 300_000)
    assert huge.status_code == 413


@pytest.mark.skipif(not manim_render.status()["manim"] or not manim_render.status()["ffmpeg"],
                    reason="Manim absent : rendu MP4 non testé ici")
def test_real_manim_render() -> None:
    import asyncio

    mp4 = asyncio.run(manim_render.render(storyboard.validate(GOOD)))
    assert mp4[4:8] == b"ftyp" and len(mp4) > 10_000
