#!/usr/bin/env python3
"""E01 execution preflight: the fail-closed entry point.

Issue https://durandal.exe.xyz/smolmodelco/thesmolmodelcompany/issues/21.

This is the execution-side seam for E01, and it deliberately stops short of a
run. It answers three questions and nothing else:

1. is there a recorded authorization whose scope is ``e01-execution`` and whose
   ``run_id`` names *this* run (issue #21: "a separate operator go/no-go names
   the experiment ID")?
2. is the run target on the ``results/E01/<run-id>`` layout?
3. does the declared plan name the model identity the merged readiness record
   pins, and is the protocol frozen?

What this does **not** do, and must not be read as doing:

* no dependency install, no artifact retrieval, no model or tokenizer load, no
  GPU reservation, no inference;
* no generator, scorer, split or reference-answer work -- that apparatus belongs
  to Research B and is not implemented in this scaffold;
* no run directory. Nothing writes under ``results/`` here, authorized or not.
  Pre-authorization the directory must not exist, so the preflight creates
  nothing and reports to stdout.

The gate is the first statement that can touch the filesystem, ahead of the pin
read and the plan read, so a closed gate reads no artifact record at all.

Because the merged plan's generator/scorer revisions are still ``UNSET``, the
preflight on the current ``main`` state refuses at the freeze check. That is the
intended behaviour, not a defect: it is the executable form of "protocol freeze"
in issue #21's ordering.

Usage, from the repository root:

    python3 scripts/e01_preflight.py --run-id e01-pilot-001 --owner eido \
        --plan configs/e01-execution-plan.json \
        --r02-record results/R02/r02-smoke-001 \
        --authorization-file FILE [--run-dir results/E01/e01-pilot-001] \
        [--record-out FILE]

Exit codes: 0 the preflight passed (no run was executed), 1 a check failed,
2 the gate is closed or the run target is off the layout.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

try:  # bare script (sys.path[0] is scripts/) or scripts/ already on sys.path
    from e01_gate import (
        EXPERIMENT_ID,
        SCOPE_E01_EXECUTION,
        GateClosed,
        OperatorRecord,
        expected_run_dir,
        require_e01_authorization,
        validate_run_target,
    )
    from e01_identity import PinError, load_pin, load_plan, validate_plan
    from e01_records import verify_frozen_outputs
    from r02_gate import EXIT_GATE_CLOSED, EXIT_OK, EXIT_STEP_FAILED, is_unset, redact_secrets
except ModuleNotFoundError:  # imported as scripts.<module> from the repository root
    from scripts.e01_gate import (
        EXPERIMENT_ID,
        SCOPE_E01_EXECUTION,
        GateClosed,
        OperatorRecord,
        expected_run_dir,
        require_e01_authorization,
        validate_run_target,
    )
    from scripts.e01_identity import PinError, load_pin, load_plan, validate_plan
    from scripts.e01_records import verify_frozen_outputs
    from scripts.r02_gate import (
        EXIT_GATE_CLOSED,
        EXIT_OK,
        EXIT_STEP_FAILED,
        is_unset,
        redact_secrets,
    )

KIND = "e01-execution-preflight"

NOT_ESTABLISHED = (
    "this preflight did not execute a run, load a model, or touch the GPU",
    "no episode manifest or reference answer was generated",
    "no directory was created under results/",
)


def _utc_now() -> str:
    return _dt.datetime.now(tz=_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fail-closed preflight for an E01 execution (never executes a run)."
    )
    parser.add_argument("--run-id", required=True, help="run id, e.g. e01-pilot-001")
    parser.add_argument("--owner", required=True, help="executing agent, e.g. eido")
    parser.add_argument("--plan", required=True, help="declared execution plan JSON")
    parser.add_argument(
        "--r02-record",
        required=True,
        help="merged readiness record directory, e.g. results/R02/r02-smoke-001",
    )
    parser.add_argument(
        "--run-dir",
        default=None,
        help="optional; when given it must equal results/E01/<run-id>",
    )
    parser.add_argument(
        "--record-out",
        default=None,
        help="optional path for the preflight record; refused under results/",
    )
    parser.add_argument(
        "--authorization-file",
        required=True,
        help="operator record naming this run (required; the gate fails closed without it)",
    )
    parser.add_argument("--episode-manifest", required=True, help="frozen candidate manifest JSONL")
    parser.add_argument("--reference-answers", required=True, help="frozen independent references JSONL")
    return parser


def _record_out_problem(path: str) -> str | None:
    """Refuse any record path that looks like a run-results path.

    Deliberately conservative: a preflight record is evidence about a run that
    has not happened, so writing it under ``results/`` would create the very
    directory the gate exists to keep absent.
    """
    normalized = str(path).replace("\\", "/")
    parts = [part for part in normalized.split("/") if part not in ("", ".")]
    if "results" in parts:
        return (
            f"--record-out {path!r} names a results path: this preflight must not write into a "
            "run directory before authorization"
        )
    return None


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    # 1. The gate. This is the first statement that can read the filesystem, so a
    #    closed gate opens no artifact record and creates nothing.
    try:
        record = OperatorRecord.from_file(args.authorization_file)
        require_e01_authorization(record, run_id=args.run_id)
    except GateClosed as exc:
        print(f"e01_preflight: gate closed: {redact_secrets(exc)}", file=sys.stderr)
        return EXIT_GATE_CLOSED

    if not isinstance(args.owner, str) or not args.owner.strip() or is_unset(args.owner):
        print("e01_preflight: --owner must name the executing agent", file=sys.stderr)
        return EXIT_GATE_CLOSED

    # 2. The run target, before any setup.
    target_problems = validate_run_target(run_id=args.run_id, run_dir=args.run_dir)
    if target_problems:
        for problem in target_problems:
            print(f"e01_preflight: {redact_secrets(problem)}", file=sys.stderr)
        return EXIT_GATE_CLOSED

    if args.record_out:
        blocked = _record_out_problem(args.record_out)
        if blocked:
            print(f"e01_preflight: {redact_secrets(blocked)}", file=sys.stderr)
            return EXIT_GATE_CLOSED

    # 3. The pinned identity and the freeze state.
    try:
        pin = load_pin(args.r02_record)
        plan = load_plan(args.plan)
    except PinError as exc:
        print(f"e01_preflight: {redact_secrets(exc)}", file=sys.stderr)
        return EXIT_STEP_FAILED

    problems = validate_plan(plan, pin)
    if problems:
        for problem in problems:
            print(f"e01_preflight: {redact_secrets(problem)}", file=sys.stderr)
        return EXIT_STEP_FAILED
    try:
        frozen_hashes = verify_frozen_outputs(
            args.plan, args.episode_manifest, args.reference_answers
        )
    except (OSError, KeyError, ValueError) as exc:
        print(f"e01_preflight: frozen artifact verification failed: {redact_secrets(exc)}", file=sys.stderr)
        return EXIT_STEP_FAILED

    run_dir = args.run_dir or expected_run_dir(args.run_id)
    report: dict[str, Any] = {
        "kind": KIND,
        "experiment": EXPERIMENT_ID,
        "run_id": args.run_id,
        "owner": args.owner,
        "scope": SCOPE_E01_EXECUTION,
        "checked_at_utc": _utc_now(),
        "executed": False,
        "run_directory": str(run_dir).replace("\\", "/"),
        "run_directory_created": False,
        "authorization": dict(record.to_record(), source=str(args.authorization_file)),
        "pin": pin.to_record(),
        "plan": {"path": str(args.plan), "kind": plan.get("kind")},
        "checks": {
            "operator_record_names_run": True,
            "scope_matches": True,
            "run_target_on_layout": True,
            "declared_identity_matches_pin": True,
            "protocol_frozen": True,
            "frozen_episode_manifest_matches": True,
            "frozen_reference_answers_match": True,
        },
        "frozen_hashes": frozen_hashes,
        "not_established": list(NOT_ESTABLISHED),
    }

    if args.record_out:
        Path(args.record_out).write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    print(json.dumps(report, indent=2, sort_keys=True))
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
