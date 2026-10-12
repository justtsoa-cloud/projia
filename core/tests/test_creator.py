"""Créations de fichiers : formats, vérifications, boucle de correction, relecture croisée."""

from __future__ import annotations

import io
import json
import zipfile
from typing import Any

import pytest

from tontolo.creator import diagram, docx, intent, latex, office, pipeline, textfile
from tontolo.creator.pipeline import CreationError, Creator, Output


def test_docx_is_valid_word_file() -> None:
    data = docx.build("# Titre\n## Partie\nTexte **gras** et $\\frac{1}{2}$.\n- a\n  - b\n"
                      "| A | B |\n|---|---|\n| 1 | 2 |\n")
    assert docx.check(data) == []
    names = zipfile.ZipFile(io.BytesIO(data)).namelist()
    assert "word/document.xml" in names and "word/numbering.xml" in names
    body = zipfile.ZipFile(io.BytesIO(data)).read("word/document.xml").decode()
    assert "1/2" in body and "<w:tbl>" in body and "Titre" in body


def test_xlsx_and_pptx() -> None:
    sheets = [{"name": "Notes",
               "rows": [["Élève", "Note"], ["A", 12], ["Moyenne", "=AVERAGE(B2:B2)"]]}]
    assert office.xlsx_problems(sheets) == []
    z = zipfile.ZipFile(io.BytesIO(office.build_xlsx(sheets)))
    assert "AVERAGE(B2:B2)" in z.read("xl/worksheets/sheet1.xml").decode()
    bad = [{"name": "a/b", "rows": [["x", "y"], ["z"]]}]
    assert len(office.xlsx_problems(bad)) == 2
    md = "# Exposé\n- sous-titre\n## Partie 1\n- point\n" + "## Trop\n" + "- x\n" * 9
    title, slides = office.parse_slides(md)
    assert title == "Exposé" and len(slides) == 3
    assert any("7 au maximum" in p for p in office.pptx_problems(slides))
    z = zipfile.ZipFile(io.BytesIO(office.build_pptx(md)))
    assert "ppt/slides/slide3.xml" in z.namelist()


def test_text_files_checked() -> None:
    assert textfile.problems("py", "def f(:\n") and not textfile.problems("py", "x = 1\n")
    assert textfile.problems("json", "{x}") and not textfile.problems("json", '{"a": 1}')
    assert textfile.problems("svg", "<svg><script>alert(1)</script></svg>")
    assert textfile.problems("svg", '<!DOCTYPE x [<!ENTITY a "b">]><svg/>')
    assert textfile.problems("csv", "a,b\n1\n")


def test_intent() -> None:
    assert intent.detect("Génère un document Word sur l'eau") == "docx"
    assert intent.detect("fais-moi une carte mentale du chapitre") == "mindmap"
    assert intent.detect("explique-moi ce pdf") is None
    assert intent.detect("crée un fichier json des pays") == "text:json"
    assert intent.valid("pptx") and intent.valid("text:csv") and not intent.valid("text:../x")


def test_mindmap_outline_checks_and_dot() -> None:
    long = "x" * 80
    data = diagram.parse_outline('```json\n{"title": "T", "children": [{"label": "A"}, '
                                 '{"label": "B", "children": [{"label": "' + long + '"}]}]}\n```')
    assert any("trop long" in p for p in diagram.outline_problems(data))
    dot = diagram.outline_to_dot(data)
    assert dot.startswith("digraph") and 'label="T"' in dot
    with pytest.raises(diagram.DiagramError):
        diagram.parse_outline("pas de json")


def test_latex_checks() -> None:
    assert pipeline.latex_problems("\\section{x}")  # document incomplet
    assert pipeline.latex_problems("\\documentclass{article}\\begin{document}\\input{x}"
                                   "\\end{document}")
    assert pipeline.latex_title("\\title{\\textbf{Fiche}\\\\ Maths}") == "Fiche Maths"
    log = "./document.tex:12: Undefined control sequence.\nl.12 \\oops\n"
    assert "Undefined control sequence" in latex.errors_from_log(log)
    assert latex.warnings_from_log("Overfull \\hbox (40.0pt too wide) in paragraph at lines 3--4")


class FakeModels:
    """Rédacteur puis correcteur scriptés ; relecteur d'une autre famille."""

    def __init__(self, answers: list[str], review: str = '{"ok": true, "issues": []}') -> None:
        self.answers = answers
        self.review = review
        self.calls: list[dict[str, Any]] = []

    async def ask(self, messages: list[dict[str, Any]], *, category: Any = None,
                  model: str | None = None) -> tuple[str, str, str]:
        self.calls.append({"model": model, "last": messages[-1]["content"]})
        if model == "r:reviewer-model":
            return self.review, "r:reviewer-model", "Relecteur"
        return self.answers.pop(0), "w:writer-model", "Rédacteur"

    async def pick(self, *, exclude: str, vision: bool = False) -> str | None:
        assert exclude == "w:writer-model"
        return "r:reviewer-model"


async def _run(models: FakeModels, kind: str) -> tuple[Output, list[str]]:
    out = Output(b"", "", "", "", "", "")
    steps = [ev["step"] async for ev in Creator(models.ask, models.pick).run(
        kind, "demande", out=out)]
    return out, steps


async def test_fix_loop_feeds_errors_back() -> None:
    models = FakeModels(["Pas de titre", "# Mon document\nTexte."])
    out, steps = await _run(models, "docx")
    assert out.filename == "mon-document.docx" and docx.check(out.data) == []
    assert "doc_fixing" in steps and steps[-1] == "doc_done"
    assert "titre" in str(models.calls[1]["last"])  # le problème a été renvoyé au rédacteur
    assert [s["step"] for s in out.steps] == ["doc_writing", "doc_fixing", "doc_reviewing"]


async def test_review_by_other_model_triggers_fix() -> None:
    models = FakeModels(["# A\nx", "# A\nx corrigé"],
                        review='{"ok": false, "issues": ["il manque une conclusion"]}')
    out, steps = await _run(models, "docx")
    assert steps.count("doc_reviewing") == 1 and "doc_fixing" in steps
    assert "conclusion" in str(models.calls[2]["last"])
    assert out.models == ["w:writer-model", "r:reviewer-model"]


async def test_latex_error_log_is_sent_back(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    async def fake_compile(source: str) -> tuple[bytes, str, str]:
        calls.append(source)
        if "\\oops" in source:
            raise latex.LatexError("erreur de compilation", "! Undefined control sequence. \\oops")
        return b"%PDF-1.7 ok", "", "local"

    monkeypatch.setattr(latex, "compile_pdf", fake_compile)
    doc = "\\documentclass{article}\\title{Fiche}\\begin{document}%s\\end{document}"
    models = FakeModels([doc % "\\oops", doc % "ok"])
    out, _ = await _run(models, "pdf")
    assert out.mime == "application/pdf" and len(calls) == 2
    assert "Undefined control sequence" in str(models.calls[1]["last"])


async def test_unbuildable_file_is_never_delivered() -> None:
    models = FakeModels(["sans titre"] * 5)
    with pytest.raises(CreationError):
        await _run(models, "docx")


async def test_service_down_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    async def down(data: Any) -> Any:
        raise diagram.DiagramError("injoignable", retryable=True)

    monkeypatch.setattr(diagram, "render_mindmap", down)
    models = FakeModels([json.dumps({"title": "T", "children": [{"label": "a"}, {"label": "b"}]})])
    with pytest.raises(CreationError, match="injoignable"):
        await _run(models, "mindmap")


async def test_reviewer_is_never_the_same_model_from_another_provider() -> None:
    from types import SimpleNamespace

    from tontolo.catalog.models import ModelInfo
    from tontolo.creator.service import CreatorService

    writer = ModelInfo(provider="openrouter", model_id="nvidia/nemotron-ultra:free",
                       family="Nemotron")
    same = ModelInfo(provider="kilo", model_id="nvidia/nemotron-ultra", family="Nemotron")
    other = ModelInfo(provider="groq", model_id="qwen/qwen3-32b", family="Qwen")
    models = {m.key: m for m in (writer, same, other)}

    class Router:
        catalog = SimpleNamespace(catalog=SimpleNamespace(get=models.get))

        async def decide(self, *a: Any, **k: Any) -> Any:
            return SimpleNamespace(chain=[SimpleNamespace(model=m) for m in (writer, same, other)])

    svc = CreatorService(None, Router(), __import__("pathlib").Path("/tmp"))  # type: ignore[arg-type]
    assert await svc.pick_reviewer(exclude=writer.key) == other.key


def test_same_model_detection() -> None:
    from tontolo.creator.pipeline import same_model

    assert same_model("openrouter:nvidia/nemotron-3-ultra:free", "kilo:nvidia/nemotron-3-ultra")
    assert not same_model("groq:qwen/qwen3-32b", "openrouter:nvidia/nemotron-3-ultra:free")


async def test_self_review_after_fallback_is_not_counted() -> None:
    class Fallback(FakeModels):
        async def ask(self, messages: list[dict[str, Any]], *, category: Any = None,
                      model: str | None = None) -> tuple[str, str, str]:
            # Relecteur indisponible : la bascule renvoie au rédacteur.
            if model == "r:reviewer-model":
                return '{"ok": false, "issues": ["x"]}', "w:writer-model", "Rédacteur"
            return await super().ask(messages, category=category, model=model)

    models = Fallback(["# Doc\ntexte"])
    out, steps = await _run(models, "docx")
    assert [s["step"] for s in out.steps] == ["doc_writing"] and "doc_fixing" not in steps


async def test_writer_failure_is_retried_once() -> None:
    class Flaky(FakeModels):
        failed = False

        async def ask(self, messages: list[dict[str, Any]], *, category: Any = None,
                      model: str | None = None) -> tuple[str, str, str]:
            if not Flaky.failed:
                Flaky.failed = True
                raise TimeoutError
            return await super().ask(messages, category=category, model=model)

    out, _ = await _run(Flaky(["# Plan\ntexte"]), "docx")
    assert out.filename == "plan.docx"


def test_feedback_after_a_file_is_a_revision() -> None:
    for yes in ("excellent mais des vraies citations", "rajoute des exemples", "plus court",
                "trop long, résume", "en couleur", "parfait mais en anglais",
                "Great but with real quotes", "mets des citations exactes"):
        assert intent.is_revision(yes), yes
    for no in ("merci", "Super !", "ok", "je ne comprends pas la partie Popper",
               "pourquoi Kuhn parle de paradigmes", "c'est quoi la falsification ?",
               "Quelle est la capitale de la France", ""):
        assert not intent.is_revision(no), no


def test_text_tool_calls_become_real_calls() -> None:
    from tontolo.agent.tools import extract_text_tool_calls

    text = ('Je détaille avec les sources\n<tool_call>web_search\n<arg_key>query</arg_key>\n'
            '<arg_value>Einstein letter to Born 1926</arg_value>\n</tool_call>\n'
            '<tool_call>inconnu\n<arg_key>x</arg_key><arg_value>1</arg_value></tool_call>\n'
            '<tool_call>{"name": "calculator", "arguments": {"expression": "2+2"}}</tool_call>\n'
            '<tool_call>web_search\n<arg_key>query</arg_key><arg_value>tronqué')
    clean, calls = extract_text_tool_calls(text, {"web_search", "calculator"})
    assert clean == "Je détaille avec les sources" and "<" not in clean
    assert [c["function"]["name"] for c in calls] == ["web_search", "calculator", "web_search"]
    assert json.loads(calls[0]["function"]["arguments"]) == {
        "query": "Einstein letter to Born 1926"}
    assert extract_text_tool_calls("Bonjour", {"web_search"}) == ("Bonjour", [])
