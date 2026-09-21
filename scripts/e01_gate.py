#!/usr/bin/env python3
"""E01 execution gate: authorization, run target, and freeze checks.

Issue https://durandal.exe.xyz/smolmodelco/thesmolmodelcompany/issues/21.

Issue #21 freezes the order the first controlled records baseline may run in:

    protocol freeze -> independent review -> recorded operator go -> execution

This module is the execution-side half of that order, and it fails closed. It
holds no model library, opens no socket, reads no artifact and touches no GPU.

Why the gate is defined here rather than widened in ``scripts/r02_gate.py``:
that module closes its own scope set (``KNOWN_SCOPES``) and refuses an unknown
scope at parse time, which is exactly the property that stops a grant for one
step being spent on another. Adding ``e01-execution`` to a merged, reviewed
grant surface would weaken it, so E01 owns its own gate and the two modules
share only the generic sentinel and redaction helpers.

An authorization for E01 must carry *two decisions*, and a reviewer will send it
back if the file blurs them:

* the **procedure** approval -- the independent review of the frozen protocol,
  named by ``approved_by`` / ``approved_at_utc`` / ``reference``;
* the **operator go/no-go** -- a separate decision, carried in ``operator_go``
  and timestamped by ``operator_go_received_before_utc``, which must name the
  run it authorizes in ``run_id``.

``procedure_reviewer_only: true`` keeps the second reading out of the file: the
reviewer approved the procedure, not the run. The merged R02 records
(``results/R02/r02-smoke-001/authorization-*.json``) carry the same distinction,
including the scope-limiting note that a readiness smoke is "Not authorization
for training, tuning, evaluation, or any experiment".

Nothing here is an authorization by itself. A record is a claim about a decision
made elsewhere; ``docs/coordination.md`` and issue #21 remain the source of the
order the run happens in.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

try:  # bare script (sys.path[0] is scripts/) or scripts/ already on sys.path
    from r02_gate import EXIT_GATE_CLOSED, EXIT_OK, EXIT_STEP_FAILED, is_unset
except ModuleNotFoundError:  # imported as scripts.<module> from the repository root
    from scripts.r02_gate import EXIT_GATE_CLOSED, EXIT_OK, EXIT_STEP_FAILED, is_unset

EXPERIMENT_ID = "E01"

SCOPE_E01_EXECUTION = "e01-execution"

KNOWN_SCOPES = (SCOPE_E01_EXECUTION,)

# The run-id form fixed by results/README.md ("e01-pilot-001") and by the
# pull-request template ("E01 run e01-pilot-002").
RUN_ID_PATTERN = re.compile(r"\Ae01-pilot-\d{3}\Z")

RUN_DIR_PREFIX = f"results/{EXPERIMENT_ID}"

BASE_FIELDS = ("granted", "scope", "reference", "approved_by", "approved_at_utc")

OPERATOR_FIELDS = (
    "experiment",
    "run_id",
    "operator_go",
    "operator_go_received_before_utc",
    "procedure_reviewer_only",
)


class GateClosed(RuntimeError):
    """An E01 execution was attempted without a matching authorization record."""


class AuthorizationError(GateClosed):
    """An authorization record was present but malformed or inconsistent."""


def expected_run_dir(run_id: str) -> str:
    """The only directory layout a run of ``run_id`` may write into."""
    return f"{RUN_DIR_PREFIX}/{run_id}"


def _require_text(source: str, name: str, value: Any) -> str:
    if not isinstance(value, str) or not value.strip() or is_unset(value):
        raise AuthorizationError(f"{source}: '{name}' must name the decision, not {value!r}")
    return value.strip()


@dataclass(frozen=True)
class OperatorRecord:
    """The two E01 decisions, read from one reviewable JSON file.

    ``procedure_reviewer_only`` is required to be ``True`` so a record can never
    read as though the reviewer authorized the run, and ``run_id`` is required to
    name the run this grant covers, which is what issue #21 means by "a separate
    operator go/no-go names the experiment ID".
    """

    granted: bool
    scope: str
    reference: str
    approved_by: str
    approved_at_utc: str
    experiment: str
    run_id: str
    operator_go: str
    operator_go_received_before_utc: str
    procedure_reviewer_only: bool
    extra: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any], *, source: str = "mapping") -> "OperatorRecord":
        if not isinstance(data, Mapping):
            raise AuthorizationError(f"{source}: authorization must be a JSON object")
        missing = [name for name in BASE_FIELDS + OPERATOR_FIELDS if name not in data]
        if missing:
            raise AuthorizationError(f"{source}: missing field(s): {', '.join(missing)}")

        granted = data["granted"]
        if not isinstance(granted, bool):
            raise AuthorizationError(f"{source}: 'granted' must be true or false, not {granted!r}")

        scope = data["scope"]
        if scope not in KNOWN_SCOPES:
            raise AuthorizationError(
                f"{source}: unknown scope {scope!r}; this gate only opens "
                f"{', '.join(KNOWN_SCOPES)}"
            )

        experiment = data["experiment"]
        if experiment != EXPERIMENT_ID:
            raise AuthorizationError(
                f"{source}: names experiment {experiment!r}, not {EXPERIMENT_ID!r}"
            )

        run_id = data["run_id"]
        if not isinstance(run_id, str) or is_unset(run_id):
            raise AuthorizationError(
                f"{source}: 'run_id' must name the run this record covers, not {run_id!r}"
            )
        if not RUN_ID_PATTERN.match(run_id):
            raise AuthorizationError(f"{source}: run_id {run_id!r} is not the form e01-pilot-<nnn>")

        reviewer_only = data["procedure_reviewer_only"]
        if reviewer_only is not True:
            raise AuthorizationError(
                f"{source}: 'procedure_reviewer_only' must be true, so the file cannot read "
                f"as though the reviewer authorized the run; got {reviewer_only!r}"
            )

        extra = {
            k: v for k, v in data.items() if k not in BASE_FIELDS + OPERATOR_FIELDS
        }
        return cls(
            granted=granted,
            scope=scope,
            reference=_require_text(source, "reference", data["reference"]),
            approved_by=_require_text(source, "approved_by", data["approved_by"]),
            approved_at_utc=_require_text(source, "approved_at_utc", data["approved_at_utc"]),
            experiment=experiment,
            run_id=run_id,
            operator_go=_require_text(source, "operator_go", data["operator_go"]),
            operator_go_received_before_utc=_require_text(
                source, "operator_go_received_before_utc", data["operator_go_received_before_utc"]
            ),
            procedure_reviewer_only=True,
            extra=extra,
        )

    @classmethod
    def from_file(cls, path: str | Path) -> "OperatorRecord":
        candidate = Path(path)
        if not candidate.is_file():
            raise GateClosed(f"authorization file not found: {candidate}")
        try:
            data = json.loads(candidate.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise AuthorizationError(f"{candidate}: not valid JSON ({exc.msg})") from exc
        return cls.from_mapping(data, source=str(candidate))

    def to_record(self) -> dict[str, Any]:
        record: dict[str, Any] = {
            name: getattr(self, name) for name in BASE_FIELDS + OPERATOR_FIELDS
        }
        record.update(self.extra)
        return record


def require_e01_authorization(
    record: OperatorRecord | None, *, run_id: str
) -> OperatorRecord:
    """Return the grant for ``run_id`` or raise before any side effect happens."""
    if record is None:
        raise GateClosed(
            f"no authorization supplied for {SCOPE_E01_EXECUTION!r}: E01 runs only under a "
            "recorded operator go/no-go naming the run"
        )
    if not isinstance(record, OperatorRecord):
        raise AuthorizationError("authorization must be an OperatorRecord")
    if not record.granted:
        raise GateClosed(f"authorization for {SCOPE_E01_EXECUTION!r} is not granted")
    if record.scope != SCOPE_E01_EXECUTION:
        raise GateClosed(
            f"authorization scope {record.scope!r} does not cover {SCOPE_E01_EXECUTION!r}"
        )
    if record.run_id != run_id:
        raise GateClosed(
            f"authorization names run {record.run_id!r}, which does not cover {run_id!r}"
        )
    return record


def validate_run_target(*, run_id: str, run_dir: str | None = None) -> list[str]:
    """Problems with the run id or its directory, or an empty list.

    Rejecting an off-layout target before any setup is what keeps a mistyped run
    id from creating a stray directory under ``results/``.
    """
    problems: list[str] = []
    if not isinstance(run_id, str) or not RUN_ID_PATTERN.match(run_id or ""):
        problems.append(f"run id {run_id!r} is not the form e01-pilot-<nnn>")
    if run_dir is not None:
        wanted = expected_run_dir(run_id) if not problems else None
        normalized = str(run_dir).replace("\\", "/").strip("/")
        if wanted is not None and normalized != wanted:
            problems.append(f"run directory {run_dir!r} is off the layout; expected {wanted!r}")
    return problems
