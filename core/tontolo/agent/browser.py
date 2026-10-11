"""Navigateur web piloté par l'agent.

Bureau (Linux) : un vrai navigateur de la famille Chromium déjà installé (Chromium, Chrome,
Brave, Vivaldi, Edge, Opera) est lancé avec un **profil dédié à Tontolo** (jamais le profil
personnel de l'utilisateur) et piloté par le protocole DevTools. La fenêtre est visible :
l'utilisateur voit ce que fait l'agent et peut reprendre la main.

Tablette (Android) : les mêmes commandes sont exécutées par l'application dans son panneau
WebView (pont : le cœur dépose la commande, l'application renvoie le résultat).

Onglets : UN onglet par discussion, réutilisé à chaque commande (jamais un onglet par
commande) ; au plus MAX_TABS onglets, le moins récemment utilisé est fermé.

Garde-fous : le texte des pages est une donnée non fiable ; saisir du texte et envoyer un
formulaire demandent la confirmation de l'utilisateur ; aucun champ mot de passe ni carte
bancaire n'est jamais rempli.
"""

from __future__ import annotations

import asyncio
import contextlib
import itertools
import json
import os
import shutil
import time
import uuid
from pathlib import Path
from typing import Any

import httpx

from tontolo.agent.tools import Tool, untrusted

MAX_TABS = 6
LOAD_TIMEOUT = 20.0
MAX_TEXT = 12_000
CANDIDATES = ["chromium", "chromium-browser", "google-chrome-stable", "google-chrome", "brave",
              "brave-browser", "vivaldi-stable", "vivaldi", "microsoft-edge-stable",
              "microsoft-edge", "opera"]

# Script injecté : texte lisible et éléments utilisables numérotés (data-tontolo-id).
READ_JS = r"""
(() => {
  const vis = e => { const r = e.getBoundingClientRect(); const s = getComputedStyle(e);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  const sel = 'a[href],button,input,textarea,select,[role=button],[role=link],[onclick],summary';
  const items = [];
  let n = 0;
  document.querySelectorAll('[data-tontolo-id]').forEach(e => e.removeAttribute('data-tontolo-id'));
  for (const e of document.querySelectorAll(sel)) {
    if (!vis(e) || n >= 150) continue;
    n += 1; e.setAttribute('data-tontolo-id', String(n));
    const tag = e.tagName.toLowerCase();
    const type = e.getAttribute('type') || '';
    const label = (e.innerText || e.value || e.getAttribute('aria-label') ||
                   e.getAttribute('placeholder') || e.getAttribute('title') || '').trim()
                   .replace(/\s+/g, ' ').slice(0, 80);
    const href = tag === 'a' ? (' → ' + (e.getAttribute('href') || '').slice(0, 80)) : '';
    items.push('[' + n + '] ' + tag + (type ? '(' + type + ')' : '') + ' ' + label + href);
  }
  const text = (document.body ? document.body.innerText : '').replace(/\n{3,}/g, '\n\n');
  return JSON.stringify({title: document.title, url: location.href, text: text, items: items});
})()
"""

CLICK_JS = r"""
((id, text, press) => {
  const isButton = x => {
    const tag = x.tagName, type = (x.getAttribute('type') || '').toLowerCase();
    return tag === 'BUTTON' || (tag === 'INPUT' && /submit|button|image|reset/.test(type)) ||
           x.getAttribute('role') === 'button' || (x.hasAttribute('onclick') && tag !== 'A');
  };
  let e = id ? document.querySelector('[data-tontolo-id="' + id + '"]') : null;
  if (!e && text) {
    const t = text.toLowerCase();
    e = [...document.querySelectorAll(press ? 'button,[role=button],input,[onclick]'
                                            : 'a[href],summary,[role=link],[role=tab]')]
      .find(x => (x.innerText || x.value || '').toLowerCase().includes(t));
  }
  if (!e) return 'introuvable';
  // Lien : libre. Bouton (envoi, achat, suppression…) : seulement par browser_press, après
  // confirmation de l'utilisateur.
  if (!press && isButton(e)) return 'bouton';
  e.scrollIntoView({block: 'center'}); e.click();
  return 'ok : ' + (e.innerText || e.value || e.tagName).trim().slice(0, 80);
})
"""

TYPE_JS = r"""
((id, value, submit) => {
  const e = document.querySelector('[data-tontolo-id="' + id + '"]');
  if (!e) return 'introuvable';
  const type = (e.getAttribute('type') || '').toLowerCase();
  const ac = (e.getAttribute('autocomplete') || '').toLowerCase();
  if (type === 'password' || /cc-|card|password|one-time-code/.test(ac))
    return 'refusé : champ sensible (mot de passe, carte, code)';
  e.focus();
  const proto = e.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype
                                         : HTMLInputElement.prototype;
  const setter = Object.getOwnPropertyDescriptor(proto, 'value');
  if (setter && setter.set && e.tagName !== 'SELECT') setter.set.call(e, value);
  else e.value = value;
  e.dispatchEvent(new Event('input', {bubbles: true}));
  e.dispatchEvent(new Event('change', {bubbles: true}));
  if (submit) { if (e.form) { e.form.requestSubmit ? e.form.requestSubmit() : e.form.submit(); }
    else e.dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter', bubbles: true})); }
  return 'ok';
})
"""


BUTTON_MSG = ("c'est un bouton (envoi, achat, suppression…) : utilise browser_press, qui "
              "demande l'accord de l'utilisateur")


class BrowserError(Exception):
    pass


def find_browser() -> str | None:
    custom = os.environ.get("TONTOLO_BROWSER")
    if custom and shutil.which(custom):
        return shutil.which(custom)
    for name in CANDIDATES:
        path = shutil.which(name)
        if path:
            return path
    return None


def _safe_url(url: str) -> str:
    url = url.strip()
    if not url:
        raise BrowserError("adresse vide")
    if "://" not in url:
        url = "https://" + url
    if not url.startswith(("http://", "https://")):
        raise BrowserError("seules les adresses http(s) sont permises")
    return url


class CdpBrowser:
    """Navigateur de bureau piloté par DevTools (une connexion, un onglet par discussion)."""

    def __init__(self, profile: Path, executable: str | None = None,
                 cache: Path | None = None) -> None:
        self.profile = profile
        self.cache = cache  # cache web dans le dossier de cache unique, plafonné
        self.executable = executable or find_browser()
        self.proc: asyncio.subprocess.Process | None = None
        self.ws: Any = None
        self._ids = itertools.count(1)
        self._waiters: dict[int, asyncio.Future[dict[str, Any]]] = {}
        self._reader: asyncio.Task[None] | None = None
        self.tabs: dict[str, dict[str, Any]] = {}  # discussion → {target, session, used}
        self._lock = asyncio.Lock()

    @property
    def available(self) -> bool:
        return self.executable is not None

    async def _start(self) -> None:
        if self.ws is not None and self.proc is not None and self.proc.returncode is None:
            return
        if self.executable is None:
            raise BrowserError("aucun navigateur Chromium, Chrome, Brave, Vivaldi ou Edge "
                               "installé")
        self.profile.mkdir(parents=True, exist_ok=True)
        port_file = self.profile / "DevToolsActivePort"
        port_file.unlink(missing_ok=True)
        self.proc = await asyncio.create_subprocess_exec(
            self.executable, f"--user-data-dir={self.profile}", "--remote-debugging-port=0",
            "--remote-debugging-address=127.0.0.1", "--no-first-run",
            "--no-default-browser-check", "--disable-sync",
            *([f"--disk-cache-dir={self.cache}", f"--disk-cache-size={64 * 1024 * 1024}",
               f"--media-cache-size={16 * 1024 * 1024}"] if self.cache else []),
            *(["--headless=new"] if os.environ.get("TONTOLO_BROWSER_HEADLESS") else []),
            "about:blank",
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
            start_new_session=True)
        for _ in range(150):
            if port_file.exists() and port_file.read_text().strip():
                break
            await asyncio.sleep(0.1)
        else:
            raise BrowserError("le navigateur n'a pas démarré")
        port = int(port_file.read_text().split()[0])
        async with httpx.AsyncClient() as client:
            info = (await client.get(f"http://127.0.0.1:{port}/json/version", timeout=5)).json()
        import websockets

        self.ws = await websockets.connect(info["webSocketDebuggerUrl"], max_size=50_000_000)
        self.tabs.clear()
        self._reader = asyncio.create_task(self._read())
        # S'attacher à un onglet pendant que le navigateur prépare son interface peut le
        # figer (constaté avec Vivaldi) : courte pause, une seule fois par lancement.
        await asyncio.sleep(2.5)

    async def _read(self) -> None:
        try:
            async for raw in self.ws:
                msg = json.loads(raw)
                fut = self._waiters.pop(msg.get("id", -1), None)
                if fut is not None and not fut.done():
                    fut.set_result(msg)
        except Exception:
            pass
        finally:
            self.ws = None
            for fut in self._waiters.values():
                if not fut.done():
                    fut.set_exception(BrowserError("navigateur fermé"))
            self._waiters.clear()

    async def _call(self, method: str, params: dict[str, Any] | None = None,
                    session: str | None = None, wait: float = 30) -> dict[str, Any]:
        if self.ws is None:
            raise BrowserError("navigateur fermé")
        mid = next(self._ids)
        fut: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        self._waiters[mid] = fut
        msg: dict[str, Any] = {"id": mid, "method": method, "params": params or {}}
        if session:
            msg["sessionId"] = session
        await self.ws.send(json.dumps(msg))
        try:
            res = await asyncio.wait_for(fut, wait)
        finally:
            self._waiters.pop(mid, None)
        if "error" in res:
            raise BrowserError(str(res["error"].get("message")))
        return dict(res.get("result") or {})

    async def _tab(self, cid: str) -> str:
        """Session de l'onglet de cette discussion (créé une seule fois, puis réutilisé)."""
        await self._start()
        tab = self.tabs.get(cid)
        if tab is not None:
            targets = (await self._call("Target.getTargets")).get("targetInfos", [])
            if any(t["targetId"] == tab["target"] for t in targets):
                tab["used"] = time.time()
                return str(tab["session"])
            self.tabs.pop(cid, None)
        if len(self.tabs) >= MAX_TABS:
            old_cid = min(self.tabs, key=lambda k: self.tabs[k]["used"])
            with contextlib.suppress(BrowserError):
                await self._call("Target.closeTarget", {"targetId": self.tabs[old_cid]["target"]})
            self.tabs.pop(old_cid, None)
        # Un onglet créé pendant que le navigateur démarre son interface (ex. Vivaldi) peut
        # rester figé : s'il ne répond pas, il est fermé et recréé (25 s au plus).
        deadline = time.monotonic() + 25
        blank = await self._reuse_blank()
        while True:
            # Premier onglet : dans une nouvelle fenêtre (certains navigateurs, comme Vivaldi,
            # n'ont pas encore de fenêtre de navigation au démarrage) ; les suivants à côté.
            target = blank or (await self._call("Target.createTarget", {
                "url": "about:blank", "newWindow": not self.tabs}))["targetId"]
            blank = None
            await asyncio.sleep(0.4)
            session = (await self._call("Target.attachToTarget",
                                        {"targetId": target, "flatten": True}))["sessionId"]
            if await self._responsive(session):
                break
            with contextlib.suppress(BrowserError, TimeoutError):
                await self._call("Target.closeTarget", {"targetId": target}, wait=5)
            if time.monotonic() > deadline:
                raise BrowserError("l'onglet du navigateur ne répond pas")
            await asyncio.sleep(1)
        await self._call("Page.enable", session=session)
        self.tabs[cid] = {"target": target, "session": session, "used": time.time()}
        return str(session)

    async def _responsive(self, session: str) -> bool:
        try:
            await self._call("Runtime.evaluate", {"expression": "1"}, session=session, wait=3)
            return True
        except (BrowserError, TimeoutError):
            return False

    async def _reuse_blank(self) -> str | None:
        """Le premier onglet vide (ouvert au lancement) sert à la première discussion."""
        used = {t["target"] for t in self.tabs.values()}
        for t in (await self._call("Target.getTargets")).get("targetInfos", []):
            if t.get("type") == "page" and t.get("url") in ("about:blank", "chrome://newtab/") \
                    and t["targetId"] not in used:
                return str(t["targetId"])
        return None

    async def _eval(self, session: str, expr: str) -> Any:
        res = await self._call("Runtime.evaluate", {"expression": expr, "returnByValue": True,
                                                    "awaitPromise": True}, session=session)
        if res.get("exceptionDetails"):
            raise BrowserError("erreur de script dans la page")
        return (res.get("result") or {}).get("value")

    async def _wait_loaded(self, session: str) -> None:
        deadline = time.monotonic() + LOAD_TIMEOUT
        await asyncio.sleep(0.3)
        while time.monotonic() < deadline:
            with contextlib.suppress(BrowserError):
                if await self._eval(session, "document.readyState") == "complete":
                    return
            await asyncio.sleep(0.3)

    async def command(self, cid: str, action: str, args: dict[str, Any]) -> dict[str, Any]:
        async with self._lock:
            session = await self._tab(cid)
            if action == "open":
                await self._call("Page.navigate", {"url": _safe_url(str(args.get("url", "")))},
                                 session=session)
                await self._wait_loaded(session)
            elif action == "back":
                await self._eval(session, "history.back()")
                await self._wait_loaded(session)
            elif action in ("click", "press"):
                out = await self._eval(session, f"({CLICK_JS})({json.dumps(args.get('id'))}, "
                                                f"{json.dumps(args.get('text') or '')}, "
                                                f"{json.dumps(action == 'press')})")
                if out == "introuvable":
                    return {"error": "élément introuvable : relis la page (browser_read)"}
                if out == "bouton":
                    return {"error": BUTTON_MSG}
                await self._wait_loaded(session)
            elif action == "type":
                out = await self._eval(session, f"({TYPE_JS})({json.dumps(args.get('id'))}, "
                                                f"{json.dumps(str(args.get('text', '')))}, "
                                                f"{json.dumps(bool(args.get('submit')))})")
                if out != "ok":
                    return {"error": str(out)}
                if args.get("submit"):
                    await self._wait_loaded(session)
            elif action == "scroll":
                await self._eval(session, "window.scrollBy(0, window.innerHeight * 0.9)")
            elif action == "screenshot":
                shot = await self._call("Page.captureScreenshot",
                                        {"format": "jpeg", "quality": 60}, session=session)
                return {"screenshot": "data:image/jpeg;base64," + str(shot.get("data") or "")}
            await self._call("Target.activateTarget", {"targetId": self.tabs[cid]["target"]})
            raw = await self._eval(session, READ_JS)
            return dict(json.loads(raw or "{}"))

    async def close(self) -> None:
        if self.ws is not None:
            with contextlib.suppress(Exception):
                await self.ws.close()
        if self.proc is not None and self.proc.returncode is None:
            self.proc.terminate()
        self.proc = None


class AppBridge:
    """Tablette : l'application exécute les commandes dans son panneau WebView."""

    def __init__(self) -> None:
        self.queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self.waiting: dict[str, asyncio.Future[dict[str, Any]]] = {}
        self.last_seen = 0.0  # dernière lecture par l'application (panneau disponible)

    @property
    def available(self) -> bool:
        return time.time() - self.last_seen < 60

    async def command(self, cid: str, action: str, args: dict[str, Any]) -> dict[str, Any]:
        if action == "open":
            args = {**args, "url": _safe_url(str(args.get("url", "")))}
        rid = uuid.uuid4().hex
        fut: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        self.waiting[rid] = fut
        await self.queue.put({"id": rid, "conversation_id": cid, "action": action, "args": args,
                              "read_js": READ_JS, "click_js": CLICK_JS, "type_js": TYPE_JS,
                              "button_msg": BUTTON_MSG})
        try:
            return await asyncio.wait_for(fut, 60)
        except TimeoutError as exc:
            raise BrowserError("le panneau navigateur de l'application ne répond pas") from exc
        finally:
            self.waiting.pop(rid, None)

    async def next(self, wait: float = 25) -> dict[str, Any] | None:
        self.last_seen = time.time()
        try:
            return await asyncio.wait_for(self.queue.get(), wait)
        except TimeoutError:
            return None
        finally:
            self.last_seen = time.time()

    def result(self, rid: str, data: dict[str, Any]) -> bool:
        fut = self.waiting.get(rid)
        if fut is None or fut.done():
            return False
        fut.set_result(data)
        return True


def describe(page: dict[str, Any]) -> str:
    if page.get("error"):
        return f"Erreur : {page['error']}"
    text = str(page.get("text") or "")[:MAX_TEXT]
    items = "\n".join(list(page.get("items") or [])[:150])
    return (f"Page : {page.get('title', '')}\nAdresse : {page.get('url', '')}\n"
            + untrusted(f"{text}\n\nÉléments utilisables (id pour browser_click/browser_type) :"
                        f"\n{items}"))


LOOK_PROMPT = ("Tu regardes une capture d'écran de navigateur pour un agent qui ne la voit pas. "
               "Décris en français ce qui est affiché : type de page, éléments principaux, "
               "messages, fenêtres ou bandeaux (cookies, connexion), images importantes, et "
               "où se trouvent les boutons utiles. N'invente rien ; 12 lignes au plus.")


def browser_tools(get_backend: Any, conversation: Any, describe_image: Any = None
                  ) -> list[Tool]:
    """Outils de l'agent. `get_backend()` renvoie le navigateur disponible (ou None) ;
    `conversation()` la discussion en cours (son onglet) ; `describe_image(url, prompt)`
    fait décrire une capture par un modèle qui voit."""

    async def look(args: dict[str, Any]) -> str:
        backend = get_backend()
        if not isinstance(backend, CdpBrowser):
            return "Capture indisponible ici : utilise browser_read."
        try:
            shot = (await backend.command(conversation(), "screenshot", {})).get("screenshot")
        except BrowserError as exc:
            return f"Erreur du navigateur : {exc}"
        if not shot or describe_image is None:
            return "Capture impossible : utilise browser_read."
        seen = await describe_image(shot, LOOK_PROMPT, 2500)
        return untrusted(seen) if seen else "Aucun modèle de vision disponible : browser_read."

    def runner(action: str) -> Any:
        async def run(args: dict[str, Any]) -> str:
            backend = get_backend()
            if backend is None:
                return ("Navigateur indisponible : installez Chromium, Chrome, Brave ou Vivaldi "
                        "(bureau) ou ouvrez le panneau navigateur (tablette). Utilise fetch_url.")
            try:
                return describe(await backend.command(conversation(), action, args))
            except BrowserError as exc:
                return f"Erreur du navigateur : {exc}"
        return run

    url = {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}
    empty: dict[str, Any] = {"type": "object", "properties": {}}
    return [
        Tool("browser_open", "Ouvre une adresse dans l'onglet de cette discussion du navigateur "
             "intégré (visible par l'utilisateur) et renvoie le texte et les éléments "
             "cliquables numérotés.", url, runner("open")),
        Tool("browser_read", "Relit la page actuelle de l'onglet (texte et éléments).", empty,
             runner("read")),
        Tool("browser_click", "Suit un lien ou un onglet de la page (id de browser_read, ou "
             "texte visible). Pour un bouton, utilise browser_press.",
             {"type": "object", "properties": {"id": {"type": "integer"},
                                               "text": {"type": "string"}}},
             runner("click")),
        Tool("browser_press", "Appuie sur un bouton (envoyer, valider, acheter, supprimer…) : "
             "demande l'accord de l'utilisateur.",
             {"type": "object", "properties": {"id": {"type": "integer"},
                                               "text": {"type": "string"}}},
             runner("press"), side_effect=True,
             preview=lambda a: f"Bouton : {a.get('text') or '#' + str(a.get('id'))}"),
        Tool("browser_type", "Saisit du texte dans un champ (id) et l'envoie si submit = true. "
             "Demande confirmation ; jamais de mot de passe ni de carte bancaire.",
             {"type": "object", "properties": {"id": {"type": "integer"},
                                               "text": {"type": "string"},
                                               "submit": {"type": "boolean"}},
              "required": ["id", "text"]}, runner("type"), side_effect=True,
             preview=lambda a: f"Champ #{a.get('id')} : « {a.get('text', '')} »"
             + (" puis envoi" if a.get("submit") else "")),
        Tool("browser_scroll", "Fait défiler la page vers le bas.", empty, runner("scroll")),
        Tool("browser_back", "Revient à la page précédente.", empty, runner("back")),
        Tool("browser_look", "Regarde la page affichée (capture décrite par un modèle qui "
             "voit) : mise en page, images, fenêtres surgissantes.", empty, look),
    ]
