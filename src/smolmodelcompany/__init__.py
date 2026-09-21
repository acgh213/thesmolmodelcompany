"""Deterministic, model-free evaluation apparatus for SMCo research."""

__version__ = "0.1.0"

from .episode import Episode, canonical_json
from .records import generate_episode, generate_task, small_case_audit

__all__ = ["Episode", "canonical_json", "generate_episode", "generate_task", "small_case_audit", "__version__"]
