"""Création de fichiers par une **équipe de modèles** : rédaction, vérification, correction.

1. Rédacteur : le meilleur modèle gratuit pour la tâche (choisi par le routeur) écrit le
   source (Markdown pour un DOCX, LaTeX pour un PDF, plan JSON pour une carte mentale).
2. Vérifications automatiques : construction réelle du fichier (compilation LaTeX, rendu du
   schéma, validité du DOCX) et contrôles de mise en page ; chaque problème est renvoyé au
   rédacteur avec le journal d'erreur, jusqu'à MAX_FIXES corrections.
3. Relecteur : un modèle d'une **autre famille** relit le résultat (avec l'image quand il
   sait voir) et liste les défauts de fond ou de forme ; le rédacteur corrige, puis les
   vérifications automatiques repassent avant livraison.
Le fichier n'est livré qu'une fois construit sans erreur. Les étapes sont émises
(`{"type": "step"}`) pour être affichées en direct."""

from __future__ import annotations

import asyncio
import base64
import json
import re
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from typing import Any

from tontolo.catalog.models import Category
from tontolo.creator import charts, diagram, docx, latex, office, textfile

MAX_FIXES = 3
CALL_TIMEOUT = 240     # rédaction ou correction d'un document long par un modèle gratuit
REVIEW_TIMEOUT = 100   # relecture : utile mais jamais bloquante
TOTAL_TIMEOUT = 480    # au-delà, on livre la dernière version construite sans erreur

KINDS = {
    "docx": ("document Word", Category.WRITING),
    "pdf": ("document PDF (LaTeX)", Category.CODE),
    "latex": ("source LaTeX et PDF", Category.CODE),
    "mindmap": ("carte mentale", Category.REASONING),
    "xlsx": ("classeur Excel", Category.REASONING),
    "pptx": ("présentation PowerPoint", Category.WRITING),
    "chart": ("graphique", Category.CODE),
    "diagram": ("schéma", Category.CODE),
}


def kind_info(kind: str) -> tuple[str, Category]:
    if kind in KINDS:
        return KINDS[kind]
    if kind.startswith("text:"):
        ext = kind[5:]
        return (f"fichier .{ext}", Category.CODE if ext in textfile.CODE_EXTS else
                Category.WRITING)
    raise CreationError(f"type inconnu : {kind}")

_LANG = {"fr": "français", "en": "anglais", "mg": "malgache"}

WRITER_PROMPTS = {
    "docx": """Tu rédiges un document Word soigné en {language}. Réponds UNIQUEMENT avec le \
document en Markdown, sans texte avant ni après : commence par « # Titre », puis des sections \
« ## », des paragraphes clairs, des listes, des tableaux Markdown si utile, des formules \
$…$ simples. Contenu complet, exact, bien structuré (introduction, parties, conclusion ou \
résumé). Pas d'images.""",
    "pdf": """Tu écris un document LaTeX complet, compilable directement avec pdflatex, en \
{language}. Réponds UNIQUEMENT avec le source LaTeX (de \\documentclass à \\end{{document}}), \
sans bloc de code ni commentaire autour. Paquets autorisés : inputenc (utf8), fontenc (T1), \
lmodern, babel ({babel}), geometry (marges 2,2 cm), amsmath, amssymb, xcolor, hyperref, \
booktabs, enumitem, titlesec, tcolorbox, tikz. Pas d'image externe ni de \\input. Design \
soigné : titre, titres de sections colorés (bleu 2E3A87), encadrés tcolorbox AVEC un titre \
(title=Définition, Méthode…) pour définitions et méthodes, tableaux booktabs, listes aérées. \
Contenu exact et complet.""",
    "mindmap": """Tu conçois une carte mentale de révision en {language}. Réponds UNIQUEMENT \
avec du JSON : {{"title": "sujet central", "children": [{{"label": "branche", "children": \
[{{"label": "idée", "children": []}}]}}]}}. Règles : 3 à 7 branches principales, 2 à 5 idées \
par branche, 3 niveaux au plus, libellés COURTS (mots-clés, moins de 40 caractères), \
formules en texte simple (a/b, x², √). Couvre l'essentiel du sujet pour réviser : \
définitions, méthodes, exemples, pièges.""",
}
WRITER_PROMPTS["latex"] = WRITER_PROMPTS["pdf"]
WRITER_PROMPTS["xlsx"] = """Tu prépares un classeur Excel en {language}. Réponds UNIQUEMENT \
avec du JSON : {{"sheets": [{{"name": "Feuille", "rows": [["En-tête 1", "En-tête 2"], \
["texte", 12.5]]}}]}}. La première ligne de chaque feuille est l'en-tête ; nombres en nombres \
(pas en texte) ; calculs en formules Excel anglaises (=SUM(B2:B9), =AVERAGE(…), =IF(…)) ; \
toutes les lignes d'une feuille ont le même nombre de cellules ; noms de feuilles courts."""
WRITER_PROMPTS["pptx"] = """Tu prépares une présentation en {language}. Réponds UNIQUEMENT en \
Markdown : « # Titre » (diapositive de couverture, une ligne « - sous-titre »), puis chaque \
diapositive « ## Titre » avec 3 à 6 puces « - » courtes (sous-puces « - » indentées de deux \
espaces si utile) et éventuellement une ligne « > notes de l'orateur ». 6 à 12 diapositives, \
progression claire, conclusion à la fin."""
WRITER_PROMPTS["chart"] = """Tu crées un graphique. Réponds UNIQUEMENT avec la configuration \
Chart.js 4 en JSON strict : {{"type": "bar|line|pie|doughnut|radar|scatter", "data": \
{{"labels": […], "datasets": [{{"label": "…", "data": […]}}]}}, "options": {{"plugins": \
{{"title": {{"display": true, "text": "…"}}}}}}}}. Textes en {language}, données exactes \
(celles de l'utilisateur ou de la discussion), axes nommés si utile. Pas de fonction JavaScript."""
WRITER_PROMPTS["diagram"] = """Tu dessines un schéma avec Mermaid. Réponds UNIQUEMENT avec le \
source Mermaid valide (flowchart TD, sequenceDiagram, timeline, classDiagram, gantt ou \
erDiagram selon la demande), libellés courts en {language} entre guillemets si ils \
contiennent des espaces ou de la ponctuation."""
TEXT_PROMPT = """Tu écris le contenu complet d'un fichier « .{ext} » demandé par \
l'utilisateur, en {language} pour les textes. Réponds UNIQUEMENT avec le contenu du fichier, \
sans explication ni bloc de code autour. Il doit être directement utilisable (syntaxe \
valide, complet, commenté si c'est du code)."""

FIX_PROMPT = """Le fichier n'est pas encore correct. Problèmes détectés :
{problems}

Corrige le source et renvoie-le EN ENTIER, dans le même format, sans explication."""

REVIEW_PROMPT = """Tu es relecteur exigeant. Voici un {what} demandé par un utilisateur \
({request}). Vérifie le fond (exactitude, complétude, adaptation à la demande) et la forme \
(structure, lisibilité, mise en page{visual}). Réponds UNIQUEMENT en JSON : \
{{"ok": true|false, "issues": ["problème précis et corrigeable", …]}} — 0 à 6 problèmes \
importants seulement ; ok = true s'il n'y a rien d'important à corriger."""


class CreationError(Exception):
    pass


@dataclass
class Output:
    data: bytes
    mime: str
    filename: str
    title: str
    source: str
    source_name: str
    steps: list[dict[str, Any]] = field(default_factory=list)
    models: list[str] = field(default_factory=list)


Ask = Callable[..., Any]


def same_model(a: str, b: str) -> bool:
    """Deux clés « fournisseur:modèle » désignent-elles le même modèle (même servi ailleurs) ?"""
    def base(key: str) -> str:
        mid = key.split(":", 1)[-1] if ":" in key else key
        return re.sub(r"[^a-z0-9]", "", mid.lower().split("/")[-1].split(":")[0])
    return bool(a) and bool(b) and base(a) == base(b)


def strip_fences(text: str) -> str:
    """Retire un éventuel bloc ```…``` autour de la réponse du modèle."""
    m = re.search(r"```[a-zA-Z]*\n(.*?)```", text or "", re.S)
    return (m.group(1) if m else text or "").strip()


def slug(title: str) -> str:
    s = re.sub(r"[^\w\s-]", " ", title, flags=re.U).strip().lower()
    return (re.sub(r"[\s_-]+", "-", s)[:50] or "document").strip("-") or "document"


def latex_problems(source: str) -> list[str]:
    """Contrôles avant compilation (erreurs fréquentes des modèles)."""
    problems = []
    if "\\documentclass" not in source:
        problems.append("il manque \\documentclass : renvoie un document complet")
    if "\\begin{document}" not in source or "\\end{document}" not in source:
        problems.append("il manque \\begin{document} ou \\end{document}")
    if re.search(r"\\(input|include|includegraphics)\b", source):
        problems.append("pas de \\input, \\include ni \\includegraphics (aucun fichier externe)")
    if re.search(r"\\write18|\\immediate\\write|\\openout", source):
        problems.append("commandes d'écriture de fichiers interdites")
    return problems


def latex_design(source: str) -> list[str]:
    """Défauts de présentation fréquents (non bloquants, corrigés si possible)."""
    out = []
    boxes = re.findall(r"\\begin\{tcolorbox\}(\[[^\]]*\])?", source)
    if any("title" not in (b or "") for b in boxes):
        out.append("chaque encadré tcolorbox doit avoir un titre visible (option title=…), "
                   "sinon son bandeau coloré est vide")
    return out


def latex_title(source: str) -> str:
    m = re.search(r"\\title\{((?:[^{}]|\{[^{}]*\})*)\}", source)
    raw = m.group(1) if m else "Document"
    raw = re.sub(r"\\(\\|newline|linebreak)", " ", raw)
    raw = re.sub(r"\\[a-zA-Z]+\*?(\[[^\]]*\])?", "", raw)
    return re.sub(r"\s+", " ", raw.replace("{", "").replace("}", "")).strip() or "Document"


class Creator:
    """Orchestration ; `ask(messages, *, category=None, model=None, exclude=())` appelle un
    modèle et renvoie (texte, clé du modèle, nom)."""

    def __init__(self, ask: Ask, pick_reviewer: Callable[..., Any] | None = None) -> None:
        self.ask = ask
        self.pick_reviewer = pick_reviewer

    async def run(self, kind: str, request: str, *, context: str = "", language: str = "fr",
                  out: Output | None = None) -> AsyncIterator[dict[str, Any]]:
        what, category = kind_info(kind)
        lang = _LANG.get(language, "français")
        system = (TEXT_PROMPT.format(ext=kind[5:], language=lang) if kind.startswith("text:")
                  else WRITER_PROMPTS[kind].format(
                      language=lang, babel={"en": "english"}.get(language, "french")))
        user = request if not context else f"{request}\n\nContexte de la discussion :\n{context}"
        messages: list[dict[str, Any]] = [{"role": "system", "content": system},
                                          {"role": "user", "content": user[:12000]}]
        loop = asyncio.get_running_loop()
        deadline = loop.time() + TOTAL_TIMEOUT
        yield {"type": "step", "step": "doc_writing"}
        text, writer, writer_name = await self.ask(messages, category=category)
        steps: list[dict[str, Any]] = [{"step": "doc_writing", "model": writer_name}]
        models = [writer]
        result: Output | None = None
        fixes = 0
        reviewed = False
        while True:
            source = strip_fences(text)
            yield {"type": "step", "step": "doc_building"}
            try:
                built, problems = await self._build(kind, source)
                # Un fichier vide (source refusé avant construction) n'est jamais livrable.
                result = built if built.data else None
            except (latex.LatexError, diagram.DiagramError, charts.ChartError) as exc:
                if getattr(exc, "retryable", False):
                    raise CreationError(f"service de création injoignable : {exc}") from exc
                problems = [str(exc) + (f"\n{exc.log}" if isinstance(exc, latex.LatexError)
                                        and exc.log else "")]
                result = None
            late = loop.time() > deadline - CALL_TIMEOUT / 2
            if not problems and not reviewed and self.pick_reviewer is not None and not late:
                reviewed = True
                yield {"type": "step", "step": "doc_reviewing"}
                issues, reviewer_name, reviewer = await self._review(
                    kind, what, request, source, result, writer)
                if reviewer:
                    steps.append({"step": "doc_reviewing", "model": reviewer_name,
                                  "issues": len(issues)})
                    models.append(reviewer)
                problems = issues
            if not problems and result is not None:
                break
            if fixes >= MAX_FIXES or (late and result is not None):
                if result is not None:
                    break  # construit sans erreur : remarques de relecture restantes tolérées
                raise CreationError("le fichier n'a pas pu être construit sans erreur : "
                                    + "; ".join(p.splitlines()[0] for p in problems)[:300])
            fixes += 1
            yield {"type": "step", "step": "doc_fixing", "n": fixes}
            messages += [{"role": "assistant", "content": text},
                         {"role": "user", "content": FIX_PROMPT.format(
                             problems="\n".join(f"- {p}" for p in problems))}]
            try:
                text, _, _ = await self.ask(messages, model=writer)
            except (TimeoutError, CreationError):
                if result is None:
                    raise
                break  # correction trop lente : la version construite sans erreur est livrée
            steps.append({"step": "doc_fixing", "model": writer_name, "problems": problems[:6]})
        assert result is not None
        result.steps = steps
        result.models = models
        if out is not None:
            out.__dict__.update(result.__dict__)
        yield {"type": "step", "step": "doc_done"}

    async def _build(self, kind: str, source: str) -> tuple[Output, list[str]]:
        if kind == "docx":
            title, _ = docx.markdown_to_body(source)
            if not title:
                return Output(b"", "", "", "", source, ""), [
                    "le document doit commencer par un titre « # … »"]
            data = docx.build(source)
            return Output(data, "application/vnd.openxmlformats-officedocument."
                          "wordprocessingml.document", f"{slug(title)}.docx", title, source,
                          f"{slug(title)}.md"), docx.check(data)
        if kind in ("pdf", "latex"):
            pre = latex_problems(source)
            if pre:
                return Output(b"", "", "", "", source, ""), pre
            pdf, log, _ = await latex.compile_pdf(source)
            title = latex_title(source)
            return Output(pdf, "application/pdf", f"{slug(title)}.pdf", title, source,
                          f"{slug(title)}.tex"), latex.warnings_from_log(log) + latex_design(
                              source)
        if kind == "xlsx":
            try:
                sheets = office.parse_sheets(source)
            except (ValueError, RecursionError) as exc:
                return Output(b"", "", "", "", source, ""), [f"JSON invalide : {exc}"]
            problems = office.xlsx_problems(sheets)
            title = str(sheets[0].get("name") or "Classeur")
            return Output(office.build_xlsx(sheets), "application/vnd.openxmlformats-"
                          "officedocument.spreadsheetml.sheet", f"{slug(title)}.xlsx", title,
                          source, f"{slug(title)}.json"), problems
        if kind == "pptx":
            title, slides = office.parse_slides(source)
            problems = office.pptx_problems(slides)
            title = title or "Présentation"
            return Output(office.build_pptx(source) if slides else b"",
                          "application/vnd.openxmlformats-officedocument.presentationml."
                          "presentation", f"{slug(title)}.pptx", title, source,
                          f"{slug(title)}.md"), problems
        if kind == "chart":
            config = charts.parse_config(source)
            png = await charts.render(config)
            title = charts.title_of(config) or "Graphique"
            return Output(png, "image/png", f"graphique-{slug(title)}.png", title,
                          json.dumps(config, ensure_ascii=False, indent=1),
                          f"graphique-{slug(title)}.json"), charts.problems(config)
        if kind == "diagram":
            png, _ = await diagram.render_mermaid(source)
            first = source.strip().splitlines()[0] if source.strip() else "schema"
            return Output(png, "image/png", "schema.png", "Schéma", source, "schema.mmd"), (
                [] if diagram.png_size(png)[0] > 0 else [f"rendu vide ({first})"])
        if kind.startswith("text:"):
            ext = kind[5:]
            problems = textfile.problems(ext, source)
            name = textfile.filename(ext, source)
            return Output(source.encode(), textfile.mime(ext), name, name, source, name), problems
        outline = diagram.parse_outline(source)
        problems = diagram.outline_problems(outline)
        png, _ = await diagram.render_mindmap(outline)
        title = str(outline["title"])
        return Output(png, "image/png", f"carte-mentale-{slug(title)}.png", title,
                      json.dumps(outline, ensure_ascii=False, indent=1),
                      f"carte-mentale-{slug(title)}.json"), problems

    async def _review(self, kind: str, what: str, request: str, source: str,
                      result: Output | None, writer: str) -> tuple[list[str], str, str]:
        """Relecture par un modèle d'une autre famille ; ([], "", "") si aucun disponible."""
        assert self.pick_reviewer is not None
        pages = await pdf_pages(result.data) if result is not None and kind in ("pdf", "latex") \
            else []
        vision = (kind in ("mindmap", "chart", "diagram") and result is not None) or bool(pages)
        reviewer = await self.pick_reviewer(exclude=writer, vision=vision)
        if reviewer is None:
            return [], "", ""
        content: Any = f"Source ({kind}) :\n{source[:14000]}"
        if vision and result is not None:
            images = pages or [result.data]
            content = [{"type": "text", "text": content}, *[
                {"type": "image_url", "image_url": {
                    "url": "data:image/png;base64," + base64.b64encode(img).decode()}}
                for img in images]]
        prompt = REVIEW_PROMPT.format(
            what=what, request=request[:400],
            visual=(" — les pages rendues sont jointes : vérifie la mise en page réelle"
                    if pages else " — l'image rendue est jointe : texte lisible, rien de coupé,"
                    " rien qui se chevauche") if vision else "")
        try:
            async with asyncio.timeout(REVIEW_TIMEOUT):
                text, key, name = await self.ask(
                    [{"role": "system", "content": prompt},
                     {"role": "user", "content": content}], model=reviewer)
        except Exception:  # relecteur indisponible : la relecture n'empêche pas la livraison
            return [], "", ""
        if same_model(key, writer):
            # Le relecteur prévu était indisponible et la bascule est revenue au rédacteur :
            # une auto-relecture n'est pas une relecture croisée, elle n'est pas comptée.
            return [], "", ""
        m = re.search(r"\{.*\}", text or "", re.S)
        try:
            data = json.loads(m.group(0)) if m else {}
        except ValueError:
            data = {}
        issues = [str(i)[:300] for i in data.get("issues") or [] if str(i).strip()]
        return ([] if data.get("ok") is True else issues[:6]), name, key


async def pdf_pages(pdf: bytes, limit: int = 2) -> list[bytes]:
    """Premières pages en PNG pour le relecteur (si `pdftoppm` est installé : bureau)."""
    import shutil
    import tempfile
    from pathlib import Path

    exe = shutil.which("pdftoppm")
    if exe is None:
        return []
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "d.pdf"
        src.write_bytes(pdf)
        proc = await asyncio.create_subprocess_exec(
            exe, "-png", "-r", "70", "-f", "1", "-l", str(limit), str(src), str(Path(tmp) / "p"),
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
        try:
            await asyncio.wait_for(proc.wait(), 30)
        except TimeoutError:
            proc.kill()
            return []
        return [p.read_bytes() for p in sorted(Path(tmp).glob("p*.png"))]


async def gather_with_timeout(coro: Any, seconds: float = CALL_TIMEOUT) -> Any:
    async with asyncio.timeout(seconds):
        return await coro
