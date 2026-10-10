"""Stockage des clés API personnelles (BYOK).

Ordre de lecture : variable d'environnement `<FOURNISSEUR>_API_KEY` (ou fichier
`.env` du dossier courant), trousseau du système (`keyring`, KWallet/Secret
Service), puis fichier `secrets.json` en mode 0600 dans le dossier de données.
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

from tontolo.config import data_dir

log = logging.getLogger(__name__)

_SERVICE = "tontolo"
_memory: dict[str, str] = {}


def env_name(provider: str) -> str:
    """`openrouter` → `OPENROUTER_API_KEY`, `google-gemini` → `GOOGLE_GEMINI_API_KEY`."""
    return re.sub(r"[^A-Z0-9]+", "_", provider.upper()).strip("_") + "_API_KEY"


def _secrets_file() -> Path:
    return data_dir() / "secrets.json"


def _read_file() -> dict[str, str]:
    path = _secrets_file()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {str(k): str(v) for k, v in data.items()}
    except (OSError, ValueError):
        log.warning("Fichier de secrets illisible : ignoré")
        return {}


def _write_file(data: dict[str, str]) -> None:
    path = _secrets_file()
    tmp = path.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(data, fh)
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
    return re.sub(r"(sk-[A-Za-z0-9_\-]{6})[A-Za-z0-9_\-]+", r"\1…", text)
