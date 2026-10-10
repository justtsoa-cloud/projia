"""Mises à jour automatiques depuis les releases GitHub.

1. Vérification non bloquante de la dernière release (`/releases/latest`).
2. Choix du fichier adapté : AppImage (Linux, selon l'architecture) ou APK
   (Android, selon l'ABI).
3. Téléchargement en arrière-plan et vérification de l'empreinte SHA-256
   publiée dans `SHA256SUMS` ; un fichier non vérifié n'est jamais proposé.
4. L'installation est faite par l'application : remplacement de l'AppImage
   puis redémarrage (Linux) ; installeur système Android (un appui, car Android
   interdit l'installation silencieuse aux applications ordinaires).
"""

from __future__ import annotations

import hashlib
import platform
import re
from pathlib import Path
from typing import Any

from tontolo import __version__, http

REPO = "raantss18/tontolo"
LATEST_URL = f"https://api.github.com/repos/{REPO}/releases/latest"


def parse_version(v: str) -> tuple[int, ...]:
    nums = re.findall(r"\d+", v.split("-")[0])
    return tuple(int(n) for n in nums[:3]) or (0,)


async def latest_release() -> dict[str, Any] | None:
    try:
        resp = await http.client().get(LATEST_URL, timeout=10,
                                       headers={"Accept": "application/vnd.github+json"})
        if resp.status_code != 200:
            return None
        data: dict[str, Any] = resp.json()
        return data
    except Exception:
        return None


def pick_asset(assets: list[dict[str, Any]], target: str, arch: str | None = None
               ) -> dict[str, Any] | None:
    """`target` : « linux » ou « android ». `arch` : x86_64/aarch64 ou ABI Android."""
    names = {a["name"]: a for a in assets}
    if target == "android":
        abi = arch or "arm64-v8a"
        for n, a in names.items():
            if n.endswith(".apk") and abi in n:
                return a
        return next((a for n, a in names.items() if n.endswith(".apk")
                     and "universal" in n), None)
    machine = (arch or platform.machine()).lower()
    machine = {"amd64": "x86_64", "arm64": "aarch64"}.get(machine, machine)
    for n, a in names.items():
        if n.endswith(".AppImage") and machine in n:
            return a
    return next((a for n, a in names.items() if n.endswith(".AppImage")), None)


def parse_sums(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in text.splitlines():
        m = re.match(r"^([0-9a-fA-F]{64})\s+\*?(.+)$", line.strip())
        if m:
            out[m.group(2).strip()] = m.group(1).lower()
    return out


async def check_update(current: str = __version__, target: str | None = None,
                       arch: str | None = None) -> dict[str, Any]:
    data = await latest_release()
    if not data:
        return {"current": current, "available": False}
    latest = str(data.get("tag_name", "")).lstrip("v")
    asset = pick_asset(data.get("assets") or [], target, arch) if target else None
    return {
        "current": current,
        "latest": latest,
        "available": bool(latest) and parse_version(latest) > parse_version(current),
        "url": data.get("html_url"),
        "notes": (data.get("body") or "")[:2000],
        "asset": asset and {"name": asset["name"], "size": asset.get("size")},
    }


async def download_update(dest_dir: Path, target: str, arch: str | None = None,
                          current: str = __version__) -> dict[str, Any]:
    """Télécharge et vérifie la mise à jour. Renvoie le chemin du fichier vérifié."""
    data = await latest_release()
    if not data:
        return {"ok": False, "error": "Release introuvable"}
    latest = str(data.get("tag_name", "")).lstrip("v")
    if parse_version(latest) <= parse_version(current):
        return {"ok": False, "error": "Déjà à jour", "latest": latest}
    assets = data.get("assets") or []
    asset = pick_asset(assets, target, arch)
    sums_asset = next((a for a in assets if a["name"] == "SHA256SUMS"), None)
    if asset is None or sums_asset is None:
        return {"ok": False, "error": "Fichier ou SHA256SUMS absent de la release"}
    client = http.client()
    sums = parse_sums((await client.get(sums_asset["browser_download_url"], timeout=30)).text)
    expected = sums.get(asset["name"])
    if not expected:
        return {"ok": False, "error": "Empreinte absente de SHA256SUMS"}
    dest_dir.mkdir(parents=True, exist_ok=True)
    final = dest_dir / asset["name"]
    if final.exists() and _sha256(final) == expected:
        return {"ok": True, "path": str(final), "version": latest, "sha256": expected}
    part = final.with_suffix(final.suffix + ".part")
    h = hashlib.sha256()
    async with client.stream("GET", asset["browser_download_url"], timeout=600) as resp:
        resp.raise_for_status()
        with part.open("wb") as fh:
            async for chunk in resp.aiter_bytes(1 << 16):
                fh.write(chunk)
                h.update(chunk)
    if h.hexdigest() != expected:
        part.unlink(missing_ok=True)
        return {"ok": False, "error": "Empreinte SHA-256 invalide : fichier rejeté"}
    part.replace(final)
    if target == "linux":
        final.chmod(0o755)
    return {"ok": True, "path": str(final), "version": latest, "sha256": expected}


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()
