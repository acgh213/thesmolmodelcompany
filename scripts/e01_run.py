#!/usr/bin/env python3
"""E01 execution runner: one authorized, gated, single-attempt pass.

Issues https://durandal.exe.xyz/smolmodelco/thesmolmodelcompany/issues/24 and .../21.

This is the seam between the frozen protocol ``e01-records-v1`` and the operator
authorization for exactly one run, ``e01-pilot-001``. It is deliberately thin: it
renders the frozen prompt, invokes the pinned model once per manifest row, hands
the raw predictions to the independent scorer, and writes the evidence package.

Boundaries this module holds:

* **The gate is first.** ``E01Run.__init__`` calls ``require_e01_authorization``
  before anything else, so an ungated invocation raises before the deferred access
  layer is constructed, before ``torch`` or ``transformers`` is imported, and
  before any CUDA call.
* **The frozen prompt is bound, not just cited.** After the manifest is generated
  and before the preflight or any load, the runner re-renders the whole prompt set
  and compares its digest with ``plan.artifacts.prompt_sha256``. A drifted renderer
  stops the run while nothing has been loaded, because a recorded digest that is
  never recomputed is a label rather than a binding.
* **The preflight runs before the model.** Candidate and reference files are
  generated from the frozen protocol and then checked by ``e01_preflight``, which
  verifies the gate, the run target, the pinned identity, the freeze state and
  both frozen input digests. A non-zero preflight stops the run with nothing
  loaded.
* **Injected access.** Every touch of a model library or the GPU goes through
  ``ModelAccess`` callables, so tests exercise the whole flow with pure fakes and
  never load or reserve anything.
* **One attempt.** One deterministic generation per row, ``do_sample=false``, no
  retries. The first failure is recorded and returned; nothing is retried.
* **The prompt is not chosen here.** It comes from ``e01_prompt`` at the frozen
  revision ``e01-prompt-v1``; this module only calls it.
* **Raw output stays out of Git.** Predictions are written under
  ``<run-dir>/predictions/`` and inputs under ``<run-dir>/inputs/``, both
  git-ignored. Only the manifest, report, aggregate, error summary and resource
  record are committed, and none of them contains a prediction or a reference
  answer.

``do_sample=False`` is greedy decoding, so ``temperature`` and ``top_p`` are inert
and are not passed; the record states that rather than echoing a value the
sampler ignores.

The per-episode wall-clock cap is armed with ``SIGALRM`` when the platform allows
it, and the record labels which behaviour applied. A process killed from outside
writes nothing and is recorded by whoever killed it.

Usage, from the repository root:

    python3 scripts/e01_run.py --run-id e01-pilot-001 --owner eido \
        --plan configs/e01-execution-plan.json \
        --protocol configs/e01-protocol.json \
        --r02-record results/R02/r02-smoke-001 \
        --run-dir results/E01/e01-pilot-001 \
        --authorization-file FILE

Exit codes: 0 the run completed, 1 a step failed (the failure is recorded),
2 the gate is closed or the run target is off the layout.
"""

from __future__ import annotations

import argparse
import contextlib
import datetime as _dt
import hashlib
import io
import json
import signal
import subprocess
import sys
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping, Sequence

try:  # bare script (sys.path[0] is scripts/) or scripts/ already on sys.path
    from e01_gate import (
        GateClosed,
        OperatorRecord,
        expected_run_dir,
        require_e01_authorization,
        validate_run_target,
    )
    from e01_identity import PinError, load_pin, load_plan
    from e01_prompt import (
        INSTRUCTION,
        OUTPUT_HEADER,
        PROMPT_FIELDS,
        PROMPT_RENDERER_REVISION,
        TASK_HEADER,
        instruction_sha256,
        payloads_from_manifest,
        prompt_set_sha256,
        prompt_sha256,
        render_prompt,
    )
    from e01_records import GENERATOR_REVISION, _write_jsonl, build as build_episodes
    from e01_score import SCORER_REVISION, score as score_predictions
    from r02_gate import EXIT_GATE_CLOSED, EXIT_OK, EXIT_STEP_FAILED, is_unset, redact_secrets
    from r02_preflight import UNSET
    from r02_resources import ResourceSampler, torch_peak_probe
except ModuleNotFoundError:  # imported as scripts.<module> from the repository root
    from scripts.e01_gate import (
        GateClosed,
        OperatorRecord,
        expected_run_dir,
        require_e01_authorization,
        validate_run_target,
    )
    from scripts.e01_identity import PinError, load_pin, load_plan
    from scripts.e01_prompt import (
        INSTRUCTION,
        OUTPUT_HEADER,
        PROMPT_FIELDS,
        PROMPT_RENDERER_REVISION,
        TASK_HEADER,
        instruction_sha256,
        payloads_from_manifest,
        prompt_set_sha256,
        prompt_sha256,
        render_prompt,
    )
    from scripts.e01_records import GENERATOR_REVISION, _write_jsonl, build as build_episodes
    from scripts.e01_score import SCORER_REVISION, score as score_predictions
    from scripts.r02_gate import (
        EXIT_GATE_CLOSED,
        EXIT_OK,
        EXIT_STEP_FAILED,
        is_unset,
        redact_secrets,
    )
    from scripts.r02_preflight import UNSET
    from scripts.r02_resources import ResourceSampler, torch_peak_probe

RUNNER_REVISION = "e01-runner-v1"

KIND_RUN = "e01-run"
KIND_FAILURE = "e01-run-failure"

EXPERIMENT_ID = "E01"

PREDICTIONS_DIRNAME = "predictions"
INPUTS_DIRNAME = "inputs"
PREDICTIONS_FILENAME = "predictions.jsonl"
EPISODE_MANIFEST_FILENAME = "episode-manifest.jsonl"
REFERENCE_ANSWERS_FILENAME = "reference-answers.jsonl"
EPISODE_METADATA_FILENAME = "episode-metadata.jsonl"

ATTEMPTS_PER_EPISODE = 1

CAP_ARMED = "sigalrm armed: the cap raises inside the interpreter and aborts the episode"
CAP_NOT_ARMED = "not armed: the observed episode duration is recorded after the call returns"

NOT_ESTABLISHED = (
    "one condition only: no baseline, ablation or matched-compute comparison ran",
    "no transfer, broad-reasoning or assistant-capability claim follows from this run",
    "the final split was not inspected before the run and is not reusable for tuning",
)


def _utc_now() -> str:
    return _dt.datetime.now(tz=_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _seconds_between(start: str, end: str) -> float:
    first = _dt.datetime.strptime(start, "%Y-%m-%dT%H:%M:%SZ")
    second = _dt.datetime.strptime(end, "%Y-%m-%dT%H:%M:%SZ")
    return (second - first).total_seconds()


def _sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def git_commit() -> str:
    """The commit being executed, or ``UNSET`` when git cannot answer."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return UNSET
    value = (result.stdout or "").strip()
    return value or UNSET


class RunStopped(RuntimeError):
    """A declared stop condition fired. The run is preserved, never retried."""

    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind = kind


class EpisodeTimeout(RunStopped):
    """One episode exceeded the declared cap."""

    def __init__(self, message: str) -> None:
        super().__init__("episode-timeout", message)


@contextmanager
def episode_time_guard(seconds: int, *, arm: bool = True) -> Iterator[str]:
    """Abort one episode at the declared cap when the platform allows it.

    Yields the label the record carries, so the manifest states which behaviour
    actually applied rather than which was intended.
    """
    armable = hasattr(signal, "SIGALRM") and threading.current_thread() is threading.main_thread()
    if not arm or not armable:
        yield CAP_NOT_ARMED
        return

    def _raise(signum: int, frame: Any) -> None:
        raise EpisodeTimeout(f"episode exceeded the declared cap of {seconds}s")

    previous = signal.signal(signal.SIGALRM, _raise)
    signal.alarm(int(seconds))
    try:
        yield CAP_ARMED
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)


@dataclass(frozen=True)
class RunPlan:
    """Everything the runner needs, taken from the frozen plan and the CLI."""

    run_id: str
    owner: str
    repo_id: str
    revision: str
    precision: str
    device: str
    max_new_tokens: int
    run_dir: str
    plan_path: str
    protocol_path: str
    r02_record: str
    authorization_file: str
    episode_time_cap_seconds: int
    code_commit: str = UNSET
    # Defaults to scoring rather than stopping: the frozen protocol's error
    # classes are the more specific instrument, and a stopped run cannot reach
    # them. The plan sets this explicitly; see configs/e01-protocol.md, erratum.
    stop_on_malformed_output: bool = False

    def to_record(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "owner": self.owner,
            "repo_id": self.repo_id,
            "revision": self.revision,
            "precision": self.precision,
            "device": self.device,
            "max_new_tokens": self.max_new_tokens,
            "run_dir": str(self.run_dir).replace("\\", "/"),
            "plan_path": self.plan_path,
            "protocol_path": self.protocol_path,
            "r02_record": self.r02_record,
            "episode_time_cap_seconds": self.episode_time_cap_seconds,
            "code_commit": self.code_commit,
            "stop_on_malformed_output": self.stop_on_malformed_output,
        }


@dataclass(frozen=True)
class ModelAccess:
    """The only code permitted to import a model library or touch the GPU."""

    reset_peak_counters: Callable[[RunPlan], None]
    load_tokenizer: Callable[[RunPlan], Any]
    load_model: Callable[[RunPlan, Any], Any]
    describe_device: Callable[[RunPlan], Mapping[str, Any]]
    generate: Callable[[RunPlan, Any, Any, str], Mapping[str, Any]]


def deferred_access() -> ModelAccess:
    """Default access whose imports happen inside the callables.

    Importing this module, or calling this factory, imports neither ``torch`` nor
    ``transformers``: those imports live inside the function bodies, so an
    ungated invocation cannot reach them.
    """

    def reset_peak_counters(plan: RunPlan) -> None:
        import torch  # noqa: PLC0415 - deferred behind the gate

        torch.cuda.reset_peak_memory_stats()

    def load_tokenizer(plan: RunPlan) -> Any:
        from transformers import AutoTokenizer  # noqa: PLC0415 - deferred behind the gate

        return AutoTokenizer.from_pretrained(plan.repo_id, revision=plan.revision)

    def load_model(plan: RunPlan, tokenizer: Any) -> Any:
        import torch  # noqa: PLC0415 - deferred behind the gate
        from transformers import AutoModelForCausalLM  # noqa: PLC0415

        dtype = getattr(torch, plan.precision, torch.bfloat16)
        model = AutoModelForCausalLM.from_pretrained(
            plan.repo_id, revision=plan.revision, dtype=dtype
        )
        return model.to(plan.device).eval()

    def describe_device(plan: RunPlan) -> Mapping[str, Any]:
        import torch  # noqa: PLC0415 - deferred behind the gate
        import transformers  # noqa: PLC0415 - deferred behind the gate

        return {
            "device": plan.device,
            "device_name": torch.cuda.get_device_name(0),
            "cuda_available": torch.cuda.is_available(),
            # docs/coordination.md requires environment identity in the manifest,
            # and the deferred model path passes a version-dependent ``dtype=``.
            "library_versions": {
                "torch": getattr(torch, "__version__", UNSET),
                "transformers": getattr(transformers, "__version__", UNSET),
            },
        }

    def generate(plan: RunPlan, model: Any, tokenizer: Any, prompt: str) -> Mapping[str, Any]:
        import torch  # noqa: PLC0415 - deferred behind the gate

        inputs = tokenizer(prompt, return_tensors="pt").to(plan.device)
        with torch.no_grad():
            output = model.generate(**inputs, max_new_tokens=plan.max_new_tokens, do_sample=False)
        generated_ids = output[0][inputs["input_ids"].shape[-1] :]
        return {
            "text": tokenizer.decode(generated_ids, skip_special_tokens=True),
            "input_token_count": int(inputs["input_ids"].shape[-1]),
            "output_token_count": int(generated_ids.shape[-1]),
        }

    return ModelAccess(
        reset_peak_counters=reset_peak_counters,
        load_tokenizer=load_tokenizer,
        load_model=load_model,
        describe_device=describe_device,
        generate=generate,
    )


def write_run_manifest(run_dir: str | Path, record: Mapping[str, Any]) -> None:
    """Write the manifest for a failed run exactly as for a successful one."""
    target = Path(run_dir)
    target.mkdir(parents=True, exist_ok=True)
    (target / "manifest.json").write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    resources = record.get("resources")
    if isinstance(resources, Mapping):
        (target / "resource-samples.json").write_text(
            json.dumps(resources, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )


def _yaml_value(value: Any) -> str:
    text = str(value).replace("\n", " ").replace('"', "'").replace("|", "/")
    return f'"{text}"'


def render_report(record: Mapping[str, Any]) -> str:
    """The run report, with the front matter the results ledger is built from."""
    scoring = record.get("scoring") or {}
    splits = scoring.get("split_aggregates") or {}
    development = splits.get("development") or {}
    final = splits.get("final") or {}
    resources = record.get("resources") or {}
    peaks = resources.get("peak_claims") or {}
    vram = peaks.get("vram_peak_reserved_mib") or {}
    vram_value = vram.get("value", UNSET) if isinstance(vram, Mapping) else UNSET

    wall = record.get("wall_clock_seconds", UNSET)
    quality = (
        f"development {development.get('correct', UNSET)}/{development.get('total', UNSET)}, "
        f"final {final.get('correct', UNSET)}/{final.get('total', UNSET)} exact match "
        f"({scoring.get('correct', UNSET)}/{scoring.get('total', UNSET)} overall)"
    )
    resource_cost = f"{wall} s wall, peak {vram_value} MiB VRAM reserved, $0"
    candidate = "condition D - " + str(record.get("condition", UNSET))

    front_matter = "\n".join(
        [
            "---",
            f"experiment: {record['experiment']}",
            f"run_id: {record['run_id']}",
            f"candidate: {_yaml_value(candidate)}",
            f"baseline: {_yaml_value('none - single condition, baseline matrix deferred')}",
            f"split_axis: {_yaml_value('unseen composition; development versus final seeds')}",
            f"quality: {_yaml_value(quality)}",
            f"resource_cost: {_yaml_value(resource_cost)}",
            f"status: {_yaml_value(record.get('status', UNSET))}",
            f"claim_level: {_yaml_value(record.get('claim_tier', UNSET))}",
            f"evidence: {_yaml_value(str(record.get('run_dir', UNSET)) + '/manifest.json')}",
            f"date: {str(record.get('finished_at_utc', UNSET))[:10]}",
            "---",
        ]
    )

    lines = [
        front_matter,
        "",
        f"# E01 run {record['run_id']}",
        "",
        "## 1. Identity and claim level",
        "",
        f"- Experiment/run: `{record['experiment']}` / `{record['run_id']}`",
        f"- Frozen protocol: `{record.get('protocol_version', UNSET)}`; "
        f"condition: `{record.get('condition', UNSET)}`",
        f"- Claim tier: **{record.get('claim_tier', UNSET)}**",
        f"- Owner: `{record.get('owner', UNSET)}`; one attempt, no retry",
        f"- Runner revision: `{record.get('runner_revision', UNSET)}`; "
        f"prompt renderer: `{record.get('prompt_renderer_revision', UNSET)}`",
        f"- Started/finished (UTC): `{record.get('started_at_utc')}` / "
        f"`{record.get('finished_at_utc')}`",
        f"- Code commit: `{record.get('code_commit', UNSET)}`; manifest: `manifest.json`",
        "",
        "## 2. Outcome",
        "",
        quality,
        "",
        f"Per-episode error classes: `{record.get('episode_errors_path', UNSET)}`.",
        "This is a bounded development signal for one explicitly supplied structured",
        "representation, on one model revision, with no comparator condition.",
        "",
        "## 3. Baselines and ablations",
        "",
        "None ran. This protocol has a single condition, and the baseline matrix in",
        "`docs/evaluation.md` is deferred, so no paired effect can be reported.",
        "",
        "## 4. Failures",
        "",
        json.dumps(record.get("failure", {}), indent=2, sort_keys=True),
        "",
        "## 5. Resources",
        "",
        f"- Wall clock: `{wall}` s, against a declared per-episode cap of "
        f"`{record.get('episode_time_cap_seconds', UNSET)}` s",
        f"- Peak VRAM reserved: `{vram_value}` MiB; sampling record: `resource-samples.json`",
        f"- Sampling status: `{resources.get('status', UNSET)}`",
        "- Billed cost: none (local GPU, no external service)",
        "",
        "## 6. Evidence",
        "",
        f"- Run manifest: `{record.get('run_dir', UNSET)}/manifest.json`",
        f"- Aggregate: `{record.get('aggregate_path', UNSET)}`",
        f"- Per-episode error classes: `{record.get('episode_errors_path', UNSET)}`",
        "- Raw predictions: not committed, deliberately (git-ignored run storage)",
        "- Episodes and reference answers: regenerated from the frozen protocol; "
        "only hashes are committed",
        "",
        "## 7. Interpretation",
        "",
    ]
    lines.extend(f"- Not established: {item}" for item in record.get("not_established", []))
    lines.extend(
        [
            "",
            "## 8. Reproduction",
            "",
            "Not independently reproduced. This is a single authorized attempt and is",
            "explicitly labeled unreplicated; a reproduction must rebuild the software",
            "environment and re-derive artifacts from the manifest rather than reuse them.",
            "",
            "## 9. Decision",
            "",
            str(record.get("decision", UNSET)),
            "",
        ]
    )
    return "\n".join(lines)


class E01Run:
    """Ordered procedure: gate, generate inputs, preflight, load, one pass, score, record."""

    def __init__(
        self,
        *,
        authorization: OperatorRecord | None,
        plan: RunPlan,
        access: ModelAccess | None = None,
        sampler: ResourceSampler | None = None,
        peak_probe_factory: Callable[[], Any] | None = None,
        clock: Callable[[], str] = _utc_now,
        preflight_runner: Callable[[Sequence[str]], int] | None = None,
        protocol: Mapping[str, Any] | None = None,
    ) -> None:
        self.authorization = require_e01_authorization(  # fail closed before anything else
            authorization, run_id=plan.run_id
        )
        self.plan = plan
        self.access = access
        self.sampler = sampler
        self.peak_probe_factory = peak_probe_factory or torch_peak_probe
        self.clock = clock
        self.preflight_runner = preflight_runner
        self.protocol = dict(protocol or {})
        self._prompt_binding: dict[str, Any] = {
            "prompt_sha256": UNSET,
            "prompt_sha256_recomputed": UNSET,
            "instruction_sha256": UNSET,
        }
        self.record: dict[str, Any] | None = None

    # ---- inputs and protocol checks -----------------------------------------

    def _seed_sets(self) -> dict[str, list[int]]:
        task = self.protocol.get("task")
        if not isinstance(task, Mapping):
            raise RunStopped("protocol-mismatch", "protocol carries no 'task' object")
        return {
            "development": list(task["development_seeds"]),
            "final": list(task["final_seeds"]),
        }

    def _assert_protocol_matches_plan(self, plan_doc: Mapping[str, Any]) -> None:
        """The plan's frozen revisions must match the protocol being executed."""
        artifacts = plan_doc.get("artifacts") or {}
        expected = {
            "generator_revision": GENERATOR_REVISION,
            "scorer_revision": SCORER_REVISION,
            "prompt_renderer_revision": PROMPT_RENDERER_REVISION,
            "runner_revision": RUNNER_REVISION,
        }
        for field, wanted in expected.items():
            if wanted is None:
                continue
            if artifacts.get(field) != wanted:
                raise RunStopped(
                    "protocol-mismatch",
                    f"plan {field} {artifacts.get(field)!r} does not match {wanted!r}",
                )
        decoding = self.protocol.get("decoding") or {}
        if decoding.get("do_sample") is not False:
            raise RunStopped("protocol-mismatch", "protocol does not declare do_sample=false")
        if decoding.get("max_new_tokens") != self.plan.max_new_tokens:
            raise RunStopped(
                "protocol-mismatch",
                f"plan max_new_tokens {self.plan.max_new_tokens} does not match the "
                f"protocol's {decoding.get('max_new_tokens')!r}",
            )
        if int(decoding.get("retries", 0)) != 0:
            raise RunStopped("protocol-mismatch", "protocol does not declare zero retries")

    def _generate_inputs(self, run_dir: Path) -> dict[str, Any]:
        """Freeze the candidate and reference files before any model is loaded."""
        inputs_dir = run_dir / INPUTS_DIRNAME
        task = self.protocol["task"]
        candidates, references, metadata = build_episodes(
            self._seed_sets(), int(task["record_count"])
        )
        paths = {
            "episode_manifest": inputs_dir / EPISODE_MANIFEST_FILENAME,
            "reference_answers": inputs_dir / REFERENCE_ANSWERS_FILENAME,
            "episode_metadata": inputs_dir / EPISODE_METADATA_FILENAME,
        }
        _write_jsonl(paths["episode_manifest"], candidates)
        _write_jsonl(paths["reference_answers"], references)
        _write_jsonl(paths["episode_metadata"], metadata)
        return {
            name: {
                "path": str(path).replace("\\", "/"),
                "sha256": _sha256_file(path),
                "bytes": path.stat().st_size,
            }
            for name, path in paths.items()
        }

    def _verify_prompt_binding(
        self, manifest_rows: Sequence[Mapping[str, Any]], plan_doc: Mapping[str, Any]
    ) -> str:
        """Bind the frozen prompt-set digest to the prompts this run will render.

        Recomputing here is the difference between a label and a binding. A plan
        that records a digest without comparing it still passes every other check
        when the renderer drifts, because ``prompt_renderer_revision`` is a string
        that a drift leaves alone. This runs after the manifest is generated and
        before the preflight and before any load, so a drifted renderer stops the
        run while nothing has been loaded or scored.
        """
        expected = (plan_doc.get("artifacts") or {}).get("prompt_sha256")
        recomputed = prompt_set_sha256(payloads_from_manifest(manifest_rows))
        self._prompt_binding = {
            "prompt_sha256": expected if isinstance(expected, str) else UNSET,
            "prompt_sha256_recomputed": recomputed,
            "instruction_sha256": instruction_sha256(),
        }
        if is_unset(expected) or not isinstance(expected, str):
            raise RunStopped("protocol-mismatch", "the execution plan freezes no prompt hash")
        if recomputed != expected:
            raise RunStopped(
                "protocol-mismatch",
                f"the rendered prompt set digests to {recomputed}, but the plan freezes "
                f"{expected}: the renderer has drifted from the frozen prompt",
            )
        return recomputed

    def _invoke_preflight(self, inputs: Mapping[str, Any]) -> dict[str, Any]:
        argv = [
            "--run-id", self.plan.run_id,
            "--owner", self.plan.owner,
            "--plan", self.plan.plan_path,
            "--r02-record", self.plan.r02_record,
            "--run-dir", str(self.plan.run_dir).replace("\\", "/"),
            "--authorization-file", self.plan.authorization_file,
            "--episode-manifest", inputs["episode_manifest"]["path"],
            "--reference-answers", inputs["reference_answers"]["path"],
        ]
        runner = self.preflight_runner
        captured = io.StringIO()
        if runner is None:
            from e01_preflight import main as runner  # noqa: PLC0415 - local import keeps the seam injectable
        with contextlib.redirect_stdout(captured):
            code = int(runner(argv))
        try:
            record: Any = json.loads(captured.getvalue())
        except json.JSONDecodeError:
            record = {"unparsed_preflight_stdout": captured.getvalue()}
        if code != EXIT_OK:
            raise RunStopped(
                "preflight-failed",
                f"preflight exited {code}; the run stops before any model load",
            )
        return {"exit_code": code, "record": record}

    # ---- output contract -----------------------------------------------------

    def _check_output_contract(self, text: Any, *, episode_id: str) -> None:
        """The protocol's output contract: one JSON array and nothing else."""
        if not isinstance(text, str) or not text.strip():
            raise RunStopped("missing-output", f"episode {episode_id} produced no output")
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            parsed, detail = None, exc.msg
        else:
            detail = "not a JSON array"
        if parsed is None or not isinstance(parsed, list):
            if not self.plan.stop_on_malformed_output:
                return
            raise RunStopped(
                "malformed-output",
                f"episode {episode_id} broke the output contract ({detail}); the protocol's "
                "stop conditions stop the run here rather than continue",
            )

    # ---- records -------------------------------------------------------------

    def _frozen_block(self, inputs: Mapping[str, Any]) -> dict[str, Any]:
        """The digests this run is bound to, recorded for a failed run as well."""
        return {
            "prompt_renderer_revision": PROMPT_RENDERER_REVISION,
            "prompt_sha256": self._prompt_binding.get("prompt_sha256", UNSET),
            "prompt_sha256_recomputed": self._prompt_binding.get("prompt_sha256_recomputed", UNSET),
            "instruction_sha256": self._prompt_binding.get("instruction_sha256", UNSET),
            "episode_manifest_sha256": (inputs.get("episode_manifest") or {}).get("sha256", UNSET),
            "reference_answers_sha256": (inputs.get("reference_answers") or {}).get("sha256", UNSET),
        }

    def _frozen_prompt_block(self) -> dict[str, Any]:
        """The prompt itself, so a record states the condition rather than citing it."""
        return {
            "instruction": INSTRUCTION,
            "instruction_sha256": instruction_sha256(),
            "task_header": TASK_HEADER,
            "output_header": OUTPUT_HEADER,
            "prompt_fields": list(PROMPT_FIELDS),
        }

    def _base_record(
        self, *, started_at: str, inputs: Mapping[str, Any] | None = None
    ) -> dict[str, Any]:
        return {
            "experiment": EXPERIMENT_ID,
            "run_id": self.plan.run_id,
            "owner": self.plan.owner,
            "run_dir": str(self.plan.run_dir).replace("\\", "/"),
            "protocol_version": self.protocol.get("protocol_version", UNSET),
            "condition": self.protocol.get("condition", UNSET),
            "claim_tier": self.protocol.get("claim_tier", UNSET),
            "runner_revision": RUNNER_REVISION,
            "prompt_renderer_revision": PROMPT_RENDERER_REVISION,
            "scorer_revision": SCORER_REVISION,
            "code_commit": self.plan.code_commit,
            "episode_time_cap_seconds": self.plan.episode_time_cap_seconds,
            "attempts_per_episode": ATTEMPTS_PER_EPISODE,
            "retried": False,
            "started_at_utc": started_at,
            "authorization": dict(self.authorization.to_record()),
            "plan": self.plan.to_record(),
            "not_established": list(NOT_ESTABLISHED),
            "frozen": self._frozen_block(inputs or {}),
            "frozen_prompt": self._frozen_prompt_block(),
        }

    def _resource_summary(self, sampler: ResourceSampler, started_at: str) -> Any:
        try:
            return sampler.summary()
        except Exception as exc:  # a missing summary must be visible, not fatal
            return {"status": "error", "error": redact_secrets(exc)}

    def failure_record(
        self,
        *,
        kind: str,
        stage: str,
        error: BaseException,
        started_at: str,
        run_dir: Path,
        inputs: Mapping[str, Any],
        preflight: Mapping[str, Any],
        predictions: Sequence[Mapping[str, Any]],
        sampler: ResourceSampler | None,
    ) -> dict[str, Any]:
        finished_at = self.clock()
        predictions_path = run_dir / PREDICTIONS_DIRNAME / PREDICTIONS_FILENAME
        self._write_predictions(predictions_path, predictions)
        record = self._base_record(started_at=started_at, inputs=inputs)
        record.update(
            {
                "kind": KIND_FAILURE,
                "exit_status": "failed",
                "finished_at_utc": finished_at,
                "wall_clock_seconds": _seconds_between(started_at, finished_at),
                "failure": {
                    "kind": kind,
                    "stage": stage,
                    "message": redact_secrets(error),
                },
                "inputs": dict(inputs),
                "preflight": dict(preflight),
                "partial": {
                    "predictions_recorded": len(predictions),
                    "episodes_completed": len(predictions),
                },
                "predictions_path": str(predictions_path).replace("\\", "/"),
                "resources": self._resource_summary(sampler, started_at) if sampler else UNSET,
            }
        )
        return record

    def _write_predictions(self, path: Path, predictions: Sequence[Mapping[str, Any]]) -> None:
        """Raw predictions, written for a failed run too. Never committed."""
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("w", encoding="utf-8") as handle:
                for row in predictions:
                    handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        except OSError:
            pass  # the record still carries the counts; lose no evidence to a write error

    # ---- the run -------------------------------------------------------------

    def run(self) -> dict[str, Any]:
        access = self.access if self.access is not None else deferred_access()
        sampler = self.sampler if self.sampler is not None else ResourceSampler(clock=self.clock)

        run_dir = Path(self.plan.run_dir)
        started_at = self.clock()
        stage = "protocol-check"
        inputs: dict[str, Any] = {}
        preflight: dict[str, Any] = {}
        predictions: list[dict[str, Any]] = []
        aggregate: dict[str, Any] = {}
        device: dict[str, Any] = {}
        tokenizer: Any = None
        cap_labels: set[str] = set()
        plan_doc: Mapping[str, Any] = {}
        episode_timings: list[float] = []
        try:
            plan_doc = load_plan(self.plan.plan_path)
            self._assert_protocol_matches_plan(plan_doc)

            stage = "inputs-generate"
            run_dir.mkdir(parents=True, exist_ok=True)
            inputs = self._generate_inputs(run_dir)
            manifest_rows = _read_jsonl(inputs["episode_manifest"]["path"])
            metadata_rows = _read_jsonl(inputs["episode_metadata"]["path"])
            split_by_id = {row["episode_id"]: row.get("split", UNSET) for row in metadata_rows}

            # Bind the frozen prompt digest here: after the manifest exists, before
            # the preflight and before any model or GPU access.
            stage = "prompt-binding"
            self._verify_prompt_binding(manifest_rows, plan_doc)

            stage = "preflight"
            preflight = self._invoke_preflight(inputs)

            stage = "peak-counter-reset"
            access.reset_peak_counters(self.plan)

            stage = "resource-sample-pre"
            sampler.sample_once()

            stage = "tokenizer-load"
            tokenizer = access.load_tokenizer(self.plan)

            stage = "model-load"
            model = access.load_model(self.plan, tokenizer)

            stage = "device-describe"
            device = dict(access.describe_device(self.plan))

            sampler.add_probe(self.peak_probe_factory())

            stage = "generate"
            for row in manifest_rows:
                episode_id = str(row["episode_id"])
                prompt = render_prompt(row["payload"])
                episode_started = self.clock()
                with episode_time_guard(self.plan.episode_time_cap_seconds) as cap_label:
                    cap_labels.add(cap_label)
                    output = dict(access.generate(self.plan, model, tokenizer, prompt))
                episode_finished = self.clock()
                episode_timings.append(_seconds_between(episode_started, episode_finished))
                text = output.get("text")
                predictions.append(
                    {
                        "episode_id": episode_id,
                        "split": split_by_id.get(episode_id, UNSET),
                        "text": text,
                        "prompt_sha256": prompt_sha256(row["payload"]),
                        "input_token_count": output.get("input_token_count", UNSET),
                        "output_token_count": output.get("output_token_count", UNSET),
                        "attempts": ATTEMPTS_PER_EPISODE,
                    }
                )
                self._check_output_contract(text, episode_id=episode_id)

            predictions_path = run_dir / PREDICTIONS_DIRNAME / PREDICTIONS_FILENAME
            stage = "write-predictions"
            self._write_predictions(predictions_path, predictions)

            stage = "score"
            aggregate = score_predictions(
                Path(inputs["reference_answers"]["path"]), predictions_path
            )

            stage = "write-artifacts"
            finished_at = self.clock()
            aggregate_only = {k: v for k, v in aggregate.items() if k != "episodes"}
            (run_dir / "aggregate.json").write_text(
                json.dumps(aggregate_only, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            (run_dir / "errors.json").write_text(
                json.dumps(
                    {
                        "scorer_revision": aggregate.get("scorer_revision", SCORER_REVISION),
                        "episodes": aggregate.get("episodes", []),
                    },
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )

            record = self._base_record(started_at=started_at, inputs=inputs)
            record.update(
                {
                    "kind": KIND_RUN,
                    "exit_status": "ok",
                    "finished_at_utc": finished_at,
                    "wall_clock_seconds": _seconds_from(started_at, finished_at),
                    "model": {
                        "repo_id": self.plan.repo_id,
                        "revision": self.plan.revision,
                        "precision": self.plan.precision,
                        "device": self.plan.device,
                        "device_reported": device.get("device_name", UNSET),
                        "library_versions": device.get("library_versions", UNSET),
                        "identity_source": self.plan.r02_record,
                    },
                    "decoding": {
                        "do_sample": False,
                        "max_new_tokens": self.plan.max_new_tokens,
                        "temperature_and_top_p": "not passed: inert under greedy decoding",
                        "attempts_per_episode": ATTEMPTS_PER_EPISODE,
                        "retries": 0,
                    },
                    "inputs": dict(inputs),
                    "preflight": dict(preflight),
                    "episode_cap_enforcement": sorted(cap_labels),
                    "episode_seconds": {
                        "count": len(episode_timings),
                        "max": max(episode_timings) if episode_timings else UNSET,
                        "total": sum(episode_timings),
                    },
                    "scoring": aggregate_only,
                    "aggregate_path": str(run_dir / "aggregate.json").replace("\\", "/"),
                    "episode_errors_path": str(run_dir / "errors.json").replace("\\", "/"),
                    "predictions_path": str(predictions_path).replace("\\", "/"),
                    "predictions_committed": False,
                    "failure": {
                        "kind": UNSET,
                        "stage": UNSET,
                        "message": UNSET,
                    },
                    "status": _status_from(aggregate_only),
                    "decision": (
                        "Development signal only. Continue to the baseline matrix before any "
                        "capability claim; this single-condition run cannot support one."
                    ),
                    "resources": self._resource_summary(sampler, started_at),
                }
            )
            self.record = record
            write_run_manifest(run_dir, record)
            (run_dir / "report.md").write_text(render_report(record), encoding="utf-8")
            return record
        except Exception as exc:  # everything after the gate; the first failure stops the run
            kind = exc.kind if isinstance(exc, RunStopped) else type(exc).__name__
            self.record = self.failure_record(
                kind=kind,
                stage=stage,
                error=exc,
                started_at=started_at,
                run_dir=run_dir,
                inputs=inputs,
                preflight=preflight,
                predictions=predictions,
                sampler=sampler,
            )
            write_run_manifest(run_dir, self.record)
            (run_dir / "failure.json").write_text(
                json.dumps(self.record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            return self.record


def _seconds_from(started_at: str, finished_at: str) -> float:
    return _seconds_between(started_at, finished_at)


def _status_from(aggregate: Mapping[str, Any]) -> str:
    total = aggregate.get("total", UNSET)
    correct = aggregate.get("correct", UNSET)
    return f"complete - development signal recorded ({correct}/{total} exact match)"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the frozen E01 records baseline once, under the E01 gate."
    )
    parser.add_argument("--run-id", required=True, help="run id, e.g. e01-pilot-001")
    parser.add_argument("--owner", required=True, help="executing agent, e.g. eido")
    parser.add_argument("--plan", required=True, help="frozen execution plan JSON")
    parser.add_argument("--protocol", required=True, help="frozen protocol JSON")
    parser.add_argument("--r02-record", required=True, help="merged R02 readiness record directory")
    parser.add_argument("--run-dir", default=None, help="defaults to results/E01/<run-id>")
    parser.add_argument("--code-commit", default=None)
    parser.add_argument("--authorization-file", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    # 1. The gate, before anything else exists.
    try:
        authorization = OperatorRecord.from_file(args.authorization_file)
        require_e01_authorization(authorization, run_id=args.run_id)
    except GateClosed as exc:
        print(f"e01_run: gate closed: {redact_secrets(exc)}", file=sys.stderr)
        return EXIT_GATE_CLOSED

    target_problems = validate_run_target(run_id=args.run_id, run_dir=args.run_dir)
    if target_problems:
        for problem in target_problems:
            print(f"e01_run: {redact_secrets(problem)}", file=sys.stderr)
        return EXIT_GATE_CLOSED

    try:
        pin = load_pin(args.r02_record)
        plan_doc = load_plan(args.plan)
        protocol = json.loads(Path(args.protocol).read_text(encoding="utf-8"))
    except (PinError, OSError, json.JSONDecodeError) as exc:
        print(f"e01_run: {redact_secrets(exc)}", file=sys.stderr)
        return EXIT_STEP_FAILED

    run = E01Run(
        authorization=authorization,
        plan=RunPlan(
            run_id=args.run_id,
            owner=args.owner,
            repo_id=pin.repo_id,
            revision=pin.revision,
            precision=pin.precision,
            device="cuda:0",
            max_new_tokens=int((protocol.get("decoding") or {}).get("max_new_tokens", 256)),
            run_dir=args.run_dir or expected_run_dir(args.run_id),
            plan_path=args.plan,
            protocol_path=args.protocol,
            r02_record=args.r02_record,
            authorization_file=args.authorization_file,
            episode_time_cap_seconds=int(
                (protocol.get("resources") or {}).get("time_cap_seconds_per_episode", 0)
            )
            or 0,
            code_commit=args.code_commit or git_commit(),
            stop_on_malformed_output=bool(
                (plan_doc.get("runner") or {}).get("stop_on_malformed_output", False)
            ),
        ),
        protocol=protocol,
    )

    record = run.run()
    print(json.dumps(record, indent=2, sort_keys=True))
    return EXIT_OK if record.get("exit_status") == "ok" else EXIT_STEP_FAILED


if __name__ == "__main__":
    raise SystemExit(main())
