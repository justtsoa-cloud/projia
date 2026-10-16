"""P1.1 — banc de vitesse ET de justesse sur 15 questions fixes (vrais modèles gratuits).

    uv run python -m bench.speed_bench [étiquette]

Écrit bench/results/speed-<étiquette>.json : par question, le modèle, la préparation, le délai
avant le premier mot, la durée totale et si la réponse contient la valeur attendue (rigueur).
Compare deux étiquettes avec :  uv run python -m bench.speed_bench --compare avant après"""

from __future__ import annotations

import asyncio
import json
import statistics
import sys
import time

from bench.real_e2e import RESULTS, Api, Server, final_text

# (id, type, question, valeurs acceptées dans la réponse — une suffit ; vide = non vérifiable)
QUESTIONS: list[tuple[str, str, str, list[str]]] = [
    ("s1", "simple", "Bonjour !", []),
    ("s2", "simple", "Quelle est la capitale de Madagascar ?", ["antananarivo", "tananarive"]),
    ("s3", "simple", "What is the capital of Japan?", ["tokyo"]),
    ("s4", "simple", "Inona no renivohitry ny Frantsa?", ["paris", "pario"]),
    ("s5", "simple", "Traduis « bonne nuit » en anglais.", ["good night"]),
    ("m1", "maths", "Combien font 17 × 23 ? Réponds juste par le nombre.", ["391"]),
    ("m2", "maths", "Résous 3x + 7 = 25. Donne seulement x.", ["6"]),
    ("m3", "maths", "Quelle est la dérivée de x^3 ? Réponse courte.", ["3x^2", "3x²", "3 x^2"]),
    ("c1", "code", "Écris une fonction Python factorielle(n) récursive, sans explication.",
     ["def factorielle", "def factorial"]),
    ("c2", "code", "En SQL, comment compter les lignes d'une table users ?",
     ["count(*)", "count( * )"]),
    ("r1", "redaction", "Écris un court message de remerciement de deux phrases.", []),
    ("r2", "redaction", "Explique en trois phrases pourquoi le ciel est bleu.",
     ["diffus", "rayleigh", "scatter", "bleu"]),
    ("e1", "explication", "C'est quoi une fraction ? Réponds simplement.", ["partie", "numérateur"]),
    ("e2", "explication", "Explain what photosynthesis is in two sentences.",
     ["light", "sunlight", "energy"]),
    ("e3", "explication", "Hazavao tsotra ny photosynthèse.", ["masoandro", "zavamaniry", "plant"]),
]


def norm(text: str) -> str:
    """Comparaison tolérante (espaces, $, accolades, puissances « ² » ou « ^2 »)."""
    t = text.lower().replace("²", "^2").replace("³", "^3")
    return "".join(c for c in t if c not in " \t\n$*{}\\")


async def run(label: str) -> None:
    srv = Server()
    rows = []
    try:
        await srv.wait()
        api = Api()
        for qid, kind, text, expected in QUESTIONS:
            t0 = time.monotonic()
            ev = await api.chat(text, None, limit=180)
            done = next((e for e in ev if e["type"] == "done"), None)
            # Durée jusqu'à la réponse COMPLÈTE (la relecture par un second modèle vient après).
            wall = (done["_t"] if done else time.monotonic()) - t0
            answer = final_text(ev) if done else ""
            ok = (not expected) or any(norm(x) in norm(answer) for x in expected)
            rows.append({"id": qid, "kind": kind, "model": (done or {}).get("name"),
                         "timing": (done or {}).get("timing"), "wall_s": round(wall, 2),
                         "answered": bool(done), "correct": bool(done) and ok,
                         "chars": len(answer)})
            print(f"{qid:3} {kind:11} {wall:6.1f}s  ttft={(rows[-1]['timing'] or {}).get('ttft_s')}"
                  f"  ok={rows[-1]['correct']}  {rows[-1]['model']}", flush=True)
    finally:
        srv.stop()
    (RESULTS / f"speed-{label}.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    summary(rows)


def summary(rows: list[dict]) -> dict:
    ttft = [r["timing"]["ttft_s"] for r in rows if r["timing"] and r["timing"].get("ttft_s")]
    wall = [r["wall_s"] for r in rows if r["answered"]]
    def p90(xs: list[float]) -> float | None:
        return round(sorted(xs)[max(0, int(len(xs) * 0.9) - 1)], 2) if xs else None

    out = {"answered": sum(r["answered"] for r in rows), "correct": sum(r["correct"] for r in rows),
           "n": len(rows), "ttft_median": round(statistics.median(ttft), 2) if ttft else None,
           "ttft_p90": p90(ttft),
           "wall_median": round(statistics.median(wall), 2) if wall else None,
           "wall_p90": p90(wall)}
    print("RÉSUMÉ", out)
    return out


def compare(a: str, b: str) -> None:
    ra = json.loads((RESULTS / f"speed-{a}.json").read_text())
    rb = json.loads((RESULTS / f"speed-{b}.json").read_text())
    sa, sb = summary(ra), summary(rb)
    for key in ("ttft_median", "ttft_p90", "wall_median", "wall_p90"):
        if sa[key] and sb[key]:
            print(f"{key}: {sa[key]} -> {sb[key]}  ({(sb[key] / sa[key] - 1) * 100:+.0f} %)")
    print(f"justesse : {sa['correct']}/{sa['n']} -> {sb['correct']}/{sb['n']}")
    # Les modèles gratuits varient d'un passage à l'autre : une différence d'UNE réponse est du
    # bruit ; deux de moins, c'est une régression.
    if sb["correct"] < sa["correct"] - 1:
        raise SystemExit("RÉGRESSION de justesse : la vitesse ne doit pas coûter la rigueur")


if __name__ == "__main__":
    if sys.argv[1:2] == ["--compare"]:
        compare(sys.argv[2], sys.argv[3])
    else:
        asyncio.run(run(sys.argv[1] if len(sys.argv) > 1 else "baseline"))
