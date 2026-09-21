"""Canonical, immutable episode records for the R03 protocol.

This module intentionally contains no model, renderer, scorer, task generator,
or I/O. It establishes the boundary those later components must respect.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import math
from types import MappingProxyType
from typing import Mapping, TypeAlias

JSONScalar: TypeAlias = None | bool | int | float | str
FrozenJSON: TypeAlias = JSONScalar | tuple["FrozenJSON", ...] | Mapping[str, "FrozenJSON"]
JSONValue: TypeAlias = JSONScalar | list["JSONValue"] | dict[str, "JSONValue"]

FAMILIES = frozenset({"records", "finite-state", "rule-induction"})
SPLITS = frozenset({"train", "development", "final"})
# These names are scorer-side protocol fields, never candidate-visible JSON keys.
CANDIDATE_FORBIDDEN_KEYS = frozenset(
    {"answer", "latent_program", "seed", "input_state", "split", "provenance"}
)


def _freeze(value: object) -> FrozenJSON:
    """Validate a JSON value and recursively make its containers immutable."""
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("JSON floats must be finite")
        return value
    if isinstance(value, Mapping):
        frozen: dict[str, FrozenJSON] = {}
        for key, child in value.items():
            if not isinstance(key, str):
                raise TypeError("JSON object keys must be strings")
            frozen[key] = _freeze(child)
        return MappingProxyType(frozen)
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(child) for child in value)
    raise TypeError(f"not a JSON value: {type(value).__name__}")


def _thaw(value: FrozenJSON) -> JSONValue:
    """Return a fresh standard JSON container from an immutable representation."""
    if isinstance(value, Mapping):
        return {key: _thaw(child) for key, child in value.items()}
    if isinstance(value, tuple):
        return [_thaw(child) for child in value]
    return value


def canonical_json(value: object) -> str:
    """Serialize a JSON-compatible value in the protocol's canonical form."""
    frozen = _freeze(value)
    return json.dumps(
        _thaw(frozen),
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _validate_candidate_visible(value: FrozenJSON) -> None:
    """Reject scorer-side field names anywhere in candidate-visible JSON."""
    if isinstance(value, Mapping):
        for key, child in value.items():
            if key in CANDIDATE_FORBIDDEN_KEYS:
                raise ValueError(f"candidate-visible JSON may not contain {key!r}")
            _validate_candidate_visible(child)
    elif isinstance(value, tuple):
        for child in value:
            _validate_candidate_visible(child)


@dataclass(frozen=True, slots=True)
class Episode:
    """One scorer-side R03 episode before candidate rendering/execution.

    ``input_state`` remains scorer-side canonical state. ``rendered_input`` is
    the explicitly candidate-visible surface created by a later renderer. The
    distinction keeps a candidate export from accidentally becoming an implicit
    debugger for the generator or answer oracle.
    """

    protocol_version: str
    family: str
    split: str
    seed: int
    input_state: FrozenJSON
    rendered_input: FrozenJSON
    support: FrozenJSON
    query: FrozenJSON
    answer: FrozenJSON
    latent_program: FrozenJSON
    structure_signature: str
    presentation_variant: FrozenJSON
    difficulty: FrozenJSON
    provenance: FrozenJSON

    def __post_init__(self) -> None:
        if not self.protocol_version:
            raise ValueError("protocol_version must be non-empty")
        if self.family not in FAMILIES:
            raise ValueError(f"unknown episode family: {self.family!r}")
        if self.split not in SPLITS:
            raise ValueError(f"unknown split: {self.split!r}")
        if isinstance(self.seed, bool) or not isinstance(self.seed, int):
            raise TypeError("seed must be an integer")
        if not self.structure_signature:
            raise ValueError("structure_signature must be non-empty")
        for field_name in (
            "input_state",
            "rendered_input",
            "support",
            "query",
            "answer",
            "latent_program",
            "presentation_variant",
            "difficulty",
            "provenance",
        ):
            object.__setattr__(self, field_name, _freeze(getattr(self, field_name)))
        for field_name in ("rendered_input", "support", "query", "presentation_variant"):
            _validate_candidate_visible(getattr(self, field_name))

    def scorer_record(self) -> dict[str, JSONValue]:
        """Return a fresh, complete canonical record for scoring/provenance."""
        return {
            "protocol_version": self.protocol_version,
            "family": self.family,
            "split": self.split,
            "seed": self.seed,
            "input_state": _thaw(self.input_state),
            "rendered_input": _thaw(self.rendered_input),
            "support": _thaw(self.support),
            "query": _thaw(self.query),
            "answer": _thaw(self.answer),
            "latent_program": _thaw(self.latent_program),
            "structure_signature": self.structure_signature,
            "presentation_variant": _thaw(self.presentation_variant),
            "difficulty": _thaw(self.difficulty),
            "provenance": _thaw(self.provenance),
        }

    def record_hash(self) -> str:
        """Hash the complete scorer-side canonical record."""
        return sha256(canonical_json(self.scorer_record()).encode("utf-8")).hexdigest()

    def candidate_id(self) -> str:
        """Derive a stable ID from candidate-visible state only.

        This must not be the scorer-side record hash: changing a hidden answer,
        seed, split, provenance object, or latent program must not create a
        public side channel.
        """
        visible_identity = {
            "family": self.family,
            "input": _thaw(self.rendered_input),
            "support": _thaw(self.support),
            "query": _thaw(self.query),
            "presentation_variant": _thaw(self.presentation_variant),
        }
        return sha256(canonical_json(visible_identity).encode("utf-8")).hexdigest()

    def candidate_payload(self, declared_budget: object) -> dict[str, JSONValue]:
        """Export only information permitted to reach a candidate.

        The returned object is fresh mutable JSON data for transport. It omits
        the answer, latent program, generator seed, canonical input state, split,
        and provenance by construction. Candidate-visible values and the caller's
        budget are recursively checked for reserved scorer-side field names.
        """
        frozen_budget = _freeze(declared_budget)
        _validate_candidate_visible(frozen_budget)
        return {
            "task_id": self.candidate_id(),
            "family": self.family,
            "input": _thaw(self.rendered_input),
            "support": _thaw(self.support),
            "query": _thaw(self.query),
            "declared_budget": _thaw(frozen_budget),
            "presentation_variant": _thaw(self.presentation_variant),
        }
