#!/usr/bin/env python3
"""Règle de version de Projia : chaque chiffre va de 0 à 9.

    0.2.8 → 0.2.9 → 0.3.0      (après x.y.9 : x.(y+1).0)
    0.9.9 → 1.0.0              (après x.9.9 : (x+1).0.0)

Un saut volontaire au palier supérieur reste permis (0.4.7 → 0.5.0 ou → 1.0.0), jamais un
chiffre à 10 ni un retour en arrière.

Usage :
    python3 scripts/bump_version.py            # passe à la version suivante (+1 build Android)
    python3 scripts/bump_version.py 0.6.0      # passe à une version précise (si permise)
    python3 scripts/bump_version.py --check    # vérifie les fichiers (CI)
    python3 scripts/bump_version.py --check-tag v0.5.1   # vérifie une étiquette (release)

Après une montée de version : section du CHANGELOG, nouveautés fr/en/mg
(app/lib/core/whats_new.dart), puis tests cœur et Flutter avant l'étiquette.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = {
    "core/pyproject.toml": re.compile(r'^(version = ")(\d+\.\d+\.\d+)(")', re.M),
    "core/projia/__init__.py": re.compile(r'^(__version__ = ")(\d+\.\d+\.\d+)(")', re.M),
    "app/lib/core/updater.dart": re.compile(r"^(const appVersion = ')(\d+\.\d+\.\d+)(')", re.M),
    "app/pubspec.yaml": re.compile(r"^(version: )(\d+\.\d+\.\d+)(\+\d+)", re.M),
}
Version = tuple[int, int, int]


def parse(v: str) -> Version:
    m = re.fullmatch(r"v?(\d)\.(\d)\.(\d)", v.strip())
    if not m:
        raise ValueError(f"version invalide « {v} » : trois chiffres de 0 à 9 (ex. 0.5.1)")
    return int(m[1]), int(m[2]), int(m[3])


def fmt(v: Version) -> str:
    return ".".join(map(str, v))


def next_version(v: Version) -> Version:
    x, y, z = v
    if z < 9:
        return x, y, z + 1
    if y < 9:
        return x, y + 1, 0
    return x + 1, 0, 0


def allowed_after(prev: Version) -> set[Version]:
    """Suivante, ou saut volontaire au palier mineur / majeur suivant."""
    x, y, _ = prev
    out = {next_version(prev), (x + 1, 0, 0)}
    if y < 9:
        out.add((x, y + 1, 0))
    return out


def current() -> tuple[dict[str, str], int]:
    found: dict[str, str] = {}
    build = 0
    for rel, rx in FILES.items():
        m = rx.search((ROOT / rel).read_text(encoding="utf-8"))
        if not m:
            raise SystemExit(f"version introuvable dans {rel}")
        found[rel] = m[2]
        if rel.endswith("pubspec.yaml"):
            build = int(m[3][1:])
    return found, build


def previous_tag(exclude: str | None = None) -> str | None:
    tags = subprocess.run(["git", "tag", "-l", "v*", "--sort=-v:refname"], cwd=ROOT,
                          capture_output=True, text=True, check=False).stdout.split()
    tags = [t for t in tags if t != exclude and re.fullmatch(r"v\d\.\d\.\d", t)]
    return tags[0] if tags else None


def check(tag: str | None = None) -> int:
    found, _ = current()
    versions = set(found.values())
    if len(versions) != 1:
        print("Versions différentes selon les fichiers :", found)
        return 1
    v = parse(versions.pop())
    if tag is not None:
        if parse(tag) != v:
            print(f"L'étiquette {tag} ne correspond pas à la version des fichiers {fmt(v)}")
            return 1
        prev = previous_tag(exclude=tag)
        if prev is not None and v not in allowed_after(parse(prev)):
            ok = ", ".join(sorted(fmt(a) for a in allowed_after(parse(prev))))
            print(f"{fmt(v)} ne suit pas la règle après {prev} (permis : {ok})")
            return 1
    print(f"Version {fmt(v)} cohérente")
    return 0


def bump(target: str | None) -> int:
    found, build = current()
    now = parse(next(iter(found.values())))
    new = parse(target) if target else next_version(now)
    if new not in allowed_after(now):
        ok = ", ".join(sorted(fmt(a) for a in allowed_after(now)))
        print(f"{fmt(new)} ne suit pas la règle après {fmt(now)} (permis : {ok})")
        return 1
    for rel, rx in FILES.items():
        path = ROOT / rel
        text = path.read_text(encoding="utf-8")
        if rel.endswith("pubspec.yaml"):
            text = rx.sub(lambda m: f"{m[1]}{fmt(new)}+{build + 1}", text, count=1)
        else:
            text = rx.sub(lambda m: f"{m[1]}{fmt(new)}{m[3]}", text, count=1)
        path.write_text(text, encoding="utf-8")
    print(f"{fmt(now)} → {fmt(new)} (build Android {build + 1}).")
    print("À faire : CHANGELOG, app/lib/core/whats_new.dart (fr/en/mg), tests, puis étiquette.")
    return 0


if __name__ == "__main__":
    args = sys.argv[1:]
    if args[:1] == ["--check"]:
        sys.exit(check())
    if args[:1] == ["--check-tag"] and len(args) == 2:
        sys.exit(check(args[1]))
    sys.exit(bump(args[0] if args else None))
