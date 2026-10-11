"""Option « réponse rapide d'abord » : la vitesse prime pour les demandes simples seulement."""

from __future__ import annotations

from tontolo.catalog.models import Category
from tontolo.config import Settings
from tontolo.router.classifier import TaskProfile
from tontolo.router.engine import Router
from tontolo.router.scoring import rank


def _first(router: Router, cat: Category) -> str:
    for m in router.catalog.catalog.models.values():
        m.speed = 0.95 if m.model_id == "small" else 0.2
    dec = rank(router.catalog.catalog, TaskProfile(category=cat),
               usable=router.catalog.usable_providers(), quota=router.quota,
               reliability=router.reliability, settings=router.settings)
    return dec.chain[0].model.model_id


def test_speed_first_only_for_simple_requests(router: Router, settings: Settings) -> None:
    assert _first(router, Category.CHAT) == "chatty"          # par défaut : la qualité
    settings.speed_first = True
    assert _first(router, Category.CHAT) == "small"           # simple : le plus rapide
    assert _first(router, Category.CODE) == "coder-pro"       # complexe : toujours le meilleur
