"""Pièces jointes de tous types → texte, localement, sans dépendance ni service en ligne.

- Texte et code (md, csv, json, yaml, sources…) : lus tels quels.
- Bureautique : docx, pptx, xlsx, odt, ods, odp, epub (archives zip de XML), rtf.
- Archives zip et tar(.gz) : liste du contenu, puis texte des fichiers lisibles.
- Son et vidéo : voir `media_kind` (transcription par le service vocal du cœur).

Garde-fous : rien n'est jamais exécuté ni écrit sur le disque ; taille, nombre de fichiers et
taux de compression bornés (bombe zip) ; XML sans DTD ni entité (billion laughs, XXE) ; une
archive dans une archive est seulement listée.
"""

from __future__ import annotations

import io
import posixpath
import re
import tarfile
import zipfile
from xml.etree import ElementTree as ET

from tontolo.documents import DocumentError, html_to_text

MAX_MEMBERS = 300
MAX_TOTAL = 60 * 1024 * 1024       # décompressé, toute l'archive
MAX_MEMBER = 20 * 1024 * 1024      # décompressé, un fichier
MAX_RATIO = 120                    # au-delà : bombe de compression
MAX_TEXT = 2_000_000

TEXT_EXT = frozenset(" ".join((
    "txt md markdown rst csv tsv json jsonl ndjson xml yaml yml toml ini cfg conf log srt vtt "
    "tex bib sql py js mjs ts tsx jsx dart java kt kts c h cpp hpp cc cs go rs rb php sh bash "
    "zsh ps1 bat swift r m lua css scss sass less vue svelte gradle properties env gitignore "
    "dockerfile makefile ipynb org adoc",
)).split())
HTML_EXT = frozenset({"html", "htm", "xhtml"})
OFFICE_EXT = frozenset({"docx", "pptx", "xlsx", "odt", "ods", "odp", "epub"})
ARCHIVE_EXT = frozenset({"zip", "tar", "tgz", "gz"})
AUDIO_EXT = frozenset({"mp3", "wav", "m4a", "aac", "ogg", "oga", "opus", "flac", "amr", "weba"})
VIDEO_EXT = frozenset({"mp4", "mov", "mkv", "webm", "avi", "3gp", "m4v"})


def ext_of(name: str) -> str:
    low = name.lower().rsplit("/", 1)[-1]
    if low.endswith((".tar.gz", ".tgz")):
        return "tgz"
    if low in ("dockerfile", "makefile"):
        return low
    return low.rsplit(".", 1)[-1] if "." in low else ""


def media_kind(name: str) -> str | None:
    """« audio » ou « video » : transcrits par le service vocal, pas extraits ici."""
    e = ext_of(name)
    return "audio" if e in AUDIO_EXT else "video" if e in VIDEO_EXT else None


def supported(name: str) -> bool:
    e = ext_of(name)
    return (e in TEXT_EXT or e in HTML_EXT or e in OFFICE_EXT or e in ARCHIVE_EXT
            or e in {"pdf", "rtf"} or media_kind(name) is not None)


# --- Texte -----------------------------------------------------------------------------------

def decode(data: bytes) -> str:
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return data.decode("utf-16", "replace")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("latin-1")


def _looks_binary(data: bytes) -> bool:
    return b"\x00" in data[:4096] and data[:2] not in (b"\xff\xfe", b"\xfe\xff")


def text_pages(name: str, data: bytes) -> list[str]:
    if _looks_binary(data):
        raise DocumentError(f"« {name} » n'est pas un fichier texte.")
    text = decode(data)
    if ext_of(name) in HTML_EXT or text.lstrip()[:15].lower().startswith(("<!doctype", "<html")):
        text = html_to_text(text)
    elif ext_of(name) == "ipynb":
        text = _notebook(text)
    return [text[:MAX_TEXT]]


def _notebook(raw: str) -> str:
    import json

    try:
        cells = json.loads(raw).get("cells", [])
    except (ValueError, AttributeError):
        return raw
    out = []
    for c in cells if isinstance(cells, list) else []:
        src = c.get("source", "") if isinstance(c, dict) else ""
        src = "".join(src) if isinstance(src, list) else str(src)
        out.append(f"```{'python' if c.get('cell_type') == 'code' else ''}\n{src}\n```"
                   if c.get("cell_type") == "code" else src)
    return "\n\n".join(out)


def rtf_to_text(raw: str) -> str:
    """RTF simple : groupes de police/couleur/images retirés, mots de contrôle effacés."""
    text = re.sub(r"\{(?:\\\*)?\\(fonttbl|colortbl|stylesheet|info|pict|header|footer)[^{}]*"
                  r"(\{[^{}]*\}[^{}]*)*\}", "", raw)
    text = re.sub(r"\\par[d]?\b|\\line\b", "\n", text)
    text = re.sub(r"\\'([0-9a-f]{2})", lambda m: bytes([int(m.group(1), 16)]).decode("cp1252",
                                                                                   "replace"), text)
    text = re.sub(r"\\u(-?\d+)\??", lambda m: chr(int(m.group(1)) % 65536), text)
    text = re.sub(r"\\[a-zA-Z]+-?\d* ?|[{}]", "", text)
    return re.sub(r"\n\s*\n+", "\n\n", text).strip()


# --- XML bureautique -------------------------------------------------------------------------

def _xml(data: bytes) -> ET.Element:
    head = data[:4096].upper()
    if b"<!DOCTYPE" in head or b"<!ENTITY" in data.upper():
        raise DocumentError("Document refusé (XML avec DTD ou entités).")
    try:
        return ET.fromstring(data)
    except ET.ParseError as exc:
        raise DocumentError("Document illisible (XML abîmé).") from exc


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _texts(root: ET.Element, para: set[str], text_tags: set[str]) -> str:
    """Texte d'un arbre XML : un saut de ligne par paragraphe, tabulations et sauts gardés."""
    lines: list[str] = []
    for p in root.iter():
        if _local(p.tag) not in para:
            continue
        parts = []
        for el in p.iter():
            name = _local(el.tag)
            if name in text_tags and el.text:
                parts.append(el.text)
            elif name in ("tab",):
                parts.append("\t")
            elif name in ("br", "line-break"):
                parts.append("\n")
        line = "".join(parts).strip()
        if line:
            lines.append(line)
    return "\n".join(lines)


def _safe_zip(data: bytes) -> zipfile.ZipFile:
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise DocumentError("Archive ou document abîmé.") from exc
    infos = z.infolist()
    if len(infos) > MAX_MEMBERS * 10:
        raise DocumentError("Archive refusée (trop de fichiers).")
    total = sum(i.file_size for i in infos)
    packed = sum(i.compress_size for i in infos) or 1
    if total > MAX_TOTAL * 4 or total / packed > MAX_RATIO:
        raise DocumentError("Archive refusée (taille décompressée suspecte).")
    return z


def _read(z: zipfile.ZipFile, name: str) -> bytes:
    info = z.getinfo(name)
    if info.file_size > MAX_MEMBER or info.file_size / (info.compress_size or 1) > MAX_RATIO:
        raise DocumentError("Document refusé (partie trop volumineuse).")
    with z.open(info) as fh:
        return fh.read(MAX_MEMBER + 1)[:MAX_MEMBER]


def _n(name: str) -> int:
    m = re.search(r"(\d+)\.xml$", name)
    return int(m.group(1)) if m else 0


def office_pages(name: str, data: bytes) -> list[str]:
    e = ext_of(name)
    z = _safe_zip(data)
    names = set(z.namelist())
    if e == "docx":
        root = _xml(_read(z, "word/document.xml"))
        return [_texts(root, {"p"}, {"t"})]
    if e == "pptx":
        slides = sorted((n for n in names if re.match(r"ppt/slides/slide\d+\.xml$", n)), key=_n)
        return [f"Diapositive {_n(s)}\n" + _texts(_xml(_read(z, s)), {"p"}, {"t"})
                for s in slides[:500]]
    if e == "xlsx":
        return _xlsx(z, names)
    if e in ("odt", "ods", "odp"):
        root = _xml(_read(z, "content.xml"))
        lines = ["".join(p.itertext()).strip() for p in root.iter()
                 if _local(p.tag) in ("p", "h")]
        return ["\n".join(x for x in lines if x)]
    if e == "epub":
        return _epub(z, names)
    raise DocumentError("Format de document non pris en charge.")


def _xlsx(z: zipfile.ZipFile, names: set[str]) -> list[str]:
    shared: list[str] = []
    if "xl/sharedStrings.xml" in names:
        for si in _xml(_read(z, "xl/sharedStrings.xml")):
            shared.append("".join(t.text or "" for t in si.iter() if _local(t.tag) == "t"))
    pages = []
    sheets = sorted((n for n in names if re.match(r"xl/worksheets/sheet\d+\.xml$", n)), key=_n)
    for s in sheets[:50]:
        rows = []
        for row in _xml(_read(z, s)).iter():
            if _local(row.tag) != "row":
                continue
            cells = []
            for c in row:
                if _local(c.tag) != "c":
                    continue
                v = next((x.text or "" for x in c.iter() if _local(x.tag) in ("v", "t")), "")
                if c.get("t") == "s" and v.isdigit() and int(v) < len(shared):
                    v = shared[int(v)]
                cells.append(v.replace("\t", " "))
            if any(cells):
                rows.append("\t".join(cells))
            if len(rows) >= 5000:
                break
        pages.append(f"Feuille {_n(s)}\n" + "\n".join(rows))
    return pages


def _epub(z: zipfile.ZipFile, names: set[str]) -> list[str]:
    order: list[str] = []
    opf = next((n for n in names if n.endswith(".opf")), None)
    if opf:
        root = _xml(_read(z, opf))
        base = posixpath.dirname(opf)
        items = {i.get("id"): i.get("href") for i in root.iter() if _local(i.tag) == "item"}
        for ref in root.iter():
            if _local(ref.tag) == "itemref" and items.get(ref.get("idref")):
                order.append(posixpath.normpath(posixpath.join(base, str(items[ref.get("idref")]))))
    if not order:
        order = sorted(n for n in names if n.endswith((".xhtml", ".html", ".htm")))
    pages = []
    for n in order[:500]:
        if n in names:
            text = html_to_text(decode(_read(z, n)))
            if text.strip():
                pages.append(text)
    return pages


# --- Archives --------------------------------------------------------------------------------

def _member_ok(name: str) -> bool:
    return not (name.startswith(("/", "\\")) or ".." in name.split("/") or "__MACOSX" in name
                or name.rsplit("/", 1)[-1].startswith("._"))


def archive_pages(name: str, data: bytes) -> list[str]:
    """Liste du contenu, puis texte des fichiers lisibles (une page par fichier)."""
    members: list[tuple[str, int, bytes | None]] = []  # (chemin, taille, contenu ou None)
    total = 0
    seen = 0  # fichiers de l'archive (au-delà de MAX_MEMBERS : seulement comptés)
    if ext_of(name) == "zip" or data[:4] == b"PK\x03\x04":
        z = _safe_zip(data)
        for info in z.infolist():
            if info.is_dir() or not _member_ok(info.filename):
                continue
            seen += 1
            if len(members) >= MAX_MEMBERS:
                continue
            body = None
            if (_readable(info.filename) and info.file_size <= MAX_MEMBER
                    and total + info.file_size <= MAX_TOTAL):
                body = _read(z, info.filename)
                total += len(body)
            members.append((info.filename, info.file_size, body))
    else:
        try:
            tar = tarfile.open(fileobj=io.BytesIO(data), mode="r:*")  # noqa: SIM115
        except (tarfile.TarError, EOFError, OSError) as exc:
            raise DocumentError("Archive illisible.") from exc
        with tar:
            for m in tar:
                if not m.isfile() or not _member_ok(m.name):
                    continue  # liens, périphériques, chemins sortants : ignorés
                seen += 1
                if len(members) >= MAX_MEMBERS:
                    continue
                body = None
                if _readable(m.name) and m.size <= MAX_MEMBER and total + m.size <= MAX_TOTAL:
                    fh = tar.extractfile(m)
                    body = fh.read(MAX_MEMBER + 1)[:MAX_MEMBER] if fh else None
                    total += len(body or b"")
                members.append((m.name, m.size, body))
    if not members:
        raise DocumentError("Archive vide.")
    listing = "\n".join(f"- {n} ({_size(s)})" for n, s, _ in members)
    count = (f"{len(members)} fichiers" if seen == len(members)
             else f"{len(members)} premiers fichiers sur {seen}")
    pages = [f"Contenu de l'archive « {name} » ({count}) :\n{listing}"]
    for n, _, body in members:
        if body is None:
            continue
        try:
            sub = extract_any(n, body, nested=True)
        except DocumentError:
            continue
        pages += [f"=== {n} ===\n{p}" for p in sub if p.strip()]
    return pages


def _readable(name: str) -> bool:
    e = ext_of(name)
    return e in TEXT_EXT or e in HTML_EXT or e in OFFICE_EXT or e in {"pdf", "rtf"}


def _size(n: int) -> str:
    return f"{n / 1024 / 1024:.1f} Mo" if n >= 1024 * 1024 else f"{max(1, n // 1024)} Ko"


# --- Point d'entrée --------------------------------------------------------------------------

def extract_any(name: str, data: bytes, *, nested: bool = False) -> list[str]:
    """Texte par page d'une pièce jointe (hors son et vidéo, transcrits ailleurs)."""
    from tontolo.documents import _pdf_pages

    e = ext_of(name)
    if data[:5] == b"%PDF-" or e == "pdf":
        return _pdf_pages(data)
    if e in OFFICE_EXT:
        return office_pages(name, data)
    if e in ARCHIVE_EXT or (not e and data[:4] == b"PK\x03\x04"):
        if nested:
            raise DocumentError("Archive dans une archive : seulement listée.")
        return archive_pages(name, data)
    if e == "rtf" or data[:5] == b"{\\rtf":
        return [rtf_to_text(decode(data))]
    if media_kind(name):
        raise DocumentError("Son ou vidéo : transcription nécessaire.")
    return text_pages(name, data)
