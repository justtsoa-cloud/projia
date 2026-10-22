#!/usr/bin/env python3
"""Logo Projia : « Spark P », un monogramme.

    python3 docs/brand/build_logo.py

Sorties : projia-icon.svg / projia-mark.svg, PNG (512), app/assets/icon.png, icônes Android
(héritée, adaptative et monochrome). Nécessite le paquet Python `cairosvg` (groupe dev).

Lecture du logo
- Le fût du « P » : la base, le routeur qui reçoit la demande.
- Le losange : la boucle du « P », aplatie en diamant — le catalogue de modèles, condensé en
  une seule forme.
- L'étincelle qui s'en détache : la réponse choisie, celle qui sort du routage automatique.
"""

from __future__ import annotations

import math
from pathlib import Path

import cairosvg

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

INK0, INK1 = "#2E2142", "#120D1C"   # fond : encre violette, dégradé radial
GOLD, CORAL = "#FFD166", "#FF6B4A"  # fût : dégradé chaud (haut -> bas)
PERI = "#7C6CF0"                    # losange : la boucle du P
MINT = "#2FBE9C"                    # étincelle


def _star(cx: float, cy: float, r_out: float, r_in: float, points: int = 4,
          rotation: float = -90) -> str:
    """Chemin d'une étincelle à N branches (alternance rayon ext./int.)."""
    pts: list[str] = []
    steps = points * 2
    for i in range(steps):
        r = r_out if i % 2 == 0 else r_in
        a = math.radians(rotation + 360 * i / steps)
        pts.append(f"{cx + r * math.cos(a):.1f} {cy + r * math.sin(a):.1f}")
    return "M" + " L".join(pts) + " Z"


def defs() -> str:
    return f"""<defs>
<radialGradient id="bg" cx="0.28" cy="0.2" r="0.95">
<stop offset="0" stop-color="{INK0}"/><stop offset="1" stop-color="{INK1}"/>
</radialGradient>
<linearGradient id="stem" x1="0" y1="0" x2="0" y2="1">
<stop offset="0" stop-color="{GOLD}"/><stop offset="1" stop-color="{CORAL}"/>
</linearGradient>
<linearGradient id="bowl" x1="0" y1="0" x2="1" y2="1">
<stop offset="0" stop-color="#9A8CFF"/><stop offset="1" stop-color="{PERI}"/>
</linearGradient>
<linearGradient id="spark" x1="0" y1="0" x2="0" y2="1">
<stop offset="0" stop-color="#6BE6C8"/><stop offset="1" stop-color="{MINT}"/>
</linearGradient>
</defs>"""


def mark(*, mono: bool = False) -> str:
    """Le logo sans fond (1024 x 1024, centré) : fût, losange, étincelle."""
    stem = "#fff" if mono else "url(#stem)"
    bowl = "#fff" if mono else "url(#bowl)"
    spark_fill = "#fff" if mono else "url(#spark)"
    spark_path = _star(722, 210, 60, 17)
    dot = '<circle cx="600" cy="300" r="14" fill="{0}" opacity="{1}"/>'.format(
        "#fff" if mono else MINT, "0.9" if mono else "0.85")
    return (f'<rect x="368" y="300" width="132" height="560" rx="66" fill="{stem}"/>'
            f'<rect x="388" y="230" width="300" height="300" rx="68" fill="{bowl}" '
            f'transform="rotate(45 538 380)"/>'
            f'<path d="{spark_path}" fill="{spark_fill}"/>' + dot)


def icon(size: int = 1024, *, rounded: bool = True) -> str:
    bg = '<rect width="1024" height="1024" rx="232" fill="url(#bg)"/>' if rounded else \
        '<rect width="1024" height="1024" fill="url(#bg)"/>'
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024" '
            f'width="{size}" height="{size}">{defs()}{bg}{mark()}</svg>')


def foreground(mono: bool = False) -> str:
    """Icône adaptative Android : 108 dp, zone sûre centrale (66 dp) : le logo y est réduit."""
    inner = mark(mono=mono)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024" '
            f'width="1024" height="1024">{defs()}'
            f'<g transform="translate(512 512) scale(0.72) translate(-512 -512)">{inner}</g></svg>')


def render(svg: str, out: Path, size: int) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    cairosvg.svg2png(bytestring=svg.encode(), write_to=str(out),
                      output_width=size, output_height=size)


def main() -> None:
    (HERE / "projia-icon.svg").write_text(icon(), "utf-8")
    (HERE / "projia-mark.svg").write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024" '
        f'width="1024" height="1024">{defs()}{mark()}</svg>', "utf-8")
    render(icon(), HERE / "projia-icon-512.png", 512)
    render(icon(), ROOT / "app/assets/icon.png", 512)
    res = ROOT / "app/android/app/src/main/res"
    sizes = {"mdpi": 48, "hdpi": 72, "xhdpi": 96, "xxhdpi": 144, "xxxhdpi": 192}
    for dens, px in sizes.items():
        render(icon(), res / f"mipmap-{dens}/ic_launcher.png", px)
        render(foreground(), res / f"mipmap-{dens}/ic_launcher_foreground.png", px * 108 // 48)
        render(foreground(mono=True), res / f"mipmap-{dens}/ic_launcher_monochrome.png",
               px * 108 // 48)
    print("logo généré")


if __name__ == "__main__":
    main()
