"""Fichier de secrets de repli chiffré, migration de l'ancien format en clair."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tontolo import secrets, vault


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("TONTOLO_HOME", str(tmp_path))
    monkeypatch.setenv("TONTOLO_NO_KEYRING", "1")
    secrets._memory.clear()
    return tmp_path


def test_file_is_encrypted_and_readable(home: Path) -> None:
    secrets.set_key("groq", "gsk_secretvaleur1234567890")
    raw = (home / "secrets.json").read_text()
    assert "gsk_secret" not in raw and vault.is_encrypted(json.loads(raw))
    assert (home / "secrets.key").stat().st_mode & 0o777 == 0o600
    assert (home / "secrets.json").stat().st_mode & 0o777 == 0o600
    secrets._memory.clear()
    assert secrets.get_key("groq") == "gsk_secretvaleur1234567890"
    secrets.delete_key("groq")
    secrets._memory.clear()
    assert secrets.get_key("groq") is None


def test_old_plaintext_file_is_migrated(home: Path) -> None:
    (home / "secrets.json").write_text(json.dumps({"openrouter": "sk-or-ancienne"}))
    assert secrets.get_key("openrouter") == "sk-or-ancienne"
    assert "sk-or-ancienne" not in (home / "secrets.json").read_text()  # réécrit chiffré
    secrets._memory.clear()
    assert secrets.get_key("openrouter") == "sk-or-ancienne"


def test_tampering_or_missing_key_is_refused(home: Path, monkeypatch: pytest.MonkeyPatch
                                             ) -> None:
    for fernet in (True, False):
        if not fernet:
            monkeypatch.setattr(vault, "_fernet", lambda key: None)  # comme sous Android
        blob = vault.encrypt({"a": "b"}, home / "k")
        assert vault.decrypt(blob, home / "k") == {"a": "b"}
        bad = dict(blob)
        field = "token" if blob["format"] == vault.FORMAT_FERNET else "ct"
        bad[field] = bad[field][:-4] + ("AAAA" if not bad[field].endswith("AAAA") else "BBBB")
        with pytest.raises(ValueError):
            vault.decrypt(bad, home / "k")
        with pytest.raises(ValueError):
            vault.decrypt(blob, home / "absente")
