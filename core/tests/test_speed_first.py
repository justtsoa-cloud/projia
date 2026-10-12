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


def test_observed_speed_beats_catalog_guess(router: Router, settings: Settings) -> None:
    """Modèles gratuits sans mesure de vitesse au catalogue : la vitesse réellement observée
    (attente comprise) départage, en mode « réponse rapide d'abord »."""
    settings.speed_first = True
    models = router.catalog.catalog.models.values()
    for m in models:
        m.speed = None
    chatty = next(m.key for m in models if m.model_id == "chatty")
    small = next(m.key for m in models if m.model_id == "small")
    router.reliability.record_speed(chatty, 400, 60.0)   # 7 car./s : très lent
    router.reliability.record_speed(small, 3000, 10.0)   # 300 car./s
    dec = rank(router.catalog.catalog, TaskProfile(category=Category.CHAT),
               usable=router.catalog.usable_providers(), quota=router.quota,
               reliability=router.reliability, settings=router.settings)
    assert dec.chain[0].model.model_id == "small"
    assert router.reliability.speed("inconnu") is None
    router.reliability.record_speed(small, 10, 0.01)  # trop court : ignoré
    assert router.reliability.speeds[small] == 300.0
