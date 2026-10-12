"""Projets de plusieurs fichiers (livre LaTeX en chapitres, petit site, programme en modules,
jeu de données…) livrés ensemble dans une archive .zip (zipfile de Python : gratuit, local).

Le modèle écrit chaque fichier après une ligne « === FICHIER: chemin/relatif.ext === » (format
plus sûr que du JSON pour du LaTeX ou du code). Avant livraison : chemins sûrs, syntaxe de
chaque fichier, et pour un projet LaTeX, compilation réelle du document principal (les
\\input et \\include sont résolus dans l'archive) ; le PDF obtenu est ajouté au .zip."""

from __future__ import annotations

import io
import re
import zipfile
from pathlib import PurePosixPath

from tontolo.creator import textfile

MAX_FILES = 80
MAX_TOTAL = 8 * 1024 * 1024
_HEADER = re.compile(r"^\s*={3,}\s*(?:FICHIER|FILE|RAKITRA)\s*:\s*(.+?)\s*={3,}\s*$", re.M | re.I)
_SAFE_PART = re.compile(r"^[\w.\- ()]{1,80}$", re.U)
_INPUT = re.compile(r"\\(input|include|subfile)\{([^}]+)\}")


class BundleError(ValueError):
    pass


def parse(source: str) -> dict[str, str]:
    """{chemin: contenu} ; lève BundleError si le format ou un chemin est invalide."""
    heads = list(_HEADER.finditer(source or ""))
    if not heads:
        raise BundleError("aucun fichier : chaque fichier doit commencer par une ligne "
                          "« === FICHIER: chemin/nom.ext === »")
    files: dict[str, str] = {}
    for i, h in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(source)
        path = safe_path(h.group(1))
        body = source[h.end():end].strip("\n")
        body = re.sub(r"^```[\w+-]*\n(.*?)\n?```\s*$", r"\1", body, flags=re.S)  # bloc de code
        if i + 1 == len(heads):
            body = re.sub(r"\n```\s*$", "", body)  # réponse entière dans un bloc de code
        files[path] = body.rstrip() + "\n"
    if len(files) > MAX_FILES:
        raise BundleError(f"trop de fichiers ({len(files)} > {MAX_FILES})")
    if sum(len(c.encode()) for c in files.values()) > MAX_TOTAL:
        raise BundleError("projet trop volumineux")
    return files


def safe_path(raw: str) -> str:
    p = PurePosixPath(raw.strip().strip("`\"'").replace("\\", "/"))
    parts = [x for x in p.parts if x not in ("", ".")]
    if not parts or p.is_absolute() or any(x == ".." or not _SAFE_PART.match(x)
                                           for x in parts):
        raise BundleError(f"chemin de fichier refusé : {raw.strip()[:80]}")
    return "/".join(parts)


def problems(files: dict[str, str]) -> list[str]:
    out: list[str] = []
    for path, content in files.items():
        ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
        for p in textfile.problems(ext, content) if ext else []:
            out.append(f"{path} : {p}")
        if ext == "tex" and re.search(
                r"\\write18|\\immediate\\write|\\openout|\\openin(?![A-Za-z])|"
                r"\\read(?![A-Za-z])|\\directlua|\\luaexec|\\InputIfFileExists|"
                r"\\verbatiminput|\\lstinputlisting", content):
            out.append(f"{path} : commandes de lecture ou d'écriture de fichiers interdites")
    return out[:8]


def main_tex(files: dict[str, str]) -> str | None:
    mains = [p for p, c in files.items() if p.endswith(".tex") and "\\documentclass" in c]
    if not mains:
        return None
    return min(mains, key=lambda p: (p.count("/"), p != "main.tex", len(p)))


def inline_tex(files: dict[str, str], main: str) -> tuple[str, list[str]]:
    """Document principal avec ses \\input / \\include remplacés par le contenu des fichiers
    du projet (compilation par un service qui ne reçoit qu'un seul source)."""
    missing: list[str] = []
    base = PurePosixPath(main).parent

    def resolve(name: str, depth: int) -> str:
        name = name.strip()
        candidates = [name, f"{name}.tex", str(base / name), str(base / f"{name}.tex")]
        found = next((c.removeprefix("./") for c in candidates
                      if c.removeprefix("./") in files), None)
        if found is None:
            missing.append(name)
            return f"% fichier manquant : {name}\n"
        return expand(files[found], depth + 1)

    def expand(text: str, depth: int) -> str:
        if depth > 6:
            return text
        return _INPUT.sub(lambda m: ("\\clearpage\n" if m.group(1) == "include" else "")
                          + resolve(m.group(2), depth), text)

    return expand(files[main], 0), missing


def build_zip(files: dict[str, str], extra: dict[str, bytes] | None = None) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for path, content in files.items():
            z.writestr(path, content)
        for path, data in (extra or {}).items():
            z.writestr(path, data)
    return buf.getvalue()


def title_of(files: dict[str, str]) -> str:
    for content in files.values():
        m = re.search(r"\\title\{([^{}]{1,80})\}", content) or re.search(
            r"^#\s+(.{1,80})$", content, re.M)
        if m:
            return m.group(1).strip()
    return "Projet"
