"""Mises à jour automatiques : choix du fichier et vérification SHA-256."""

from __future__ import annotations

import hashlib
from pathlib import Path

import httpx
import pytest
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
async def test_download_verifies_checksum(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Ce test isole le contrôle du fichier ; les signatures réelles sont testées séparément.
    monkeypatch.setattr("tontolo.update.verify_sums", lambda data, sig: True)
    respx.get("https://github.com/dl/sig").mock(return_value=httpx.Response(200, content=b"sig"))
    payload = b"nouvelle version"
    good = hashlib.sha256(payload).hexdigest()
    release = {"tag_name": "v0.2.0", "assets": [*ASSETS,
        {"name": "SHA256SUMS.sig", "browser_download_url": "https://github.com/dl/sig"}]}
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


@respx.mock
async def test_unsigned_release_is_rejected_before_download(tmp_path: Path) -> None:
    payload = b'unsigned'
    respx.get('https://api.github.com/repos/raantss18/tontolo/releases/latest').mock(
        return_value=httpx.Response(200, json={'tag_name': 'v0.2.0', 'assets': ASSETS}))
    respx.get('https://github.com/dl/sums').mock(return_value=httpx.Response(
        200, text=f'{hashlib.sha256(payload).hexdigest()}  Tontolo-0.2.0-x86_64.AppImage\n'))
    download = respx.get('https://github.com/dl/x86').mock(
        return_value=httpx.Response(200, content=payload))
    result = await download_update(tmp_path, 'linux', current='0.1.0')
    assert not result['ok']
    assert not download.called
    assert not list(tmp_path.iterdir())


def test_real_signature_vector_and_tampering() -> None:
    import base64

    from tontolo.update import verify_sums

    pytest.importorskip('cryptography')
    pub = 'O6l5dFQk2gG7WSLOhlZaXWiLlsnwYcR0qqGZjvoJUkU='
    sig = base64.b64decode(
        'APW7Dt353xmHGJxKAhL9XiGau+oAkay56kjNNiMW04jbRr+R2HMBw7rKAteASlgh+'
        'b6azvoGbPQcW8hyAHXvCA==')
    data = b'abc123  Tontolo-9.9.9-x86_64.AppImage\n'
    assert verify_sums(data, sig, pub)
    assert not verify_sums(data + b'x', sig, pub)
    assert not verify_sums(data, sig[:-1], pub)
    assert not verify_sums(data, sig)  # clé de production différente


@respx.mock
@pytest.mark.parametrize('version,assets', [('0.0.1', ASSETS), ('0.2.0', [])])
async def test_downgrade_and_missing_asset_refused(tmp_path, version, assets):
    respx.get('https://api.github.com/repos/raantss18/tontolo/releases/latest').mock(
        return_value=httpx.Response(200, json={'tag_name': f'v{version}', 'assets': assets}))
    assert not (await download_update(tmp_path, 'linux', current='0.1.0'))['ok']
    assert not list(tmp_path.iterdir())


@respx.mock
async def test_invalid_signature_prevents_payload_download(tmp_path):
    assets = [*ASSETS, {'name': 'SHA256SUMS.sig',
                       'browser_download_url': 'https://github.com/dl/sig'}]
    respx.get('https://api.github.com/repos/raantss18/tontolo/releases/latest').mock(
        return_value=httpx.Response(200, json={'tag_name': 'v0.2.0', 'assets': assets}))
    respx.get('https://github.com/dl/sums').mock(return_value=httpx.Response(200, text='forged'))
    respx.get('https://github.com/dl/sig').mock(return_value=httpx.Response(200, content=b'x' * 64))
    result = await download_update(tmp_path, 'linux', current='0.1.0')
    assert not result['ok'] and 'Signature invalide' in result['error']
    assert not list(tmp_path.iterdir())
