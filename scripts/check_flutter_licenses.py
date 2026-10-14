#!/usr/bin/env python3
"""Contrôle fermé des licences Dart résolues : Apache-2.0, MIT ou BSD uniquement."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.parse import unquote, urljoin, urlparse


# MPL-2.0 (copyleft au niveau du fichier) : dépendance transitive non modifiée, utilisée telle
# quelle ; compatible avec une diffusion Apache-2.0. Toute autre exception est refusée.
MPL_UNMODIFIED = frozenset({'dbus'})


def classify(text: str) -> str | None:
    lower = text.lower()
    # Une mention MIT dans les attributions ne doit pas masquer un copyleft principal.
    if any(mark in lower for mark in ('mozilla public license', 'gnu general public license',
                                     'gnu lesser general public license', 'affero')):
        return None
    if 'apache license' in lower and 'version 2.0' in lower:
        return 'Apache-2.0'
    if 'permission is hereby granted, free of charge' in lower:
        return 'MIT'
    if 'redistribution and use in source and binary forms' in lower:
        return 'BSD'
    return None


def check(config: Path) -> list[str]:
    failed = []
    for item in json.loads(config.read_text())['packages']:
        root = Path(unquote(urlparse(urljoin(config.as_uri(), item['rootUri'])).path))
        candidates = [root / name for name in ('LICENSE', 'LICENSE.md', 'LICENSE.txt', 'COPYING')]
        if item['name'] in ('flutter', 'flutter_test', 'flutter_web_plugins', 'sky_engine'):
            # Paquets du SDK Flutter : licence commune à la racine du SDK.
            candidates += [parent / 'LICENSE' for parent in root.parents
                           if (parent / 'bin' / 'flutter').exists()]
        if item['name'] == 'tontolo':
            candidates.append(root.parent / 'LICENSE')
        text = '\n'.join(p.read_text(errors='replace') for p in candidates if p.is_file())
        kind = classify(text)
        if kind is None and item['name'] in MPL_UNMODIFIED and 'mozilla public license' in text.lower():
            print(f"Exception documentée : {item['name']} (MPL-2.0, non modifié)")
            continue
        if kind is None:
            failed.append(item['name'])
            print(f"REFUS : {item['name']} — licence absente, non reconnue ou hors liste")
    return failed


if __name__ == '__main__':
    config = Path(sys.argv[1] if len(sys.argv) > 1 else 'app/.dart_tool/package_config.json').resolve()
    failures = check(config)
    print(f'Contrôle des licences : {len(failures)} refus')
    raise SystemExit(bool(failures))
