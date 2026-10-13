"""Métriques locales (format texte Prometheus), lisibles sur `/tontolo/metrics` avec le jeton.
Rien n'est envoyé nulle part : c'est pour observer son propre cœur (bureau, serveur maison).
Compteurs en mémoire, remis à zéro au redémarrage."""

from __future__ import annotations

import re
import time
from collections import defaultdict

STARTED = time.time()
_counters: dict[tuple[str, tuple[tuple[str, str], ...]], float] = defaultdict(float)
_HELP = {
    "tontolo_turns_total": "Tours de discussion lancés",
    "tontolo_model_calls_total": "Appels de modèle, par modèle et résultat",
    "tontolo_model_seconds_sum": "Durée cumulée des appels réussis, par modèle",
    "tontolo_answer_cache_hits_total": "Réponses servies depuis les réponses déjà données",
    "tontolo_errors_total": "Erreurs de fournisseur, par type",
}


def inc(name: str, value: float = 1.0, **labels: str) -> None:
    _counters[(name, tuple(sorted((k, str(v)[:120]) for k, v in labels.items())))] += value


def _escape(v: str) -> str:
    return re.sub(r'(["\\\\])', r"\\\\\\1", v).replace("\n", " ")


def render(gauges: dict[str, float] | None = None) -> str:
    lines: list[str] = []
    seen: set[str] = set()
    for (name, labels), value in sorted(_counters.items()):
        if name not in seen:
            seen.add(name)
            lines += [f"# HELP {name} {_HELP.get(name, name)}", f"# TYPE {name} counter"]
        lab = ",".join(f'{k}="{_escape(v)}"' for k, v in labels)
        lines.append(f"{name}{{{lab}}} {value:g}" if lab else f"{name} {value:g}")
    for name, value in sorted({**(gauges or {}),
                               "tontolo_uptime_seconds": time.time() - STARTED}.items()):
        lines += [f"# TYPE {name} gauge", f"{name} {value:g}"]
    return "\n".join(lines) + "\n"


def reset() -> None:
    _counters.clear()
