"""Erreur commune des créations de fichiers (module séparé : évite les imports circulaires)."""

from __future__ import annotations


class CreationError(Exception):
    pass
