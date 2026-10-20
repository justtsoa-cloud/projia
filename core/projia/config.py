"""Configuration de Projia.

Ordre de priorité : valeurs par défaut < fichier `config.yaml` < variables
d'environnement `PROJIA_*`. Aucune liste de modèles, aucun classement ni
quota n'est défini ici : tout vient des catalogues en ligne.
"""

from __future__ import annotations

import os
from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator


def data_dir() -> Path:
    """Dossier de données inscriptible (XDG sous Linux, fourni par l'app sous Android)."""
    env = os.environ.get("PROJIA_HOME")
    if env:
        path = Path(env)
    else:
        base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
        path = Path(base) / "projia"
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


class CustomProvider(BaseModel):
    """Fournisseur compatible OpenAI ajouté par l'utilisateur (mode avancé, réglable sur
    l'appareil seulement). Clé dans le stockage sécurisé, jamais ici ; envoyée uniquement en
    HTTPS à l'hôte épinglé. Un serveur local en HTTP (réseau privé) fonctionne sans clé."""

    id: str = Field(pattern=r"^custom-[a-z0-9-]{1,40}$")
    name: str = Field(min_length=1, max_length=60)
    base_url: str = Field(max_length=300, pattern=r"^https?://[^\s]+$")
    free: bool = True
    needs_key: bool = True
    # Prix en USD par million de jetons : obligatoires pour un fournisseur payant (sans prix,
    # le plafond de dépense ne pourrait pas être garanti).
    price_in_per_m: float = Field(default=0.0, ge=0, le=1000)
    price_out_per_m: float = Field(default=0.0, ge=0, le=1000)


class RoutingRules(BaseModel):
    """Souplesse du mode avancé, toujours dans des bornes sûres."""

    # Fournisseurs jamais utilisés (même s'ils ont une clé).
    excluded_providers: list[str] = Field(default_factory=list, max_length=200)
    # Enchaînements choisis par catégorie (« code » → [modèle1, modèle2…]) : essayés d'abord,
    # dans cet ordre, puis le choix automatique habituel prend le relais.
    chains: dict[str, list[str]] = Field(default_factory=dict, max_length=30)
    # Délais du routeur (secondes) ; None = valeurs par défaut.
    first_token_s: float | None = Field(default=None, ge=20, le=300)
    stall_s: float | None = Field(default=None, ge=15, le=180)
    think_s: float | None = Field(default=None, ge=60, le=600)

    @field_validator("chains")
    @classmethod
    def _short_chains(cls, v: dict[str, list[str]]) -> dict[str, list[str]]:
        return {str(k)[:40]: [str(x)[:200] for x in items][:10] for k, items in v.items()}


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
    # Réponses déjà données réutilisées (question quasi identique) ou fournies en contexte
    # (question voisine) : index local, jamais synchronisé (voir projia/semantic.py).
    answer_cache: bool = True
    memory_budget_chars: int = 1500
    custom_instructions: str = ""
    # Téléchargement et installation automatiques des nouvelles versions.
    auto_update: bool = True
    # « Réponse rapide d'abord » : pour les demandes simples, le modèle le plus rapide passe
    # devant ; les demandes complexes (raisonnement, code, maths…) gardent le meilleur.
    speed_first: bool = False
    # Mode économie : un seul modèle à la fois pour les appels courts (moins de réseau, de batterie
    # et de quota) ; un peu plus lent quand un modèle gratuit est saturé.
    economy: bool = False
    # Accueil : « piste du jour » tirée des discussions récentes (calculée sur l'appareil).
    home_tracks: bool = True
    # Équipe de modèles : un second modèle (autre famille) vérifie les réponses de maths,
    # code et raisonnement, et signale une erreur éventuelle.
    team_review: bool = True
    # Dossiers dont les discussions partagent leur contexte (titres et résumés), en priorité
    # secondaire après le fil. Par défaut un dossier ne sert qu'au rangement.
    shared_folders: list[str] = Field(default_factory=list)
    # Compactage automatique des longues discussions (fiche structurée du début du fil).
    auto_compact: bool = True
    # Tâches complexes : plan en étapes (en parallèle sur plusieurs modèles ou pas à pas).
    task_planning: bool = True
    # Orchestration multi-modèles pour les demandes en plusieurs parties (sous-tâches en
    # parallèle sur des modèles gratuits, puis fusion). Désactivée par défaut.
    orchestrate: bool = False
    # Prénom pour l'accueil (« Bonsoir » + prénom) ; vide : compte ou mémoire, sinon aucun.
    user_name: str = Field(default="", max_length=40)
    # Mode avancé : fournisseurs personnalisés et règles de routage.
    custom_providers: list[CustomProvider] = Field(default_factory=list, max_length=20)
    routing: RoutingRules = Field(default_factory=RoutingRules)

    @property
    def data_dir(self) -> Path:
        return data_dir()


def config_path() -> Path:
    return Path(os.environ.get("PROJIA_CONFIG") or data_dir() / "config.yaml")


def _deep_update(base: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_update(base[key], value)
        else:
            base[key] = value
    return base


def _env_overrides() -> dict[str, Any]:
    out: dict[str, Any] = {}
    if v := os.environ.get("PROJIA_PORT"):
        out.setdefault("server", {})["port"] = int(v)
    if v := os.environ.get("PROJIA_HOST"):
        out.setdefault("server", {})["host"] = v
    if v := os.environ.get("PROJIA_TOKEN"):
        out.setdefault("server", {})["token"] = v
    if v := os.environ.get("PROJIA_CATALOG_TTL_HOURS"):
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
