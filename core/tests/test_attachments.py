"""Pièces jointes de tous types : texte extrait localement, fichiers piégés refusés."""

from __future__ import annotations

import io
import json
import tarfile
import zipfile

import pytest

from tontolo import attachments
from tontolo.documents import DocumentError, extract_pages


def _zip(files: dict[str, bytes | str], method: int = zipfile.ZIP_DEFLATED) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", method) as z:
        for n, v in files.items():
            z.writestr(n, v)
    return buf.getvalue()


W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
A = 'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"'


def test_office_documents() -> None:
    docx = _zip({"word/document.xml": f'<w:document {W}><w:body><w:p><w:r><w:t>Bonjour</w:t>'
                 '</w:r><w:r><w:t xml:space="preserve"> le monde</w:t></w:r></w:p><w:p><w:r>'
                 '<w:t>Deuxième</w:t></w:r></w:p></w:body></w:document>'})
    assert extract_pages("cours.docx", docx) == ["Bonjour le monde\nDeuxième"]
    pptx = _zip({f"ppt/slides/slide{i}.xml": f'<p:sld xmlns:p="x" {A}><a:p><a:r><a:t>Diapo {i}'
                 '</a:t></a:r></a:p></p:sld>' for i in (2, 1, 10)})
    pages = extract_pages("expo.pptx", pptx)
    assert [p.splitlines()[0] for p in pages] == ["Diapositive 1", "Diapositive 2",
                                                    "Diapositive 10"]
    xlsx = _zip({
        "xl/sharedStrings.xml": '<sst xmlns="s"><si><t>Nom</t></si><si><t>Rabe</t></si></sst>',
        "xl/worksheets/sheet1.xml": '<worksheet xmlns="s"><sheetData><row><c t="s"><v>0</v></c>'
        '<c><v>42</v></c></row><row><c t="s"><v>1</v></c><c><v>7</v></c></row></sheetData>'
        '</worksheet>'})
    assert extract_pages("notes.xlsx", xlsx) == ["Feuille 1\nNom\t42\nRabe\t7"]
    odt = _zip({"content.xml": '<o xmlns:text="t"><text:p>Salama <text:span>tompoko</text:span>'
                '</text:p><text:h>Titre</text:h></o>'})
    assert extract_pages("lettre.odt", odt) == ["Salama tompoko\nTitre"]
    epub = _zip({"OEBPS/content.opf": '<package><manifest><item id="c2" href="b.xhtml"/>'
                 '<item id="c1" href="a.xhtml"/></manifest><spine><itemref idref="c1"/>'
                 '<itemref idref="c2"/></spine></package>',
                 "OEBPS/a.xhtml": "<html><body><p>Chapitre un</p></body></html>",
                 "OEBPS/b.xhtml": "<html><body><p>Chapitre deux</p></body></html>"})
    assert extract_pages("livre.epub", epub) == ["Chapitre un", "Chapitre deux"]
    rtf = rb"{\rtf1\ansi{\fonttbl{\f0 Arial;}}\f0 Caf\'e9 \b gras\b0\par Ligne}"
    text = extract_pages("note.rtf", rtf)[0]
    assert "Café gras" in text and "Ligne" in text and "Arial" not in text and "\\" not in text


def test_text_and_code_files() -> None:
    assert extract_pages("data.csv", b"a;b\n1;2") == ["a;b\n1;2"]
    assert extract_pages("app.dart", b"void main() {}") == ["void main() {}"]
    assert extract_pages("Dockerfile", b"FROM python") == ["FROM python"]
    nb = json.dumps({"cells": [{"cell_type": "markdown", "source": ["# Titre"]},
                               {"cell_type": "code", "source": "print(1)"}]}).encode()
    assert "print(1)" in extract_pages("analyse.ipynb", nb)[0]
    assert extract_pages("u16.txt", "Salama".encode("utf-16")) == ["Salama"]
    with pytest.raises(DocumentError):
        extract_pages("binaire.txt", b"\x00\x01\x02ELF")


def test_archives_list_and_read_safely() -> None:
    inner = _zip({"x.txt": "dedans"})
    z = _zip({"projet/README.md": "# Projet", "projet/main.py": "print('ok')",
              "projet/logo.png": b"\x89PNG\x00\x00", "../evil.txt": "sortie",
              "__MACOSX/._main.py": "x", "projet/autre.zip": inner})
    pages = extract_pages("projet.zip", z)
    assert "projet/README.md" in pages[0] and "projet/logo.png" in pages[0]
    assert "evil" not in pages[0] and "__MACOSX" not in pages[0]
    body = "\n".join(pages)
    assert "=== projet/main.py ===\nprint('ok')" in body and "dedans" not in body  # imbriquée
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as t:
        data = b"contenu tar"
        info = tarfile.TarInfo("doc/a.txt")
        info.size = len(data)
        t.addfile(info, io.BytesIO(data))
        link = tarfile.TarInfo("doc/lien")
        link.type = tarfile.SYMTYPE
        link.linkname = "/etc/passwd"
        t.addfile(link)
    pages = extract_pages("archive.tar.gz", buf.getvalue())
    assert "doc/a.txt" in pages[0] and "lien" not in pages[0]
    assert "contenu tar" in pages[1]


def test_traps_are_refused() -> None:
    bomb = _zip({"zero.txt": b"\x00" * (30 * 1024 * 1024)})  # ~30 Mo → quelques Ko
    with pytest.raises(DocumentError):
        extract_pages("bombe.zip", bomb)
    xxe = _zip({"word/document.xml": '<?xml version="1.0"?><!DOCTYPE d [<!ENTITY x SYSTEM '
                '"file:///etc/passwd">]><d>&x;</d>'})
    with pytest.raises(DocumentError):
        extract_pages("piege.docx", xxe)
    with pytest.raises(DocumentError):
        extract_pages("faux.docx", b"pas un zip")
    many = _zip({f"f{i}.txt": "x" for i in range(400)})
    head = extract_pages("beaucoup.zip", many)[0]
    assert head.count("\n- ") == attachments.MAX_MEMBERS and "300 premiers fichiers sur 400" in head


def test_media_kinds() -> None:
    assert attachments.media_kind("cours.MP3") == "audio"
    assert attachments.media_kind("video.webm") == "video"
    assert attachments.media_kind("x.pdf") is None
    assert all(attachments.supported(n) for n in ("a.zip", "a.tar.gz", "a.docx", "a.m4a",
                                                   "a.py", "a.epub", "a.mov"))
    assert not attachments.supported("a.exe")
