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


def test_book_requests_without_creation_verb() -> None:
    for yes in ("Je veux un livre de 200 pages sur Madagascar", "peux-tu me faire un roman",
                "J'ai besoin d'un livre de 100 pages", "I need a book of 150 pages",
                "tiako ny boky 100 pejy momba an'i Madagasikara"):
        assert intent.detect(yes) == "book", yes
    for no in ("je voudrais lire un livre", "conseille-moi un livre",
               "quel est le meilleur livre ?", "explique ce livre",
               "j'ai besoin d'un livre de poche pour le voyage à lire"):
        assert intent.detect(no) is None, no


async def test_chapters_are_kept_as_they_arrive(monkeypatch: pytest.MonkeyPatch) -> None:
    kept: list[tuple[str, str, str]] = []

    async def compile_pdf(source: str) -> tuple[bytes, str, str]:
        return b"%PDF", "", "local"

    monkeypatch.setattr(latex, "compile_pdf", compile_pdf)
    w = Writer(4)
    out = Output(b"", "", "", "", "", "")
    creator = Creator(w.ask)
    # le chapitre 2 de Writer contient \oops : le test de compilation simulé l'accepte ici
    async for _ in creator.run("book", "livre de 30 pages", out=out,
                               store=lambda k, t, c: kept.append((k, t, c))):
        pass
    titles = [t for _, t, _ in kept]
    assert titles[0].startswith("Plan du livre")
    assert sum(t.startswith("Chapitre") for t in titles) == 4
    assert all(k == "part" for k, _, _ in kept)


async def test_slow_chapter_is_retried_then_replaced(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(book, "CHAPTER_DEADLINE", 0.05)
    monkeypatch.setattr(book, "CHAPTER_TRIES", 2)

    async def compile_pdf(source: str) -> tuple[bytes, str, str]:
        return b"%PDF", "", "local"

    monkeypatch.setattr(latex, "compile_pdf", compile_pdf)
    w = Writer(4)
    plain = w.ask
    attempts: dict[str, int] = {}

    async def hanging(messages: list[dict[str, Any]], **kw: Any) -> tuple[str, str, str]:
        system = str(messages[0]["content"])
        if "chapitre 3 sur" in system:
            attempts["3"] = attempts.get("3", 0) + 1
            try:
                await asyncio.sleep(3600)  # fournisseur muet
            except asyncio.CancelledError:
                await asyncio.sleep(3600)  # … qui ignore même l'annulation
        return await plain(messages, **kw)

    out = Output(b"", "", "", "", "", "")
    async for _ in Creator(hanging).run("book", "livre de 30 pages", out=out):
        pass
    assert attempts["3"] == 2 and out.data == b"%PDF"  # deux essais, puis le livre est livré
    assert "n'a pas pu être rédigé" in out.source and "Partie 3" in out.source
