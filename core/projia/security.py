"""Protections transverses : CSRF / DNS rebinding, SSRF, épinglage des fournisseurs, liens.

- Le serveur local refuse les requêtes dont l'en-tête `Host` n'est pas la boucle
  locale (attaque par DNS rebinding) et celles portant un `Origin` de navigateur
  étranger (CSRF depuis une page web).
- `fetch_url` et les autres téléchargements pilotés par un modèle refusent les
  adresses privées, de boucle locale ou de métadonnées cloud (SSRF).
- Les URL des fournisseurs proviennent d'une source en ligne : elles doivent être
  en HTTPS et leur hôte est épinglé à la première utilisation (TOFU). Si une source
  compromise changeait l'hôte, les clés ne lui seraient jamais envoyées.
"""

from __future__ import annotations

import asyncio
import contextlib
import ipaddress
import json
import logging
import socket
from pathlib import Path
from urllib.parse import urlsplit

log = logging.getLogger(__name__)

LOOPBACK_NAMES = {"127.0.0.1", "localhost", "::1"}


def host_of(host_header: str) -> str:
    """« 127.0.0.1:8765 » → « 127.0.0.1 », « [::1]:8765 » → « ::1 »."""
    h = host_header.strip().lower()
    if h.startswith("["):
        return h[1:h.find("]")] if "]" in h else h
    return h.rsplit(":", 1)[0] if h.count(":") == 1 else h


def origin_allowed(origin: str | None) -> bool:
    """Sans Origin (clients natifs, curl) : accepté ; navigateur : boucle locale seulement."""
    if origin is None:
        return True
    try:
        host = urlsplit(origin).hostname
    except ValueError:
        return False
    return host in LOOPBACK_NAMES


def _ip_is_public(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped:
        addr = addr.ipv4_mapped
    return not (addr.is_private or addr.is_loopback or addr.is_link_local
                or addr.is_multicast or addr.is_reserved or addr.is_unspecified)


async def assert_public_url(url: str) -> None:
    """Lève `PermissionError` si l'URL vise le réseau local, la machine ou un service interne."""
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise PermissionError("URL http(s) attendue")
    host = parts.hostname
    try:
        infos = await asyncio.to_thread(socket.getaddrinfo, host, parts.port or 443,
                                        proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise PermissionError(f"hôte introuvable : {host}") from exc
    for info in infos:
        if not _ip_is_public(str(info[4][0])):
            raise PermissionError("adresse privée ou locale refusée")


def connected_ip(resp: object) -> str | None:
    """Adresse IP à laquelle la réponse a VRAIMENT été servie (httpcore), ou None."""
    try:
        stream = resp.extensions.get("network_stream")  # type: ignore[attr-defined]
        addr = stream.get_extra_info("server_addr") if stream is not None else None
    except Exception:
        return None
    return str(addr[0]) if addr else None


def assert_public_peer(resp: object) -> None:
    """Contre le « DNS rebinding » : un nom peut résoudre vers une adresse publique lors de la
    vérification, puis vers 127.0.0.1 au moment de la connexion. On contrôle donc aussi
    l'adresse effectivement connectée, avant de lire le moindre octet."""
    ip = connected_ip(resp)
    if ip is not None and not _ip_is_public(ip):
        raise PermissionError("adresse privée ou locale refusée (après connexion)")


class ProviderPins:
    """Épinglage TOFU des hôtes des fournisseurs (fichier JSON dans le dossier de données)."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._pins: dict[str, str] | None = None

    def _load(self) -> dict[str, str]:
        if self._pins is None:
            try:
                self._pins = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                self._pins = {}
        return self._pins

    def check(self, provider: str, base_url: str, *, builtin: bool = False) -> bool:
        """Vrai si l'URL est sûre pour recevoir la clé de ce fournisseur."""
        parts = urlsplit(base_url)
        if parts.scheme != "https" or not parts.hostname:
            return False
        if builtin:
            return True
        pins = self._load()
        host = parts.hostname.lower()
        pinned = pins.get(provider)
        if pinned is None:
            pins[provider] = host
            with contextlib.suppress(OSError):
                self.path.write_text(json.dumps(pins, indent=1), encoding="utf-8")
            return True
        if pinned != host:
            log.warning("Hôte du fournisseur %s modifié (%s → %s) : refusé", provider, pinned,
                        host)
            return False
        return True

    def reset(self, provider: str) -> None:
        pins = self._load()
        if pins.pop(provider, None) is not None:
            self.path.write_text(json.dumps(pins, indent=1), encoding="utf-8")


SAFE_LINK_SCHEMES = ("http", "https", "mailto")


_pins: ProviderPins | None = None


def pins() -> ProviderPins:
    global _pins
    if _pins is None:
        from projia.config import data_dir

        _pins = ProviderPins(data_dir() / "provider_pins.json")
    return _pins


BUILTIN_PROVIDERS = {"openrouter", "pollinations", "local", "openai", "anthropic", "deepseek",
                     "xai", "moonshot", "qwen", "perplexity",
                     # gratuits avec clé, adresses codées en dur (catalog/sources/keyed.py)
                     "groq", "cerebras", "sambanova", "github", "together", "mistral", "gemini",
                     "nvidia", "huggingface"}


def key_allowed(provider: str, base_url: str) -> bool:
    """La clé de `provider` peut-elle être envoyée à `base_url` ?"""
    return pins().check(provider, base_url, builtin=provider in BUILTIN_PROVIDERS)
