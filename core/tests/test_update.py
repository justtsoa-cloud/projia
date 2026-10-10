"""Mises à jour automatiques : choix du fichier et vérification SHA-256."""

from __future__ import annotations

import hashlib
from pathlib import Path

import httpx
import respx

from tontolo.update import download_update, parse_sums, parse_version, pick_asset

ASSETS = [
    {"name": "Tontolo-0.2.0-x86_64.AppImage", "browser_download_url": "https://github.com/dl/x86"},
    {"name": "Tontolo-0.2.0-aarch64.AppImage", "browser_download_url": "https://github.com/dl/arm"},
    {"name": "tontolo-0.2.0-arm64-v8a.apk", "browser_download_url": "https://github.com/dl/apk64"},
    {"name": "tontolo-0.2.0-armeabi-v7a.apk", "browser_download_url": "https://github.com/dl/apk32"},
    {"name": "SHA256SUMS", "browser_download_url": "https://github.com/dl/sums"},
]


def test_pick_asset() -> None:
    assert pick_asset(ASSETS, "linux", "x86_64")["name"].endswith("x86_64.AppImage")
    assert pick_asset(ASSETS, "linux", "arm64")["name"].endswith("aarch64.AppImage")
    assert pick_asset(ASSETS, "android", "armeabi-v7a")["name"].endswith("v7a.apk")
    assert pick_asset(ASSETS, "android")["name"].endswith("arm64-v8a.apk")


def test_versions_and_sums() -> None:
    assert parse_version("0.10.0") > parse_version("0.9.9")
    sums = parse_sums("a" * 64 + "  file.apk\n" + "b" * 64 + " *other.AppImage\n")
    assert sums == {"file.apk": "a" * 64, "other.AppImage": "b" * 64}


@respx.mock
async def test_download_verifies_checksum(tmp_path: Path) -> None:
    payload = b"nouvelle version"
    good = hashlib.sha256(payload).hexdigest()
    release = {"tag_name": "v0.2.0", "assets": ASSETS}
    respx.get("https://api.github.com/repos/raantss18/tontolo/releases/latest").mock(
        return_value=httpx.Response(200, json=release))
    respx.get("https://github.com/dl/x86").mock(return_value=httpx.Response(200, content=payload))
    respx.get("https://github.com/dl/sums").mock(return_value=httpx.Response(
        200, text=f"{good}  Tontolo-0.2.0-x86_64.AppImage\n"))
    res = await download_update(tmp_path, "linux", "x86_64", current="0.1.0")
    assert res["ok"] and Path(res["path"]).read_bytes() == payload
    assert Path(res["path"]).stat().st_mode & 0o111

    respx.get("https://github.com/dl/sums").mock(return_value=httpx.Response(
        200, text=f"{'0' * 64}  tontolo-0.2.0-arm64-v8a.apk\n"))
    respx.get("https://github.com/dl/apk64").mock(return_value=httpx.Response(200, content=payload))
    bad = await download_update(tmp_path, "android", current="0.1.0")
    assert not bad["ok"] and "invalide" in bad["error"]
    assert not list(tmp_path.glob("*.apk*"))


@respx.mock
async def test_no_update_when_current(tmp_path: Path) -> None:
    respx.get("https://api.github.com/repos/raantss18/tontolo/releases/latest").mock(
        return_value=httpx.Response(200, json={"tag_name": "v0.1.0", "assets": ASSETS}))
    res = await download_update(tmp_path, "linux", current="0.1.0")
    assert not res["ok"] and res["error"] == "Déjà à jour"
