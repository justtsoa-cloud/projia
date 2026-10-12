"""Markdown → DOCX (Word) en pur Python : un fichier .docx est une archive ZIP de XML.

Pris en charge : titres (#, ##, ###), paragraphes, gras/italique/code en ligne, listes à puces
et numérotées (deux niveaux), tableaux GFM, blocs de code, citations, séparateurs, formules
($…$ rendues en italique, $$…$$ centrées). Styles soignés (police, couleurs, interligne)
pour un document propre sans retouche."""

from __future__ import annotations

import io
import re
import zipfile
from datetime import UTC, datetime
from xml.sax.saxutils import escape

ACCENT = "2E3A87"  # bleu de la marque Tontolo

_CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
<Override PartName="/word/numbering.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml"/>
<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
</Types>"""

_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
</Relationships>"""

_DOC_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/numbering" Target="numbering.xml"/>
</Relationships>"""

_W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'


def _style(sid: str, name: str, size: int, *, bold: bool = False, color: str = "222222",
           before: int = 0, after: int = 120, font: str = "Calibri", italic: bool = False,
           extra: str = "") -> str:
    return (f'<w:style w:type="paragraph" w:styleId="{sid}"><w:name w:val="{name}"/>'
            f'<w:basedOn w:val="Normal"/><w:qFormat/><w:pPr><w:keepNext/>'
            f'<w:spacing w:before="{before}" w:after="{after}"/>{extra}</w:pPr>'
            f'<w:rPr><w:rFonts w:ascii="{font}" w:hAnsi="{font}"/>{"<w:b/>" if bold else ""}'
            f'{"<w:i/>" if italic else ""}<w:color w:val="{color}"/><w:sz w:val="{size}"/></w:rPr>'
            '</w:style>')


_STYLES = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles {_W}>
<w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri" w:cs="Calibri"/>
<w:sz w:val="22"/><w:lang w:val="fr-FR"/></w:rPr></w:rPrDefault>
<w:pPrDefault><w:pPr><w:spacing w:after="120" w:line="276" w:lineRule="auto"/></w:pPr></w:pPrDefault></w:docDefaults>
<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/><w:qFormat/></w:style>
{_style("Title", "Title", 52, bold=True, color=ACCENT, after=240, font="Calibri Light")}
{_style("Heading1", "heading 1", 34, bold=True, color=ACCENT, before=360, after=120,
        extra='<w:pBdr><w:bottom w:val="single" w:sz="6" w:space="2" w:color="C9CDEB"/></w:pBdr>')}
{_style("Heading2", "heading 2", 28, bold=True, color="3949AB", before=240, after=80)}
{_style("Heading3", "heading 3", 24, bold=True, color="444444", before=200, after=60)}
{_style("Quote", "Quote", 22, italic=True, color="555555",
        extra='<w:ind w:left="567"/><w:pBdr><w:left w:val="single" w:sz="18" w:space="8" w:color="9FA8DA"/></w:pBdr>')}
{_style("Code", "Code", 19, font="Consolas", color="1B1B1B", after=0,
        extra='<w:shd w:val="clear" w:color="auto" w:fill="F1F3F9"/><w:ind w:left="284"/>')}
{_style("Formula", "Formula", 24, italic=True, color="1B1B1B", extra='<w:jc w:val="center"/>')}
<w:style w:type="table" w:styleId="Grid"><w:name w:val="Grid"/><w:tblPr><w:tblBorders>
<w:top w:val="single" w:sz="4" w:color="B0B6D9"/><w:left w:val="single" w:sz="4" w:color="B0B6D9"/>
<w:bottom w:val="single" w:sz="4" w:color="B0B6D9"/><w:right w:val="single" w:sz="4" w:color="B0B6D9"/>
<w:insideH w:val="single" w:sz="4" w:color="B0B6D9"/><w:insideV w:val="single" w:sz="4" w:color="B0B6D9"/>
</w:tblBorders><w:tblCellMar><w:left w:w="100" w:type="dxa"/><w:right w:w="100" w:type="dxa"/></w:tblCellMar></w:tblPr></w:style>
</w:styles>"""


def _numbering() -> str:
    def lvl(i: int, fmt: str, text: str) -> str:
        return (f'<w:lvl w:ilvl="{i}"><w:start w:val="1"/><w:numFmt w:val="{fmt}"/>'
                f'<w:lvlText w:val="{text}"/><w:lvlJc w:val="left"/>'
                f'<w:pPr><w:ind w:left="{720 + 360 * i}" w:hanging="360"/></w:pPr></w:lvl>')
    bullets = lvl(0, "bullet", "•") + lvl(1, "bullet", "◦")
    numbers = lvl(0, "decimal", "%1.") + lvl(1, "lowerLetter", "%2)")
    return (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:numbering {_W}>'
            f'<w:abstractNum w:abstractNumId="0">{bullets}</w:abstractNum>'
            f'<w:abstractNum w:abstractNumId="1">{numbers}</w:abstractNum>'
            '<w:num w:numId="1"><w:abstractNumId w:val="0"/></w:num>'
            '<w:num w:numId="2"><w:abstractNumId w:val="1"/></w:num></w:numbering>')


_INLINE = re.compile(r"(\*\*[^*]+\*\*|__[^_]+__|\*[^*\s][^*]*\*|_[^_\s][^_]*_|`[^`]+`|\$[^$\n]+\$)")


def _runs(text: str) -> str:
    """Texte avec **gras**, *italique*, `code` et $formule$ → runs Word."""
    out = []
    for part in _INLINE.split(text):
        if not part:
            continue
        props = ""
        if part.startswith(("**", "__")) and len(part) > 4:
            part, props = part[2:-2], "<w:b/>"
        elif part.startswith("`") and len(part) > 2:
            part, props = part[1:-1], '<w:rFonts w:ascii="Consolas" w:hAnsi="Consolas"/><w:shd w:val="clear" w:fill="F1F3F9"/>'
        elif part.startswith("$") and len(part) > 2:
            part, props = _tex_to_text(part[1:-1]), '<w:i/><w:rFonts w:ascii="Cambria Math" w:hAnsi="Cambria Math"/>'
        elif part[0] in "*_" and part[-1] == part[0] and len(part) > 2:
            part, props = part[1:-1], "<w:i/>"
        out.append(f'<w:r>{f"<w:rPr>{props}</w:rPr>" if props else ""}'
                   f'<w:t xml:space="preserve">{escape(part)}</w:t></w:r>')
    return "".join(out)


_TEX = {r"\times": "×", r"\cdot": "·", r"\leq": "≤", r"\geq": "≥", r"\neq": "≠", r"\pm": "±",
        r"\infty": "∞", r"\pi": "π", r"\alpha": "α", r"\beta": "β", r"\theta": "θ",
        r"\lambda": "λ", r"\Delta": "Δ", r"\sum": "∑", r"\int": "∫", r"\sqrt": "√",
        r"\rightarrow": "→", r"\to": "→", r"\in": "∈", r"\approx": "≈", r"\,": " "}


def _tex_to_text(tex: str) -> str:
    """Formule LaTeX lisible en texte (Word ne lit pas le LaTeX)."""
    def frac(m: re.Match[str]) -> str:
        a, b = (x.strip() for x in m.groups())
        wrap = (lambda x: x if re.fullmatch(r"[\w.,]+", x) else f"({x})")  # noqa: E731
        return f"{wrap(a)}/{wrap(b)}"

    tex = re.sub(r"\\frac\{([^{}]*)\}\{([^{}]*)\}", frac, tex)
    for k, v in _TEX.items():
        tex = tex.replace(k, v)
    tex = re.sub(r"\^\{([^{}]*)\}", r"^\1", tex)
    tex = re.sub(r"_\{([^{}]*)\}", r"_\1", tex)
    return re.sub(r"\\([a-zA-Z]+)", r"\1", tex).replace("{", "").replace("}", "")


def _p(text: str, style: str | None = None, num: tuple[int, int] | None = None) -> str:
    ppr = ""
    if style or num:
        ppr = "<w:pPr>" + (f'<w:pStyle w:val="{style}"/>' if style else "")
        if num:
            ppr += f'<w:numPr><w:ilvl w:val="{num[1]}"/><w:numId w:val="{num[0]}"/></w:numPr>'
        ppr += "</w:pPr>"
    return f"<w:p>{ppr}{_runs(text)}</w:p>"


def _table(rows: list[list[str]]) -> str:
    cols = max(len(r) for r in rows)
    width = 9000 // max(cols, 1)
    out = ['<w:tbl><w:tblPr><w:tblStyle w:val="Grid"/><w:tblW w:w="5000" w:type="pct"/></w:tblPr>',
           "<w:tblGrid>" + f'<w:gridCol w:w="{width}"/>' * cols + "</w:tblGrid>"]
    for i, r in enumerate(rows):
        out.append("<w:tr>")
        for c in [*r, *[""] * (cols - len(r))]:
            shade = '<w:shd w:val="clear" w:fill="E8EAF6"/>' if i == 0 else ""
            text = f"**{c}**" if i == 0 and c else c
            out.append(f'<w:tc><w:tcPr><w:tcW w:w="{width}" w:type="dxa"/>{shade}</w:tcPr>'
                       f"{_p(text)}</w:tc>")
        out.append("</w:tr>")
    out.append("</w:tbl><w:p/>")
    return "".join(out)


def ensure_title(md: str, fallback: str = "Document") -> str:
    """Rend le Markdown d'un modèle acceptable : retire une phrase d'introduction avant le
    premier titre (« Voici la version corrigée : »), et si le texte n'a pas de titre « # »,
    fait du premier titre (ou de la première ligne courte) le titre du document."""
    text = (md or "").replace("\r\n", "\n").strip()
    lines = text.split("\n")
    h1 = next((i for i, ln in enumerate(lines) if re.match(r"^#\s+\S", ln)), None)
    if h1 is not None:
        return "\n".join(lines[h1:]) + "\n"
    first_heading = next((i for i, ln in enumerate(lines) if re.match(r"^#{2,6}\s+\S", ln)),
                         None)
    if first_heading is not None:
        title = re.sub(r"^#+\s+", "", lines[first_heading]).strip()
        return f"# {title}\n" + "\n".join(lines[first_heading + 1:]) + "\n"
    for i, ln in enumerate(lines):
        clean = re.sub(r"[*_`]+", "", ln).strip().rstrip(":")
        if clean and len(clean) <= 100 and not re.match(r"^([-*+]|\d+[.)]|\|)", clean):
            return f"# {clean}\n" + "\n".join(lines[i + 1:]) + "\n"
        if clean:
            break
    return f"# {fallback}\n{text}\n"


def markdown_to_body(md: str) -> tuple[str, str]:
    """(titre, corps XML). Le premier titre « # » devient le titre du document."""
    lines = md.replace("\r\n", "\n").split("\n")
    body: list[str] = []
    title = ""
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if stripped.startswith("```"):
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                body.append(f'<w:p><w:pPr><w:pStyle w:val="Code"/></w:pPr><w:r>'
                            f'<w:t xml:space="preserve">{escape(lines[i])}</w:t></w:r></w:p>')
                i += 1
            body.append("<w:p/>")
        elif stripped.startswith("$$"):
            parts = [stripped[2:]]
            while not parts[-1].rstrip().endswith("$$") and i + 1 < len(lines):
                i += 1
                parts.append(lines[i].strip())
            formula = " ".join(parts).strip().removesuffix("$$").strip()
            body.append(f'<w:p><w:pPr><w:pStyle w:val="Formula"/></w:pPr><w:r><w:t xml:space='
                        f'"preserve">{escape(_tex_to_text(formula))}</w:t></w:r></w:p>')
        elif m := re.match(r"^(#{1,6})\s+(.*)$", stripped):
            level = len(m.group(1))
            if level == 1 and not title:
                title = m.group(2).strip()
                body.append(_p(title, "Title"))
            else:
                body.append(_p(m.group(2).strip(), f"Heading{min(max(level - 1, 1), 3)}"))
        elif stripped.startswith("|") and i + 1 < len(lines) and re.match(
                r"^\|?\s*:?-{2,}", lines[i + 1].strip()):
            rows = [[c.strip() for c in stripped.strip("|").split("|")]]
            i += 2
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            body.append(_table(rows))
            continue
        elif m := re.match(r"^(\s*)[-*+]\s+(.*)$", line):
            body.append(_p(m.group(2), num=(1, 1 if len(m.group(1)) >= 2 else 0)))
        elif m := re.match(r"^(\s*)\d+[.)]\s+(.*)$", line):
            body.append(_p(m.group(2), num=(2, 1 if len(m.group(1)) >= 2 else 0)))
        elif stripped.startswith(">"):
            body.append(_p(stripped.lstrip("> "), "Quote"))
        elif re.match(r"^(-{3,}|\*{3,})$", stripped):
            body.append('<w:p><w:pPr><w:pBdr><w:bottom w:val="single" w:sz="6" w:space="1" '
                        'w:color="C9CDEB"/></w:pBdr></w:pPr></w:p>')
        elif stripped:
            para = [stripped]
            while i + 1 < len(lines) and lines[i + 1].strip() and not re.match(
                    r"^(#|```|\$\$|\||>|\s*[-*+]\s|\s*\d+[.)]\s)", lines[i + 1]):
                i += 1
                para.append(lines[i].strip())
            body.append(_p(" ".join(para)))
        i += 1
    return title, "".join(body)


def build(markdown: str, *, title: str | None = None, author: str = "Tontolo") -> bytes:
    doc_title, body = markdown_to_body(markdown)
    doc_title = title or doc_title or "Document"
    sect = ('<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1134" w:right="1134" '
            'w:bottom="1134" w:left="1134" w:header="708" w:footer="708" w:gutter="0"/></w:sectPr>')
    document = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document {_W}>'
                f"<w:body>{body}{sect}</w:body></w:document>")
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    core = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><cp:coreProperties '
            'xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" '
            'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
            f"<dc:title>{escape(doc_title)}</dc:title><dc:creator>{escape(author)}</dc:creator>"
            f'<dcterms:created xsi:type="dcterms:W3CDTF">{now}</dcterms:created>'
            "</cp:coreProperties>")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", _CONTENT_TYPES)
        z.writestr("_rels/.rels", _RELS)
        z.writestr("word/_rels/document.xml.rels", _DOC_RELS)
        z.writestr("word/document.xml", document)
        z.writestr("word/styles.xml", _STYLES)
        z.writestr("word/numbering.xml", _numbering())
        z.writestr("docProps/core.xml", core)
    return buf.getvalue()


def check(data: bytes) -> list[str]:
    """Contrôle du fichier produit : archive valide et XML bien formé (problèmes trouvés)."""
    import xml.dom.minidom

    problems = []
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            for name in ("word/document.xml", "word/styles.xml", "word/numbering.xml"):
                try:
                    part = z.read(name)
                    if b"<!DOCTYPE" in part[:4096] or b"<!ENTITY" in part:
                        raise ValueError("DTD ou entité interdite")
                    xml.dom.minidom.parseString(part)  # nosec B318
                except Exception as exc:  # XML mal formé
                    problems.append(f"{name} : {exc}")
    except zipfile.BadZipFile:
        problems.append("archive DOCX invalide")
    return problems
