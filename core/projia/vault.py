"""Chiffrement du fichier de secrets de repli (`secrets.json`), quand le trousseau du système
n'est pas disponible.

- Fernet (AES-128-CBC + HMAC) si le paquet `cryptography` est installé (bureau) ;
- sinon, chiffrement authentifié de la bibliothèque standard : flux HMAC-SHA256 en mode
  compteur, puis étiquette HMAC-SHA256 sur nonce + chiffré (chiffrer-puis-authentifier).

La clé (32 octets aléatoires) est dans `secrets.key`, en mode 0600, à côté du fichier.
# NOTE: Choix autonome - la clé reste sur le même disque : cela protège contre la fuite du
# seul fichier de secrets (sauvegarde, synchronisation, partage par erreur, journaux), pas
# contre quelqu'un qui lit tout le dossier de données. Le trousseau du système reste la voie
# préférée ; ceci durcit le repli sans dépendance obligatoire (Android).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets as _rand
from pathlib import Path
from typing import Any

FORMAT_STDLIB = "projia-v1"
FORMAT_FERNET = "fernet-v1"


def _key(path: Path) -> bytes:
    """Clé du dossier (créée au premier besoin, 0600)."""
    if path.exists():
        raw = path.read_bytes()
        if len(raw) == 32:
            return raw
    raw = _rand.token_bytes(32)
    tmp = path.with_name(path.name + ".tmp")  # propre à chaque fichier (clé et secrets)
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as fh:
        fh.write(raw)
    tmp.replace(path)
    return raw


def _stream(key: bytes, nonce: bytes, n: int) -> bytes:
    out = bytearray()
    counter = 0
    while len(out) < n:
        out += hmac.new(key, nonce + counter.to_bytes(8, "big"), hashlib.sha256).digest()
        counter += 1
    return bytes(out[:n])


def _subkeys(key: bytes) -> tuple[bytes, bytes]:
    enc = hmac.new(key, b"projia-enc", hashlib.sha256).digest()
    mac = hmac.new(key, b"projia-mac", hashlib.sha256).digest()
    return enc, mac


def _fernet(key: bytes) -> Any:
    try:
        from cryptography.fernet import Fernet
    except ImportError:
        return None
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt(data: dict[str, str], key_path: Path) -> dict[str, str]:
    key = _key(key_path)
    plain = json.dumps(data).encode()
    f = _fernet(key)
    if f is not None:
        return {"format": FORMAT_FERNET, "token": f.encrypt(plain).decode()}
    enc, mac = _subkeys(key)
    nonce = _rand.token_bytes(16)
    ct = bytes(a ^ b for a, b in zip(plain, _stream(enc, nonce, len(plain)), strict=True))
    tag = hmac.new(mac, nonce + ct, hashlib.sha256).digest()
    b64 = base64.b64encode
    return {"format": FORMAT_STDLIB, "nonce": b64(nonce).decode(), "ct": b64(ct).decode(),
            "tag": b64(tag).decode()}


def decrypt(blob: dict[str, Any], key_path: Path) -> dict[str, str]:
    """Contenu déchiffré ; ValueError si la clé ne correspond pas ou si le fichier est altéré."""
    key = key_path.read_bytes() if key_path.exists() else b""
    if len(key) != 32:  # jamais régénérée ici : ce serait perdre les secrets existants
        raise ValueError("clé absente ou invalide")
    fmt = blob.get("format")
    if fmt == FORMAT_FERNET:
        f = _fernet(key)
        if f is None:
            raise ValueError("cryptography indisponible pour ce fichier")
        try:
            plain = f.decrypt(str(blob["token"]).encode())
        except Exception as exc:
            raise ValueError("fichier de secrets altéré") from exc
    elif fmt == FORMAT_STDLIB:
        enc, mac = _subkeys(key)
        nonce, ct, tag = (base64.b64decode(str(blob[k])) for k in ("nonce", "ct", "tag"))
        if not hmac.compare_digest(tag, hmac.new(mac, nonce + ct, hashlib.sha256).digest()):
            raise ValueError("fichier de secrets altéré")
        plain = bytes(a ^ b for a, b in zip(ct, _stream(enc, nonce, len(ct)), strict=True))
    else:
        raise ValueError("format inconnu")
    data = json.loads(plain)
    return {str(k): str(v) for k, v in data.items()}


def is_encrypted(blob: Any) -> bool:
    return isinstance(blob, dict) and blob.get("format") in (FORMAT_FERNET, FORMAT_STDLIB)
