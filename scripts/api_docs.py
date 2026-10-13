#!/usr/bin/env python3
"""Génère docs/API.md depuis le schéma OpenAPI du cœur (aucun serveur lancé).

    cd core && uv run python ../scripts/api_docs.py
"""

from __future__ import annotations

from pathlib import Path

from tontolo.server.app import create_app

ROOT = Path(__file__).resolve().parents[1]


def render() -> str:
    schema = create_app(refresh=False).openapi()
    out = ["# API du cœur Tontolo", "",
           "Serveur local (127.0.0.1, jeton `Authorization: Bearer …` hors boucle locale). "
           "Schéma complet : `GET /openapi.json`. Fichier généré par `scripts/api_docs.py` : "
           "ne pas modifier à la main.", ""]
    groups: dict[str, list[str]] = {}
    for path, ops in sorted(schema["paths"].items()):
        group = ("OpenAI (compatible)" if path.startswith("/v1/") else
                 path.split("/")[2].capitalize() if path.startswith("/tontolo/") else "Divers")
        for method, op in ops.items():
            doc = (op.get("description") or op.get("summary") or "").strip().split("\n")[0]
            groups.setdefault(group, []).append(f"| `{method.upper()}` | `{path}` | {doc} |")
    for group, rows in sorted(groups.items()):
        out += [f"## {group}", "", "| Méthode | Chemin | Rôle |", "|---|---|---|", *rows, ""]
    out += ["WebSockets : `/tontolo/ws` (événements), `/tontolo/terminal/{cid}/ws` (terminal du "
            "bureau, application locale avec jeton uniquement).", ""]
    return "\n".join(out)


if __name__ == "__main__":
    (ROOT / "docs" / "API.md").write_text(render(), encoding="utf-8")
    print("docs/API.md")
