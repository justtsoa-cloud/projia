"""Stockage des clés API personnelles (BYOK).

Ordre de lecture : variable d'environnement `<FOURNISSEUR>_API_KEY` (ou fichier
`.env` du dossier courant), trousseau du système (`keyring`, KWallet/Secret
Service), puis fichier `secrets.json` CHIFFRÉ, en mode 0600, dans le dossier de données.
Sous Android, l'application Flutter garde les clés dans le Keystore
(`flutter_secure_storage`) et les transmet au cœur au démarrage, en mémoire.

Les clés ne sont jamais écrites dans SQLite ni dans les journaux.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import re
from pathlib import Path
from typing import Any

from tontolo import vault
from tontolo.config import data_dir

log = logging.getLogger(__name__)

_SERVICE = "tontolo"
_memory: dict[str, str] = {}


def env_name(provider: str) -> str:
    """`openrouter` → `OPENROUTER_API_KEY`, `google-gemini` → `GOOGLE_GEMINI_API_KEY`."""
    return re.sub(r"[^A-Z0-9]+", "_", provider.upper()).strip("_") + "_API_KEY"


def _secrets_file() -> Path:
    return data_dir() / "secrets.json"


def _key_file() -> Path:
    return data_dir() / "secrets.key"


def _read_file() -> dict[str, str]:
    """Fichier de repli, chiffré (voir `tontolo.vault`). Un ancien fichier en clair est lu
    puis réécrit chiffré (migration transparente)."""
    path = _secrets_file()
    if not path.exists():
        return {}
    try:
        blob = json.loads(path.read_text(encoding="utf-8"))
        if vault.is_encrypted(blob):
            return vault.decrypt(blob, _key_file())
        data = {str(k): str(v) for k, v in blob.items()}
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        log.warning("Fichier de secrets illisible ou altéré : ignoré")
        return {}
    if data:
        with contextlib.suppress(OSError):
            _write_file(data)  # ancien format en clair : chiffré dès la première lecture
    return data


def _write_file(data: dict[str, str]) -> None:
    path = _secrets_file()
    tmp = path.with_name(path.name + ".tmp")  # propre à chaque fichier (clé et secrets)
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(vault.encrypt(data, _key_file()), fh)
    tmp.replace(path)


def _keyring() -> Any:
    if os.environ.get("TONTOLO_NO_KEYRING"):
        return None
    try:
        import keyring  # import paresseux : absent sous Android
        from keyring.backends import fail

        if isinstance(keyring.get_keyring(), fail.Keyring):
            return None
        return keyring
    except Exception:
        return None


def load_dotenv(path: Path | None = None) -> None:
    """Charge un `.env` minimal (CLE=valeur) sans écraser l'environnement."""
    p = path or Path.cwd() / ".env"
    if not p.is_file():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def get_key(provider: str) -> str | None:
    if provider in _memory:
        return _memory[provider]
    if value := os.environ.get(env_name(provider)):
        return value
    kr = _keyring()
    if kr is not None:
        try:
            if value := kr.get_password(_SERVICE, provider):
                return str(value)
        except Exception:
            pass
    return _read_file().get(provider)


def set_key(provider: str, value: str, *, persist: bool = True) -> None:
    _memory[provider] = value
    if not persist:
        return
    kr = _keyring()
    if kr is not None:
        try:
            kr.set_password(_SERVICE, provider, value)
            return
        except Exception:
            log.info("Trousseau indisponible, repli sur le fichier 0600")
    data = _read_file()
    data[provider] = value
    _write_file(data)


def delete_key(provider: str) -> None:
    _memory.pop(provider, None)
    kr = _keyring()
    if kr is not None:
        with contextlib.suppress(Exception):
            kr.delete_password(_SERVICE, provider)
    data = _read_file()
    if data.pop(provider, None) is not None:
        _write_file(data)


def has_key(provider: str) -> bool:
    return bool(get_key(provider))


def redact(text: str) -> str:
    """Masque tout ce qui ressemble à une clé dans un message de journal."""
    text = re.sub(r"((?:sk|gsk|nvapi|hf|pk)[-_][A-Za-z0-9_\-]{4})[A-Za-z0-9_\-]{8,}", r"\1…", text)
    text = re.sub(r"(AIza[A-Za-z0-9_\-]{4})[A-Za-z0-9_\-]{20,}", r"\1…", text)
    return re.sub(r"(Bearer\s+\S{4})\S+", r"\1…", text)
