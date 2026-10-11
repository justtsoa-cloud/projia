"""Fichiers texte de tout type (code, CSV, JSON, HTML, SVG, Markdown, iCalendar…) :
contrôles de syntaxe avant livraison, renvoyés au modèle en cas d'erreur."""

from __future__ import annotations

import ast
import csv
import io
import json
import re

CODE_EXTS = {"py", "js", "ts", "java", "c", "cpp", "h", "cs", "go", "rs", "kt", "dart", "php",
             "rb", "sh", "sql", "r", "m", "swift", "lua", "html", "css", "svg", "json", "xml",
             "yaml", "yml", "toml", "ini", "tex", "ics", "csv", "ipynb", "bat", "ps1"}
SAFE_EXT = re.compile(r"^[a-z0-9]{1,8}$")
MIMES = {"csv": "text/csv", "json": "application/json", "html": "text/html",
         "svg": "image/svg+xml", "md": "text/markdown", "xml": "application/xml",
         "ics": "text/calendar", "py": "text/x-python", "js": "text/javascript",
         "css": "text/css", "tex": "application/x-tex", "ipynb": "application/x-ipynb+json"}


def mime(ext: str) -> str:
    return MIMES.get(ext, "text/plain") + "; charset=utf-8"


def filename(ext: str, source: str) -> str:
    m = re.search(r"<title>([^<]{1,60})</title>", source) if ext == "html" else None
    base = re.sub(r"[^\w-]+", "-", m.group(1)).strip("-").lower() if m else "fichier"
    return f"{base or 'fichier'}.{ext}"


def problems(ext: str, source: str) -> list[str]:
    out: list[str] = []
    if not source.strip():
        return ["fichier vide"]
    try:
        if ext == "py":
            ast.parse(source)
        elif ext in ("json", "ipynb"):
            json.loads(source)
        elif ext in ("svg", "xml"):
            import xml.dom.minidom

            if re.search(r"<!DOCTYPE|<!ENTITY", source, re.I):
                out.append("pas de DOCTYPE ni d'ENTITY")
            else:
                xml.dom.minidom.parseString(source.encode())
            if ext == "svg" and "<script" in source.lower():
                out.append("pas de <script> dans un SVG")
        elif ext == "csv":
            rows = list(csv.reader(io.StringIO(source)))
            widths = {len(r) for r in rows if r}
            if len(widths) > 1:
                out.append(f"lignes de longueurs différentes : {sorted(widths)} colonnes")
        elif ext == "html" and "<html" not in source.lower():
            out.append("document HTML complet attendu (<!doctype html><html>…)")
        elif ext == "ics" and ("BEGIN:VCALENDAR" not in source
                               or "END:VCALENDAR" not in source):
            out.append("calendrier iCalendar incomplet (BEGIN:VCALENDAR … END:VCALENDAR)")
    except SyntaxError as exc:
        out.append(f"erreur de syntaxe Python ligne {exc.lineno} : {exc.msg}")
    except (ValueError, RecursionError) as exc:
        out.append(f"contenu invalide : {exc}")
    except Exception as exc:  # XML mal formé (ExpatError)
        out.append(f"XML mal formé : {exc}")
    return out[:6]
