"""Export PDF d'une discussion, sans dépendance ni service en ligne (la discussion reste
sur l'appareil). Polices standard du PDF (Helvetica, Courier) en WinAnsi : accents
français et malgaches compris ; les caractères hors de ce jeu (émojis, symboles rares)
sont remplacés. Mise en page simple : orateur en gras, paragraphes, titres Markdown,
blocs de code en chasse fixe, numéros de page."""

from __future__ import annotations

import re
import unicodedata
import zlib
from dataclasses import dataclass

W, H = 595.0, 842.0  # A4 en points
MARGIN = 56.0
BODY, SMALL, CODE = 10.5, 8.5, 9.0
LEAD = 1.35

# Largeurs Helvetica (AFM, millièmes de cadratin) des caractères 32 à 126.
_HELV = [278, 278, 355, 556, 556, 889, 667, 191, 333, 333, 389, 584, 278, 333, 278, 278,
         *[556] * 10, 278, 278, 584, 584, 584, 556, 1015, 667, 667, 722, 722, 667, 611,
         778, 722, 278, 500, 667, 556, 833, 722, 778, 667, 778, 722, 667, 611, 722, 667,
         944, 667, 667, 611, 278, 278, 278, 469, 556, 333, 556, 556, 500, 556, 556, 278,
         556, 556, 222, 222, 500, 222, 833, 556, 556, 556, 556, 333, 500, 278, 556, 500,
         722, 500, 500, 500, 334, 260, 334, 584]
_SUBST = {
    "\u2010": "-", "\u2011": "-", "\u2012": "-", "\u2015": "-", "\u2212": "-",
    "→": "->", "←": "<-", "⇒": "=>", "≤": "<=", "≥": ">=", "≠": "!=", "×": "x",
    "✓": "v", "✔": "v", "✗": "x", "\t": "    ", "\u00a0": " ", "\u202f": " ",
}


def _clean(text: str) -> str:
    out = []
    for ch in text:
        ch = _SUBST.get(ch, ch)
        try:
            ch.encode("cp1252")
            out.append(ch)
        except UnicodeEncodeError:
            base = unicodedata.normalize("NFKD", ch).encode("cp1252", "ignore").decode("cp1252")
            out.append(base if base.strip() else ("" if unicodedata.category(ch)[0] == "S"
                                                  else "?"))
    return "".join(out)


def _width(text: str, size: float, font: str) -> float:
    if font == "F3":
        return len(text) * 0.6 * size
    total = 0
    for ch in text:
        o = ord(ch)
        if 32 <= o <= 126:
            total += _HELV[o - 32]
        else:
            base = unicodedata.normalize("NFKD", ch)[:1]
            total += _HELV[ord(base) - 32] if base and 32 <= ord(base) <= 126 else 556
    return total * size / 1000 * (1.08 if font == "F2" else 1.0)


def _wrap(text: str, size: float, font: str, width: float) -> list[str]:
    if not text:
        return [""]
    if font == "F3":  # code : coupure brute à la largeur, espaces conservés
        n = max(1, int(width / (0.6 * size)))
        return [text[i:i + n] for i in range(0, len(text), n)]
    lines: list[str] = []
    cur = ""
    for word in text.split():
        cand = f"{cur} {word}" if cur else word
        if _width(cand, size, font) <= width:
            cur = cand
            continue
        if cur:
            lines.append(cur)
        while _width(word, size, font) > width:  # mot trop long (URL) : coupé
            cut = len(word)
            while cut > 1 and _width(word[:cut], size, font) > width:
                cut -= 1
            lines.append(word[:cut])
            word = word[cut:]
        cur = word
    lines.append(cur)
    return lines


_TABLE_SEP = re.compile(r"^\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?$")


def _table_row(line: str) -> str | None:
    """Ligne de tableau Markdown → cellules séparées par « | » ; la ligne de séparation
    (|---|---|) est supprimée (None)."""
    if _TABLE_SEP.match(line):
        return None
    cells = [c.strip() for c in line.strip().strip("|").split("|")]
    return "  |  ".join(c for c in cells if c)


def _inline(text: str) -> str:
    """Marques Markdown en ligne retirées (gras, italique, code, liens)."""
    text = re.sub(r"<(https?://[^>\s]+)>", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r"\1 (\2)", text)
    text = re.sub(r"(\*\*|__)(.+?)\1", r"\2", text)
    text = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"\1", text)
    return text.replace("`", "")


@dataclass
class _Line:
    text: str
    font: str
    size: float
    gap: float = 0.0  # espace avant la ligne
    sub: str = ""  # précision en gris sur la même ligne (le modèle)


def _layout(title: str, turns: list[tuple[str, str, str]]) -> list[_Line]:
    width = W - 2 * MARGIN
    out = [_Line(t, "F2", 16) for t in _wrap(_clean(title), 16, "F2", width)]
    for who, sub, body in turns:
        out.append(_Line(_clean(who), "F2", BODY + 0.5, gap=14, sub=_clean(sub)))
        in_code = False
        gap = 3.0
        for raw in body.replace("\r", "").split("\n"):
            if raw.strip().startswith("```"):
                in_code = not in_code
                gap = 4.0
                continue
            if in_code:
                for t in _wrap(_clean(raw.rstrip()), CODE, "F3", width - 8):
                    out.append(_Line(t, "F3", CODE, gap=gap))
                    gap = 0.0
                continue
            line = raw.strip()
            if not line:
                gap = 5.0
                continue
            if line.startswith("|") and line.count("|") >= 2:
                row = _table_row(line)
                if row is None:
                    continue
                line = row
            elif re.fullmatch(r"-{3,}|\*{3,}|_{3,}", line):
                gap = 8.0  # filet horizontal Markdown : simple espace
                continue
            font, size = "F1", BODY
            if m := re.match(r"(#{1,6})\s+(.*)", line):
                font, size, line = "F2", BODY + max(0, 4 - len(m.group(1))) * 1.5, m.group(2)
                gap = max(gap, 6.0)
            elif m := re.match(r"[-*+]\s+(.*)", line):
                line = "• " + m.group(1)
            for t in _wrap(_clean(_inline(line)), size, font, width):
                out.append(_Line(t, font, size, gap=gap))
                gap = 0.0
    return out


def _esc(text: str) -> bytes:
    raw = text.encode("cp1252", "replace")
    return raw.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")


def build(title: str, turns: list[tuple[str, str, str]], *, footer: str = "Tontolo") -> bytes:
    """`turns` : (orateur, précision en petit — le modèle —, texte Markdown)."""
    pages: list[list[bytes]] = [[]]
    y = H - MARGIN
    for ln in _layout(title, turns):
        step = ln.size * LEAD
        y -= ln.gap + step
        if y < MARGIN + 18:
            pages.append([])
            y = H - MARGIN - step
        if ln.font == "F3":
            pages[-1].append(b"0.95 g %.2f %.2f %.2f %.2f re f 0 g"
                             % (MARGIN, y - 2.5, W - 2 * MARGIN, step))
        x = MARGIN + (4 if ln.font == "F3" else 0)
        pages[-1].append(b"BT /%s %.1f Tf %.2f %.2f Td (%s) Tj ET"
                         % (ln.font.encode(), ln.size, x, y, _esc(ln.text)))
        if ln.sub:
            pages[-1].append(b"0.45 g BT /F1 %.1f Tf %.2f %.2f Td (%s) Tj ET 0 g"
                             % (SMALL, x + _width(ln.text, ln.size, ln.font) + 6, y,
                                _esc(ln.sub)))
    return _assemble(pages, _clean(footer))


def _assemble(pages: list[list[bytes]], footer: str) -> bytes:
    n = len(pages)
    objs: list[bytes] = []
    fonts = b"<< /F1 3 0 R /F2 4 0 R /F3 5 0 R >>"
    objs.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    kids = " ".join(f"{6 + 2 * i} 0 R" for i in range(n)).encode()
    objs.append(b"<< /Type /Pages /Kids [%s] /Count %d >>" % (kids, n))
    for name in (b"Helvetica", b"Helvetica-Bold", b"Courier"):
        objs.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /%s "
                    b"/Encoding /WinAnsiEncoding >>" % name)
    for i, ops in enumerate(pages):
        foot = f"{footer} · {i + 1}/{n}"
        ops = [*ops, b"0.55 g BT /F1 8 Tf %.2f %.2f Td (%s) Tj ET 0 g"
               % (W - MARGIN - _width(foot, 8, "F1"), MARGIN / 2, _esc(foot))]
        data = zlib.compress(b"\n".join(ops))
        objs.append(b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %d %d] "
                    b"/Resources << /Font %s >> /Contents %d 0 R >>"
                    % (W, H, fonts, 7 + 2 * i))
        objs.append(b"<< /Length %d /Filter /FlateDecode >>\nstream\n%s\nendstream"
                    % (len(data), data))
    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for k, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n%s\nendobj\n" % (k, body)
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offsets)
    out += (b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n"
            % (len(objs) + 1, xref))
    return bytes(out)
