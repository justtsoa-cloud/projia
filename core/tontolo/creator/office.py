"""Classeurs Excel (XLSX) et présentations PowerPoint (PPTX) en pur Python (archives ZIP
de XML Office Open), sans dépendance : fonctionne aussi sur Android.

- XLSX : JSON {"sheets": [{"name", "rows": [[…]]}]} ; nombres, texte et formules (« =SUM(…) »),
  en-tête en gras sur fond coloré, largeur de colonnes ajustée, première ligne figée.
- PPTX : Markdown (« # » diapositive de titre, « ## » diapositive, puces « - », notes « > »),
  thème sobre aux couleurs de Tontolo, 16:9."""

from __future__ import annotations

import io
import json
import re
import zipfile
from typing import Any
from xml.sax.saxutils import escape

# --- XLSX -------------------------------------------------------------------------------


def _col(n: int) -> str:
    s = ""
    n += 1
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def parse_sheets(text: str) -> list[dict[str, Any]]:
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        raise ValueError("classeur introuvable (JSON attendu)")
    data = json.loads(m.group(0))
    sheets = data.get("sheets") if isinstance(data, dict) else None
    if not isinstance(sheets, list) or not sheets:
        raise ValueError("« sheets » doit être une liste non vide")
    return sheets


def xlsx_problems(sheets: list[dict[str, Any]]) -> list[str]:
    problems = []
    names = set()
    for s in sheets:
        name = str(s.get("name") or "")
        rows = s.get("rows")
        if not name or len(name) > 31 or re.search(r"[\[\]:*?/\\]", name):
            problems.append(f"nom de feuille invalide « {name} » (1 à 31 caractères, sans []:*?/\\)")
        if name in names:
            problems.append(f"feuille « {name} » en double")
        names.add(name)
        if not isinstance(rows, list) or not rows or not all(isinstance(r, list) for r in rows):
            problems.append(f"feuille « {name} » : « rows » doit être une liste de lignes")
            continue
        width = len(rows[0])
        if any(len(r) != width for r in rows):
            problems.append(f"feuille « {name} » : toutes les lignes doivent avoir {width} cellules")
        for r in rows:
            for c in r:
                if isinstance(c, str) and c.startswith("=") and c.count("(") != c.count(")"):
                    problems.append(f"formule mal parenthésée : {c[:40]}")
    return problems[:8]


def build_xlsx(sheets: list[dict[str, Any]]) -> bytes:
    shared: list[str] = []
    index: dict[str, int] = {}

    def sst(text: str) -> int:
        if text not in index:
            index[text] = len(shared)
            shared.append(text)
        return index[text]

    sheet_xml = []
    for s in sheets:
        rows = s.get("rows") or []
        widths: dict[int, int] = {}
        out = []
        for r_i, row in enumerate(rows):
            cells = []
            for c_i, val in enumerate(row):
                ref = f"{_col(c_i)}{r_i + 1}"
                style = ' s="1"' if r_i == 0 else ""
                widths[c_i] = max(widths.get(c_i, 8), min(len(str(val)) + 2, 60))
                if isinstance(val, bool):
                    cells.append(f'<c r="{ref}" t="b"{style}><v>{int(val)}</v></c>')
                elif isinstance(val, int | float):
                    cells.append(f'<c r="{ref}"{style}><v>{val}</v></c>')
                elif isinstance(val, str) and val.startswith("=") and len(val) > 1:
                    cells.append(f'<c r="{ref}"{style}><f>{escape(val[1:])}</f></c>')
                elif val is None or val == "":
                    continue
                else:
                    cells.append(f'<c r="{ref}" t="s"{style}><v>{sst(str(val))}</v></c>')
            out.append(f'<row r="{r_i + 1}">{"".join(cells)}</row>')
        cols = "".join(f'<col min="{i + 1}" max="{i + 1}" width="{w}" customWidth="1"/>'
                       for i, w in sorted(widths.items()))
        sheet_xml.append(
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" '
            'activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>'
            f'{f"<cols>{cols}</cols>" if cols else ""}<sheetData>{"".join(out)}</sheetData>'
            '</worksheet>')
    ns = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
    rel_ns = 'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
    workbook = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook {ns} {rel_ns}>'
                '<sheets>' + "".join(
                    f'<sheet name="{escape(str(s.get("name") or f"Feuille{i + 1}"))[:31]}" '
                    f'sheetId="{i + 1}" r:id="rId{i + 1}"/>' for i, s in enumerate(sheets))
                + '</sheets><calcPr fullCalcOnLoad="1"/></workbook>')
    wb_rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships '
               'xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' + "".join(
                   f'<Relationship Id="rId{i + 1}" Type="http://schemas.openxmlformats.org/'
                   f'officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i + 1}'
                   '.xml"/>' for i in range(len(sheets)))
               + f'<Relationship Id="rId{len(sheets) + 1}" Type="http://schemas.openxmlformats.'
               'org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
               f'<Relationship Id="rId{len(sheets) + 2}" Type="http://schemas.openxmlformats.'
               'org/officeDocument/2006/relationships/sharedStrings" Target="sharedStrings.xml"/>'
               '</Relationships>')
    styles = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><styleSheet {ns}>'
              '<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font>'
              '<font><b/><sz val="11"/><color rgb="FFFFFFFF"/><name val="Calibri"/></font></fonts>'
              '<fills count="3"><fill><patternFill patternType="none"/></fill>'
              '<fill><patternFill patternType="gray125"/></fill>'
              '<fill><patternFill patternType="solid"><fgColor rgb="FF2E3A87"/></patternFill>'
              '</fill></fills><borders count="1"><border/></borders>'
              '<cellStyleXfs count="1"><xf/></cellStyleXfs><cellXfs count="2"><xf/>'
              '<xf fontId="1" fillId="2" applyFont="1" applyFill="1"/></cellXfs></styleSheet>')
    sst_xml = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><sst {ns} '
               f'count="{len(shared)}" uniqueCount="{len(shared)}">'
               + "".join(f'<si><t xml:space="preserve">{escape(t)}</t></si>' for t in shared)
               + "</sst>")
    types = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://'
             'schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" '
             'ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
             '<Default Extension="xml" ContentType="application/xml"/>'
             '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-'
             'officedocument.spreadsheetml.sheet.main+xml"/>'
             '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-'
             'officedocument.spreadsheetml.styles+xml"/>'
             '<Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.'
             'openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>' + "".join(
                 f'<Override PartName="/xl/worksheets/sheet{i + 1}.xml" ContentType="application/'
                 'vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                 for i in range(len(sheets))) + "</Types>")
    rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://'
            'schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/'
            'officeDocument" Target="xl/workbook.xml"/></Relationships>')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", types)
        z.writestr("_rels/.rels", rels)
        z.writestr("xl/workbook.xml", workbook)
        z.writestr("xl/_rels/workbook.xml.rels", wb_rels)
        z.writestr("xl/styles.xml", styles)
        z.writestr("xl/sharedStrings.xml", sst_xml)
        for i, x in enumerate(sheet_xml):
            z.writestr(f"xl/worksheets/sheet{i + 1}.xml", x)
    return buf.getvalue()


# --- PPTX -------------------------------------------------------------------------------

EMU_W, EMU_H = 12192000, 6858000  # 16:9
_P = ('xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
      'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
      'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"')


def parse_slides(md: str) -> tuple[str, list[dict[str, Any]]]:
    """(titre, diapositives [{title, bullets: [(niveau, texte)], notes}])."""
    title = ""
    slides: list[dict[str, Any]] = []
    for raw in md.replace("\r\n", "\n").split("\n"):
        line = raw.rstrip()
        if m := re.match(r"^#\s+(.*)", line):
            title = title or m.group(1).strip()
            slides.append({"title": m.group(1).strip(), "bullets": [], "notes": "", "cover": True})
        elif m := re.match(r"^##+\s+(.*)", line):
            slides.append({"title": m.group(1).strip(), "bullets": [], "notes": "", "cover": False})
        elif not slides:
            continue
        elif m := re.match(r"^(\s*)[-*+]\s+(.*)", line):
            slides[-1]["bullets"].append((1 if len(m.group(1)) >= 2 else 0, m.group(2).strip()))
        elif line.startswith(">"):
            slides[-1]["notes"] += line.lstrip("> ") + " "
        elif line.strip():
            slides[-1]["bullets"].append((0, line.strip()))
    return title, slides


def pptx_problems(slides: list[dict[str, Any]]) -> list[str]:
    problems = []
    if not slides:
        problems.append("aucune diapositive (« # Titre » puis « ## Diapositive »)")
    for s in slides:
        if not s["cover"] and len(s["bullets"]) > 7:
            problems.append(f"diapositive « {s['title'][:40]} » : {len(s['bullets'])} points, 7 au"
                            " maximum (coupe en deux)")
        for _, b in s["bullets"]:
            if len(b) > 160:
                problems.append(f"point trop long dans « {s['title'][:40]} » : phrases courtes")
                break
    return problems[:8]


def _clean(text: str) -> str:
    return re.sub(r"\*\*|__|`", "", text)


def _shape(sid: int, name: str, x: int, y: int, w: int, h: int, paras: str) -> str:
    return (f'<p:sp><p:nvSpPr><p:cNvPr id="{sid}" name="{name}"/><p:cNvSpPr txBox="1"/><p:nvPr/>'
            f'</p:nvSpPr><p:spPr><a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{w}" cy="{h}"/></a:xfrm>'
            '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr><p:txBody><a:bodyPr wrap='
            f'"square"><a:normAutofit/></a:bodyPr><a:lstStyle/>{paras}</p:txBody></p:sp>')


def _para(text: str, size: int, color: str, *, bold: bool = False, level: int = 0,
          bullet: bool = False, align: str = "l") -> str:
    ppr = f'<a:pPr algn="{align}" lvl="{level}"'
    if bullet:
        ppr += f' marL="{342900 + level * 342900}" indent="-285750"><a:buChar char="•"/></a:pPr>'
    else:
        ppr += "><a:buNone/></a:pPr>"
    return (f'<a:p>{ppr}<a:r><a:rPr lang="fr-FR" sz="{size}" b="{int(bold)}" dirty="0">'
            f'<a:solidFill><a:srgbClr val="{color}"/></a:solidFill><a:latin typeface="Calibri"/>'
            f'</a:rPr><a:t>{escape(_clean(text))}</a:t></a:r></a:p>')


def _slide_xml(s: dict[str, Any], number: int, total: int) -> str:
    if s["cover"]:
        bg = "2E3A87"
        shapes = _shape(2, "Titre", 700000, 2300000, EMU_W - 1400000, 1400000,
                        _para(s["title"], 4400, "FFFFFF", bold=True, align="ctr"))
        sub = " · ".join(b for _, b in s["bullets"][:2])
        if sub:
            shapes += _shape(3, "Sous-titre", 700000, 3800000, EMU_W - 1400000, 900000,
                             _para(sub, 2200, "C5CAE9", align="ctr"))
    else:
        bg = "FFFFFF"
        shapes = ('<p:sp><p:nvSpPr><p:cNvPr id="4" name="Bandeau"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>'
                  f'<p:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{EMU_W}" cy="120000"/></a:xfrm>'
                  '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom><a:solidFill><a:srgbClr val='
                  '"2E3A87"/></a:solidFill></p:spPr></p:sp>')
        shapes += _shape(2, "Titre", 600000, 350000, EMU_W - 1200000, 1000000,
                         _para(s["title"], 3200, "2E3A87", bold=True))
        body = "".join(_para(b, 2000 if lvl else 2400, "333333", level=lvl, bullet=True)
                       for lvl, b in s["bullets"]) or _para("", 2000, "333333")
        shapes += _shape(3, "Contenu", 600000, 1500000, EMU_W - 1200000, EMU_H - 2200000, body)
        shapes += _shape(5, "Numéro", EMU_W - 1600000, EMU_H - 600000, 1000000, 400000,
                         _para(f"{number}/{total}", 1200, "9E9E9E", align="r"))
    return (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><p:sld {_P}><p:cSld><p:bg>'
            f'<p:bgPr><a:solidFill><a:srgbClr val="{bg}"/></a:solidFill><a:effectLst/></p:bgPr>'
            '</p:bg><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/>'
            '</p:nvGrpSpPr><p:grpSpPr/>' + shapes + '</p:spTree></p:cSld><p:clrMapOvr>'
            '<a:masterClrMapping/></p:clrMapOvr></p:sld>')


_THEME = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><a:theme xmlns:a="http://'
          'schemas.openxmlformats.org/drawingml/2006/main" name="Tontolo"><a:themeElements>'
          '<a:clrScheme name="Tontolo"><a:dk1><a:srgbClr val="212121"/></a:dk1><a:lt1><a:srgbClr '
          'val="FFFFFF"/></a:lt1><a:dk2><a:srgbClr val="1A237E"/></a:dk2><a:lt2><a:srgbClr '
          'val="E8EAF6"/></a:lt2><a:accent1><a:srgbClr val="2E3A87"/></a:accent1><a:accent2>'
          '<a:srgbClr val="00897B"/></a:accent2><a:accent3><a:srgbClr val="F4511E"/></a:accent3>'
          '<a:accent4><a:srgbClr val="8E24AA"/></a:accent4><a:accent5><a:srgbClr val="43A047"/>'
          '</a:accent5><a:accent6><a:srgbClr val="FB8C00"/></a:accent6><a:hlink><a:srgbClr '
          'val="1E88E5"/></a:hlink><a:folHlink><a:srgbClr val="8E24AA"/></a:folHlink>'
          '</a:clrScheme><a:fontScheme name="Tontolo"><a:majorFont><a:latin typeface="Calibri"/>'
          '<a:ea typeface=""/><a:cs typeface=""/></a:majorFont><a:minorFont><a:latin typeface='
          '"Calibri"/><a:ea typeface=""/><a:cs typeface=""/></a:minorFont></a:fontScheme>'
          '<a:fmtScheme name="Tontolo"><a:fillStyleLst><a:solidFill><a:schemeClr val="phClr"/>'
          '</a:solidFill><a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:solidFill>'
          '<a:schemeClr val="phClr"/></a:solidFill></a:fillStyleLst><a:lnStyleLst><a:ln w="6350">'
          '<a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln><a:ln w="12700"><a:solidFill>'
          '<a:schemeClr val="phClr"/></a:solidFill></a:ln><a:ln w="19050"><a:solidFill><a:schemeClr'
          ' val="phClr"/></a:solidFill></a:ln></a:lnStyleLst><a:effectStyleLst><a:effectStyle>'
          '<a:effectLst/></a:effectStyle><a:effectStyle><a:effectLst/></a:effectStyle>'
          '<a:effectStyle><a:effectLst/></a:effectStyle></a:effectStyleLst><a:bgFillStyleLst>'
          '<a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:solidFill><a:schemeClr '
          'val="phClr"/></a:solidFill><a:solidFill><a:schemeClr val="phClr"/></a:solidFill>'
          '</a:bgFillStyleLst></a:fmtScheme></a:themeElements></a:theme>')


def build_pptx(md: str) -> bytes:
    _, slides = parse_slides(md)
    n = len(slides)
    rel = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    rels_ns = 'xmlns="http://schemas.openxmlformats.org/package/2006/relationships"'
    hdr = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    tree = ('<p:cSld><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/>'
            '</p:nvGrpSpPr><p:grpSpPr/></p:spTree></p:cSld>')
    master = (f'{hdr}<p:sldMaster {_P}>{tree}<p:clrMap bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" '
              'accent1="accent1" accent2="accent2" accent3="accent3" accent4="accent4" '
              'accent5="accent5" accent6="accent6" hlink="hlink" folHlink="folHlink"/>'
              '<p:sldLayoutIdLst><p:sldLayoutId id="2147483649" r:id="rId1"/></p:sldLayoutIdLst>'
              '</p:sldMaster>')
    layout = (f'{hdr}<p:sldLayout {_P} type="blank" preserve="1">{tree}<p:clrMapOvr>'
              '<a:masterClrMapping/></p:clrMapOvr></p:sldLayout>')
    presentation = (f'{hdr}<p:presentation {_P}><p:sldMasterIdLst><p:sldMasterId id="2147483648" '
                    'r:id="rId1"/></p:sldMasterIdLst><p:sldIdLst>' + "".join(
                        f'<p:sldId id="{256 + i}" r:id="rId{i + 3}"/>' for i in range(n))
                    + f'</p:sldIdLst><p:sldSz cx="{EMU_W}" cy="{EMU_H}"/><p:notesSz cx="6858000" '
                    'cy="9144000"/></p:presentation>')
    pres_rels = (f'{hdr}<Relationships {rels_ns}><Relationship Id="rId1" Type="{rel}/slideMaster" '
                 f'Target="slideMasters/slideMaster1.xml"/><Relationship Id="rId2" Type="{rel}/'
                 'theme" Target="theme/theme1.xml"/>' + "".join(
                     f'<Relationship Id="rId{i + 3}" Type="{rel}/slide" Target="slides/slide{i + 1}'
                     '.xml"/>' for i in range(n)) + "</Relationships>")
    types = (f'{hdr}<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
             '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.'
             'relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>'
             '<Override PartName="/ppt/presentation.xml" ContentType="application/vnd.'
             'openxmlformats-officedocument.presentationml.presentation.main+xml"/>'
             '<Override PartName="/ppt/slideMasters/slideMaster1.xml" ContentType="application/'
             'vnd.openxmlformats-officedocument.presentationml.slideMaster+xml"/>'
             '<Override PartName="/ppt/slideLayouts/slideLayout1.xml" ContentType="application/'
             'vnd.openxmlformats-officedocument.presentationml.slideLayout+xml"/>'
             '<Override PartName="/ppt/theme/theme1.xml" ContentType="application/vnd.'
             'openxmlformats-officedocument.theme+xml"/>' + "".join(
                 f'<Override PartName="/ppt/slides/slide{i + 1}.xml" ContentType="application/vnd.'
                 'openxmlformats-officedocument.presentationml.slide+xml"/>' for i in range(n))
             + "</Types>")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", types)
        z.writestr("_rels/.rels", f'{hdr}<Relationships {rels_ns}><Relationship Id="rId1" Type='
                   f'"{rel}/officeDocument" Target="ppt/presentation.xml"/></Relationships>')
        z.writestr("ppt/presentation.xml", presentation)
        z.writestr("ppt/_rels/presentation.xml.rels", pres_rels)
        z.writestr("ppt/slideMasters/slideMaster1.xml", master)
        z.writestr("ppt/slideMasters/_rels/slideMaster1.xml.rels",
                   f'{hdr}<Relationships {rels_ns}><Relationship Id="rId1" Type="{rel}/slideLayout"'
                   ' Target="../slideLayouts/slideLayout1.xml"/><Relationship Id="rId2" Type='
                   f'"{rel}/theme" Target="../theme/theme1.xml"/></Relationships>')
        z.writestr("ppt/slideLayouts/slideLayout1.xml", layout)
        z.writestr("ppt/slideLayouts/_rels/slideLayout1.xml.rels",
                   f'{hdr}<Relationships {rels_ns}><Relationship Id="rId1" Type="{rel}/slideMaster"'
                   ' Target="../slideMasters/slideMaster1.xml"/></Relationships>')
        z.writestr("ppt/theme/theme1.xml", _THEME)
        for i, s in enumerate(slides):
            z.writestr(f"ppt/slides/slide{i + 1}.xml", _slide_xml(s, i + 1, n))
            z.writestr(f"ppt/slides/_rels/slide{i + 1}.xml.rels",
                       f'{hdr}<Relationships {rels_ns}><Relationship Id="rId1" Type="{rel}/'
                       'slideLayout" Target="../slideLayouts/slideLayout1.xml"/></Relationships>')
    return buf.getvalue()
