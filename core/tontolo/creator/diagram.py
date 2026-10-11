"""Cartes mentales et schémas en images **précises** (texte net, aucune invention d'une IA
d'image) : le modèle fournit seulement la structure ; le dessin est calculé.

- Carte mentale : plan JSON {"title", "children": [{"label", "children": […]}]} → Graphviz
  (couleur par branche, texte replié, nœud central marqué), rendu par `dot` s'il est installé,
  sinon par Kroki (kroki.io, gratuit et anonyme, vérifié le 2026-10-11).
- Schéma : source Mermaid (organigramme, frise, séquence) → Kroki.
"""

from __future__ import annotations

import asyncio
import json
import re
import shutil
import textwrap
from typing import Any

import httpx

from tontolo import http

KROKI = "https://kroki.io"
MAX_IMAGE = 15 * 1024 * 1024
MAX_NODES = 120
PALETTE = [  # (branche, feuilles) — contrastes lisibles en clair comme en impression
    ("#3949AB", "#E8EAF6"), ("#00897B", "#E0F2F1"), ("#F4511E", "#FBE9E7"),
    ("#8E24AA", "#F3E5F5"), ("#43A047", "#E8F5E9"), ("#FB8C00", "#FFF3E0"),
    ("#1E88E5", "#E3F2FD"), ("#D81B60", "#FCE4EC"),
]


class DiagramError(Exception):
    def __init__(self, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable


def parse_outline(text: str) -> dict[str, Any]:
    """Plan JSON (éventuellement entouré de texte ou d'un bloc ```json)."""
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        raise DiagramError("plan de carte mentale introuvable (JSON attendu)")
    try:
        data = json.loads(m.group(0))
    except (ValueError, RecursionError) as exc:
        raise DiagramError(f"JSON invalide : {exc}") from exc
    if not isinstance(data, dict) or not str(data.get("title", "")).strip():
        raise DiagramError("le plan doit avoir un « title »")
    return data


def _wrap(label: str, width: int = 22) -> str:
    lines = textwrap.wrap(re.sub(r"\s+", " ", label.strip()), width) or [""]
    return "\\n".join(_esc(x) for x in lines[:4])


def _esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def outline_problems(data: dict[str, Any]) -> list[str]:
    """Défauts de conception détectables sans dessiner (renvoyés au modèle pour correction)."""
    problems: list[str] = []
    count = 0

    def walk(node: dict[str, Any], depth: int) -> None:
        nonlocal count
        for child in node.get("children") or []:
            if not isinstance(child, dict):
                continue
            count += 1
            label = str(child.get("label", "")).strip()
            if not label:
                problems.append("nœud sans libellé")
            elif len(label) > 70:
                problems.append(f"libellé trop long ({len(label)} caractères) : « {label[:40]}… »"
                                " — utilise des mots-clés")
            if depth >= 4:
                problems.append("profondeur supérieure à 4 niveaux : regroupe les idées")
            walk(child, depth + 1)

    walk(data, 1)
    branches = len([c for c in data.get("children") or [] if isinstance(c, dict)])
    if branches < 2:
        problems.append("moins de 2 branches principales")
    if branches > 8:
        problems.append(f"{branches} branches principales : 8 au maximum pour rester lisible")
    if count > MAX_NODES:
        problems.append(f"{count} nœuds : {MAX_NODES} au maximum")
    return sorted(set(problems))[:8]


def outline_to_dot(data: dict[str, Any]) -> str:
    out = ['digraph mindmap {', '  graph [rankdir=LR, splines=spline, nodesep=0.3, ranksep=0.6,'
           ' pad=0.4, bgcolor="white", dpi=150];',
           '  node [fontname="Helvetica", fontsize=13, style="rounded,filled", shape=box,'
           ' penwidth=0, margin="0.18,0.08"];', '  edge [arrowhead=none, penwidth=2.2];',
           f'  root [label="{_wrap(str(data["title"]), 18)}", shape=ellipse, fontsize=18,'
           ' fontcolor="white", fillcolor="#1A237E", margin="0.3,0.15"];']
    counter = 0

    def walk(node: dict[str, Any], parent: str, colors: tuple[str, str], depth: int) -> None:
        nonlocal counter
        for child in (node.get("children") or [])[:12]:
            if not isinstance(child, dict) or counter >= MAX_NODES:
                continue
            counter += 1
            nid = f"n{counter}"
            strong, light = colors
            if depth == 1:
                attrs = f'fillcolor="{strong}", fontcolor="white", fontsize=15'
            else:
                attrs = f'fillcolor="{light}", fontcolor="#212121", fontsize={max(11, 14 - depth)}'
            out.append(f'  {nid} [label="{_wrap(str(child.get("label", "")))}", {attrs}];')
            out.append(f'  {parent} -> {nid} [color="{strong}"];')
            walk(child, nid, colors, depth + 1)

    for i, branch in enumerate(c for c in (data.get("children") or []) if isinstance(c, dict)):
        walk({"children": [branch]}, "root", PALETTE[i % len(PALETTE)], 1)
    out.append("}")
    return "\n".join(out)


async def _kroki(kind: str, source: str, fmt: str = "png") -> bytes:
    try:
        r = await http.client().post(f"{KROKI}/{kind}/{fmt}", content=source.encode(),
                                     headers={"Content-Type": "text/plain"}, timeout=60.0)
    except httpx.HTTPError as exc:
        raise DiagramError("service de schémas injoignable", retryable=True) from exc
    if r.status_code == 400:
        raise DiagramError(f"source du schéma invalide : {r.text[:500]}")
    if r.status_code != 200 or len(r.content) > MAX_IMAGE:
        raise DiagramError(f"service de schémas : réponse {r.status_code}", retryable=True)
    return r.content


async def _dot_local(source: str) -> bytes | None:
    exe = shutil.which("dot")
    if exe is None:
        return None
    proc = await asyncio.create_subprocess_exec(exe, "-Tpng", stdin=asyncio.subprocess.PIPE,
                                                stdout=asyncio.subprocess.PIPE,
                                                stderr=asyncio.subprocess.PIPE)
    try:
        out, err = await asyncio.wait_for(proc.communicate(source.encode()), 60)
    except TimeoutError:
        proc.kill()
        return None
    if proc.returncode != 0:
        raise DiagramError(f"source du schéma invalide : {err.decode()[:500]}")
    return out


async def render_mindmap(data: dict[str, Any]) -> tuple[bytes, str]:
    dot = outline_to_dot(data)
    png = await _dot_local(dot)
    return (png, "graphviz (local)") if png else (await _kroki("graphviz", dot), "kroki.io")


async def render_mermaid(source: str) -> tuple[bytes, str]:
    return await _kroki("mermaid", source), "kroki.io"


def png_size(data: bytes) -> tuple[int, int]:
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        return (0, 0)
    return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")
