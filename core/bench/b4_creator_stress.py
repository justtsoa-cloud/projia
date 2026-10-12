"""E1d — créations en masse : fichiers Word/Excel/PowerPoint/texte en parallèle, livre de
120 chapitres, projet multi-fichiers de 60 fichiers (modèles et compilation simulés)."""

import asyncio
import json
import sys

from bench.harness import Timer, rss_mb
from tontolo.creator import latex
from tontolo.creator.pipeline import Creator, Output

N = int(sys.argv[1]) if len(sys.argv) > 1 else 30


async def fake_compile(source: str):
    await asyncio.sleep(0.05)
    return b"%PDF-1.7 " + b"x" * (len(source) // 4), "", "local"


latex.compile_pdf = fake_compile  # type: ignore[assignment]


class Writer:
    def __init__(self, chapters: int = 3) -> None:
        self.chapters = chapters
        self.calls = 0

    async def ask(self, messages, *, category=None, model=None):
        self.calls += 1
        await asyncio.sleep(0.01)
        system = str(messages[0]["content"])
        if "éditeur d'un livre" in system:
            return json.dumps({"title": "Grand livre", "chapters": [
                {"title": f"Chapitre {i}", "summary": "…"}
                for i in range(1, self.chapters + 1)]}), "m:0", "M"
        if "chapitre " in system and "Tu écris le chapitre" in system:
            return "\\chapter{X}\n" + ("Paragraphe de test. " * 300), "m:1", "M"
        if "XLSX" in system or "classeur Excel" in system:
            return json.dumps({"sheets": [{"name": "Notes", "rows": [["a", "b"], [1, 2]]}]}), "m", "M"
        if "présentation" in system:
            return "# Titre\n- sous-titre\n## Diapo 1\n- point\n- point\n", "m", "M"
        if "document Word" in system:
            return "# Titre\n## Partie\nTexte " * 50, "m", "M"
        if "PLUSIEURS fichiers" in system:
            return "".join(f"=== FICHIER: src/mod{i:02d}.py ===\nx = {i}\n" for i in range(60)), "m", "M"
        return "contenu", "m", "M"


async def one(kind: str, request: str, language: str = "fr") -> Output:
    out = Output(b"", "", "", "", "", "")
    w = Writer(120 if kind == "book" else 3)
    async for _ in Creator(w.ask, None, w.ask).run(kind, request, out=out, language=language):
        pass
    return out


async def main() -> None:
    t = Timer()
    with t(f"{N} créations en parallèle (docx, xlsx, pptx)"):
        kinds = ["docx", "xlsx", "pptx"]
        outs = await asyncio.gather(*[one(kinds[i % 3], "demande") for i in range(N)])
    print(f"  tailles : {[len(o.data) for o in outs[:6]]} ; RSS {rss_mb():.0f} Mo")
    with t("livre de 120 chapitres (400 pages), 3 en parallèle"):
        book = await one("book", "Génère un livre de 840 pages")
    print(f"  PDF {len(book.data) // 1024} Ko ; sources {len(book.source) // 1024} Ko")
    with t("projet multi-fichiers : 60 fichiers dans un zip"):
        proj = await one("bundle", "projet python en plusieurs fichiers")
    print(f"  zip {len(proj.data)} o ; {proj.title}")
    with t("10 livres de 40 chapitres simultanés"):
        class W2(Writer):
            pass
        outs = []

        async def small_book() -> Output:
            out = Output(b"", "", "", "", "", "")
            w = Writer(40)
            async for _ in Creator(w.ask, None, w.ask).run("book", "livre de 280 pages", out=out):
                pass
            return out

        outs = await asyncio.gather(*[small_book() for _ in range(10)])
    print(f"  {len(outs)} livres ; RSS {rss_mb():.0f} Mo")
    t.report()


asyncio.run(main())
