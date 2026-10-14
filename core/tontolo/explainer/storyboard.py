"""Scénario d'une vidéo explicative : des DONNÉES, jamais du code.

Un modèle propose un scénario en JSON ; `validate` le nettoie et le borne (scènes, longueurs,
LaTeX filtré, nombres finis) ; les courbes sont calculées ici par un évaluateur d'expressions à
liste blanche (`plot_points`), pas par le modèle ni par l'application. Le même scénario alimente
le lecteur animé de l'application (partout) et le rendu Manim (Linux, gabarits fixes).

Types de scènes : title, bullets, equation, steps, plot, bars, recap.
"""

from __future__ import annotations

import ast
import math
import re
from collections.abc import Callable
from typing import Any

MAX_SCENES = 8
MAX_TEXT = 140
MAX_NARRATION = 320
MAX_ITEMS = 5
MAX_LATEX = 160
POINTS = 64

TYPES = ("title", "bullets", "equation", "steps", "plot", "bars", "recap")


class StoryboardError(ValueError):
    """Scénario inutilisable (message destiné au rédacteur, pour une réparation)."""


# --- Nettoyage --------------------------------------------------------------------------------

_CTRL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


def _text(value: Any, limit: int = MAX_TEXT) -> str:
    s = _CTRL.sub(" ", str(value if value is not None else ""))
    s = re.sub(r"\s+", " ", s).strip()
    return s[:limit]


_LATEX_OK = re.compile(r"^[\\A-Za-z0-9{}\[\]()_^=+\-*/.,:;<>|!&' ~%]+$")
_LATEX_BAD = re.compile(
    r"\\(?:input|include|write|openin|openout|read|def|edef|gdef|xdef|let|catcode|newcommand|"
    r"renewcommand|usepackage|documentclass|immediate|csname|expandafter|newread|newwrite|"
    r"directlua|special|jobname|string|detokenize|verb|url|href|includegraphics)(?![A-Za-z])")


def latex(value: Any) -> str:
    """LaTeX d'une formule : jeu de caractères restreint, aucune commande système ou de
    définition (le même texte part chez Manim, qui l'envoie à `latex`)."""
    s = _text(value, 1000).replace("$", "")
    if len(s) > MAX_LATEX:
        raise StoryboardError(f"formule trop longue ({len(s)} caractères, {MAX_LATEX} au plus)")
    if not s or not _LATEX_OK.match(s) or _LATEX_BAD.search(s):
        raise StoryboardError(
            f"formule LaTeX refusée : {s[:60]!r} (caractères ou commande interdits)")
    if s.count("{") != s.count("}"):
        raise StoryboardError(f"accolades non équilibrées dans la formule : {s[:60]!r}")
    return s


# --- Courbes : évaluateur d'expressions à liste blanche ---------------------------------------

_FUNCS: dict[str, Callable[[float], float]] = {
    "sin": math.sin, "cos": math.cos, "tan": math.tan, "exp": math.exp, "log": math.log,
    "ln": math.log, "sqrt": math.sqrt, "abs": abs, "atan": math.atan}
_CONSTS = {"pi": math.pi, "e": math.e}
_MAX_NODES = 60


def _eval(node: ast.AST, x: float, depth: int = 0) -> float:
    if depth > 12:
        raise StoryboardError("expression trop profonde")
    if isinstance(node, ast.Expression):
        return _eval(node.body, x, depth + 1)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) \
            and not isinstance(node.value, bool):
        if abs(node.value) > 1e6:
            raise StoryboardError("constante trop grande")
        return float(node.value)
    if isinstance(node, ast.Name):
        if node.id == "x":
            return x
        if node.id in _CONSTS:
            return _CONSTS[node.id]
        raise StoryboardError(f"nom inconnu dans l'expression : {node.id}")
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        v = _eval(node.operand, x, depth + 1)
        return -v if isinstance(node.op, ast.USub) else v
    if isinstance(node, ast.BinOp):
        a, b = _eval(node.left, x, depth + 1), _eval(node.right, x, depth + 1)
        if isinstance(node.op, ast.Add):
            return a + b
        if isinstance(node.op, ast.Sub):
            return a - b
        if isinstance(node.op, ast.Mult):
            return a * b
        if isinstance(node.op, ast.Div):
            return a / b
        if isinstance(node.op, ast.Pow):
            if abs(b) > 12:
                raise StoryboardError("exposant trop grand")
            return a ** b
        raise StoryboardError("opérateur non autorisé")
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
            and node.func.id in _FUNCS and len(node.args) == 1 and not node.keywords:
        return float(_FUNCS[node.func.id](_eval(node.args[0], x, depth + 1)))
    raise StoryboardError("expression non autorisée (seuls x, pi, e, + - * / ** et "
                          "sin cos tan exp log sqrt abs atan)")


def parse_expr(expr: str) -> ast.Expression:
    s = _text(expr, 80).replace("^", "**").replace("ln(", "log(")
    if not s:
        raise StoryboardError("expression de courbe vide")
    try:
        tree = ast.parse(s, mode="eval")
    except SyntaxError as exc:
        raise StoryboardError(f"expression de courbe illisible : {s!r}") from exc
    if sum(1 for _ in ast.walk(tree)) > _MAX_NODES:
        raise StoryboardError("expression de courbe trop longue")
    return tree


def plot_points(expr: str, xmin: float, xmax: float, n: int = POINTS
                ) -> list[tuple[float, float]]:
    """Points (x, y) de la courbe, finis seulement (les trous : asymptotes, racines négatives)."""
    tree = parse_expr(expr)
    if not (math.isfinite(xmin) and math.isfinite(xmax)) or xmax <= xmin or xmax - xmin > 1e4:
        raise StoryboardError("intervalle de courbe invalide")
    out: list[tuple[float, float]] = []
    for i in range(n + 1):
        x = xmin + (xmax - xmin) * i / n
        try:
            y = _eval(tree, x)
        except (ArithmeticError, ValueError):
            continue
        if math.isfinite(y) and abs(y) < 1e6:
            out.append((round(x, 4), round(y, 4)))
    if len(out) < 8:
        raise StoryboardError("la courbe n'a pas assez de points calculables sur cet intervalle")
    return out


# --- Validation -------------------------------------------------------------------------------

def _items(raw: Any, limit: int = MAX_ITEMS) -> list[str]:
    if not isinstance(raw, list):
        return []
    return [t for t in (_text(i) for i in raw[:limit]) if t]


def _scene(raw: Any, index: int) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise StoryboardError(f"scène {index + 1} : objet attendu")
    kind = _text(raw.get("type"), 20).lower()
    if kind not in TYPES:
        raise StoryboardError(f"scène {index + 1} : type inconnu « {kind} » (types : "
                              + ", ".join(TYPES) + ")")
    out: dict[str, Any] = {"type": kind, "narration": _text(raw.get("narration"), MAX_NARRATION)}
    if kind == "title":
        out["text"] = _text(raw.get("text") or raw.get("title"))
        out["subtitle"] = _text(raw.get("subtitle"))
        if not out["text"]:
            raise StoryboardError(f"scène {index + 1} (title) : « text » manquant")
    elif kind in ("bullets", "recap"):
        out["title"] = _text(raw.get("title"))
        out["items"] = _items(raw.get("items"), 4)
        if not out["items"]:
            raise StoryboardError(f"scène {index + 1} ({kind}) : « items » manquant")
        if len(out["items"]) == 1 and kind == "bullets":
            # Une seule puce sur un écran presque vide : mieux vaut une grande phrase centrée.
            return {"type": "title", "text": out["items"][0], "subtitle": out["title"],
                    "narration": out["narration"]}
    elif kind == "equation":
        out["latex"] = latex(raw.get("latex"))
        out["caption"] = _text(raw.get("caption"))
    elif kind == "steps":
        out["title"] = _text(raw.get("title"))
        steps = []
        for s in (raw.get("steps") or [])[:MAX_ITEMS] if isinstance(raw.get("steps"), list) else []:
            if isinstance(s, str):
                s = {"text": s}
            if not isinstance(s, dict):
                continue
            step = {"text": _text(s.get("text"))}
            if s.get("latex"):
                step["latex"] = latex(s.get("latex"))
            if step["text"] or step.get("latex"):
                steps.append(step)
        if len(steps) < 2:
            raise StoryboardError(f"scène {index + 1} (steps) : au moins 2 étapes")
        out["steps"] = steps
    elif kind == "plot":
        out["title"] = _text(raw.get("title"))
        out["caption"] = _text(raw.get("caption"))
        out["expr"] = _text(raw.get("expr"), 80)
        try:
            xmin, xmax = float(raw.get("xmin", -5)), float(raw.get("xmax", 5))
        except (TypeError, ValueError) as exc:
            raise StoryboardError(f"scène {index + 1} (plot) : xmin et xmax numériques") from exc
        out["xmin"], out["xmax"] = xmin, xmax
        out["points"] = plot_points(out["expr"], xmin, xmax)
    elif kind == "bars":
        out["title"] = _text(raw.get("title"))
        labels = _items(raw.get("labels"), 6)
        values: list[float] = []
        for v in (raw.get("values") or [])[:6] if isinstance(raw.get("values"), list) else []:
            try:
                f = float(v)
            except (TypeError, ValueError):
                continue
            if math.isfinite(f) and abs(f) < 1e9:
                values.append(f)
        if len(labels) < 2 or len(values) != len(labels):
            raise StoryboardError(f"scène {index + 1} (bars) : autant de « values » que de "
                                  "« labels » (2 à 6)")
        out["labels"], out["values"] = labels, values
    return out


def validate(raw: Any, *, language: str = "fr") -> dict[str, Any]:
    """Scénario nettoyé et borné, ou StoryboardError (liste des défauts pour la réparation)."""
    if not isinstance(raw, dict):
        raise StoryboardError("le scénario doit être un objet JSON")
    scenes_raw = raw.get("scenes")
    if not isinstance(scenes_raw, list) or not scenes_raw:
        raise StoryboardError("« scenes » : liste non vide attendue")
    scenes = [_scene(s, i) for i, s in enumerate(scenes_raw[:MAX_SCENES])]
    if len(scenes) < 3:
        raise StoryboardError("au moins 3 scènes (accroche, exemple, récapitulation)")
    title = _text(raw.get("title")) or next(
        (s.get("text", "") for s in scenes if s["type"] == "title"), "")
    if not title:
        raise StoryboardError("« title » manquant")
    for s in scenes:
        s["seconds"] = scene_seconds(s)
    return {"version": 1, "title": title, "language": language if language in (
        "fr", "en", "mg") else "fr", "scenes": scenes,
        "seconds": sum(s["seconds"] for s in scenes)}


def scene_seconds(scene: dict[str, Any]) -> float:
    """Durée d'une scène : le temps de dire la narration (≈ 2,6 mots par seconde) ou, à défaut,
    de lire le contenu ; entre 3 et 20 secondes."""
    words = len(str(scene.get("narration") or "").split())
    shown = len(" ".join([str(scene.get("text") or ""), *scene.get("items", []),
                          *[str(s.get("text", "")) for s in scene.get("steps", [])]]).split())
    return round(max(3.0, min(20.0, max(words / 2.6 + 0.8, shown / 3.2 + 2.0))), 1)


# --- Repli sans modèle ------------------------------------------------------------------------

def fallback_from_text(topic: str, text: str, language: str = "fr") -> dict[str, Any] | None:
    """Scénario minimal tiré d'une explication déjà donnée dans la discussion (phrases clés en
    puces) quand le modèle n'a pas fourni de scénario valide. None si le texte est trop pauvre."""
    clean = re.sub(r"```.*?```|\$\$.*?\$\$|\$[^$\n]{1,200}\$|https?://\S+", " ", text or "",
                   flags=re.S)
    clean = re.sub(r"[#*_`>|]+", " ", clean)
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", re.sub(r"\s+", " ", clean))
                 if 25 <= len(s.strip()) <= 220]
    if len(sentences) < 3 or not topic.strip():
        return None
    head = _text(topic.strip().capitalize(), 80)
    pick = sentences[: 4 + 4]
    recap = [_text(s, 110) for s in pick[-3:]]
    scenes = [
        {"type": "title", "text": head, "narration": head + "."},
        {"type": "bullets", "title": "L'idée", "items": [_text(s, 110) for s in pick[:3]],
         "narration": " ".join(pick[:2])[:MAX_NARRATION]},
        {"type": "bullets", "title": "À retenir", "items": [_text(s, 110) for s in pick[3:6]]
         or recap, "narration": " ".join(pick[3:5])[:MAX_NARRATION]},
        {"type": "recap", "title": "En résumé", "items": recap,
         "narration": " ".join(recap)[:MAX_NARRATION]},
    ]
    return validate({"title": head, "scenes": scenes}, language=language)
