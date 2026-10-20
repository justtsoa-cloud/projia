#!/usr/bin/env python3
"""Poster de version Projia (1080 × 1920, français / anglais / malgache).

Simple mais complet : le changement majeur de la version est montré par un exemple d'usage
(capture réelle de l'application + trois étapes), puis les autres changements.

    python3 press/posters/build_poster.py 0.5.2            (version courante : + affiche de l'app)
    python3 press/posters/build_poster.py 0.5.2 --no-app   (ancienne version : posters seulement)

Entrée  : press/posters/v<version>/poster.json et shots/<capture>-<langue>.png
Sortie  : press/posters/v<version>/Projia-<version>-poster-<langue>.png (publication GitHub)
          app/assets/posters/latest-<langue>.webp (fenêtre « Nouveautés » de l'application)
Nécessite rsvg-convert et magick (ImageMagick)."""

from __future__ import annotations

import base64
import html
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
W, H = 1080, 1920
WHITE, MUTED, MINT, GOLD, DARK = "#f7f7fb", "#b9c4df", "#67e5be", "#c9c6ff", "#0f0e2a"
FONT = "Noto Sans, DejaVu Sans"


def uri(path: Path) -> str:
    return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode()


def text(x: float, y: float, s: str, size: int = 36, fill: str = WHITE, weight: int = 400,
         anchor: str = "start") -> str:
    return (f'<text x="{x}" y="{y}" fill="{fill}" font-family="{FONT}" font-size="{size}" '
            f'font-weight="{weight}" text-anchor="{anchor}">{html.escape(s)}</text>')


def lines(x: float, y: float, rows: list[str], size: int, step: int, fill: str = WHITE,
          weight: int = 400, anchor: str = "start") -> str:
    return "".join(text(x, y + i * step, r, size, fill, weight, anchor)
                   for i, r in enumerate(rows))


QR_LABEL = {"fr": "Télécharger", "en": "Download", "mg": "Ampidino"}


def release_url(version: str) -> str:
    return f"https://github.com/justtsoa-cloud/projia/releases/tag/v{version}"


def qr_png(url: str) -> bytes:
    """QR code (qrencode), relu aussitôt (zbarimg) : jamais un code illisible ou faux."""
    png = subprocess.run(["qrencode", "-o", "-", "-s", "10", "-m", "2", "-l", "M", url],
                         check=True, capture_output=True).stdout
    read = subprocess.run(["zbarimg", "-q", "--raw", "-"], input=png, capture_output=True)
    if read.stdout.decode().strip() != url:
        raise SystemExit(f"QR code illisible ou faux pour {url}")
    return png


def width(s: str, size: int, bold: bool = False) -> float:
    """Largeur approximative d'une ligne (Noto Sans), assez juste pour refuser un débordement."""
    return len(s) * size * (0.58 if bold else 0.53)


def check_layout(t: dict, lang: str) -> None:
    """Les autres changements s'arrêtent avant le QR code (x = 820) ; pas d'émoji (la police du
    poster ne les dessine pas : ils sortaient en traits illisibles)."""
    import json as _json

    if any(ord(c) >= 0x1F000 or 0x2600 <= ord(c) < 0x2800 for c in _json.dumps(
            t, ensure_ascii=False)):
        raise SystemExit(f"[{lang}] émoji dans le texte du poster : remplacez-le par des mots")
    for title, rows in t["items"]:
        if 116 + width(title, 34, True) > 820:
            raise SystemExit(f"[{lang}] titre trop long (chevauche le QR) : {title}")
        for r in rows:
            if 116 + width(r, 28) > 820:
                raise SystemExit(f"[{lang}] ligne trop longue (chevauche le QR) : {r}")


def poster(data: dict, lang: str, version: str, shot: Path) -> str:
    t = data["lang"][lang]
    check_layout(t, lang)
    logo = uri(ROOT / "docs/brand/projia-icon-512.png")
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">',
        '<defs>'
        '<linearGradient id="bg" x1="0" y1="0" x2="0.4" y2="1">'
        f'<stop offset="0" stop-color="{DARK}"/><stop offset="1" stop-color="#272a73"/>'
        '</linearGradient>'
        '<radialGradient id="glow" cx="0.75" cy="0.25" r="0.6">'
        f'<stop offset="0" stop-color="{MINT}" stop-opacity="0.25"/>'
        f'<stop offset="1" stop-color="{MINT}" stop-opacity="0"/></radialGradient>'
        '<clipPath id="logo"><rect x="60" y="64" width="124" height="124" rx="30"/></clipPath>'
        '<clipPath id="screen"><rect x="74" y="510" width="330" height="733" rx="28"/></clipPath>'
        '</defs>',
        f'<rect width="{W}" height="{H}" fill="url(#bg)"/>',
        f'<rect width="{W}" height="{H}" fill="url(#glow)"/>',
        f'<circle cx="980" cy="1500" r="220" fill="{MINT}" opacity="0.05"/>',
        f'<circle cx="80" cy="1720" r="140" fill="{GOLD}" opacity="0.06"/>',
        # en-tête
        f'<image href="{logo}" x="60" y="64" width="124" height="124" clip-path="url(#logo)"/>',
        text(214, 130, "Projia", 66, WHITE, 700),
        f'<rect x="214" y="150" width="190" height="52" rx="26" fill="{MINT}"/>',
        text(309, 188, version, 34, DARK, 700, "middle"),
        text(424, 188, t["tagline"] + " · " + t["date"], 26, MUTED),
        # changement majeur
        lines(60, 316, t["hero"], 80, 90, WHITE, 700),
        text(60, 316 + 90 * (len(t["hero"]) - 1) + 56, t["sub"], 32, MINT, 500),
        # téléphone
        f'<rect x="60" y="496" width="358" height="761" rx="40" fill="#05050f" '
        f'stroke="{MINT}" stroke-width="4"/>',
        f'<image href="{uri(shot)}" x="74" y="510" width="330" height="733" '
        'preserveAspectRatio="xMidYMid slice" clip-path="url(#screen)"/>',
    ]
    # trois étapes : l'exemple d'usage
    ys = [546, 806, 1046]
    out.append(f'<line x1="498" y1="586" x2="498" y2="1146" stroke="{MINT}" stroke-width="3" '
               'stroke-dasharray="2 14" stroke-linecap="round" opacity="0.7"/>')
    for i, (y, rows) in enumerate(zip(ys, t["steps"], strict=True)):
        out.append(f'<circle cx="498" cy="{y + 20}" r="32" fill="{MINT}"/>')
        out.append(text(498, y + 32, str(i + 1), 36, DARK, 700, "middle"))
        out.append(lines(552, y + 10, rows, 32, 42, WHITE, 600))
    # autres changements
    out.append(f'<line x1="60" y1="1292" x2="1020" y2="1292" stroke="{MUTED}" '
               'stroke-width="1" opacity="0.4"/>')
    out.append(text(60, 1352, t["also"], 40, GOLD, 700))
    y = 1418
    for title, rows in t["items"]:
        out.append(f'<circle cx="84" cy="{y - 10}" r="12" fill="{MINT}"/>')
        out.append(text(116, y, title, 34, WHITE, 700))
        out.append(lines(116, y + 40, rows, 28, 34, MUTED))
        y += 40 + 34 * len(rows) + 34
    # QR code vers la page de cette version (téléchargements)
    qr = "data:image/png;base64," + base64.b64encode(qr_png(release_url(version))).decode()
    out.append(f'<rect x="836" y="1316" width="188" height="188" rx="18" fill="{WHITE}"/>')
    out.append(f'<image href="{qr}" x="846" y="1326" width="168" height="168"/>')
    out.append(text(930, 1544, QR_LABEL.get(lang, QR_LABEL["en"]), 28, MINT, 700, "middle"))
    # pied
    out.append(text(60, 1872, "github.com/justtsoa-cloud/projia", 30, WHITE, 600))
    out.append(text(1020, 1872, t["footer"], 26, MUTED, 400, "end"))
    out.append("</svg>")
    return "".join(out)


def main(version: str, for_app: bool = True) -> None:
    folder = ROOT / "press/posters" / f"v{version}"
    data = json.loads((folder / "poster.json").read_text(encoding="utf-8"))
    assets = ROOT / "app/assets/posters"
    assets.mkdir(parents=True, exist_ok=True)
    for lang in ("fr", "en", "mg"):
        shot = folder / "shots" / f"{data['shot']}-{lang}.png"
        svg = folder / f"poster-{lang}.svg"
        png = folder / f"Projia-{version}-poster-{lang}.png"
        svg.write_text(poster(data, lang, version, shot), encoding="utf-8")
        subprocess.run(["rsvg-convert", str(svg), "-o", str(png)], check=True)
        svg.unlink()
        if for_app:  # version légère pour l'application (une seule affiche : la dernière)
            subprocess.run(["magick", str(png), "-resize", "810x", "-quality", "82",
                            str(assets / f"latest-{lang}.webp")], check=True)
        print(png.relative_to(ROOT), png.stat().st_size // 1024, "Ko")
    if for_app:
        (assets / "version.txt").write_text(version + "\n", encoding="utf-8")


if __name__ == "__main__":
    # --no-app : refaire les posters d'une ancienne version sans toucher à l'affiche embarquée.
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    main(args[0] if args else "0.5.2", "--no-app" not in sys.argv)
