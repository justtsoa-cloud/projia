#!/usr/bin/env python3
"""Affiches de campagne Projia (1080 × 1440, fr / en / mg) : des prompts courts et usuels à
copier, la façon la plus efficace de s'en servir, un QR code vers la dernière version.

    python3 press/posters/build_campaign.py 2026-10-14

Entrée : press/campaigns/<date>/campaign.json
Sortie : press/campaigns/<date>/<id>-<langue>.png et captions.md (textes pour les réseaux)
Règles : aucun prénom ni donnée personnelle, pas d'orange, pas d'émoji (police du poster).
Nécessite rsvg-convert, qrencode, zbarimg."""

from __future__ import annotations

import base64
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from build_poster import (DARK, FONT, GOLD, MINT, MUTED, ROOT, WHITE, qr_png,  # noqa: E402
                          text, uri, width)

W, H = 1080, 1440
LATEST = "https://github.com/justtsoa-cloud/projia/releases/latest"
LABELS = {
    "fr": {"say": "Dites-lui", "tip": "La façon la plus efficace", "get": "Télécharger",
           "free": "Gratuit · Android · Linux"},
    "en": {"say": "Just say", "tip": "The most effective way", "get": "Download",
           "free": "Free · Android · Linux"},
    "mg": {"say": "Lazao azy", "tip": "Ny fomba mahomby indrindra", "get": "Ampidino",
           "free": "Maimaim-poana · Android · Linux"},
}


def title_size(line: str) -> int:
    """Taille du titre : 76 si ça tient, sinon réduite pour tenir dans 960 px."""
    return int(min(76, 960 / (len(line) * 0.58)))


def check(poster: dict, lang: str) -> None:
    blob = json.dumps(poster, ensure_ascii=False)
    if any(ord(c) >= 0x1F000 or 0x2600 <= ord(c) < 0x2800 for c in blob):
        raise SystemExit(f"[{lang}] émoji interdit dans {poster['id']}")
    for line in poster["title"]:
        if title_size(line) < 52:
            raise SystemExit(f"[{lang}] titre trop long : {line}")
    for rows in poster["prompts"]:
        for r in rows:
            if width(r, 38) > 840:
                raise SystemExit(f"[{lang}] prompt trop long : {r}")
    for r in poster["tip"]:
        if width(r, 31) > 880:
            raise SystemExit(f"[{lang}] astuce trop longue : {r}")


def wrap_prompts(poster: dict) -> dict:
    """Un prompt trop long pour une ligne passe sur deux lignes (jamais tronqué)."""
    import textwrap

    rows = []
    for r in poster["prompts"]:
        rows.append(r if all(width(x, 38) <= 840 for x in r)
                    else textwrap.wrap(" ".join(r), 40))
    return {**poster, "prompts": rows}


def build(poster: dict, lang: str) -> str:
    poster = wrap_prompts(poster)
    check(poster, lang)
    lab = LABELS[lang]
    logo = uri(ROOT / "docs/brand/projia-icon-512.png")
    qr = "data:image/png;base64," + base64.b64encode(qr_png(LATEST)).decode()
    o = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
        f'viewBox="0 0 {W} {H}"><defs>'
        '<linearGradient id="bg" x1="0" y1="0" x2="0.4" y2="1">'
        f'<stop offset="0" stop-color="{DARK}"/><stop offset="1" stop-color="#272a73"/>'
        '</linearGradient><radialGradient id="glow" cx="0.8" cy="0.2" r="0.6">'
        f'<stop offset="0" stop-color="{MINT}" stop-opacity="0.25"/>'
        f'<stop offset="1" stop-color="{MINT}" stop-opacity="0"/></radialGradient>'
        '<clipPath id="logo"><rect x="60" y="56" width="96" height="96" rx="24"/></clipPath>'
        '</defs>',
        f'<rect width="{W}" height="{H}" fill="url(#bg)"/>',
        f'<rect width="{W}" height="{H}" fill="url(#glow)"/>',
        f'<image href="{logo}" x="60" y="56" width="96" height="96" clip-path="url(#logo)"/>',
        text(182, 120, "Projia", 56, WHITE, 700),
        text(1020, 118, poster["kicker"], 28, MINT, 600, "end"),
    ]
    y = 262
    for line in poster["title"]:
        o.append(text(60, y, line, title_size(line), WHITE, 700))
        y += 88
    o.append(text(60, y + 4, poster["sub"], 32, MINT, 500))
    y += 74
    o.append(text(60, y, lab["say"], 36, GOLD, 700))
    y += 26
    for rows in poster["prompts"]:
        h = 48 + 54 * len(rows)
        o.append(f'<rect x="60" y="{y}" width="960" height="{h}" rx="26" fill="#ffffff" '
                 'fill-opacity="0.09"/>')
        o.append(f'<rect x="60" y="{y}" width="10" height="{h}" rx="5" fill="{MINT}"/>')
        for i, r in enumerate(rows):
            o.append(text(100, y + 64 + 54 * i, r, 38, WHITE, 600))
        y += h + 24
    y += 16
    th = 86 + 46 * len(poster["tip"])
    o.append(f'<rect x="60" y="{y}" width="960" height="{th}" rx="26" fill="{MINT}" '
             'fill-opacity="0.16" stroke="' + MINT + '" stroke-width="2"/>')
    o.append(text(90, y + 48, lab["tip"], 28, MINT, 700))
    for i, r in enumerate(poster["tip"]):
        o.append(text(90, y + 96 + 46 * i, r, 31, WHITE, 500))
    o.append(f'<rect x="866" y="1208" width="154" height="154" rx="16" fill="{WHITE}"/>')
    o.append(f'<image href="{qr}" x="874" y="1216" width="138" height="138"/>')
    o.append(text(943, 1394, lab["get"], 24, MINT, 700, "middle"))
    o.append(text(60, 1380, "github.com/justtsoa-cloud/projia", 30, WHITE, 600))
    o.append(text(60, 1418, lab["free"], 24, MUTED))
    o.append("</svg>")
    return "".join(o)


def main(day: str) -> None:
    folder = ROOT / "press/campaigns" / day
    data = json.loads((folder / "campaign.json").read_text(encoding="utf-8"))
    caps = [f"# Campagne du {day}\n"]
    for p in data["posters"]:
        for lang in ("fr", "en", "mg"):
            svg = folder / f"{p['id']}-{lang}.svg"
            png = folder / f"{p['id']}-{lang}.png"
            svg.write_text(build({**p["lang"][lang], "id": p["id"]}, lang), encoding="utf-8")
            subprocess.run(["rsvg-convert", str(svg), "-o", str(png)], check=True)
            svg.unlink()
            print(png.relative_to(ROOT), png.stat().st_size // 1024, "Ko")
        caps.append(f"## {p['id']}\n")
        for lang in ("fr", "en", "mg"):
            caps.append(f"**{lang}** — {p['lang'][lang]['caption']}\n")
    (folder / "captions.md").write_text("\n".join(caps), encoding="utf-8")


if __name__ == "__main__":
    main(sys.argv[1])
