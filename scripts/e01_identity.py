"""E01 pinned model identity, read from the merged R02 readiness record.

Issue https://durandal.exe.xyz/smolmodelco/thesmolmodelcompany/issues/21.

Issue #21 fixes the model identity for E01 by reference, not by copy:

    "Exact model/artifact references point to the readiness record without
     copying weights or caches into Git."

So the pin is not restated as a constant here. It is *read back* from the merged
readiness record ``results/R02/r02-smoke-001/`` and then asserted against the
declared E01 plan. Two consequences a reviewer should check:

* a declared plan that names a different repository, source, precision or
  revision is refused, which is what "do not alter the model identity or use
  alternate transport" means in code; and
* the pin cannot silently drift, because the constant it would have been is
  gone -- the record is the only source.

This module transfers nothing. There is no transport, no client and no
``fetch_and_hash`` seam: artifact retrieval is ``scripts/r02_artifacts.py`` and
is deliberately not re-implemented here. Importing this module reads no file
until a caller asks for one, and the only files it ever opens are committed JSON
records under ``results/``.

Note what is *not* here: the generator, scorer, split and reference-answer
apparatus. Those belong to Research B (``docs/R03-generator-scorer-split-protocol.md``)
and are absent from this scaffold on purpose.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

try:  # bare script (sys.path[0] is scripts/) or scripts/ already on sys.path
    from r02_gate import is_unset
    from r02_preflight import UNSET
except ModuleNotFoundError:  # imported as scripts.<module> from the repository root
    from scripts.r02_gate import is_unset
    from scripts.r02_preflight import UNSET

PIN_RECORD_DIR = "results/R02/r02-smoke-001"
PIN_ARTIFACT_MANIFEST = "artifact-manifest.json"
PIN_RUN_MANIFEST = "manifest.json"

PLAN_KIND = "e01-execution-plan"

EXPERIMENT_ID = "E01"

# Every identity field of the declared plan is pinned, not just the revision:
# a manifest that changes `precision` or `source` names a different system.
PINNED_IDENTITY_FIELDS = ("source", "repo_id", "precision", "revision")

REVISION_PATTERN = re.compile(r"\A[0-9a-f]{40}\Z")

# Fields that must still be UNSET until the protocol is frozen and the run is
# authorized. The generator/scorer revisions are Research B's apparatus; the two
# digests are produced before model invocation, so an execution preflight that
# sees them unset is looking at an unfrozen protocol.
UNFROZEN_FIELDS = (
    "generator_revision",
    "scorer_revision",
    "episode_manifest_sha256",
    "reference_answers_sha256",
)


class PinError(RuntimeError):
    """The pinned identity could not be read, or two records disagree."""


def is_frozen(value: Any) -> bool:
    """True when ``value`` carries a real value rather than the ``UNSET`` marker."""
    if is_unset(value):
        return False
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


@dataclass(frozen=True)
class ModelPin:
    """The model identity recorded by the readiness smoke, and its file digests."""

    source: str
    repo_id: str
    precision: str
    revision: str
    resolved_revision: str
    files: Mapping[str, Mapping[str, Any]]
    artifact_manifest_path: str
    run_manifest_path: str

    def identity(self) -> dict[str, str]:
        return {
            "source": self.source,
            "repo_id": self.repo_id,
            "precision": self.precision,
            "revision": self.revision,
        }

    def file_digests(self) -> dict[str, str]:
        return {
            path: str(entry.get("observed_sha256", UNSET))
            for path, entry in self.files.items()
        }

    def to_record(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "repo_id": self.repo_id,
            "precision": self.precision,
            "revision": self.revision,
            "resolved_revision": self.resolved_revision,
            "files": {path: dict(entry) for path, entry in self.files.items()},
            "artifact_manifest": self.artifact_manifest_path,
            "run_manifest": self.run_manifest_path,
        }


def _read_json(path: Path) -> Mapping[str, Any]:
    if not path.is_file():
        raise PinError(f"pin record not found: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PinError(f"{path}: not valid JSON ({exc.msg})") from exc
    if not isinstance(data, Mapping):
        raise PinError(f"{path}: expected a JSON object")
    return data


def load_pin(record_dir: str | Path) -> ModelPin:
    """Read the pinned identity from the merged readiness record.

    The readiness smoke wrote the identity twice -- once in the run manifest and
    once in the artifact manifest -- so both are read and required to agree. A
    record whose own two files disagree is not a pin.
    """
    directory = Path(record_dir)
    artifact_path = directory / PIN_ARTIFACT_MANIFEST
    run_path = directory / PIN_RUN_MANIFEST

    artifact = _read_json(artifact_path)
    run = _read_json(run_path)

    artifact_identity = {
        "source": artifact.get("source"),
        "repo_id": artifact.get("repo_id"),
        "precision": artifact.get("precision"),
        "revision": artifact.get("requested_revision"),
    }
    model = run.get("model")
    if not isinstance(model, Mapping):
        raise PinError(f"{run_path}: missing 'model' object")
    run_identity = {
        "source": artifact_identity["source"],
        "repo_id": model.get("repo_id"),
        "precision": model.get("precision"),
        "revision": model.get("revision"),
    }

    disagreements = [
        f"{name}: artifact manifest {artifact_identity[name]!r} vs run manifest {run_identity[name]!r}"
        for name in PINNED_IDENTITY_FIELDS
        if artifact_identity[name] != run_identity[name]
    ]
    if disagreements:
        raise PinError(
            f"{directory}: the readiness record is internally inconsistent; "
            + "; ".join(disagreements)
        )

    for name in PINNED_IDENTITY_FIELDS:
        value = artifact_identity[name]
        if not isinstance(value, str) or not value.strip() or is_unset(value):
            raise PinError(f"{directory}: pinned field {name!r} is {value!r}, not a value")

    revision = artifact_identity["revision"]
    if not REVISION_PATTERN.match(revision):
        raise PinError(f"{directory}: pinned revision {revision!r} is not a 40-char hex revision")

    raw_files = artifact.get("files")
    if not isinstance(raw_files, list) or not raw_files:
        raise PinError(f"{artifact_path}: 'files' must be a non-empty list")
    files: dict[str, Mapping[str, Any]] = {}
    for entry in raw_files:
        if not isinstance(entry, Mapping) or not isinstance(entry.get("path"), str):
            raise PinError(f"{artifact_path}: each entry needs a 'path' string")
        files[str(entry["path"])] = entry

    resolved = artifact.get("resolved_revision")
    if not isinstance(resolved, str) or is_unset(resolved):
        resolved = revision

    return ModelPin(
        source=str(artifact_identity["source"]),
        repo_id=str(artifact_identity["repo_id"]),
        precision=str(artifact_identity["precision"]),
        revision=str(revision),
        resolved_revision=resolved,
        files=files,
        artifact_manifest_path=str(artifact_path),
        run_manifest_path=str(run_path),
    )


def validate_declared_identity(declared: Mapping[str, Any], pin: ModelPin) -> list[str]:
    """Problems with a declared model identity, or an empty list.

    Mirrors the R02 rule that every identity field is pinned, not just the
    revision, so a plan cannot swap precision or source under a matching pin.
    """
    problems: list[str] = []
    if not isinstance(declared, Mapping):
        return ["declared model identity must be an object"]

    expected = pin.identity()
    for name in PINNED_IDENTITY_FIELDS:
        value = declared.get(name)
        if not isinstance(value, str) or not value.strip() or is_unset(value):
            problems.append(f"declared {name!r} is {value!r}, not a value")
            continue
        if value != expected[name]:
            problems.append(
                f"declared {name!r} is {value!r}; the readiness record pins {expected[name]!r}"
            )

    revision = declared.get("revision")
    if isinstance(revision, str) and not is_unset(revision) and not REVISION_PATTERN.match(revision):
        problems.append(f"declared revision {revision!r} is not a 40-char hex revision")
    return problems


def load_plan(path: str | Path) -> Mapping[str, Any]:
    """Read the declared E01 execution plan."""
    data = _read_json(Path(path))
    kind = data.get("kind")
    if kind != PLAN_KIND:
        raise PinError(f"{path}: expected kind {PLAN_KIND!r}, found {kind!r}")
    return data


def freeze_problems(plan: Mapping[str, Any]) -> list[str]:
    """Problems that mean the protocol is not yet frozen.

    These are not identity mismatches: they are the fields Research B's protocol
    owns. While any of them is ``UNSET`` the execution path stays closed, which
    is the executable form of "protocol freeze" in issue #21's ordering.
    """
    artifacts = plan.get("artifacts")
    if not isinstance(artifacts, Mapping):
        return ["plan has no 'artifacts' object"]
    problems: list[str] = []
    for name in UNFROZEN_FIELDS:
        if not is_frozen(artifacts.get(name)):
            problems.append(f"{name} is not frozen ({artifacts.get(name, UNSET)!r}); ")
    return [p.rstrip("; ") for p in problems]


def validate_plan(plan: Mapping[str, Any], pin: ModelPin) -> list[str]:
    """Every problem with the declared plan, identity and freeze alike."""
    problems: list[str] = []
    experiment = plan.get("experiment")
    if experiment != EXPERIMENT_ID:
        problems.append(f"plan names experiment {experiment!r}, not {EXPERIMENT_ID!r}")
    model = plan.get("model")
    if not isinstance(model, Mapping):
        problems.append("plan has no 'model' object")
    else:
        problems.extend(validate_declared_identity(model, pin))
    problems.extend(freeze_problems(plan))
    return problems
