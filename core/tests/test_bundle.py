"""Projets de plusieurs fichiers livrés en .zip (livre LaTeX en chapitres, code…)."""

from __future__ import annotations

import io
import zipfile

import pytest

from tontolo.creator import bundle, intent, latex
from tontolo.creator.pipeline import CreationError, Creator, Output

BOOK = """=== FICHIER: main.tex ===
\\documentclass{book}
\\title{Algèbre}
\\begin{document}
\\maketitle
\\include{chapitres/ch1}
\\input{chapitres/ch2.tex}
\\end{document}
=== FICHIER: chapitres/ch1.tex ===
\\chapter{Groupes} Texte.
=== FICHIER: chapitres/ch2.tex ===
```latex
\\chapter{Anneaux} Texte.
```
=== FICHIER: README.md ===
# Algèbre
"""


def test_parse_and_paths() -> None:
    files = bundle.parse(BOOK)
    assert list(files) == ["main.tex", "chapitres/ch1.tex", "chapitres/ch2.tex", "README.md"]
    assert files["chapitres/ch2.tex"].startswith("\\chapter{Anneaux}")  # bloc de code retiré
    for bad in ("../x.tex", "/etc/passwd", "a/../../b", "a\\..\\b", ""):
        with pytest.raises(bundle.BundleError):
            bundle.safe_path(bad)
    with pytest.raises(bundle.BundleError):
        bundle.parse("pas de fichiers ici")


def test_inline_tex() -> None:
    files = bundle.parse(BOOK)
    full, missing = bundle.inline_tex(files, bundle.main_tex(files) or "")
    assert missing == [] and "Groupes" in full and "Anneaux" in full and "\\input" not in full
    files["main.tex"] += "\\input{absent}"
    assert bundle.inline_tex(files, "main.tex")[1] == ["absent"]


def test_detects_multi_file_requests() -> None:
    assert intent.detect("écris un livre en latex structuré en plusieurs fichiers") == "bundle"
    assert intent.detect("donne-moi le projet en zip") == "bundle"
    assert intent.detect("crée un livre latex avec un fichier par chapitre") == "bundle"
    assert intent.detect("explique ce zip") is None
    assert intent.detect("génère un pdf sur les fractions") == "pdf"


class Writer:
    def __init__(self, answers: list[str]) -> None:
        self.answers = answers
        self.calls: list[str] = []

    async def ask(self, messages: list, *, category: object = None,
                  model: str | None = None) -> tuple[str, str, str]:
        self.calls.append(str(messages[-1]["content"]))
        return self.answers.pop(0), "w:m", "Rédacteur"


async def _run(answers: list[str]) -> tuple[Output, Writer]:
    w = Writer(answers)
    out = Output(b"", "", "", "", "", "")
    async for _ in Creator(w.ask).run("bundle", "projet en plusieurs fichiers", out=out):
        pass
    return out, w


async def test_latex_book_zip_with_pdf(monkeypatch: pytest.MonkeyPatch) -> None:
    compiled: list[str] = []

    async def fake_compile(source: str) -> tuple[bytes, str, str]:
        compiled.append(source)
        return b"%PDF-1.7 livre", "", "local"

    monkeypatch.setattr(latex, "compile_pdf", fake_compile)
    out, _ = await _run([BOOK])
    assert out.mime == "application/zip" and out.filename == "algèbre.zip"
    z = zipfile.ZipFile(io.BytesIO(out.data))
    assert sorted(z.namelist()) == ["README.md", "chapitres/ch1.tex", "chapitres/ch2.tex",
                                    "main.pdf", "main.tex"]
    assert z.read("main.pdf") == b"%PDF-1.7 livre" and "Groupes" in compiled[0]
    assert "5 fichiers" in out.title


async def test_errors_are_sent_back_then_fixed() -> None:
    bad = "=== FICHIER: data.json ===\n{oops\n=== FICHIER: app.py ===\nprint('ok')\n"
    good = bad.replace("{oops", '{"ok": true}')
    out, w = await _run([bad, good])
    assert "data.json" in w.calls[1] and zipfile.ZipFile(io.BytesIO(out.data)).namelist() == [
        "data.json", "app.py"]


async def test_unsafe_project_is_never_delivered() -> None:
    with pytest.raises(CreationError):
        await _run(["=== FICHIER: ../../.bashrc ===\nrm -rf ~\n"] * 5)


def test_whole_answer_in_code_block() -> None:
    files = bundle.parse("```\n=== FICHIER: a.py ===\nx = 1\n=== FICHIER: b.py ===\ny = 2\n```")
    assert files == {"a.py": "x = 1\n", "b.py": "y = 2\n"}
