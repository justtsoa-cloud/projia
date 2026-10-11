"""Documents joints : extraction locale, extraits pertinents, citations par page."""

from __future__ import annotations

import pytest

from tontolo import documents
from tontolo.agent.loop import ChatService
from tontolo.config import Settings
from tontolo.router.engine import Router
from tontolo.storage.db import Database


def tiny_pdf(pages: list[str]) -> bytes:
    """PDF minimal valide (une ligne de texte par page), sans dépendance."""
    objs: list[bytes] = []
    kids = " ".join(f"{3 + 2 * i} 0 R" for i in range(len(pages)))
    objs.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objs.append(f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode())
    font = 3 + 2 * len(pages)
    for i, text in enumerate(pages):
        content = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
        objs.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {4 + 2 * i} "
                    f"0 R /Resources << /Font << /F1 {font} 0 R >> >> >>".encode())
        objs.append(b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream")
    objs.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for n, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{n} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets)
    out += f"trailer << /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode()
    return bytes(out)


def test_pdf_pages_extracted() -> None:
    pages = documents.extract_pages("cours.pdf", tiny_pdf(["Introduction aux vanilles",
                                                           "Culture de la vanille a Sambava"]))
    assert len(pages) == 2 and "Sambava" in pages[1]


def test_text_and_html() -> None:
    assert documents.extract_pages("a.txt", b"Bonjour") == ["Bonjour"]
    html = (b"<html><head><style>x{}</style></head><body><p>Titre</p>"
            b"<script>evil()</script>Fin</body></html>")
    text = documents.extract_pages("page.html", html)[0]
    assert "Titre" in text and "Fin" in text and "evil" not in text


def test_bad_pdf_is_reported() -> None:
    with pytest.raises(documents.DocumentError):
        documents.extract_pages("x.pdf", b"%PDF-1.4 cass\xe9")


def test_select_relevant_and_summary() -> None:
    chunks = documents.chunk_pages([f"page {i} sur le riz et les rizieres" for i in range(10)]
                                   + ["La vanille de Sambava est celebre."])
    best = documents.select(chunks, "Où pousse la vanille ?", k=2)
    assert best[0].page == 11
    spread = documents.select(chunks, "Résume ce document", k=3)
    assert len(spread) == 3 and spread[0].page == 1


async def test_agent_cites_document(router: Router, db: Database, settings: Settings) -> None:
    chat = ChatService(settings, db, router)
    cid = await db.create_conversation("doc")
    await db.add_document(cid, "d1", "rapport.pdf", ["Intro", "Le budget 2026 est de 12 millions."])
    block = await chat._documents_block(cid, "Quel est le budget ?")
    assert block is not None
    assert "[rapport.pdf, p. 2]" in block["content"] and "12 millions" in block["content"]
    assert "NON FIABLES" in block["content"]  # contenu externe balisé (injection de prompt)
