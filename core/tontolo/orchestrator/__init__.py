"""Orchestration multi-modèles optionnelle (`orchestrate=true` sur `/tontolo/chat`)."""

from tontolo.orchestrator.decomposer import Plan, Subtask, TaskDecomposer
from tontolo.orchestrator.pipeline import HierarchicalPipeline
from tontolo.orchestrator.synthesizer import PartResult, ResponseSynthesizer

__all__ = ["HierarchicalPipeline", "PartResult", "Plan", "ResponseSynthesizer", "Subtask",
           "TaskDecomposer"]
