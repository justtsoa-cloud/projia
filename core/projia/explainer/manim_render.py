"""Rendu MP4 d'un scénario par Manim (Linux, facultatif).

Aucun code n'est écrit par un modèle : le script est TOUJOURS le même (gabarit fixe) et le
scénario validé lui est transmis en base64. Le rendu s'exécute dans un dossier temporaire, avec
délai et limites de ressources, sous bubblewrap obligatoire, sans réseau. Sans Manim,
`status()` l'indique et le lecteur animé de l'application prend le relais."""

from __future__ import annotations

import asyncio
import base64
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from projia import sandbox

RENDER_TIMEOUT = 300.0
MAX_MP4 = 60 * 1024 * 1024

TEMPLATE = r'''
import base64, json, textwrap
from manim import *

DATA = json.loads(base64.b64decode("__DATA__").decode("utf-8"))
TEX = bool(DATA.get("tex"))
BG, FG, ACCENT, SOFT = "#0f0e2a", "#f7f7fb", "#67e5be", "#b9c4df"


def wrap(text, width=58):
    return "\n".join(textwrap.wrap(text, width)) if text else ""


class Explainer(Scene):
    def construct(self):
        self.camera.background_color = BG
        for sc in DATA["scenes"]:
            getattr(self, "scene_" + sc["type"])(sc)
            self.play(FadeOut(*self.mobjects), run_time=0.4)

    # --- éléments communs -------------------------------------------------------------
    def sub(self, sc):
        if not sc.get("narration"):
            return VGroup()
        t = Text(wrap(sc["narration"]), font_size=22, color=SOFT, line_spacing=0.9)
        t.to_edge(DOWN, buff=0.35)
        return t

    def head(self, sc):
        if not sc.get("title"):
            return VGroup()
        t = Text(sc["title"], font_size=40, color=ACCENT).to_edge(UP, buff=0.5)
        return t

    def hold(self, sc, used):
        self.wait(max(0.5, float(sc.get("seconds", 5)) - used))

    def formula(self, s, size=56):
        return MathTex(s, color=FG, font_size=size) if TEX else Text(s, font_size=36, color=FG)

    # --- scènes -----------------------------------------------------------------------
    def scene_title(self, sc):
        t = Text(wrap(sc["text"], 30), font_size=60, color=FG)
        sub = Text(wrap(sc.get("subtitle", ""), 50), font_size=30, color=ACCENT)
        g = VGroup(t, sub).arrange(DOWN, buff=0.4)
        self.play(Write(t), run_time=1.5)
        if sc.get("subtitle"):
            self.play(FadeIn(sub), run_time=0.8)
        s = self.sub(sc)
        self.add(s)
        self.hold(sc, 2.3)

    def scene_bullets(self, sc):
        head = self.head(sc)
        rows = VGroup(*[Text("• " + wrap(i, 46), font_size=34, color=FG, line_spacing=0.9)
                        for i in sc["items"]]).arrange(DOWN, aligned_edge=LEFT, buff=0.5)
        rows.next_to(head, DOWN, buff=0.7).to_edge(LEFT, buff=1.0)
        self.play(FadeIn(head), run_time=0.5)
        used = 0.5
        for r in rows:
            self.play(FadeIn(r, shift=RIGHT * 0.3), run_time=0.7)
            used += 0.7
            self.wait(0.5)
            used += 0.5
        self.add(self.sub(sc))
        self.hold(sc, used)

    scene_recap = scene_bullets

    def scene_equation(self, sc):
        eq = self.formula(sc["latex"])
        self.play(Write(eq), run_time=1.8)
        used = 1.8
        if sc.get("caption"):
            cap = Text(wrap(sc["caption"], 50), font_size=30, color=ACCENT).next_to(eq, DOWN, buff=0.6)
            self.play(FadeIn(cap), run_time=0.6)
            used += 0.6
        self.add(self.sub(sc))
        self.hold(sc, used)

    def scene_steps(self, sc):
        head = self.head(sc)
        rows = []
        for st in sc["steps"]:
            parts = []
            if st.get("text"):
                parts.append(Text(wrap(st["text"], 52), font_size=26, color=SOFT))
            if st.get("latex"):
                parts.append(self.formula(st["latex"], 40))
            rows.append(VGroup(*parts).arrange(DOWN, buff=0.12))
        block = VGroup(*rows).arrange(DOWN, buff=0.35)
        block.next_to(head, DOWN, buff=0.45)
        if block.height > 5.2:
            block.scale(5.2 / block.height).next_to(head, DOWN, buff=0.45)
        self.play(FadeIn(head), run_time=0.5)
        used = 0.5
        for row in rows:
            self.play(FadeIn(row, shift=UP * 0.2), run_time=0.8)
            self.wait(0.4)
            used += 1.2
        self.add(self.sub(sc))
        self.hold(sc, used)

    def scene_plot(self, sc):
        head = self.head(sc)
        pts = sc["points"]
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        lo, hi = min(ys), max(ys)
        pad = max(0.5, (hi - lo) * 0.15)
        ax = Axes(x_range=[sc["xmin"], sc["xmax"], max(1, round((sc["xmax"] - sc["xmin"]) / 6))],
                  y_range=[lo - pad, hi + pad, max(1, round((hi - lo + 2 * pad) / 6))],
                  x_length=8.5, y_length=3.8, tips=False,
                  axis_config={"color": SOFT}).shift(DOWN * 0.3)
        graph = ax.plot_line_graph(xs, ys, add_vertex_dots=False, line_color=ACCENT, stroke_width=5)
        self.play(FadeIn(head), Create(ax), run_time=1.0)
        self.play(Create(graph), run_time=2.0)
        used = 3.0
        if sc.get("caption"):
            cap = Text(wrap(sc["caption"], 60), font_size=26, color=FG).next_to(ax, DOWN, buff=0.3)
            self.play(FadeIn(cap), run_time=0.5)
            used += 0.5
        self.add(self.sub(sc))
        self.hold(sc, used)

    def scene_bars(self, sc):
        head = self.head(sc)
        vals = sc["values"]
        top = max(max(vals), 1)
        chart = BarChart(vals, bar_names=sc["labels"], y_range=[0, top * 1.2, max(1, round(top / 4))],
                         x_length=8.5, y_length=3.8, bar_colors=[ACCENT, "#8a7dff", "#33d6e8"])
        chart.shift(DOWN * 0.3)
        self.play(FadeIn(head), Create(chart), run_time=2.0)
        self.add(self.sub(sc))
        self.hold(sc, 2.0)
'''


def build_script(story: dict[str, Any], *, tex: bool) -> str:
    """Le script Manim : le gabarit fixe + le scénario validé en base64 (jamais de texte libre
    dans le code)."""
    payload = dict(story, tex=bool(tex))
    data = base64.b64encode(json.dumps(payload, ensure_ascii=False).encode("utf-8")).decode()
    return TEMPLATE.replace("__DATA__", data)


def _manim_python() -> str | None:
    """Interpréteur qui a Manim : `PROJIA_MANIM_PYTHON`, sinon celui du cœur."""
    candidates = [os.environ.get("PROJIA_MANIM_PYTHON"), sys.executable]
    for py in filter(None, candidates):
        try:
            ok = subprocess.run([py, "-c", "import manim"], capture_output=True,
                                timeout=20).returncode == 0
        except (OSError, subprocess.SubprocessError):
            ok = False
        if ok:
            return py
    return None


def status() -> dict[str, Any]:
    """Possibilités de rendu MP4 sur cette machine."""
    from projia.agent.mcp_client import bwrap_usable

    py = _manim_python()
    return {"manim": py is not None, "ffmpeg": shutil.which("ffmpeg") is not None,
            "latex": shutil.which("latex") is not None and shutil.which("dvisvgm") is not None,
            "sandbox": bwrap_usable() is not None}


class RenderError(Exception):
    pass


def _python_roots(py: str) -> list[Path]:
    """Dossiers à rouvrir dans le bac à sable pour que `py` démarre : son environnement
    virtuel, la cible du lien symbolique (et son dossier, qui contient aussi le lien vers la
    version exacte), l'installation réelle. Ceux du système (/usr…) sont déjà visibles."""
    path = Path(py)
    found = [path.parent.parent]
    if path.is_symlink():
        target = Path(os.readlink(path))
        target = target if target.is_absolute() else (path.parent / target)
        found += [target.parent.parent, target.parent.parent.parent]
    real = path.resolve()
    found += [real.parent.parent, real.parent.parent.parent]
    home = Path.home().resolve()
    return [r for r in found if str(r) not in ("/", "/usr", "/usr/local", "/opt")
            and (str(r).startswith(("/tmp", str(home))) and r != home)]


def _argv(py: str, workdir: Path, script: Path, quality: str) -> list[str]:
    from projia.agent.mcp_client import bwrap_usable

    cmd = [py, "-m", "manim", "render", f"-q{quality}", "--disable_caching", "--progress_bar",
           "none", "--media_dir", str(workdir / "media"), "-o", "explainer", str(script),
           "Explainer"]
    bwrap = bwrap_usable()
    if not bwrap:
        raise RenderError("bubblewrap indisponible : rendu isolé impossible")
    return sandbox.argv(cmd, workdir, read_only=list(dict.fromkeys(_python_roots(py))))


def _limits() -> None:  # exécuté dans le processus fils, avant Manim
    import resource

    resource.setrlimit(resource.RLIMIT_AS, (2 * 1024**3,) * 2)
    resource.setrlimit(resource.RLIMIT_CPU, (int(RENDER_TIMEOUT) + 60,) * 2)
    resource.setrlimit(resource.RLIMIT_FSIZE, (MAX_MP4 * 4,) * 2)
    resource.setrlimit(resource.RLIMIT_NOFILE, (512, 512))


async def render(story: dict[str, Any], *, quality: str = "l") -> bytes:
    """MP4 du scénario (qualité l = 480p15, m = 720p30). RenderError si Manim est absent ou
    échoue ; jamais d'exécution de texte venu d'un modèle."""
    if quality not in ("l", "m"):
        quality = "l"
    st = status()
    py = _manim_python()
    if py is None or not st["ffmpeg"]:
        raise RenderError("Manim ou ffmpeg n'est pas installé sur cette machine")
    if not st["sandbox"]:
        raise RenderError("bubblewrap indisponible : rendu isolé impossible")
    with tempfile.TemporaryDirectory(prefix="projia-manim-") as tmp:
        work = Path(tmp)
        script = work / "scene.py"
        script.write_text(build_script(story, tex=st["latex"]), encoding="utf-8")
        env = {"PATH": os.environ.get("PATH", ""), "HOME": str(work), "LANG": "C.UTF-8",
               "TMPDIR": str(work)}
        proc = await asyncio.create_subprocess_exec(
            *_argv(py, work, script, quality), cwd=work, env=env,
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE,
            preexec_fn=_limits)
        try:
            _, err = await asyncio.wait_for(proc.communicate(), RENDER_TIMEOUT)
        except TimeoutError:
            proc.kill()
            await proc.wait()
            raise RenderError("rendu trop long : scénario abandonné") from None
        found = sorted((work / "media").rglob("explainer.mp4"))
        if proc.returncode != 0 or not found:
            tail = (err or b"").decode("utf-8", "replace").strip().splitlines()[-3:]
            raise RenderError("Manim a échoué : " + " | ".join(tail)[:400])
        data = found[0].read_bytes()
        if len(data) > MAX_MP4:
            raise RenderError("vidéo trop lourde")
        return data
