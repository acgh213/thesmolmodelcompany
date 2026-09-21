#!/usr/bin/env python3
"""R02.1 approval-gated model load and readiness smoke.

Issue https://durandal.exe.xyz/smolmodelco/thesmolmodelcompany/issues/17.

The recipe asks for one thing and one thing only: load the pinned model, run one
inference, terminate cleanly, and record a manifest. This module is that
procedure, and it is gated three ways:

1. **Authorization.** ``ReadinessSmoke.__init__`` calls ``require_authorization``
   before anything else, so without a matching grant the run raises
   ``GateClosed`` before the deferred access layer is constructed, before
   ``torch`` or ``transformers`` is imported, and before any CUDA call.
2. **Injected access.** Every touch of a model library or the GPU goes through
   ``ModelAccess`` callables, so tests exercise the whole flow with pure fakes
   and never load or reserve anything.
3. **One attempt.** The first failure is recorded and returned; nothing is
   retried. A diagnosed retry is a new run ID that links to this one.

Failure recording is total: the pre-load sampling instant, the peak-counter
reset, the loads, the inference and the post-load sampling are all inside one
failure boundary, and a probe that cannot be read produces a *record*, not a
traceback (``ResourceProbeUnavailable``). ``main`` writes the manifest for a
failed run exactly as it does for a successful one.

The wall-clock cap is reported exactly as implemented. It is armed as a
``SIGALRM`` before the run whenever that is possible (POSIX, main thread), so a
stage that returns control to the interpreter is aborted *at* the cap and still
produces a record; a stage blocked inside a C call is not interrupted, and that
case is detected only after the call returns. Both outcomes are labelled in the
record.

Usage, from the repository root:

    python3 scripts/r02_smoke.py --run-id r02-smoke-001 --owner eido \\
        --run-dir results/R02/r02-smoke-001 --authorization-file FILE [--dry-run]

``--dry-run`` validates the gate and the plan and prints what would run, without
importing a model library or touching the GPU.

Exit codes: 0 completed, 1 a step failed, 2 the gate is closed or the run target
is off the layout.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import re
import signal
import sys
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping, Sequence

try:  # bare script (sys.path[0] is scripts/) or scripts/ already on sys.path
    from r02_artifacts import PRECISION, REPO_ID, REVISION
    from r02_gate import (
        EXIT_GATE_CLOSED,
        EXIT_OK,
        EXIT_STEP_FAILED,
        SCOPE_READINESS_SMOKE,
        Authorization,
        GateClosed,
        is_unset,
        redact_secrets,
        require_authorization,
    )
    from r02_preflight import UNSET
    from r02_resources import (
        KIND as RESOURCE_SAMPLING_KIND,
        STATUS_OK as RESOURCE_STATUS_OK,
        ResourceProbeUnavailable,
        ResourceSampler,
        torch_peak_probe,
    )
except ModuleNotFoundError:  # imported as scripts.<module> from the repository root
    from scripts.r02_artifacts import PRECISION, REPO_ID, REVISION
    from scripts.r02_gate import (
        EXIT_GATE_CLOSED,
        EXIT_OK,
        EXIT_STEP_FAILED,
        SCOPE_READINESS_SMOKE,
        Authorization,
        GateClosed,
        is_unset,
        redact_secrets,
        require_authorization,
    )
    from scripts.r02_preflight import UNSET
    from scripts.r02_resources import (
        KIND as RESOURCE_SAMPLING_KIND,
        STATUS_OK as RESOURCE_STATUS_OK,
        ResourceProbeUnavailable,
        ResourceSampler,
        torch_peak_probe,
    )

KIND = "r02-readiness-smoke"

RUN_ID_PATTERN = re.compile(r"\Ar02-smoke-\d{3}\Z")

STATUS_OK = "ok"
STATUS_FAILED = "failed"

CAP_ENFORCEMENT_ARMED = (
    "sigalrm armed: the cap raises inside the interpreter and aborts the run"
)
CAP_ENFORCEMENT_DETECTION = (
    "no guard armed: the cap is compared after a stage returns"
)
CAP_ABORTED = "aborted by the armed guard at the cap"
CAP_DETECTED_AFTER_RETURN = (
    "detected after the stage returned; a call blocked inside C is not interrupted"
)

DEFAULT_PROMPT = "The capital of France is"

FAILURE_KINDS = {
    "WallClockCapExceeded": "wall-clock-cap-exceeded",
    "ResourceProbeUnavailable": "resource-probe-unavailable",
}

REQUIRED_RECORD_KEYS = (
    "kind",
    "run_id",
    "owner",
    "authorization",
    "model",
    "plan",
    "timing",
    "tokenizer",
    "generation",
    "resources",
    "started_at_utc",
    "finished_at_utc",
    "exit_status",
    "failure",
)


def _utc_now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _generation_identity(generation: Mapping[str, Any]) -> dict[str, Any]:
    """Identity, not output: a digest and counts, never the text or its token IDs."""
    return {
        "output_text_sha256": (
            _sha256_text(str(generation.get("output_text", ""))) if generation else UNSET
        ),
        "output_token_count": len(generation.get("output_token_ids", [])) if generation else UNSET,
        "logits_all_finite": generation.get("logits_all_finite", UNSET),
        "stop_reason": generation.get("stop_reason", UNSET),
    }


class WallClockCapExceeded(RuntimeError):
    """The armed wall-clock guard fired: the cap bounded the run, it did not merely describe it."""


@contextmanager
def wall_clock_guard(seconds: int, *, arm: bool = True) -> Iterator[str]:
    """Arm a ``SIGALRM`` for ``seconds`` and yield the enforcement label in force.

    Armed only where a signal can reach the running code: POSIX with
    ``SIGALRM``, in the main thread, with a positive whole-second cap. Otherwise
    the cap degrades to post-return detection and the label says so.
    """
    arm_here = (
        arm
        and int(seconds) >= 1
        and hasattr(signal, "SIGALRM")
        and threading.current_thread() is threading.main_thread()
    )
    if not arm_here:
        yield CAP_ENFORCEMENT_DETECTION
        return

    def _raise(signum: int, frame: Any) -> None:
        raise WallClockCapExceeded(
            f"wall-clock cap of {int(seconds)}s reached inside the interpreter"
        )

    previous = signal.signal(signal.SIGALRM, _raise)
    signal.alarm(int(seconds))
    try:
        yield CAP_ENFORCEMENT_ARMED
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)


@dataclass(frozen=True)
class SmokePlan:
    """Everything frozen before the run; no field is chosen at run time."""

    run_id: str
    owner: str
    repo_id: str = REPO_ID
    revision: str = REVISION
    precision: str = PRECISION
    device: str = "cuda:0"
    prompt: str = DEFAULT_PROMPT
    max_new_tokens: int = 8
    seed: int = 0
    wall_clock_cap_seconds: int = 1200
    cache_state: str = UNSET
    artifact_manifest_path: str = UNSET

    def to_record(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "owner": self.owner,
            "repo_id": self.repo_id,
            "revision": self.revision,
            "precision": self.precision,
            "device": self.device,
            "prompt": self.prompt,
            "prompt_sha256": _sha256_text(self.prompt),
            "max_new_tokens": self.max_new_tokens,
            "seed": self.seed,
            "wall_clock_cap_seconds": self.wall_clock_cap_seconds,
            "cache_state": self.cache_state,
            "artifact_manifest_path": self.artifact_manifest_path,
        }


@dataclass(frozen=True)
class ModelAccess:
    """The only code permitted to import a model library or touch the GPU."""

    reset_peak_counters: Callable[[SmokePlan], None]
    load_tokenizer: Callable[[SmokePlan], Any]
    load_model: Callable[[SmokePlan, Any], Any]
    describe_device: Callable[[SmokePlan], Mapping[str, Any]]
    generate: Callable[[SmokePlan, Any, Any], Mapping[str, Any]]


def deferred_access() -> ModelAccess:
    """Default access whose imports happen inside the callables.

    Importing this module, or calling this factory, imports neither ``torch`` nor
    ``transformers``: those imports live inside the function bodies, so an
    ungated invocation cannot reach them.
    """

    def reset_peak_counters(plan: SmokePlan) -> None:
        import torch  # noqa: PLC0415 - deferred behind the gate

        torch.cuda.reset_peak_memory_stats()

    def load_tokenizer(plan: SmokePlan) -> Any:
        from transformers import AutoTokenizer  # noqa: PLC0415 - deferred behind the gate

        return AutoTokenizer.from_pretrained(plan.repo_id, revision=plan.revision)

    def load_model(plan: SmokePlan, tokenizer: Any) -> Any:
        import torch  # noqa: PLC0415 - deferred behind the gate
        from transformers import AutoModelForCausalLM  # noqa: PLC0415

        dtype = getattr(torch, plan.precision, torch.bfloat16)
        model = AutoModelForCausalLM.from_pretrained(
            plan.repo_id, revision=plan.revision, dtype=dtype
        )
        return model.to(plan.device).eval()

    def describe_device(plan: SmokePlan) -> Mapping[str, Any]:
        import torch  # noqa: PLC0415 - deferred behind the gate

        return {
            "device": plan.device,
            "device_name": torch.cuda.get_device_name(0),
            "cuda_available": torch.cuda.is_available(),
        }

    def generate(plan: SmokePlan, model: Any, tokenizer: Any) -> Mapping[str, Any]:
        import torch  # noqa: PLC0415 - deferred behind the gate

        torch.manual_seed(plan.seed)
        inputs = tokenizer(plan.prompt, return_tensors="pt").to(plan.device)
        with torch.no_grad():
            output = model.generate(
                **inputs, max_new_tokens=plan.max_new_tokens, do_sample=False
            )
        generated_ids = output[0][inputs["input_ids"].shape[-1] :]
        text = tokenizer.decode(generated_ids, skip_special_tokens=True)
        logits = model(output).logits
        return {
            "input_token_count": int(inputs["input_ids"].shape[-1]),
            "output_token_ids": [int(token) for token in generated_ids],
            "output_text": text,
            "logits_all_finite": bool(torch.isfinite(logits).all().item()),
            "stop_reason": "max_new_tokens",
        }

    return ModelAccess(
        reset_peak_counters=reset_peak_counters,
        load_tokenizer=load_tokenizer,
        load_model=load_model,
        describe_device=describe_device,
        generate=generate,
    )


def validate_run_target(*, run_id: str, run_dir: str | None) -> list[str]:
    """The recipe assigns the run-id form and the location; assert both, don't inherit them."""
    problems: list[str] = []
    if not RUN_ID_PATTERN.match(run_id):
        problems.append("run-id must match r02-smoke-<three digits>, for example r02-smoke-001")
    if run_dir:
        parts = Path(run_dir).parts
        if tuple(parts[-3:]) != ("results", "R02", run_id):
            problems.append(f"run-dir must end with results/R02/{run_id}")
    return problems


def write_run_artifacts(run_dir: str | Path, record: Mapping[str, Any]) -> None:
    """Write the manifest and the sampling record, for a failed run as well as a successful one."""
    target = Path(run_dir)
    target.mkdir(parents=True, exist_ok=True)
    (target / "manifest.json").write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (target / "resource-samples.json").write_text(
        json.dumps(record.get("resources", UNSET), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


class ReadinessSmoke:
    """Ordered procedure: gate, arm the cap, reset the peak counter, sample, load, infer, sample, record."""

    def __init__(
        self,
        *,
        authorization: Authorization | None,
        plan: SmokePlan,
        access: ModelAccess | None = None,
        sampler: ResourceSampler | None = None,
        peak_probe_factory: Callable[[], Any] | None = None,
        clock: Callable[[], str] = _utc_now,
        resource_interval_seconds: float | None = None,
        enforce_wall_clock_cap: bool = True,
    ) -> None:
        self.authorization = require_authorization(  # fail closed before anything else
            authorization, scope=SCOPE_READINESS_SMOKE
        )
        self.plan = plan
        self.access = access
        self.sampler = sampler
        # The peak-counter probe is only constructed after the model is loaded,
        # and only ever read through the sampler; tests inject a fake here.
        self.peak_probe_factory = peak_probe_factory or torch_peak_probe
        self.clock = clock
        self.resource_interval_seconds = resource_interval_seconds
        self.enforce_wall_clock_cap = enforce_wall_clock_cap
        self.record: dict[str, Any] | None = None

    def run(self) -> dict[str, Any]:
        access = self.access if self.access is not None else deferred_access()
        sampler = self.sampler if self.sampler is not None else ResourceSampler(clock=self.clock)

        started_at = self.clock()
        pre: list[dict[str, Any]] = []
        tokenizer_loaded_at = model_loaded_at = inference_started_at = inference_finished_at = UNSET
        tokenizer: Any = None
        device: dict[str, Any] = {}
        generation: dict[str, Any] = {}
        enforcement = CAP_ENFORCEMENT_DETECTION
        stage = "wall-clock-guard"
        try:
            with wall_clock_guard(
                self.plan.wall_clock_cap_seconds, arm=self.enforce_wall_clock_cap
            ) as label:
                enforcement = label
                # The peak window starts here: before any tokenizer or model load.
                stage = "peak-counter-reset"
                access.reset_peak_counters(self.plan)

                stage = "resource-sample-pre"
                pre = [sample.to_record() for sample in sampler.sample_once()]
                self._require_probe_health(sampler, stage=stage)

                stage = "tokenizer-load"
                tokenizer = access.load_tokenizer(self.plan)
                tokenizer_loaded_at = self.clock()

                stage = "model-load"
                model = access.load_model(self.plan, tokenizer)
                model_loaded_at = self.clock()

                stage = "device-describe"
                device = dict(access.describe_device(self.plan))

                sampler.add_probe(self.peak_probe_factory())
                stage = "generate"
                inference_started_at = self.clock()
                generation = dict(access.generate(self.plan, model, tokenizer))
                inference_finished_at = self.clock()
        except Exception as exc:  # first failure stops the run; nothing is retried
            self.record = self.failure_record(
                stage=stage,
                error=exc,
                started_at=started_at,
                pre=pre,
                sampler=sampler,
                enforcement=enforcement,
            )
            return self.record

        timing = {
            "cold_load_seconds": _seconds_between(started_at, model_loaded_at),
            "tokenizer_load_seconds": _seconds_between(started_at, tokenizer_loaded_at),
            "warm_inference_seconds": _seconds_between(inference_started_at, inference_finished_at),
            "wall_clock_seconds": _seconds_between(started_at, self.clock()),
            "wall_clock_cap_seconds": self.plan.wall_clock_cap_seconds,
            "cap_enforcement": enforcement,
        }
        try:
            post = [sample.to_record() for sample in sampler.sample_once()]
            self._require_probe_health(sampler, stage="resource-sample-post")
        except Exception as exc:
            # A failed sampling instant is a failed run, not a silent gap, and the
            # measurements already taken stay in its record.
            self.record = self.failure_record(
                stage="resource-sample-post",
                error=exc,
                started_at=started_at,
                pre=pre,
                sampler=sampler,
                enforcement=enforcement,
                generation=generation,
                tokenizer=tokenizer,
                device=device,
                timing=timing,
            )
            return self.record

        resources = sampler.summary(interval_seconds=self.resource_interval_seconds)
        readiness = self._readiness(generation, device)
        failure: dict[str, Any] = {
            "stage": UNSET,
            "kind": UNSET,
            "message": UNSET,
            "enforcement": UNSET,
        }

        if timing["wall_clock_seconds"] > self.plan.wall_clock_cap_seconds:
            failure = {
                "stage": "wall-clock",
                "kind": "wall-clock-cap-exceeded",
                "message": (
                    f"wall clock {timing['wall_clock_seconds']:.1f}s exceeded the "
                    f"{self.plan.wall_clock_cap_seconds}s cap and every stage had returned; "
                    "the measurements above are retained"
                ),
                "enforcement": CAP_DETECTED_AFTER_RETURN,
            }
        elif not readiness["readiness_ok"]:
            failure = {
                "stage": "readiness",
                "kind": "readiness-check-failed",
                "message": "; ".join(readiness["failed_checks"]),
                "enforcement": UNSET,
            }

        self.record = {
            "kind": KIND,
            "run_id": self.plan.run_id,
            "owner": self.plan.owner,
            "authorization": self.authorization.to_record(),
            "model": {
                "repo_id": self.plan.repo_id,
                "revision": self.plan.revision,
                "precision": self.plan.precision,
                "device": self.plan.device,
                "device_reported": device.get("device_name", UNSET),
            },
            "plan": self.plan.to_record(),
            "timing": timing,
            "tokenizer": {
                "input_token_count": generation.get("input_token_count", UNSET),
                "vocab_size": getattr(tokenizer, "vocab_size", UNSET),
            },
            # The manifest is committed to Git, so it carries identity, not output.
            "generation": _generation_identity(generation),
            "readiness": readiness,
            "resources": resources,
            "samples_pre": pre,
            "samples_post": post,
            "started_at_utc": started_at,
            "finished_at_utc": self.clock(),
            "exit_status": STATUS_OK if failure["kind"] == UNSET else STATUS_FAILED,
            "retried": False,
            "failure": failure,
        }
        return self.record

    def _require_probe_health(self, sampler: ResourceSampler, *, stage: str) -> None:
        errors = sampler.probe_errors
        if not errors:
            return
        sources = sorted({str(entry.get("source", UNSET)) for entry in errors})
        raise ResourceProbeUnavailable(
            f"resource probe(s) {', '.join(sources)} could not be read at {stage}: "
            f"{errors[0].get('error', UNSET)} -- the run's resource record cannot be completed"
        )

    def _readiness(
        self, generation: Mapping[str, Any], device: Mapping[str, Any]
    ) -> dict[str, Any]:
        checks = {
            "tokenizer_produced_input_tokens": int(generation.get("input_token_count", 0)) > 0,
            "model_produced_output_tokens": len(generation.get("output_token_ids", [])) > 0,
            "logits_all_finite": bool(generation.get("logits_all_finite", False)),
            "device_matches_plan": device.get("device") == self.plan.device,
        }
        failed = [name for name, passed in checks.items() if not passed]
        return {
            "checks": checks,
            "readiness_ok": not failed,
            "failed_checks": failed,
            "not_established": [
                "inference fit does not demonstrate training fit",
                "one smoke run is not a throughput or resource measurement of record",
            ],
        }

    def failure_record(
        self,
        *,
        stage: str,
        error: BaseException,
        started_at: str | None = None,
        pre: Sequence[Mapping[str, Any]] = (),
        sampler: ResourceSampler | None = None,
        enforcement: str = CAP_ENFORCEMENT_DETECTION,
        generation: Mapping[str, Any] | None = None,
        tokenizer: Any = None,
        device: Mapping[str, Any] | None = None,
        timing: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """A validated failure record for any path, including the pre-load sampling instant.

        Whatever was already measured is carried into the record: a failure after
        the generation step keeps its token counts, digest and timings, because a
        failed run is a result and discarding measured facts would hide them.
        """
        resources: Any = UNSET
        probe_errors: list[dict[str, Any]] = []
        samples: list[dict[str, Any]] = []
        if sampler is not None:
            samples = [sample.to_record() for sample in sampler.samples]
            probe_errors = [dict(entry) for entry in sampler.probe_errors]
            if sampler.samples:
                resources = sampler.summary(interval_seconds=self.resource_interval_seconds)
        generation = dict(generation or {})
        kind = FAILURE_KINDS.get(type(error).__name__, type(error).__name__)
        return {
            "kind": KIND,
            "run_id": self.plan.run_id,
            "owner": self.plan.owner,
            "authorization": self.authorization.to_record(),
            "model": {
                "repo_id": self.plan.repo_id,
                "revision": self.plan.revision,
                "precision": self.plan.precision,
                "device": self.plan.device,
                "device_reported": (device or {}).get("device_name", UNSET),
            },
            "plan": self.plan.to_record(),
            "timing": dict(
                timing
                or {
                    "cold_load_seconds": UNSET,
                    "warm_inference_seconds": UNSET,
                    "wall_clock_seconds": UNSET,
                    "wall_clock_cap_seconds": self.plan.wall_clock_cap_seconds,
                    "cap_enforcement": enforcement,
                }
            ),
            "tokenizer": {
                "input_token_count": generation.get("input_token_count", UNSET),
                "vocab_size": getattr(tokenizer, "vocab_size", UNSET),
            },
            "generation": _generation_identity(generation),
            "resources": resources,
            "probe_errors": probe_errors,
            "samples_pre": list(pre),
            "samples_post": samples,
            "started_at_utc": started_at if started_at is not None else self.clock(),
            "finished_at_utc": self.clock(),
            "exit_status": STATUS_FAILED,
            "retried": False,
            "failure": {
                "stage": stage,
                "kind": kind,
                "message": redact_secrets(error),
                "enforcement": (
                    CAP_ABORTED
                    if isinstance(error, WallClockCapExceeded)
                    else enforcement if kind == "wall-clock-cap-exceeded" else UNSET
                ),
            },
        }


def _seconds_between(start: str, end: str) -> float:
    if start == UNSET or end == UNSET:
        return UNSET
    start_dt = _dt.datetime.strptime(start, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=_dt.timezone.utc)
    end_dt = _dt.datetime.strptime(end, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=_dt.timezone.utc)
    return round((end_dt - start_dt).total_seconds(), 3)


def validate_smoke_record(record: Mapping[str, Any]) -> list[str]:
    """Structural checks for a smoke manifest; returns a list of problems."""
    errors = [f"missing key {key!r}" for key in REQUIRED_RECORD_KEYS if key not in record]
    if errors:
        return errors
    if record["kind"] != KIND:
        errors.append(f"kind must be {KIND!r}")
    for key in ("run_id", "owner", "started_at_utc", "finished_at_utc"):
        if not isinstance(record[key], str) or record[key] in ("", UNSET):
            errors.append(f"{key} must be a non-empty string")
    if not RUN_ID_PATTERN.match(str(record["run_id"])):
        errors.append("run_id must match r02-smoke-<three digits>")
    authorization = record["authorization"]
    for key in ("granted", "scope", "reference", "approved_by", "approved_at_utc"):
        if key not in authorization:
            errors.append(f"authorization is missing {key!r}")
    if authorization.get("scope") != SCOPE_READINESS_SMOKE:
        errors.append("authorization scope must be the readiness-smoke scope")
    if record["exit_status"] not in (STATUS_OK, STATUS_FAILED):
        errors.append("exit_status must be 'ok' or 'failed'")
    failure = record["failure"]
    if record["exit_status"] == STATUS_FAILED and failure.get("kind", UNSET) == UNSET:
        errors.append("a failed record must name a failure kind")
    if record["exit_status"] == STATUS_OK and failure.get("kind", UNSET) != UNSET:
        errors.append("a successful record must not name a failure kind")
    resources = record["resources"]
    if not is_unset(resources):
        if not isinstance(resources, Mapping) or resources.get("kind") != RESOURCE_SAMPLING_KIND:
            errors.append(f"resources must be UNSET or a {RESOURCE_SAMPLING_KIND} record")
    generation = record["generation"]
    for key in ("output_text", "output_token_ids"):
        if key in generation:
            errors.append(f"the record must not carry {key}")
    digest = generation["output_text_sha256"]
    if not is_unset(digest) and (not isinstance(digest, str) or len(digest) != 64):
        errors.append("output_text_sha256 must be UNSET or a SHA-256 digest")
    return errors


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Load the pinned model, run one inference, and record a manifest. "
            "Runs only under an approval record; --dry-run checks the gate and stops."
        )
    )
    parser.add_argument("--run-id", required=True, help="r02-smoke-<three digits>")
    parser.add_argument("--owner", required=True, help="the agent or operator that owns the run")
    parser.add_argument("--run-dir", default=None, help="must end with results/R02/<run-id>")
    parser.add_argument("--authorization-file", required=True)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--prompt", default=DEFAULT_PROMPT)
    parser.add_argument("--max-new-tokens", type=int, default=8)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--wall-clock-cap-seconds", type=int, default=1200)
    parser.add_argument("--no-wall-clock-guard", action="store_true",
                        help="detection only: do not arm the SIGALRM guard")
    parser.add_argument("--cache-state", choices=("cold", "warm"), default=UNSET)
    parser.add_argument("--artifact-manifest", default=UNSET)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="check the gate and print the plan; imports nothing",
    )
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    sampler_factory: Callable[[], ResourceSampler] | None = None,
    access_factory: Callable[[], ModelAccess] | None = None,
) -> int:
    """CLI entry point. The two factories are test seams and default to production."""
    args = build_parser().parse_args(argv)

    try:
        authorization = Authorization.from_file(args.authorization_file)
        require_authorization(authorization, scope=SCOPE_READINESS_SMOKE)
    except GateClosed as exc:
        sys.stderr.write(f"gate closed: {redact_secrets(exc)}\n")
        return EXIT_GATE_CLOSED

    problems = validate_run_target(run_id=args.run_id, run_dir=args.run_dir)
    if problems:
        for problem in problems:
            sys.stderr.write(f"run target rejected: {problem}\n")
        return EXIT_GATE_CLOSED

    plan = SmokePlan(
        run_id=args.run_id,
        owner=args.owner,
        device=args.device,
        prompt=args.prompt,
        max_new_tokens=args.max_new_tokens,
        seed=args.seed,
        wall_clock_cap_seconds=args.wall_clock_cap_seconds,
        cache_state=args.cache_state,
        artifact_manifest_path=args.artifact_manifest,
    )

    if args.dry_run:
        sys.stdout.write(
            json.dumps(
                {
                    "dry_run": True,
                    "authorization": authorization.to_record(),
                    "plan": plan.to_record(),
                    "would_import": [
                        "torch.cuda.reset_peak_memory_stats",
                        "transformers.AutoTokenizer",
                        "transformers.AutoModelForCausalLM",
                        "torch",
                    ],
                    "would_touch_gpu": plan.device,
                    "wall_clock_cap": {
                        "seconds": plan.wall_clock_cap_seconds,
                        "enforcement": (
                            CAP_ENFORCEMENT_DETECTION
                            if args.no_wall_clock_guard
                            else CAP_ENFORCEMENT_ARMED
                        ),
                    },
                    "run_dir": args.run_dir,
                    "note": "no model library imported, no GPU call made, nothing written",
                },
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )
        return EXIT_OK

    runner = ReadinessSmoke(
        authorization=authorization,
        plan=plan,
        access=access_factory() if access_factory is not None else None,
        sampler=sampler_factory() if sampler_factory is not None else None,
        enforce_wall_clock_cap=not args.no_wall_clock_guard,
    )
    try:
        record = runner.run()
    except Exception as exc:  # nothing leaves main without a record
        record = runner.failure_record(stage="unexpected", error=exc, sampler=runner.sampler)

    if args.run_dir:
        write_run_artifacts(args.run_dir, record)

    sys.stdout.write(json.dumps(record, indent=2, sort_keys=True) + "\n")
    return EXIT_OK if record["exit_status"] == STATUS_OK else EXIT_STEP_FAILED


if __name__ == "__main__":
    raise SystemExit(main())
