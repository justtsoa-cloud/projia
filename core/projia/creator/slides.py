"""Présentations Beamer longues (« un Beamer du livre joint, avec illustrations, exemples,
code ») : comme pour un livre, une seule réponse de modèle gratuit est trop longue et trop
fragile. On procède par sections :

1. plan : titre et 4 à 8 sections, à partir de la demande et de la fiche du document ;
2. sections rédigées en parallèle (3 à la fois), chacune 3 à 5 diapositives détaillées ;
3. assemblage dans un préambule FIXE et sûr (thème, listings, TikZ), compilation réelle ;
4. erreur de compilation : seule la section fautive est corrigée ; en dernier recours elle est
   simplifiée (texte gardé) plutôt que de perdre toute la présentation.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import re
from collections.abc import AsyncIterator, Callable
from typing import Any

from projia.catalog.models import Category
from projia.creator import latex
from projia.creator.book import failing_chapter, latex_escape
from projia.creator.errors import CreationError

PARALLEL = 3
SECTION_DEADLINE = 300
SECTION_TRIES = 2
MAX_FIXES = 6          # corrections par un modèle, en tout
FIXES_PER_SECTION = 1  # puis la section est simplifiée
FIX_BUDGET = 300       # secondes de corrections ; au-delà, simplification directe

OUTLINE_PROMPT = """Tu prépares le plan d'une présentation Beamer en {language}. Réponds \
UNIQUEMENT en JSON : {{"title": "titre", "sections": [{{"title": "titre de section", \
"summary": "ce que montrent ses diapositives (notions, exemples, code, schémas)"}}]}}. \
4 à 8 sections qui suivent fidèlement le document fourni et la demande."""

SECTION_PROMPT = """Tu écris UNE section d'une présentation Beamer en {language} : « {section} » \
(section {i} sur {n} de « {title} »). Plan complet :
{outline}

Réponds UNIQUEMENT avec le code LaTeX de cette section : \\section{{{section}}} puis 3 à 5 \
diapositives \\begin{{frame}}{{titre}} … \\end{{frame}} DÉTAILLÉES : définitions, exemples \
concrets, schémas en TikZ, blocs block / exampleblock / alertblock, et du code dans \
lstlisting (la frame doit alors être \\begin{{frame}}[fragile]). Pas de préambule, pas de \
\\documentclass, pas de \\begin{{document}}, pas d'image externe ni de \\input. Appuie-toi sur \
le document fourni (ses notions, ses exemples, son code)."""

FIX_PROMPT = """Cette section Beamer ne compile pas. Erreur :
{error}

Corrige-la et renvoie UNIQUEMENT la section complète corrigée (même contenu)."""

_DENY = re.compile(r"\\(input|include|includegraphics|openin|read|readline|InputIfFileExists|"
                   r"verbatiminput|lstinputlisting|directlua|luaexec|write18|immediate|"
                   r"openout|write|catcode|@@input)(?![A-Za-z])[^\n]*")


# Accents dans le code (listings ne lit pas l'UTF-8 seul : « Invalid UTF-8 byte sequence »).
_LITERATE = "".join(
    f"{{{c}}}{{{{{t}}}}}1 " for c, t in [
        ("é", "\\'e"), ("è", "\\`e"), ("ê", "\\^e"), ("ë", '\\"e'), ("à", "\\`a"),
        ("â", "\\^a"), ("î", "\\^i"), ("ï", '\\"i'), ("ô", "\\^o"), ("ù", "\\`u"),
        ("û", "\\^u"), ("ü", '\\"u'), ("ç", "\\c c"), ("É", "\\'E"), ("È", "\\`E"),
        ("À", "\\`A"), ("Ç", "\\c C"), ("œ", "\\oe{}"), ("«", "\\guillemotleft{}"),
        ("»", "\\guillemotright{}"), ("’", "'"), ("…", "..."), ("°", "\\textdegree{}"),
    ]).strip()


def preamble(title: str, language: str) -> str:
    babel = {"en": "english"}.get(language, "french")
    return ("\\documentclass[aspectratio=169]{beamer}\n\\usetheme{Madrid}\n"
            "\\usepackage[utf8]{inputenc}\n\\usepackage[T1]{fontenc}\n\\usepackage{lmodern}\n"
            f"\\usepackage[{babel}]{{babel}}\n\\usepackage{{amsmath,amssymb}}\n"
            "\\usepackage{booktabs}\n\\usepackage{tikz}\n"
            "\\usetikzlibrary{arrows.meta,positioning,shapes}\n\\usepackage{listings}\n"
            "\\lstset{basicstyle=\\ttfamily\\scriptsize,breaklines=true,frame=single,"
            "columns=fullflexible,keepspaces=true,extendedchars=true,literate=" + _LITERATE
            + "}\n"
            f"\\title{{{latex_escape(title)}}}\n\\author{{}}\n\\date{{}}\n")


def clean_section(text: str, title: str) -> str:
    """Section sûre : sans préambule ni fichiers, frames de code marquées [fragile]."""
    body = re.sub(r"^```[\w-]*\n|```\s*$", "", (text or "").strip(), flags=re.M)
    body = re.sub(r"\\documentclass.*?\\begin\{document\}", "", body, flags=re.S)
    body = re.sub(r"\\(usepackage|documentclass|usetheme|usetikzlibrary)(\[[^\]]*\])?"
                  r"\{[^}]*\}", "", body)
    body = re.sub(r"\\(end|begin)\{document\}|\\maketitle|\\tableofcontents|\\titlepage", "",
                  body)
    body = _DENY.sub("", body)

    # Blocs de code mis de côté : leur contenu (souvent du LaTeX : « \end{frame} »…) ne doit
    # ni couper une diapositive ni tromper l'analyse. Beamer cherche « \end{frame} » même dans
    # un listing : on y glisse une espace invisible à l'œil.
    blocks: list[str] = []

    def protect(m: re.Match[str]) -> str:
        inner = re.sub(r"\\(begin|end)\{frame\}", r"\\\1 {frame}", m.group(0)[1:-1])
        blocks.append(m.group(0)[0] + inner + m.group(0)[-1])
        return f"@@CODE{len(blocks) - 1}@@"

    body = re.sub(r"\\begin\{(lstlisting|verbatim|Verbatim)\}.*?\\end\{\1\}",
                  lambda m: protect(m), body, flags=re.S)

    def fragile(m: re.Match[str]) -> str:
        opts, inner = m.group(1) or "", m.group(2)
        # \verb, lstlisting, verbatim : interdits dans une frame ordinaire (« Missing } »).
        if (re.search(r"@@CODE\d+@@|\\verb\W|\\lstinline\W", inner)
                and "fragile" not in opts):
            opts = f"[{opts[1:-1]},fragile]" if opts else "[fragile]"
        return f"\\begin{{frame}}{opts}{inner}\\end{{frame}}"

    body = re.sub(r"\\begin\{frame\}(\[[^\]]*\])?(.*?)\\end\{frame\}", fragile, body, flags=re.S)
    body = re.sub(r"@@CODE(\d+)@@", lambda m: blocks[int(m.group(1))], body)
    if "\\section" not in body:
        body = f"\\section{{{latex_escape(title)}}}\n{body}"
    return body.strip() + "\n"


def plain_section(body: str, title: str) -> str:
    """Dernier recours : le texte de la section, sans commande, en diapositives simples."""
    text = re.sub(r"\\begin\{(lstlisting|verbatim|tikzpicture)\}.*?\\end\{\1\}", " ", body,
                  flags=re.S)
    # Titres de diapositives et de blocs gardés comme repères ; environnements retirés.
    text = re.sub(r"\\begin\{(?:frame|block|exampleblock|alertblock)\}(?:\[[^\]]*\])?"
                  r"\{([^{}]*)\}", r" \1 : ", text)
    text = re.sub(r"\\(?:begin|end)\{[^{}]*\}(?:\[[^\]]*\])?(?:\{[^{}]*\})?", " ", text)
    text = re.sub(r"\\(?:frametitle|section|subsection)\*?\{([^{}]*)\}", r" \1 : ", text)
    text = re.sub(r"\\item\b", " • ", text)
    for _ in range(3):
        text = re.sub(r"\\[A-Za-z]+\*?(?:\[[^\]]*\])?\{([^{}]*)\}", r"\1", text)
    text = re.sub(r"\\[A-Za-z]+\*?|[{}$&%#_^~\\]", " ", text)  # aucune commande ne reste
    words = text.split()
    chunks = [" ".join(words[i:i + 70]) for i in range(0, min(len(words), 280), 70)]
    frames = "".join(f"\\begin{{frame}}{{{latex_escape(title)}}}\n{latex_escape(c)}\n"
                     "\\end{frame}\n" for c in chunks if c)
    return f"\\section{{{latex_escape(title)}}}\n" + (frames or "")


def assemble(title: str, sections: list[str], language: str) -> tuple[str, list[int]]:
    head = (preamble(title, language) + "\\begin{document}\n\\begin{frame}\n\\titlepage\n"
            "\\end{frame}\n\\begin{frame}{\\contentsname}\n\\tableofcontents\n\\end{frame}\n")
    starts, lines = [], head.count("\n") + 1
    parts = [head]
    for sec in sections:
        starts.append(lines)
        parts.append(sec)
        lines += sec.count("\n")
    parts.append("\\end{document}\n")
    return "".join(parts), starts


class SlidesWriter:
    def __init__(self, ask: Callable[..., Any], language: str = "fr",
                 store: Callable[[str, str, str], Any] | None = None) -> None:
        self.ask = ask
        self.store = store
        self.language = {"en": "anglais", "mg": "malgache"}.get(language, "français")
        self.lang_code = language

    def _keep(self, title: str, content: str) -> None:
        if self.store is not None:  # le rangement ne bloque jamais la présentation
            with contextlib.suppress(Exception):
                self.store("part", title, content)

    async def _compiles(self, title: str, section: str) -> bool:
        try:
            await latex.compile_pdf(assemble(title, [section], self.lang_code)[0])
        except latex.LatexError:
            return False
        return True

    async def _find_failing(self, title: str, sections: list[str]) -> int | None:
        """Section qui empêche la compilation, trouvée en compilant chacune seule."""
        for i, sec in enumerate(sections):
            source, _ = assemble(title, [sec], self.lang_code)
            try:
                await latex.compile_pdf(source)
            except latex.LatexError as exc:
                if exc.retryable:
                    return None
                return i
        return None

    async def _outline(self, request: str, context: str) -> dict[str, Any]:
        msgs = [{"role": "system", "content": OUTLINE_PROMPT.format(language=self.language)},
                {"role": "user", "content": request[:4000] + (
                    f"\n\nDocument et contexte :\n{context[:16000]}" if context else "")}]
        for _ in range(2):
            text, _, _ = await self.ask(msgs, category=Category.REASONING)
            m = re.search(r"\{.*\}", text or "", re.S)
            try:
                data = json.loads(m.group(0)) if m else {}
            except ValueError:
                data = {}
            sections = [{"title": str(s.get("title") or "").strip()[:100],
                         "summary": str(s.get("summary") or "").strip()[:400]}
                        for s in data.get("sections") or [] if isinstance(s, dict)]
            sections = [s for s in sections if s["title"]][:8]
            if len(sections) >= 3:
                return {"title": str(data.get("title") or "Présentation").strip()[:150],
                        "sections": sections}
        raise CreationError("le plan de la présentation n'a pas pu être établi")

    async def run(self, request: str, *, context: str = "", out: dict[str, Any]
                  ) -> AsyncIterator[dict[str, Any]]:
        yield {"type": "step", "step": "slides_outline"}
        plan = await self._outline(request, context)
        title, secs = plan["title"], plan["sections"]
        outline = "\n".join(f"{i + 1}. {s['title']} — {s['summary']}" for i, s in enumerate(secs))
        self._keep(f"Plan — {title}", outline)
        sections = [""] * len(secs)
        models: list[str] = []
        failed: list[int] = []
        sem = asyncio.Semaphore(PARALLEL)

        async def write(i: int, sec: dict[str, str]) -> None:
            async with sem:
                for _ in range(SECTION_TRIES):
                    call = asyncio.ensure_future(self.ask([
                        {"role": "system", "content": SECTION_PROMPT.format(
                            language=self.language, section=sec["title"], i=i + 1, n=len(secs),
                            title=title, outline=outline)},
                        {"role": "user", "content": f"Demande : {request[:2000]}\n\nCette "
                                                    f"section : {sec['summary']}\n\nDocument :\n"
                                                    f"{context[:14000]}"}],
                        category=Category.CODE))
                    done, _ = await asyncio.wait({call}, timeout=SECTION_DEADLINE)
                    if not done:
                        call.cancel()
                        continue
                    try:
                        text, key, _ = call.result()
                    except (TimeoutError, CreationError):
                        continue
                    sections[i] = clean_section(text, sec["title"])
                    models.append(key)
                    self._keep(f"Section {i + 1} — {sec['title']}", sections[i])
                    return
                failed.append(i + 1)
                sections[i] = plain_section(sec["summary"], sec["title"])

        tasks = [asyncio.create_task(write(i, s)) for i, s in enumerate(secs)]
        try:
            for n, fut in enumerate(asyncio.as_completed(tasks), 1):
                await fut
                yield {"type": "step", "step": "slides_section", "n": n, "total": len(tasks)}
        finally:
            for t in tasks:
                t.cancel()
        if len(failed) > len(secs) // 2:
            raise CreationError("les modèles gratuits ont trop tardé : réessayez plus tard")

        fixes = 0
        loop = asyncio.get_running_loop()
        fix_deadline = loop.time() + FIX_BUDGET  # la présentation sort à temps, quitte à simplifier
        tried: dict[int, int] = {}
        simplified: set[int] = set()
        while True:
            yield {"type": "step", "step": "doc_building"}
            source, starts = assemble(title, sections, self.lang_code)
            try:
                pdf, _log, _ = await latex.compile_pdf(source)
                break
            except latex.LatexError as exc:
                if exc.retryable:
                    raise
                idx = failing_chapter(exc.log or str(exc), starts, sections)
                # Le numéro de ligne peut venir du fichier .vrb d'une frame fragile (et accuser
                # la mauvaise section) : la section accusée est vérifiée seule.
                if idx is None or await self._compiles(title, sections[idx]):
                    idx = await self._find_failing(title, sections)
                if idx is None:
                    raise
                if (fixes >= MAX_FIXES or tried.get(idx, 0) >= FIXES_PER_SECTION
                        or idx in simplified or loop.time() > fix_deadline):
                    if idx in simplified:
                        raise
                    simplified.add(idx)
                    sections[idx] = plain_section(sections[idx], secs[idx]["title"])
                    failed.append(idx + 1)
                    continue
                fixes += 1
                tried[idx] = tried.get(idx, 0) + 1
                yield {"type": "step", "step": "doc_fixing", "n": fixes}
                text, _, _ = await self.ask([
                    {"role": "system", "content": "Tu corriges une section LaTeX Beamer."},
                    {"role": "user", "content": sections[idx][:20000] + "\n\n" + FIX_PROMPT.format(
                        error=(exc.log or str(exc))[:3000])}], category=Category.CODE)
                sections[idx] = clean_section(text, secs[idx]["title"])
        out.update(title=title, pdf=pdf, source=source, models=models, fixes=fixes,
                   failed=sorted(failed))
