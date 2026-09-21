#!/usr/bin/env python3
"""E01 prompt rendering: the frozen instruction and the candidate serialisation.

Issue https://durandal.exe.xyz/smolmodelco/thesmolmodelcompany/issues/24.

Protocol ``e01-records-v1`` says "the model receives one deterministic prompt per
episode" but froze no prompt. This module is that prompt, frozen as
``e01-prompt-v1``, and it is the *mechanical* half only: the task family, the
scorer and the condition belong to Research B.

The rendered prompt is exactly three parts, concatenated with no other
characters:

1. ``INSTRUCTION`` -- one literal string, so no concatenation can drift from the
   reviewed text;
2. ``"\\n\\nTASK JSON:\\n"`` followed by the canonical compact JSON of exactly
   ``family``, ``input`` and ``query`` from the candidate payload;
3. ``"\\n\\nOUTPUT JSON:\\n"``.

``declared_budget`` is deliberately not rendered. It is a control record for the
run manifest, not task content, and putting it in the prompt would hand the model
a number that no condition in the E01 matrix varies.

``support`` and ``presentation_variant`` are also absent: the frozen protocol
declares the symbolic surface with no support examples for the records family, so
rendering them would be a condition change, not a rendering detail.

Scorer-side field names are rejected recursively *before* a byte is rendered, so
a payload carrying ``answer``, ``latent_program``, ``seed``, ``input_state``,
``split`` or ``provenance`` raises rather than silently leaking through a
projection. The key set is imported from ``smolmodelcompany.episode`` rather than
restated, so this renderer cannot drift from the boundary the generator enforces.

Nothing here imports a model library, opens a socket, or reads a file.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

try:  # bare script (sys.path[0] is scripts/) or scripts/ already on sys.path
    from r02_gate import is_unset
except ModuleNotFoundError:  # imported as scripts.<module> from the repository root
    from scripts.r02_gate import is_unset

from smolmodelcompany.episode import CANDIDATE_FORBIDDEN_KEYS, canonical_json

PROMPT_RENDERER_REVISION = "e01-prompt-v1"

INSTRUCTION = "You are a deterministic JSON transformation executor. Apply the primitive operations to the supplied records. Return only one JSON array of result records, with no explanation or markdown."

TASK_HEADER = "\n\nTASK JSON:\n"
OUTPUT_HEADER = "\n\nOUTPUT JSON:\n"

# The candidate fields that reach the prompt, in the order the protocol names
# them. ``canonical_json`` sorts object keys, so this order does not affect bytes.
PROMPT_FIELDS = ("family", "input", "query")

# One byte of framing between prompts in the set digest, so two different prompt
# sets cannot hash alike through concatenation ambiguity.
PROMPT_SET_SEPARATOR = b"\n"


class PromptError(RuntimeError):
    """A candidate payload could not be rendered under the frozen prompt."""


def find_forbidden_keys(value: Any, *, path: str = "") -> list[str]:
    """Every scorer-side key found anywhere in ``value``, with its path."""
    found: list[str] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else str(key)
            if key in CANDIDATE_FORBIDDEN_KEYS:
                found.append(child_path)
            found.extend(find_forbidden_keys(child, path=child_path))
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            found.extend(find_forbidden_keys(child, path=f"{path}[{index}]"))
    return found


def task_subset(payload: Mapping[str, Any]) -> dict[str, Any]:
    """The three candidate fields the prompt is allowed to show."""
    if not isinstance(payload, Mapping):
        raise PromptError("candidate payload must be an object")
    forbidden = find_forbidden_keys(payload)
    if forbidden:
        raise PromptError(
            "candidate payload carries scorer-side field(s): " + ", ".join(sorted(set(forbidden)))
        )
    missing = [name for name in PROMPT_FIELDS if name not in payload]
    if missing:
        raise PromptError("candidate payload is missing " + ", ".join(missing))
    subset = {name: payload[name] for name in PROMPT_FIELDS}
    for name in PROMPT_FIELDS:
        if is_unset(subset[name]):
            raise PromptError(f"candidate payload field {name!r} is UNSET")
        if subset[name] is None:
            raise PromptError(f"candidate payload field {name!r} is null")
    # The projection is re-checked: a future change to PROMPT_FIELDS must not be
    # able to widen the rendered surface without failing here.
    projected_forbidden = find_forbidden_keys(subset)
    if projected_forbidden:
        raise PromptError(
            "rendered subset carries scorer-side field(s): "
            + ", ".join(sorted(set(projected_forbidden)))
        )
    return subset


def render_prompt(payload: Mapping[str, Any]) -> str:
    """Render exactly one deterministic prompt for one candidate payload."""
    task = canonical_json(task_subset(payload))
    return INSTRUCTION + TASK_HEADER + task + OUTPUT_HEADER


def prompt_sha256(payload: Mapping[str, Any]) -> str:
    """SHA-256 of one rendered prompt, as recorded per episode in the run manifest."""
    return hashlib.sha256(render_prompt(payload).encode("utf-8")).hexdigest()


def instruction_sha256() -> str:
    """SHA-256 of the instruction text alone."""
    return hashlib.sha256(INSTRUCTION.encode("utf-8")).hexdigest()


def prompt_set_sha256(payloads: Iterable[Mapping[str, Any]]) -> str:
    """SHA-256 over a whole rendered prompt set, in the order given.

    Each rendered prompt is hashed with its UTF-8 bytes followed by one newline,
    so the digest covers the instruction, the headers and the serialisation for
    every episode rather than the instruction text alone. This is the value the
    execution plan freezes as ``prompt_sha256``.
    """
    digest = hashlib.sha256()
    for payload in payloads:
        digest.update(render_prompt(payload).encode("utf-8"))
        digest.update(PROMPT_SET_SEPARATOR)
    return digest.hexdigest()


def payloads_from_manifest(rows: Iterable[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    """The candidate payloads of an episode manifest, in file order."""
    payloads: list[Mapping[str, Any]] = []
    for row in rows:
        payload = row.get("payload") if isinstance(row, Mapping) else None
        if not isinstance(payload, Mapping):
            raise PromptError("episode manifest row has no 'payload' object")
        payloads.append(payload)
    return payloads


def main(argv: list[str] | None = None) -> int:
    """Print the renderer identity, the instruction digest and a set digest.

    ``--episode-manifest`` is optional; with it the set digest for those exact
    episodes is printed, which is what the execution plan freezes.
    """
    import argparse
    import json

    parser = argparse.ArgumentParser(description="E01 prompt renderer identity and digests.")
    parser.add_argument("--episode-manifest", default=None)
    args = parser.parse_args(argv)

    report: dict[str, Any] = {
        "prompt_renderer_revision": PROMPT_RENDERER_REVISION,
        "instruction_sha256": instruction_sha256(),
        "task_header": TASK_HEADER,
        "output_header": OUTPUT_HEADER,
    }
    if args.episode_manifest:
        rows = [
            json.loads(line)
            for line in Path(args.episode_manifest).read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        payloads = payloads_from_manifest(rows)
        report["prompt_sha256"] = prompt_set_sha256(payloads)
        report["episode_count"] = len(payloads)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
