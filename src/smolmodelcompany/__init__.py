"""Deterministic, model-free evaluation apparatus for SMCo research."""

__version__ = "0.1.0"

from .episode import Episode, canonical_json
from .finite_state import (
    generate_episode as generate_finite_state_episode,
    generate_planning_task,
    generate_tracking_task,
    planning_reference,
    small_planning_audit,
    small_state_audit,
    tracking_reference,
)
from .records import generate_episode, generate_task, small_case_audit

__all__ = [
    "Episode", "canonical_json", "generate_episode", "generate_task", "small_case_audit",
    "generate_finite_state_episode", "generate_planning_task", "generate_tracking_task",
    "planning_reference", "small_planning_audit", "small_state_audit", "tracking_reference",
    "__version__",
]
