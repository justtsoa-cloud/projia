"""Présentations Beamer par sections : nettoyage, assemblage, compilation réelle, correction
ciblée et repli simplifié."""

from __future__ import annotations

import json
import shutil
from typing import Any

import pytest

from projia.creator import slides

needs_tex = pytest.mark.skipif(shutil.which("pdflatex") is None and shutil.which("tectonic")
                               is None, reason="pas de moteur LaTeX local")


def test_clean_section_is_safe_and_marks_code_frames_fragile() -> None:
    raw = ("```latex\n\\documentclass{beamer}\\usepackage{x}\\begin{document}\n"
           "\\begin{frame}{Code}\n\\begin{lstlisting}\nprint(1)\n\\end{lstlisting}\n\\end{frame}\n"
           "\\begin{frame}[t]{Texte}\nBonjour \\input{/etc/passwd}\n\\end{frame}\n"
           "\\end{document}\n```")
    out = slides.clean_section(raw, "Intro")
    assert out.startswith("\\section{Intro}") and "\\begin{frame}[fragile]{Code}" in out
    assert "\\begin{frame}[t]{Texte}" in out  # sans code : options inchangées
    for bad in ("documentclass", "usepackage", "begin{document}", "\\input", "```"):
        assert bad not in out


def test_plain_section_keeps_text_only() -> None:
    out = slides.plain_section("\\section{S}\\begin{frame}{T}\\undefinedcommand{Texte utile} 50% "
                               "\\begin{tikzpicture}\\draw (0,0);\\end{tikzpicture}\\end{frame}",
                               "Résumé & suite")
    assert "Texte utile" in out and "tikzpicture" not in out and "undefinedcommand" not in out
    assert "Résumé \\& suite" in out


SECTION = ("\\section{{{t}}}\n\\begin{{frame}}{{{t} : définition}}\nUne notion clé.\n"
           "\\begin{{block}}{{Exemple}}$x^2$\\end{{block}}\n\\end{{frame}}\n"
           "\\begin{{frame}}{{{t} : code}}\n\\begin{{lstlisting}}\ndef f(x):\n    return x\n"
           "\\end{{lstlisting}}\n\\end{{frame}}\n"
           "\\begin{{frame}}{{{t} : schéma}}\n\\begin{{tikzpicture}}\\draw[->] (0,0) -- (2,0);"
           "\\end{{tikzpicture}}\n\\end{{frame}}\n")


@needs_tex
async def test_full_run_compiles_and_repairs_a_broken_section() -> None:
    calls: list[str] = []

    async def ask(messages: list[dict[str, Any]], **kw: Any) -> tuple[str, str, str]:
        system = messages[0]["content"]
        calls.append(system[:30])
        if "plan d'une présentation" in system:
            return json.dumps({"title": "Les vecteurs", "sections": [
                {"title": f"Partie {i}", "summary": "notions"} for i in range(1, 5)]}), "m", "M"
        if "corriges une section" in system:  # correction ciblée de la section cassée
            return SECTION.format(t="Partie 3"), "fixer", "F"
        title = next(f"Partie {i}" for i in range(1, 5) if f"« Partie {i} »" in system)
        if title == "Partie 3":  # erreur de compilation volontaire
            return "\\section{Partie 3}\\begin{frame}{X}\\commandeinconnue\\end{frame}", "m", "M"
        return SECTION.format(t=title), "writer", "W"

    out: dict[str, Any] = {}
    steps = [ev async for ev in slides.SlidesWriter(ask, "fr").run("Beamer sur les vecteurs",
                                                                  context="cours", out=out)]
    assert out["pdf"][:5] == b"%PDF-" and out["fixes"] == 1
    assert out["source"].count("\\begin{frame}") >= 4 * 3 + 2
    assert any(s.get("step") == "doc_fixing" for s in steps)
    assert sum("corriges une section" in c for c in calls) == 1


@needs_tex
async def test_unfixable_section_is_simplified_not_fatal() -> None:
    async def ask(messages: list[dict[str, Any]], **kw: Any) -> tuple[str, str, str]:
        system = messages[0]["content"]
        if "plan d'une présentation" in system:
            return json.dumps({"title": "T", "sections": [
                {"title": f"P{i}", "summary": "s"} for i in range(1, 4)]}), "m", "M"
        if "corriges une section" in system or "« P2 »" in system:
            return "\\section{P2}\\begin{frame}{X}\\toujoursinconnue\\end{frame}", "m", "M"
        title = next(t for t in ("P1", "P3") if f"« {t} »" in system)
        return SECTION.format(t=title), "m", "M"

    out: dict[str, Any] = {}
    _ = [ev async for ev in slides.SlidesWriter(ask, "fr").run("x", out=out)]
    assert out["pdf"][:5] == b"%PDF-" and 2 in out["failed"]


def test_systematic_model_mistakes_are_fixed_without_a_model() -> None:
    raw = ("\\begin{frame}{Accents}\n\\begin{lstlisting}\n# résumé : \\begin{frame}{X} "
           "\\end{frame}\n\\end{lstlisting}\n\\end{frame}\n"
           "\\begin{frame}{Verb}\nUtiliser \\verb|$x$|.\n\\end{frame}\n")
    out = slides.clean_section(raw, "S")
    assert out.count("\\begin{frame}[fragile]") == 2
    assert "\\begin {frame}{X} \\end {frame}" in out  # le code ne coupe plus la diapositive
    assert "literate=" in slides.preamble("T", "fr") and "{é}" in slides.preamble("T", "fr")
    assert "\\\\" not in slides.plain_section("a \\\\ b \\newline c", "T").split("\n", 1)[1]


@needs_tex
async def test_real_mistakes_compile() -> None:
    from projia.creator import latex

    raw = ("\\section{S}\\begin{frame}{Accents}\n\\begin{lstlisting}\n# é à ç « »\n"
           "\\begin{frame}{X} \\end{frame}\n\\end{lstlisting}\n\\end{frame}\n"
           "\\begin{frame}{Verb}\nUtiliser \\verb|$x$|.\n\\end{frame}\n")
    pdf, _, _ = await latex.compile_pdf(slides.assemble("T", [slides.clean_section(raw, "S")],
                                                        "fr")[0])
    assert pdf[:5] == b"%PDF-"
