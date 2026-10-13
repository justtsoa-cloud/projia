#!/usr/bin/env python3
"""Logo Tontolo : l'Afrique et Madagascar, un logo « pas tout à fait fini ».

    python3 docs/brand/build_logo.py

Entrées : docs/brand/logo/africa-trace.svg et madagascar-trace.svg (silhouettes vectorisées
avec potrace à partir du visuel de référence `reference-globe.webp`).
Sorties : tontolo-icon.svg / tontolo-mark.svg, PNG (512), app/assets/icon.png, icônes Android
(héritée, adaptative et monochrome). Nécessite rsvg-convert et magick (ImageMagick).

Lecture du logo
- « O » : l'anneau ouvert, aux extrémités effilées, dont le trait se prolonge en pointillés
  dans l'ouverture (ce qui reste à tracer).
- « T » : une ligne fine posée sur l'Afrique, avec sa boucle (le petit « o » de Tontolo).
- Madagascar, en orange : le point de départ ; l'Afrique s'estompe vers le nord, comme si
  elle était encore en train d'être dessinée."""

from __future__ import annotations

import math
import re
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
NAVY0, NAVY1 = "#1E1B4B", "#312E81"
CX, CY = 512, 512


def trace(name: str) -> tuple[str, str]:
    """(transformation potrace, données du tracé) d'une silhouette vectorisée."""
    svg = (HERE / "logo" / name).read_text("utf-8")
    d = re.search(r'<path d="([^"]+)"', svg).group(1)
    return re.search(r'<g transform="([^"]+)"', svg).group(1), " ".join(d.split())


def ring(radius: float, width: float, gap: tuple[float, float], taper: float = 34) -> str:
    """Anneau ouvert (angles en degrés, sens horaire à l'écran) dont l'épaisseur s'effile aux
    deux extrémités ; `gap` = (début, fin) de l'ouverture."""
    start, end = gap[1], gap[0] + 360  # de la fin de l'ouverture jusqu'à son début
    pts_o, pts_i = [], []
    steps = 220
    for i in range(steps + 1):
        a = start + (end - start) * i / steps
        edge = min(a - start, end - a)
        w = width * (0.16 + 0.84 * min(1.0, edge / taper) ** 0.8)
        r_o, r_i = radius + w / 2, radius - w / 2
        t = math.radians(a)
        pts_o.append((CX + r_o * math.cos(t), CY + r_o * math.sin(t)))
        pts_i.append((CX + r_i * math.cos(t), CY + r_i * math.sin(t)))
    pts = pts_o + pts_i[::-1]
    return "M" + " L".join(f"{x:.1f} {y:.1f}" for x, y in pts) + " Z"


def dots(radius: float, gap: tuple[float, float]) -> str:
    """Pointillés dans l'ouverture : la suite du cercle, pas encore tracée."""
    out = []
    n = 6
    for i in range(n):
        a = math.radians(gap[0] + 8 + (gap[1] - gap[0] - 16) * i / (n - 1))
        out.append(f'<circle cx="{CX + radius * math.cos(a):.1f}" cy="{CY + radius * math.sin(a):.1f}" '
                   f'r="{5.5 - i * 0.0:.1f}" fill="url(#ring)" opacity="{0.55 - 0.05 * i:.2f}"/>')
    return "".join(out)


# « T » : traverse (avec sa boucle à gauche, le « o ») et fût qui finit en crochet.
T_PATH = ("M 470 322 C 420 322 392 296 392 262 C 392 232 414 212 440 212 C 468 212 486 234 486 262 "
          "L 486 322 L 690 322 M 486 322 L 486 640 C 486 700 530 738 590 738")


def africa_layers(prefix: str = "") -> str:
    """Afrique et Madagascar (couleurs ou, pour la version monochrome, blanc)."""
    ta, da = trace("africa-trace.svg")
    tm, dm = trace("madagascar-trace.svg")
    mono = prefix == "mono"
    fill_a = "#fff" if mono else "url(#land)"
    fill_m = "#fff" if mono else "url(#mada)"
    place = "translate(497 520) scale(0.3233) translate(-957 -1152)"
    # Madagascar agrandie autour de son centre (275,263 px du visuel de référence)
    mada = f"translate(497 520) scale(0.3233) translate(-957 -1152) translate(1653 1578) scale(1.5) translate(-1653 -1578)"
    return (f'<g mask="url(#fade)"><g transform="{place}"><g transform="{ta}"><path d="{da}" fill="{fill_a}"/></g></g></g>'
            f'<g transform="{mada}"><g transform="{tm}"><path d="{dm}" fill="{fill_m}"/></g></g>')


def defs() -> str:
    return f"""<defs>
<linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{NAVY0}"/><stop offset="1" stop-color="{NAVY1}"/></linearGradient>
<linearGradient id="land" x1="260" y1="230" x2="760" y2="830" gradientUnits="userSpaceOnUse"><stop offset="0" stop-color="#33D6E8"/><stop offset="0.55" stop-color="#34D3B4"/><stop offset="1" stop-color="#3FD28A"/></linearGradient>
<linearGradient id="mada" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#FFB05C"/><stop offset="1" stop-color="#FF7A3D"/></linearGradient>
<linearGradient id="ring" x1="150" y1="200" x2="880" y2="840" gradientUnits="userSpaceOnUse"><stop offset="0" stop-color="#22E3F5"/><stop offset="0.6" stop-color="#34D3B4"/><stop offset="1" stop-color="#3FD28A"/></linearGradient>
<linearGradient id="fadeg" x1="0" y1="200" x2="0" y2="520" gradientUnits="userSpaceOnUse"><stop offset="0" stop-color="#000"/><stop offset="0.45" stop-color="#555"/><stop offset="1" stop-color="#fff"/></linearGradient>
<mask id="fade" maskUnits="userSpaceOnUse" x="0" y="0" width="1024" height="1024"><rect x="0" y="0" width="1024" height="1024" fill="url(#fadeg)"/></mask>
<radialGradient id="glow" cx="0.5" cy="0.5" r="0.5"><stop offset="0" stop-color="#FF9A4D" stop-opacity="0.55"/><stop offset="1" stop-color="#FF9A4D" stop-opacity="0"/></radialGradient>
</defs>"""


GAP = (-62, 2)  # ouverture de l'anneau (à droite, en haut de Madagascar)
RADIUS, WIDTH = 408, 25


def mark(*, mono: bool = False) -> str:
    """Le logo sans fond (1024 × 1024, centré)."""
    if mono:  # silhouette blanche ; le « T » est évidé (Android la teinte selon le thème)
        return (f'<mask id="tcut" maskUnits="userSpaceOnUse" x="0" y="0" width="1024" height="1024">'
                f'<rect width="1024" height="1024" fill="#fff"/><path d="{T_PATH}" fill="none" stroke="#000" '
                f'stroke-width="20" stroke-linecap="round" stroke-linejoin="round"/></mask>'
                f'<g mask="url(#tcut)"><path d="{ring(RADIUS, WIDTH, GAP)}" fill="#fff"/>'
                + africa_layers("mono") + '</g>')
    return (f'<circle cx="758" cy="684" r="150" fill="url(#glow)"/>'
            + africa_layers()
            + f'<path d="{ring(RADIUS, WIDTH, GAP)}" fill="url(#ring)"/>' + dots(RADIUS, GAP)
            + f'<path d="{T_PATH}" fill="none" stroke="#EFFFF8" stroke-opacity="0.82" stroke-width="15" '
              'stroke-linecap="round" stroke-linejoin="round"/>')


def icon(size: int = 1024, *, rounded: bool = True) -> str:
    bg = f'<rect width="1024" height="1024" rx="232" fill="url(#bg)"/>' if rounded else \
        '<rect width="1024" height="1024" fill="url(#bg)"/>'
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024" width="{size}" height="{size}">'
            f'{defs()}{bg}{mark()}</svg>')


def foreground(mono: bool = False) -> str:
    """Icône adaptative Android : 108 dp, zone sûre centrale (66 dp) : le logo y est réduit."""
    inner = mark(mono=mono)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024" width="1024" height="1024">'
            f'{defs()}<g transform="translate(512 512) scale(0.7) translate(-512 -512)">{inner}</g></svg>')


def render(svg: str, out: Path, size: int) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["rsvg-convert", "-w", str(size), "-h", str(size), "-o", str(out)],
                   input=svg.encode(), check=True)


def main() -> None:
    (HERE / "tontolo-icon.svg").write_text(icon(), "utf-8")
    (HERE / "tontolo-mark.svg").write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024" width="1024" height="1024">'
        f'{defs()}{mark()}</svg>', "utf-8")
    render(icon(), HERE / "tontolo-icon-512.png", 512)
    render(icon(), ROOT / "app/assets/icon.png", 512)
    res = ROOT / "app/android/app/src/main/res"
    sizes = {"mdpi": 48, "hdpi": 72, "xhdpi": 96, "xxhdpi": 144, "xxxhdpi": 192}
    for dens, px in sizes.items():
        render(icon(), res / f"mipmap-{dens}/ic_launcher.png", px)
        render(foreground(), res / f"mipmap-{dens}/ic_launcher_foreground.png", px * 108 // 48)
        render(foreground(mono=True), res / f"mipmap-{dens}/ic_launcher_monochrome.png", px * 108 // 48)
    print("logo généré")


if __name__ == "__main__":
    main()
