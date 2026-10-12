"""Livres longs : plan, chapitres en parallèle, compilation, correction du seul chapitre fautif."""

from __future__ import annotations

import asyncio
import io
import json
import zipfile
from typing import Any

import pytest

from tontolo.creator import book, intent, latex
from tontolo.creator.pipeline import Creator, Output


def test_detection_and_size() -> None:
    assert intent.detect("Génère un livre de 200 pages sur l'histoire de Madagascar") == "book"
    assert intent.detect("rédige un rapport de 30 pages") == "book"
    assert intent.detect("génère un pdf de 2 pages") == "pdf"
    assert intent.detect("quel est le meilleur livre ?") is None
    assert book.target_pages("un livre de 200 pages") == 200
    assert book.target_pages("un livre de 5000 pages") == book.MAX_PAGES


def test_chapter_is_sanitized() -> None:
    raw = ("```latex\n\\documentclass{book}\\usepackage{x}\\begin{document}\n"
           "\\chapter{A}\nTexte \\input{/etc/passwd}\n\\write18{rm}\n\\end{document}\n```")
    out = book.clean_chapter(raw, "A")
    for bad in ("documentclass", "usepackage", "input", "write18", "end{document}", "```"):
        assert bad not in out
    assert out.startswith("\\chapter{A}")
    assert book.clean_chapter("Texte seul", "Titre & co").startswith("\\chapter{Titre \\& co}")


class Writer:
    def __init__(self, n: int) -> None:
        self.n = n
        self.calls: list[str] = []
        self.active = 0
        self.peak = 0

    async def ask(self, messages: list[dict[str, Any]], *, category: Any = None,
                  model: str | None = None) -> tuple[str, str, str]:
        system = str(messages[0]["content"])
        self.calls.append(system[:40])
        if "éditeur d'un livre" in system:
            return json.dumps({"title": "Histoire de Madagascar", "chapters": [
                {"title": f"Partie {i}", "summary": "…"}
                for i in range(1, self.n + 1)]}), "m:0", "M"
        if "Tu corriges" in system:
            return "\\chapter{Partie 2}\nCorrigé.", "m:fix", "M"
        self.active += 1
        self.peak = max(self.peak, self.active)
        await asyncio.sleep(0.01)
        self.active -= 1
        num = system.split("chapitre ")[1].split(" ")[0]
        body = "\\oops" if num == "2" else "Texte."
        return f"\\chapter{{Partie {num}}}\n{body}", f"m:{num}", "M"


async def _run(kind: str, request: str, monkeypatch: pytest.MonkeyPatch,
               w: Writer) -> tuple[Output, list[dict[str, Any]], list[str]]:
    compiled: list[str] = []

    async def compile_pdf(source: str) -> tuple[bytes, str, str]:
        compiled.append(source)
        if "\\oops" in source:
            line = source[:source.index("\\oops")].count("\n") + 1
            raise latex.LatexError("erreur", f"! Undefined control sequence.\nl.{line} \\oops")
        return b"%PDF-1.7 livre", "", "local"

    monkeypatch.setattr(latex, "compile_pdf", compile_pdf)
    out = Output(b"", "", "", "", "", "")
    events = [ev async for ev in Creator(w.ask).run(kind, request, out=out)]
    return out, events, compiled


async def test_book_pdf(monkeypatch: pytest.MonkeyPatch) -> None:
    w = Writer(20)
    out, events, compiled = await _run("book", "Génère un livre de 200 pages", monkeypatch, w)
    assert out.mime == "application/pdf" and out.data == b"%PDF-1.7 livre"
    progress = [e for e in events if e.get("step") == "book_chapter"]
    assert [e["n"] for e in progress] == list(range(1, 21)) and progress[-1]["total"] == 20
    assert 1 < w.peak <= book.PARALLEL  # en parallèle, mais pas tous à la fois
    assert len(compiled) == 2 and "Corrigé." in compiled[-1]  # seul le chapitre 2 corrigé
    assert sum("Tu corriges" in c for c in w.calls) == 1
    assert compiled[-1].count("\\chapter{Partie") == 20 and "\\tableofcontents" in compiled[-1]


async def test_book_as_zip(monkeypatch: pytest.MonkeyPatch) -> None:
    out, _, _ = await _run("bundle", "écris un livre en latex en plusieurs fichiers",
                           monkeypatch, Writer(4))
    z = zipfile.ZipFile(io.BytesIO(out.data))
    names = sorted(z.namelist())
    assert names == ["README.md", "chapitres/ch01.tex", "chapitres/ch02.tex",
                     "chapitres/ch03.tex", "chapitres/ch04.tex", "main.pdf", "main.tex"]
    main = z.read("main.tex").decode()
    assert "\\input{chapitres/ch03}" in main and "Partie 3" not in main
