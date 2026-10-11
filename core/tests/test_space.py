"""Espace disque : un seul dossier de cache, sans doublons, nettoyé."""

from __future__ import annotations

import os
import time
from pathlib import Path

from tontolo.storage import space


def test_tidy_and_clear(tmp_path: Path) -> None:
    (tmp_path / "updates").mkdir()
    (tmp_path / "updates" / "tontolo-0.4.0-arm64-v8a.apk").write_bytes(b"x" * 100)
    upd = space.cache_dir(tmp_path, "updates")
    for v in ("0.5.0", "0.5.1", "0.5.2", "0.5.3"):
        (upd / f"Tontolo-{v}-x86_64.AppImage").write_bytes(b"y" * 10)
    tmp = space.cache_dir(tmp_path, "tmp")
    old, fresh = tmp / "dictee.wav", tmp / "video.mp4"
    old.write_bytes(b"z" * 7)
    fresh.write_bytes(b"z")
    past = time.time() - 2 * 86400
    os.utime(old, (past, past))
    (tmp_path / "media").mkdir()
    (tmp_path / "media" / "image.png").write_bytes(b"i" * 50)

    freed = space.tidy(tmp_path, "0.5.1")
    assert not (tmp_path / "updates").exists()  # ancien emplacement regroupé
    assert [p.name for p in upd.iterdir()] == ["Tontolo-0.5.3-x86_64.AppImage"]
    assert not old.exists() and fresh.exists()
    assert freed == 100 + 3 * 10 + 7

    report = space.report(tmp_path)
    assert report["creations"] == 50 and report["cache_updates"] == 10
    assert space.clear_cache(tmp_path) == 11
    assert (tmp_path / "media" / "image.png").exists()  # les données ne sont jamais touchées
    assert space.report(tmp_path)["cache_total"] == 0


def test_keep_only_latest_download(tmp_path: Path) -> None:
    upd = space.cache_dir(tmp_path, "updates")
    a, b = upd / "a.apk", upd / "b.apk"
    a.write_bytes(b"1")
    b.write_bytes(b"2")
    space.keep_only(upd, b)
    assert not a.exists() and b.exists()
