"""E2 — essais réels de bout en bout (modèles gratuits en ligne) sur le vrai serveur HTTP.

    uv run python -m bench.real_e2e r2 r3 …      (scénarios à lancer ; sans argument : tous)

Chaque scénario écrit son verdict dans bench/results/<scénario>.json et un résumé lisible dans
bench/results/<scénario>.md. Les modèles gratuits sont lents et inégaux : un échec n'est pas
forcément un bug (le verdict dit pourquoi). Réseau et quotas requis."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "bench" / "results"
RESULTS.mkdir(parents=True, exist_ok=True)
PORT = int(os.environ.get("E2E_PORT", "8791"))
TOKEN = "e2e-token"
BASE = f"http://127.0.0.1:{PORT}"
HEAD = {"Authorization": f"Bearer {TOKEN}"}


class Server:
    def __init__(self) -> None:
        self.home = Path(tempfile.mkdtemp(prefix="tontolo-e2e-"))
        cache = Path.home() / ".local/share/tontolo/cache"
        if cache.is_dir():
            shutil.copytree(cache, self.home / "cache")  # catalogue déjà connu : démarrage rapide
        env = {**os.environ, "TONTOLO_HOME": str(self.home), "TONTOLO_PORT": str(PORT),
               "TONTOLO_TOKEN": TOKEN, "TONTOLO_NO_KEYRING": "1"}
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "tontolo.cli", "serve", "--port", str(PORT)], cwd=ROOT,
            env=env, stdout=open(self.home / "server.log", "w"), stderr=subprocess.STDOUT)

    async def wait(self) -> None:
        async with httpx.AsyncClient() as c:
            for _ in range(120):
                try:
                    if (await c.get(f"{BASE}/health")).status_code == 200:
                        return
                except httpx.HTTPError:
                    pass
                await asyncio.sleep(1)
        raise RuntimeError("serveur injoignable")

    def stop(self) -> None:
        self.proc.terminate()
        try:
            self.proc.wait(10)
        except subprocess.TimeoutExpired:
            self.proc.kill()


class Api:
    def __init__(self) -> None:
        self.http = httpx.AsyncClient(base_url=BASE, headers=HEAD, timeout=None)

    async def chat(self, content: Any, cid: str | None = None, *, limit: float = 900,
                   path: str = "/tontolo/chat", **extra: Any) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        body = {"conversation_id": cid, "content": content, **extra} if path.endswith("chat") \
            else extra
        async with asyncio.timeout(limit):
            async with self.http.stream("POST", path, json=body) as r:
                if r.status_code >= 400:
                    return [{"type": "error", "message": f"HTTP {r.status_code}: "
                             f"{(await r.aread()).decode()[:200]}"}]
                async for line in r.aiter_lines():
                    if line.startswith("data:"):
                        ev = json.loads(line[5:])
                        if ev.get("type") == "end":
                            break
                        events.append(ev)
        return events

    async def get(self, path: str, **params: Any) -> Any:
        return (await self.http.get(path, params=params)).json()

    async def conversation(self, cid: str) -> dict[str, Any]:
        return await self.get(f"/tontolo/conversations/{cid}")


def cid_of(events: list[dict[str, Any]]) -> str:
    return next(e["id"] for e in events if e["type"] == "conversation")


def final_text(events: list[dict[str, Any]]) -> str:
    done = [e for e in events if e["type"] == "done"]
    return str(((done[-1] if done else {}).get("message") or {}).get("content") or "")


def job_of(events: list[dict[str, Any]]) -> dict[str, Any] | None:
    done = [e for e in events if e["type"] == "done" and e.get("job")]
    return done[-1]["job"] if done else None


def errors_of(events: list[dict[str, Any]]) -> list[str]:
    return [str(e.get("message")) for e in events if e["type"] == "error"]


class Verdict:
    def __init__(self, name: str) -> None:
        self.name = name
        self.checks: list[tuple[bool, str]] = []
        self.notes: list[str] = []
        self.t0 = time.time()

    def check(self, ok: bool, what: str) -> bool:
        self.checks.append((bool(ok), what))
        print(("  ✓ " if ok else "  ✗ ") + what, flush=True)
        return bool(ok)

    def note(self, text: str) -> None:
        self.notes.append(text)
        print("  · " + text, flush=True)

    def save(self) -> None:
        secs = time.time() - self.t0
        ok = all(c[0] for c in self.checks)
        (RESULTS / f"{self.name}.json").write_text(json.dumps({
            "scenario": self.name, "ok": ok, "seconds": round(secs), "checks": self.checks,
            "notes": self.notes}, ensure_ascii=False, indent=1))
        lines = [f"## {self.name} — {'RÉUSSI' if ok else 'ÉCHEC'} ({round(secs)} s)"]
        lines += [f"- {'✓' if c else '✗'} {w}" for c, w in self.checks]
        lines += [f"- {n}" for n in self.notes]
        (RESULTS / f"{self.name}.md").write_text("\n".join(lines) + "\n")


SCENARIOS: dict[str, Any] = {}


def scenario(fn: Any) -> Any:
    SCENARIOS[fn.__name__] = fn
    return fn


# --- R2 : plan complexe en parallèle ------------------------------------------------------
@scenario
async def r2_complex_plan(api: Api, v: Verdict) -> None:
    ask = ("Fais-moi un cours complet comparant l'histoire de Madagascar, du Japon, du Brésil "
           "et du Maroc : 1) origines 2) colonisation ou isolement 3) indépendance et "
           "modernisation 4) défis actuels. Termine par un tableau comparatif.")
    ev = await api.chat(ask)
    cid = cid_of(ev)
    plans = [e for e in ev if e["type"] == "plan"]
    v.check(bool(plans), "un plan est établi pour la tâche complexe")
    steps = [e for e in ev if e["type"] == "plan_step"]
    v.note(f"modes/étapes : {plans[0]['plan']['mode'] if plans else '?'} ; "
           f"étapes terminées {sum(e['status'] == 'done' for e in steps)} / "
           f"échouées {sum(e['status'] == 'failed' for e in steps)}")
    text = final_text(ev)
    v.check(len(text) > 1500, f"réponse substantielle ({len(text)} caractères)")
    for word in ("Madagascar", "Japon", "Brésil", "Maroc"):
        v.check(word.lower() in text.lower(), f"« {word} » traité")
    v.check(not errors_of(ev), f"aucune erreur ({errors_of(ev)[:1]})")
    items = await api.get(f"/tontolo/conversations/{cid}/tasks")
    v.note(f"résultats intermédiaires gardés : {[i['kind'] for i in items]}")
    if plans and plans[0]["plan"]["mode"] == "steps":
        ev2 = await api.chat("continuer", cid)
        v.check(len(final_text(ev2)) > 500, "« continuer » livre l'étape suivante")


# --- R3 : longue discussion, cohérence, changement de modèle ---------------------------------
@scenario
async def r3_long_conversation(api: Api, v: Verdict) -> None:
    facts = {"nom": "Hanta", "ville": "Fianarantsoa", "projet": "une coopérative de vanille",
             "budget": "12 millions d'ariary"}
    ev = await api.chat(f"Bonjour, je m'appelle {facts['nom']}, j'habite à {facts['ville']}. "
                        f"Mon projet : {facts['projet']} avec un budget de {facts['budget']}. "
                        "Retiens-le pour la suite.")
    cid = cid_of(ev)
    questions = [
        "Quels sont les 3 premiers risques ?", "Propose un calendrier sur 6 mois.",
        "Détaille le premier mois.", "Quels équipements acheter ?", "Combien de personnes ?",
        "Quelles certifications viser ?", "Comment trouver des acheteurs ?",
        "Rédige un court argumentaire commercial.", "Quels indicateurs suivre ?",
        "Fais le point sur les coûts.", "Quels pièges juridiques ?", "Plan B si la récolte échoue ?",
        "Résume tout ce qu'on a fait en 5 points.", "Quel est mon prénom et ma ville ?",
    ]
    answers = []
    models: set[str] = set()
    for i, q in enumerate(questions):
        extra = {"model": "auto"}
        e = await api.chat(q, cid, limit=600, **extra)
        text = final_text(e)
        answers.append(text)
        models |= {str(x.get("model")) for x in e if x["type"] == "done"}
        if not text:
            v.note(f"tour {i + 2} : pas de réponse ({errors_of(e)[:1]})")
    v.check(sum(bool(a) for a in answers) >= len(questions) - 1, "au moins 13 réponses sur 14")
    last = answers[-1].lower()
    v.check(facts["nom"].lower() in last, "retrouve le prénom après 14 tours")
    v.check(facts["ville"].lower() in last, "retrouve la ville après 14 tours")
    v.note(f"modèles utilisés : {sorted(models)}")
    conv = await api.conversation(cid)
    roles = [m["role"] for m in conv["messages"]]
    v.check(roles.count("user") == len(questions) + 1, "tous les messages utilisateur conservés")
    v.note(f"résumé du fil : {'oui' if conv.get('summary') else 'non'} "
           f"({len(conv['messages'])} messages)")


# --- R4 : chaîne de corrections d'un fichier -------------------------------------------------
@scenario
async def r4_revision_chain(api: Api, v: Verdict) -> None:
    ev = await api.chat("Génère un fichier Word sur le cycle de l'eau pour des collégiens")
    cid = cid_of(ev)
    job = job_of(ev)
    v.check(bool(job) and job["status"] == "done", f"fichier créé ({errors_of(ev)[:1]})")
    names = [job["params"]["filename"]] if job else []
    for req in ("rajoute un schéma en texte et un exercice", "excellent mais plus court",
                "ajoute un glossaire", "traduis les titres en anglais"):
        ev = await api.chat(req, cid)
        job = job_of(ev)
        ok = bool(job) and job["status"] == "done"
        v.check(ok, f"« {req} » : nouvelle version livrée ({errors_of(ev)[:1]})")
        if ok:
            names.append(job["params"]["filename"])
            v.check(bool(job["params"].get("revision")), "  … traitée comme une correction")
    v.note(f"noms : {names}")
    v.check(len(set(names)) == len(names) >= 3, "aucune version ne reprend le nom d'une autre")
    items = await api.get(f"/tontolo/conversations/{cid}/tasks")
    v.check(sum(i["kind"] == "draft" for i in items) >= len(names) - 1,
            "brouillons gardés dans les résultats intermédiaires")


# --- R6 : projet multi-fichiers (code) ---------------------------------------------------------
@scenario
async def r6_code_project(api: Api, v: Verdict) -> None:
    ev = await api.chat("Crée-moi un petit projet Python en plusieurs fichiers, livré en zip : "
                        "un module calcul.py (fonctions add, mul), un module cli.py qui les "
                        "utilise et un test test_calcul.py, plus un README.md.")
    job = job_of(ev)
    v.check(bool(job) and job["status"] == "done", f"archive créée ({errors_of(ev)[:1]})")
    if not job:
        return
    r = await api.http.get(f"/tontolo/media/{job['id']}/file")
    zpath = RESULTS / "r6_project.zip"
    zpath.write_bytes(r.content)
    with zipfile.ZipFile(zpath) as z:
        names = z.namelist()
        v.note(f"fichiers : {names}")
        v.check(len(names) >= 3, "au moins 3 fichiers")
        extract = Path(tempfile.mkdtemp())
        z.extractall(extract)
    py = [p for p in extract.rglob("*.py")]
    ok = True
    for p in py:
        res = subprocess.run([sys.executable, "-m", "py_compile", str(p)], capture_output=True)
        ok = ok and res.returncode == 0
    v.check(ok and bool(py), "tous les fichiers Python compilent")
    tests = list(extract.rglob("test_*.py"))
    if tests:
        res = subprocess.run([sys.executable, "-m", "pytest", "-q", str(extract)],
                             capture_output=True, text=True, cwd=extract)
        v.check(res.returncode == 0, f"les tests générés passent ({res.stdout[-120:].strip()})")


# --- R7 : livre long (court : 21 pages) --------------------------------------------------------
@scenario
async def r7_book(api: Api, v: Verdict) -> None:
    t0 = time.time()
    ev = await api.chat("Génère un livre de 21 pages pour des lycéens : l'histoire des "
                        "mathématiques, des origines à nos jours", limit=3600)
    cid = cid_of(ev)
    job = job_of(ev)
    v.check(bool(job) and job["status"] == "done", f"livre livré en {round(time.time() - t0)} s "
            f"({errors_of(ev)[:1]})")
    chapters = [e for e in ev if e.get("step") == "book_chapter"]
    v.note(f"chapitres signalés : {len(chapters)}")
    if job:
        r = await api.http.get(f"/tontolo/media/{job['id']}/file")
        (RESULTS / "r7_book.pdf").write_bytes(r.content)
        v.check(r.content[:4] == b"%PDF", f"PDF valide ({len(r.content) // 1024} Ko)")
        pdfinfo = subprocess.run(["pdfinfo", str(RESULTS / "r7_book.pdf")], capture_output=True,
                                 text=True)
        pages = [ln for ln in pdfinfo.stdout.splitlines() if ln.startswith("Pages")]
        v.note(pages[0] if pages else "pdfinfo indisponible")
    items = await api.get(f"/tontolo/conversations/{cid}/tasks")
    v.check(sum(i["kind"] == "part" for i in items) >= 3, "plan et chapitres visibles en direct")


# --- R8 : agent avec outils (web + calcul) ------------------------------------------------------
@scenario
async def r8_agent_tools(api: Api, v: Verdict) -> None:
    ev = await api.chat("Cherche sur le web la population actuelle de Madagascar, puis calcule "
                        "avec la calculatrice combien elle représente en pourcentage de "
                        "l'Afrique (environ 1,5 milliard d'habitants).",
                        mode="agent", agent="researcher", limit=600)
    tools = [e for e in ev if e["type"] == "tool_call"]
    v.note(f"outils appelés : {[e['name'] for e in tools]}")
    v.check(bool(tools), "au moins un outil utilisé")
    text = final_text(ev)
    v.check("%" in text or "pour cent" in text.lower(), "un pourcentage est donné")
    v.check("<tool_call>" not in text, "aucun balisage d'outil brut dans la réponse")
    v.check(not errors_of(ev), f"aucune erreur ({errors_of(ev)[:1]})")


async def main() -> None:
    wanted = sys.argv[1:] or list(SCENARIOS)
    server = Server()
    try:
        await server.wait()
        api = Api()
        for name in wanted:
            fn = SCENARIOS.get(name)
            if fn is None:
                print("scénario inconnu :", name)
                continue
            print(f"\n=== {name} ===", flush=True)
            v = Verdict(name)
            try:
                await fn(api, v)
            except Exception as exc:  # un plantage du scénario est un verdict
                v.check(False, f"scénario interrompu : {type(exc).__name__}: {exc}")
            v.save()
        shutil.copy(server.home / "server.log", RESULTS / "server.log")
    finally:
        server.stop()


if __name__ == "__main__":
    asyncio.run(main())
