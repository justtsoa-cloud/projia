"""Livres et longs documents (« génère un livre de 200 pages ») : une seule réponse de modèle
ne peut pas les contenir. On procède comme un éditeur :

1. plan : titre et chapitres (environ un chapitre pour 10 pages) ;
2. chapitres rédigés en parallèle (3 à la fois, le routeur répartit sur plusieurs modèles
   gratuits), chacun en LaTeX, avec la suite demandée automatiquement s'il est coupé ;
3. assemblage dans un préambule fixe et sûr, compilation réelle ;
4. erreur de compilation : la ligne fautive est rattachée à SON chapitre, seul ce chapitre est
   corrigé (3 tours au plus).
Livré en PDF, ou en archive .zip (sources par chapitre + PDF) si plusieurs fichiers ont été
demandés.
"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import AsyncIterator, Callable
from typing import Any

from tontolo.catalog.models import Category
from tontolo.creator import bundle, latex

MAX_PAGES = 300
PAGES_PER_CHAPTER = 10
WORDS_PER_PAGE = 400
PARALLEL = 3
MAX_FIXES = 3

_PAGES = re.compile(r"(\d{1,4})\s*(?:pages?|p\.|pejy)\b", re.I)
_BOOKISH = re.compile(r"\b(livre|book|roman|novel|manuel|e-?book|ouvrage|bouquin|boky|"
                      r"polycopi[ée]|th[èe]se|m[ée]moire de fin)\b", re.I)

OUTLINE_PROMPT = """Tu es l'éditeur d'un livre. Réponds UNIQUEMENT en JSON :
{{"title": "titre du livre", "chapters": [{{"title": "titre du chapitre", "summary": "ce \
que couvre le chapitre, 2 phrases"}}]}}
Exactement {n} chapitres, dans un ordre logique et progressif, sans recouvrement. Langue : \
{language}."""

CHAPTER_PROMPT = """Tu écris le chapitre {i} sur {n} du livre « {title} », en {language}. \
Réponds UNIQUEMENT avec le corps LaTeX du chapitre, qui commence par \\chapter{{{chapter}}} : \
sections (\\section), paragraphes rédigés et développés, listes, exemples, formules \
($…$), encadrés tcolorbox avec un titre si utile, tableaux booktabs. Environ {words} mots. \
Interdit : \\documentclass, \\usepackage, \\begin{{document}}, \\input, \\include, images \
externes. Ne répète pas les autres chapitres ; reste cohérent avec le plan :
{outline}"""

FIX_PROMPT = """La compilation LaTeX échoue dans ce chapitre :
{error}

Corrige le chapitre et renvoie-le EN ENTIER (corps LaTeX seulement, sans explication)."""


def wants_book(text: str) -> bool:
    t = text or ""
    m = _PAGES.search(t)
    return bool(_BOOKISH.search(t)) or bool(m and int(m.group(1)) >= 20)


def target_pages(text: str) -> int:
    m = _PAGES.search(text or "")
    pages = int(m.group(1)) if m else 40
    return max(10, min(pages, MAX_PAGES))


def preamble(title: str, language: str) -> str:
    babel = {"en": "english"}.get(language, "french")
    safe = latex_escape(title)
    return ("\\documentclass[11pt]{book}\n\\usepackage[utf8]{inputenc}\n\\usepackage[T1]{fontenc}\n"
            "\\usepackage{lmodern}\n\\usepackage[" + babel + "]{babel}\n"
            "\\usepackage[a4paper,margin=2.3cm]{geometry}\n\\usepackage{amsmath,amssymb}\n"
            "\\usepackage{xcolor}\n\\usepackage{booktabs}\n\\usepackage{enumitem}\n"
            "\\usepackage[most]{tcolorbox}\n\\usepackage{hyperref}\n"
            f"\\title{{{safe}}}\n\\author{{}}\n\\date{{}}\n")


def latex_escape(text: str) -> str:
    return re.sub(r"([#$%&_{}])", r"\\\1", text).replace("~", "").replace("^", "")


def clean_chapter(text: str, title: str) -> str:
    """Corps de chapitre sûr : pas de préambule, pas d'inclusion ni d'écriture de fichier."""
    body = re.sub(r"^```[\w-]*\n|```\s*$", "", (text or "").strip(), flags=re.M)
    body = re.sub(r"\\documentclass.*?\\begin\{document\}", "", body, flags=re.S)
    body = re.sub(r"\\(usepackage|documentclass)(\[[^\]]*\])?\{[^}]*\}", "", body)
    body = re.sub(r"\\(end|begin)\{document\}|\\maketitle|\\tableofcontents", "", body)
    body = re.sub(r"\\(input|include|includegraphics|write18|immediate|openout)\b[^\n]*", "",
                  body)
    if "\\chapter" not in body:
        body = f"\\chapter{{{latex_escape(title)}}}\n{body}"
    return body.strip() + "\n"


def assemble(title: str, chapters: list[str], language: str) -> tuple[str, list[int]]:
    """Source complet et ligne de début de chaque chapitre (pour situer une erreur)."""
    head = preamble(title, language) + "\\begin{document}\n\\maketitle\n\\tableofcontents\n"
    starts, lines = [], head.count("\n") + 1
    parts = [head]
    for ch in chapters:
        starts.append(lines)
        parts.append(ch)
        lines += ch.count("\n")
    parts.append("\\end{document}\n")
    return "".join(parts), starts


def failing_chapter(log: str, starts: list[int]) -> int | None:
    m = re.search(r"\bl\.(\d+)\b", log) or re.search(r"\.tex:(\d+):", log)
    if not m or not starts:
        return None
    line = int(m.group(1))
    idx = None
    for i, s in enumerate(starts):
        if line >= s:
            idx = i
    return idx


class BookWriter:
    def __init__(self, ask: Callable[..., Any], language: str = "fr") -> None:
        self.ask = ask
        self.language = {"en": "anglais", "mg": "malgache"}.get(language, "français")
        self.lang_code = language

    async def run(self, request: str, *, context: str = "", out: dict[str, Any]
                  ) -> AsyncIterator[dict[str, Any]]:
        pages = target_pages(request)
        n = max(3, min(30, round(pages / PAGES_PER_CHAPTER)))
        yield {"type": "step", "step": "book_outline", "n": 0, "total": n}
        plan = await self._outline(request, context, n)
        title = plan["title"]
        outline = "\n".join(f"{i + 1}. {c['title']} — {c['summary']}"
                            for i, c in enumerate(plan["chapters"]))
        words = max(800, pages * WORDS_PER_PAGE // len(plan["chapters"]))
        chapters: list[str] = [""] * len(plan["chapters"])
        models: list[str] = []
        sem = asyncio.Semaphore(PARALLEL)

        async def write(i: int, ch: dict[str, str]) -> None:
            async with sem:
                text, key, _ = await self.ask([
                    {"role": "system", "content": CHAPTER_PROMPT.format(
                        i=i + 1, n=len(plan["chapters"]), title=title, language=self.language,
                        chapter=latex_escape(ch["title"]), words=words, outline=outline)},
                    {"role": "user", "content": f"Demande d'origine : {request[:2000]}\n\n"
                                                f"Écris le chapitre {i + 1} : {ch['title']}."}],
                    category=Category.WRITING)
                chapters[i] = clean_chapter(text, ch["title"])
                models.append(key)

        tasks = [asyncio.create_task(write(i, c)) for i, c in enumerate(plan["chapters"])]
        try:
            for done, fut in enumerate(asyncio.as_completed(tasks), 1):
                await fut  # un chapitre en échec fait échouer le livre (raison affichée)
                yield {"type": "step", "step": "book_chapter", "n": done, "total": len(tasks)}
        finally:
            for t in tasks:
                t.cancel()

        fixes = 0
        while True:
            yield {"type": "step", "step": "doc_building"}
            source, starts = assemble(title, chapters, self.lang_code)
            try:
                pdf, _log, _ = await latex.compile_pdf(source)
                break
            except latex.LatexError as exc:
                if exc.retryable or fixes >= MAX_FIXES:
                    raise
                idx = failing_chapter(exc.log or str(exc), starts)
                if idx is None:
                    raise
                fixes += 1
                yield {"type": "step", "step": "doc_fixing", "n": fixes}
                text, _, _ = await self.ask([
                    {"role": "system", "content": "Tu corriges un chapitre LaTeX."},
                    {"role": "user", "content": chapters[idx][:30000] + "\n\n" + FIX_PROMPT.format(
                        error=(exc.log or str(exc))[:3000])}], category=Category.CODE)
                chapters[idx] = clean_chapter(text, plan["chapters"][idx]["title"])
        out.update(title=title, pdf=pdf, source=source, models=models, fixes=fixes,
                   files={"main.tex": source.replace("".join(chapters), "".join(
                       f"\\input{{chapitres/ch{i + 1:02d}}}\n" for i in range(len(chapters)))),
                       **{f"chapitres/ch{i + 1:02d}.tex": c for i, c in enumerate(chapters)},
                       "README.md": f"# {title}\n\nLivre généré par Tontolo : main.tex (à "
                                    f"compiler avec pdflatex) et un fichier par chapitre ; "
                                    f"main.pdf déjà compilé.\n"})

    async def _outline(self, request: str, context: str, n: int) -> dict[str, Any]:
        msgs: list[dict[str, Any]] = [
            {"role": "system", "content": OUTLINE_PROMPT.format(n=n, language=self.language)},
            {"role": "user", "content": request[:6000] + (f"\n\nContexte :\n{context[:6000]}"
                                                          if context else "")}]
        for _ in range(2):
            text, _, _ = await self.ask(msgs, category=Category.REASONING)
            m = re.search(r"\{.*\}", text or "", re.S)
            try:
                data = json.loads(m.group(0)) if m else {}
            except ValueError:
                data = {}
            chapters = [{"title": str(c.get("title") or "").strip()[:120],
                         "summary": str(c.get("summary") or "").strip()[:400]}
                        for c in data.get("chapters") or [] if isinstance(c, dict)]
            chapters = [c for c in chapters if c["title"]][:30]
            if len(chapters) >= 3:
                return {"title": str(data.get("title") or "Livre").strip()[:150] or "Livre",
                        "chapters": chapters}
        from tontolo.creator.pipeline import CreationError

        raise CreationError("le plan du livre n'a pas pu être établi")


def zip_files(files: dict[str, str], pdf: bytes) -> bytes:
    return bundle.build_zip(files, {"main.pdf": pdf})
