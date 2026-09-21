#!/usr/bin/env python3
"""R02.1 approval-gated model load and readiness smoke.

Issue https://durandal.exe.xyz/smolmodelco/thesmolmodelcompany/issues/17.

The recipe asks for one thing and one thing only: load the pinned model, run one
inference, terminate cleanly, and record a manifest. This module is that
procedure, and it is gated three ways:

1. **Authorization.** ``run_readiness_smoke`` calls
   ``require_authorization`` as its first statement. Without a matching grant it
   raises ``GateClosed`` before constructing the deferred access layer, before
   importing ``torch`` or ``transformers``, and before any CUDA call. The
   failure path is the import-free path, and the tests assert that.
2. **Injected access.** Every touch of a model library or the GPU goes through
   ``ModelAccess`` callables, so tests exercise the whole flow with pure fakes
   and never load or reserve anything.
3. **One attempt.** The first failure is recorded and returned; nothing is
   retried. A diagnosed retry is a new run ID that links to this one.

Usage, from the repository root:

    python3 scripts/r02_smoke.py --run-id r02-smoke-001 --run-dir DIR \\
        --authorization-file FILE [--dry-run]

``--dry-run`` validates the gate and the plan and prints what would run, without
importing a model library or touching the GPU.

Exit codes: 0 completed, 1 a step failed, 2 the gate is closed.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

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
    from r02_resources import ResourceSampler, torch_peak_probe
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
    from scripts.r02_resources import ResourceSampler, torch_peak_probe

KIND = "r02-readiness-smoke"
OWNER = "eido"

STATUS_OK = "ok"
STATUS_FAILED = "failed"

DEFAULT_PROMPT = "The capital of France is"

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


@dataclass(frozen=True)
class SmokePlan:
    """Everything frozen before the run; no field is chosen at run time."""

    run_id: str
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
        torch.cuda.reset_peak_memory_stats()
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
        load_tokenizer=load_tokenizer,
        load_model=load_model,
        describe_device=describe_device,
        generate=generate,
    )


class ReadinessSmoke:
    """Ordered procedure: gate, sample, load, infer, sample, record."""

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
        self.record: dict[str, Any] | None = None

    def run(self) -> dict[str, Any]:
        access = self.access if self.access is not None else deferred_access()
        sampler = self.sampler if self.sampler is not None else ResourceSampler(clock=self.clock)

        started_at = self.clock()
        pre = [sample.to_record() for sample in sampler.sample_once()]
        stage = "tokenizer-load"
        try:
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
            post = [sample.to_record() for sample in sampler.samples]
            self.record = self._failure_record(
                stage=stage,
                error=exc,
                started_at=started_at,
                partial_samples=pre,
                samples=post,
            )
            return self.record

        try:
            post = [sample.to_record() for sample in sampler.sample_once()]
        except Exception as exc:  # a failed sampling instant is a failed run, not a silent gap
            self.record = self._failure_record(
                stage="resource-sample",
                error=exc,
                started_at=started_at,
                partial_samples=pre,
                samples=[sample.to_record() for sample in sampler.samples],
            )
            return self.record
        timing = {
            "cold_load_seconds": _seconds_between(started_at, model_loaded_at),
            "tokenizer_load_seconds": _seconds_between(started_at, tokenizer_loaded_at),
            "warm_inference_seconds": _seconds_between(inference_started_at, inference_finished_at),
            "wall_clock_seconds": _seconds_between(started_at, self.clock()),
        }
        resources = sampler.summary(interval_seconds=self.resource_interval_seconds)
        readiness = self._readiness(generation, device)
        failure: dict[str, Any] = {"stage": UNSET, "kind": UNSET, "message": UNSET}

        if timing["wall_clock_seconds"] > self.plan.wall_clock_cap_seconds:
            failure = {
                "stage": "wall-clock",
                "kind": "wall-clock-cap-exceeded",
                "message": (
                    f"wall clock {timing['wall_clock_seconds']:.1f}s exceeded the "
                    f"{self.plan.wall_clock_cap_seconds}s cap; the measurements above are retained"
                ),
            }
        elif not readiness["readiness_ok"]:
            failure = {
                "stage": "readiness",
                "kind": "readiness-check-failed",
                "message": "; ".join(readiness["failed_checks"]),
            }

        self.record = {
            "kind": KIND,
            "run_id": self.plan.run_id,
            "owner": OWNER,
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
            "generation": {
                # The manifest is committed to Git, so it carries identity, not output:
                # a digest and a token count, never the generated text or the token IDs.
                "output_text_sha256": _sha256_text(str(generation.get("output_text", ""))),
                "output_token_count": len(generation.get("output_token_ids", [])),
                "first_output_token_id": (generation.get("output_token_ids") or [UNSET])[0],
                "logits_all_finite": generation.get("logits_all_finite", UNSET),
                "stop_reason": generation.get("stop_reason", UNSET),
            },
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

    def _failure_record(
        self,
        *,
        stage: str,
        error: BaseException,
        started_at: str,
        partial_samples: Sequence[Mapping[str, Any]],
        samples: Sequence[Mapping[str, Any]],
    ) -> dict[str, Any]:
        return {
            "kind": KIND,
            "run_id": self.plan.run_id,
            "owner": OWNER,
            "authorization": self.authorization.to_record(),
            "model": {
                "repo_id": self.plan.repo_id,
                "revision": self.plan.revision,
                "precision": self.plan.precision,
                "device": self.plan.device,
                "device_reported": UNSET,
            },
            "plan": self.plan.to_record(),
            "timing": {"cold_load_seconds": UNSET, "warm_inference_seconds": UNSET},
            "tokenizer": {"input_token_count": UNSET, "vocab_size": UNSET},
            "generation": {
                "output_text_sha256": UNSET,
                "output_token_count": UNSET,
                "first_output_token_id": UNSET,
                "logits_all_finite": UNSET,
                "stop_reason": UNSET,
            },
            "resources": UNSET,
            "samples_pre": list(partial_samples),
            "samples_post": list(samples),
            "started_at_utc": started_at,
            "finished_at_utc": self.clock(),
            "exit_status": STATUS_FAILED,
            "retried": False,
            "failure": {
                "stage": stage,
                "kind": type(error).__name__,
                "message": redact_secrets(error),
            },
        }


def _seconds_between(start: str, end: str) -> float:
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
    authorization = record["authorization"]
    for key in ("granted", "scope", "reference", "approved_by", "approved_at_utc"):
        if key not in authorization:
            errors.append(f"authorization is missing {key!r}")
    if authorization.get("scope") != SCOPE_READINESS_SMOKE:
        errors.append("authorization scope must be the readiness-smoke scope")
    if record["exit_status"] not in (STATUS_OK, STATUS_FAILED):
        errors.append("exit_status must be 'ok' or 'failed'")
    if record["exit_status"] == STATUS_FAILED and record["failure"]["kind"] == UNSET:
        errors.append("a failed record must name a failure kind")
    generation = record["generation"]
    digest = generation["output_text_sha256"]
    if not is_unset(digest) and (not isinstance(digest, str) or len(digest) != 64):
        errors.append("output_text_sha256 must be UNSET or a SHA-256 digest")
    if "output_text" in generation:
        errors.append("the record must not carry raw generated text")
    return errors


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Load the pinned model, run one inference, and record a manifest. "
            "Runs only under an approval record; --dry-run checks the gate and stops."
        )
    )
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-dir", default=None, help="directory for manifest.json and samples")
    parser.add_argument("--authorization-file", required=True)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--prompt", default=DEFAULT_PROMPT)
    parser.add_argument("--max-new-tokens", type=int, default=8)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--wall-clock-cap-seconds", type=int, default=1200)
    parser.add_argument("--cache-state", choices=("cold", "warm"), default=UNSET)
    parser.add_argument("--artifact-manifest", default=UNSET)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="check the gate and print the plan; imports nothing",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        authorization = Authorization.from_file(args.authorization_file)
        require_authorization(authorization, scope=SCOPE_READINESS_SMOKE)
    except GateClosed as exc:
        sys.stderr.write(f"gate closed: {redact_secrets(exc)}\n")
        return EXIT_GATE_CLOSED

    plan = SmokePlan(
        run_id=args.run_id,
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
                    "would_import": ["transformers.AutoTokenizer", "transformers.AutoModelForCausalLM", "torch"],
                    "would_touch_gpu": plan.device,
                    "note": "no model library imported, no GPU call made, nothing written",
                },
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )
        return EXIT_OK

    record = ReadinessSmoke(authorization=authorization, plan=plan).run()

    if args.run_dir:
        run_dir = Path(args.run_dir)
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "manifest.json").write_text(
            json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        (run_dir / "resource-samples.json").write_text(
            json.dumps(record.get("resources", UNSET), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    sys.stdout.write(json.dumps(record, indent=2, sort_keys=True) + "\n")
    return EXIT_OK if record["exit_status"] == STATUS_OK else EXIT_STEP_FAILED


if __name__ == "__main__":
    raise SystemExit(main())
