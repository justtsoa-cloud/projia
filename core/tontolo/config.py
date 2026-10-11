"""Configuration de Tontolo.

Ordre de priorité : valeurs par défaut < fichier `config.yaml` < variables
d'environnement `TONTOLO_*`. Aucune liste de modèles, aucun classement ni
quota n'est défini ici : tout vient des catalogues en ligne.
"""

from __future__ import annotations

import os
from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


def data_dir() -> Path:
    """Dossier de données inscriptible (XDG sous Linux, fourni par l'app sous Android)."""
    env = os.environ.get("TONTOLO_HOME")
    if env:
        path = Path(env)
    else:
        base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
        path = Path(base) / "tontolo"
    path.mkdir(parents=True, exist_ok=True)
    return path


class PaidFallback(StrEnum):
    OFF = "off"
    ASK = "ask"
    AUTO = "auto"


class Weights(BaseModel):
    """Poids du score : `w_q·Qualité + w_s·Vitesse + w_r·Fiabilité`."""

    quality: float = 0.6
    speed: float = 0.15
    reliability: float = 0.25


class PaidSettings(BaseModel):
    fallback: PaidFallback = PaidFallback.OFF
    daily_cap_usd: float = 0.0
    monthly_cap_usd: float = 0.0
    allowed_models: list[str] = Field(default_factory=list)


class AgentSettings(BaseModel):
    max_iterations: int = 8
    max_seconds: float = 120.0
    workdir: str | None = None


class ServerSettings(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8765
    # Jeton exigé dès que le serveur écoute ailleurs que sur la boucle locale.
    token: str | None = None


class Settings(BaseModel):
    catalog_ttl_hours: float = 6.0
    weights: Weights = Field(default_factory=Weights)
    paid: PaidSettings = Field(default_factory=PaidSettings)
    agent: AgentSettings = Field(default_factory=AgentSettings)
    server: ServerSettings = Field(default_factory=ServerSettings)
    # Classifieur LLM pour les prompts ambigus (consomme un peu de quota gratuit).
    llm_classifier: bool = False
    media_quota_mb: int = 1024
    language: str = "fr"
    check_updates: bool = True
    # Mémoire à long terme (locale) et instructions personnalisées.
    memory_enabled: bool = True
    memory_max_items: int = 60
    memory_budget_chars: int = 1500
    custom_instructions: str = ""
    # Téléchargement et installation automatiques des nouvelles versions.
    auto_update: bool = True
    # « Réponse rapide d'abord » : pour les demandes simples, le modèle le plus rapide passe
    # devant ; les demandes complexes (raisonnement, code, maths…) gardent le meilleur.
    speed_first: bool = False
    # Équipe de modèles : un second modèle (autre famille) vérifie les réponses de maths,
    # code et raisonnement, et signale une erreur éventuelle.
    team_review: bool = True
    # Dossiers dont les discussions partagent leur contexte (titres et résumés), en priorité
    # secondaire après le fil. Par défaut un dossier ne sert qu'au rangement.
    shared_folders: list[str] = Field(default_factory=list)

    @property
    def data_dir(self) -> Path:
        return data_dir()


def config_path() -> Path:
    return Path(os.environ.get("TONTOLO_CONFIG") or data_dir() / "config.yaml")


def _deep_update(base: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_update(base[key], value)
        else:
            base[key] = value
    return base


def _env_overrides() -> dict[str, Any]:
    out: dict[str, Any] = {}
    if v := os.environ.get("TONTOLO_PORT"):
        out.setdefault("server", {})["port"] = int(v)
    if v := os.environ.get("TONTOLO_HOST"):
        out.setdefault("server", {})["host"] = v
    if v := os.environ.get("TONTOLO_TOKEN"):
        out.setdefault("server", {})["token"] = v
    if v := os.environ.get("TONTOLO_CATALOG_TTL_HOURS"):
        out["catalog_ttl_hours"] = float(v)
    return out


def load_settings(path: Path | None = None) -> Settings:
    raw: dict[str, Any] = {}
    p = path or config_path()
    if p.exists():
        loaded = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        if isinstance(loaded, dict):
            raw = loaded
    _deep_update(raw, _env_overrides())
    return Settings.model_validate(raw)


def save_settings(settings: Settings, path: Path | None = None) -> None:
    p = path or config_path()
    p.write_text(
        yaml.safe_dump(settings.model_dump(mode="json"), allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
