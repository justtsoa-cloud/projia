"""Navigateur intégré : vrai navigateur Chromium (sans fenêtre) s'il est installé, et pont
de la tablette."""

from __future__ import annotations

import asyncio
import functools
import http.server
import os
import threading
from pathlib import Path
from typing import Any

import pytest

from tontolo.agent import browser

PAGE = """<!doctype html><html><head><title>Accueil</title></head><body>
<h1>Bienvenue à Antsirabe</h1><a href="/page2.html">Voir la suite</a>
<form action="/page2.html"><input name="q" placeholder="Recherche">
<input type="password" name="pw"><button>Chercher</button></form></body></html>"""
PAGE2 = "<!doctype html><title>Suite</title><p>Lac Tritriva</p>"


@pytest.fixture
def site(tmp_path: Path) -> Any:
    (tmp_path / "index.html").write_text(PAGE)
    (tmp_path / "page2.html").write_text(PAGE2)
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(tmp_path))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


_EXE = browser.find_browser() or ""


# Vivaldi et Opera ne savent pas fonctionner sans fenêtre : test fait avec Chromium ou Chrome
# (présent sur les machines de la CI GitHub).
@pytest.mark.skipif(not _EXE or (any(n in _EXE for n in ("vivaldi", "opera"))
                                 and not os.environ.get("TONTOLO_BROWSER_VISIBLE_TEST")),
                    reason="aucun Chromium ou Chrome sans fenêtre")
async def test_real_browser_one_tab_per_conversation(site: str, tmp_path: Path,
                                                     monkeypatch: pytest.MonkeyPatch) -> None:
    if not os.environ.get("TONTOLO_BROWSER_VISIBLE_TEST"):
        monkeypatch.setenv("TONTOLO_BROWSER_HEADLESS", "1")
    b = browser.CdpBrowser(tmp_path / "profil")
    try:
        page = await b.command("c1", "open", {"url": site + "/index.html"})
        assert page["title"] == "Accueil" and "Antsirabe" in page["text"]
        items = "\n".join(page["items"])
        assert "Voir la suite" in items
        field = next(int(i[1:i.index("]")]) for i in page["items"] if "Recherche" in i)
        pw = next(int(i[1:i.index("]")]) for i in page["items"] if "(password)" in i)
        refused = await b.command("c1", "type", {"id": pw, "text": "secret"})
        assert "refusé" in refused["error"]
        page = await b.command("c1", "click", {"text": "voir la suite"})
        assert page["title"] == "Suite" and "Tritriva" in page["text"]
        page = await b.command("c1", "back", {})
        assert page["title"] == "Accueil"
        btn = await b.command("c1", "click", {"text": "chercher"})
        assert "introuvable" in btn["error"]  # un lien ne désigne pas un bouton
        btn_id = next(int(i[1:i.index("]")]) for i in page["items"] if "Chercher" in i)
        btn = await b.command("c1", "click", {"id": btn_id})
        assert "browser_press" in btn["error"]  # bouton : jamais sans confirmation
        page = await b.command("c1", "type", {"id": field, "text": "lac", "submit": True})
        assert "Tritriva" in page["text"]
        await b.command("c1", "back", {})
        page = await b.command("c1", "press", {"id": btn_id})
        assert page["title"] == "Suite"
        await b.command("c2", "open", {"url": site + "/page2.html"})
        await b.command("c1", "read", {})
        assert len(b.tabs) == 2  # un onglet par discussion, réutilisé à chaque commande
        targets = (await b._call("Target.getTargets"))["targetInfos"]
        ours = [t for t in targets if t["type"] == "page" and t["url"].startswith(site)]
        assert len(ours) == 2  # (les pages internes du navigateur ne comptent pas)
        shot = await b.command("c1", "screenshot", {})
        assert shot["screenshot"].startswith("data:image/jpeg;base64,/9j/")  # elle voit la page
        with pytest.raises(browser.BrowserError):
            await b.command("c1", "open", {"url": "file:///etc/passwd"})
    finally:
        await b.close()


async def test_app_bridge_roundtrip() -> None:
    bridge = browser.AppBridge()
    assert not bridge.available

    async def app() -> None:
        cmd = await bridge.next(1)
        assert cmd is not None and cmd["action"] == "open"
        assert cmd["args"]["url"] == "https://example.org"
        bridge.result(cmd["id"], {"title": "Exemple", "url": cmd["args"]["url"], "text": "ok",
                                  "items": []})

    task = asyncio.create_task(app())
    await asyncio.sleep(0)
    out = await bridge.command("c1", "open", {"url": "example.org"})
    await task
    assert out["title"] == "Exemple" and bridge.available
    assert "Exemple" in browser.describe(out)
