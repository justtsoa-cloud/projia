"""Compilation LaTeX → PDF, gratuite et anonyme, avec repli automatique :
1. moteur local s'il est installé (tectonic, pdflatex ou xelatex — Linux) ;
2. LaTeX-on-HTTP (latex.ytotech.com), TeX Live complet, journal renvoyé en cas d'erreur ;
3. latexonline.cc.
Vérifié le 2026-10-11 (compilation d'un document de test sans compte ni clé).

En cas d'échec, `LatexError.log` contient les lignes d'erreur utiles : le modèle s'en sert
pour corriger son source (boucle « vérifier puis corriger » du pipeline)."""

from __future__ import annotations

import asyncio
import re
import shutil
import tempfile
from pathlib import Path

import httpx

from tontolo import http

MAX_PDF = 30 * 1024 * 1024
YTOTECH = "https://latex.ytotech.com/builds/sync"
LATEXONLINE = "https://latexonline.cc/compile"


class LatexError(Exception):
    def __init__(self, message: str, log: str = "", *, retryable: bool = False) -> None:
        super().__init__(message)
        self.log = log
        self.retryable = retryable  # service injoignable (et non erreur dans le source)


def errors_from_log(log: str, limit: int = 12) -> str:
    """Lignes d'erreur (« ! … », « fichier:ligne: … ») et leur contexte immédiat."""
    lines = log.splitlines()
    out: list[str] = []
    for i, line in enumerate(lines):
        if line.startswith("!") or re.match(r"^[^ ]+\.tex:\d+:", line):
            out.extend(lines[i:i + 3])
            # ligne du source fautive (« l.215 … ») : sert à situer le chapitre d'un livre
            where = next((ln for ln in lines[i + 3:i + 14] if re.match(r"^l\.\d+ ", ln)), None)
            if where:
                out.append(where)
        if len(out) >= limit * 3:
            break
    return "\n".join(out)[:3000] or log[-1500:]


def warnings_from_log(log: str) -> list[str]:
    """Défauts de mise en page signalés par TeX (débordements nets, références manquantes)."""
    found = []
    for m in re.finditer(r"Overfull \\hbox \((\d+(?:\.\d+)?)pt too wide\)[^\n]*lines? (\d+)", log):
        if float(m.group(1)) > 15:
            found.append(f"ligne {m.group(2)} : texte qui dépasse la marge de {m.group(1)} pt")
    if "There were undefined references" in log or "Reference `" in log:
        found.append("références non définies (\\ref ou \\cite sans cible)")
    return found[:6]


def engine_for(source: str) -> str:
    """xelatex si le document utilise fontspec/polices système, sinon pdflatex."""
    return "xelatex" if re.search(r"\\usepackage(\[[^]]*\])?\{(fontspec|unicode-math)\}",
                                  source) else "pdflatex"


async def _local(source: str, engine: str) -> tuple[bytes, str]:
    exe = shutil.which("tectonic") or shutil.which(engine)
    if exe is None:
        raise LatexError("aucun moteur local", retryable=True)
    with tempfile.TemporaryDirectory() as tmp:
        tex = Path(tmp) / "document.tex"
        tex.write_text(source, encoding="utf-8")
        args = ([exe, "--outdir", tmp, str(tex)] if exe.endswith("tectonic") else
                [exe, "-interaction=nonstopmode", "-halt-on-error", "-no-shell-escape",
                 "-output-directory", tmp, str(tex)])
        runs = 1 if exe.endswith("tectonic") else 2  # 2 passes : table des matières, renvois
        log = ""
        for _ in range(runs):
            proc = await asyncio.create_subprocess_exec(
                *args, cwd=tmp, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
            try:
                out, _ = await asyncio.wait_for(proc.communicate(), 90)
            except TimeoutError as exc:
                proc.kill()
                raise LatexError("compilation trop longue") from exc
            log_file = Path(tmp) / "document.log"
            log = log_file.read_text("utf-8", "replace") if log_file.exists() else out.decode(
                "utf-8", "replace")
            if proc.returncode != 0:
                raise LatexError("erreur de compilation", errors_from_log(log))
        pdf = Path(tmp) / "document.pdf"
        if not pdf.exists():
            raise LatexError("aucun PDF produit", errors_from_log(log))
        return pdf.read_bytes(), log


async def _ytotech(source: str, engine: str) -> tuple[bytes, str]:
    try:
        r = await http.client().post(YTOTECH, timeout=120.0, json={
            "compiler": engine, "resources": [{"main": True, "content": source}]})
    except httpx.HTTPError as exc:
        raise LatexError("service LaTeX injoignable", retryable=True) from exc
    if r.status_code in (200, 201) and r.headers.get("content-type", "").startswith(
            "application/pdf"):
        return r.content[:MAX_PDF], ""
    try:
        data = r.json()
    except ValueError:
        raise LatexError(f"service LaTeX : réponse {r.status_code}", retryable=True) from None
    if data.get("error") == "COMPILATION_ERROR":
        log = "\n".join(str(v) for v in (data.get("log_files") or {}).values())
        raise LatexError("erreur de compilation", errors_from_log(log))
    raise LatexError(f"service LaTeX : {data.get('error') or r.status_code}", retryable=True)


async def _latexonline(source: str, engine: str) -> tuple[bytes, str]:
    try:
        r = await http.client().get(LATEXONLINE, timeout=120.0, params={
            "text": source, "command": engine, "force": "true"})
    except httpx.HTTPError as exc:
        raise LatexError("service LaTeX injoignable", retryable=True) from exc
    if r.status_code == 200 and r.headers.get("content-type", "").startswith("application/pdf"):
        return r.content[:MAX_PDF], ""
    if r.status_code == 400:  # erreur dans le source : le corps est le journal
        raise LatexError("erreur de compilation", errors_from_log(r.text))
    raise LatexError(f"service LaTeX : réponse {r.status_code}", retryable=True)


async def compile_pdf(source: str) -> tuple[bytes, str, str]:
    """(pdf, journal, service utilisé). Lève LatexError (non relançable = erreur du source)."""
    engine = engine_for(source)
    last: LatexError | None = None
    backends = [("local", _local), ("latex.ytotech.com", _ytotech),
                ("latexonline.cc", _latexonline)]
    for name, fn in backends:
        if name == "latexonline.cc" and len(source) > 6000:
            continue  # source passé dans l'URL : limité aux petits documents
        try:
            pdf, log = await fn(source, engine)
            if not pdf.startswith(b"%PDF"):
                raise LatexError("fichier produit invalide", retryable=True)
            return pdf, log, name
        except LatexError as exc:
            if not exc.retryable:
                raise  # erreur dans le document : inutile d'essayer un autre service
            last = exc
    raise last or LatexError("aucun service LaTeX disponible", retryable=True)
