"""Deterministic, model-free evaluation apparatus for SMCo research."""

__version__ = "0.1.0"

from .episode import Episode, canonical_json

__all__ = ["Episode", "canonical_json", "__version__"]
