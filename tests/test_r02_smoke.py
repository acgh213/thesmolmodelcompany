"""Tests for the R02 approval-gated readiness smoke (issue #17).

Nothing here imports ``torch`` or ``transformers``, loads a model, downloads a
weight, or reserves the GPU: the access layer is always a pure fake, and the
fail-closed tests assert that the fake is never reached.
"""

import hashlib
import io
import json
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from contextlib import redirect_stderr
from pathlib import Path

from scripts.r02_gate import SCOPE_ARTIFACT_FETCH, SCOPE_READINESS_SMOKE, Authorization, GateClosed
from scripts.r02_preflight import UNSET
from scripts.r02_resources import KIND as RESOURCE_KIND
from scripts.r02_resources import PEAK_COUNTER, SAMPLE, STATUS_DEGRADED, Probe, ResourceSampler
from scripts.r02_smoke import (
    CAP_ABORTED,
    CAP_ENFORCEMENT_ARMED,
    CAP_ENFORCEMENT_DETECTION,
    STATUS_FAILED,
    STATUS_OK,
    ModelAccess,
    ReadinessSmoke,
    SmokePlan,
    WallClockCapExceeded,
    deferred_access,
    main,
    validate_run_target,
    validate_smoke_record,
    wall_clock_guard,
)

ROOT = Path(__file__).resolve().parents[1]
GENERATED_TEXT = "Paris"


def authorization(**overrides):
    data = {
        "granted": True,
        "scope": SCOPE_READINESS_SMOKE,
        "reference": "issue #17 / executable PR",
        "approved_by": "vesper",
        "approved_at_utc": "2026-09-21T03:00:00Z",
    }
    data.update(overrides)
    return Authorization.from_mapping(data)


class StepClock:
    """A deterministic clock: returns the next stamp, then repeats the last one."""

    def __init__(self, stamps):
        self._stamps = list(stamps)
        self._last = None

    def __call__(self):
        if self._stamps:
            self._last = self._stamps.pop(0)
        return self._last


def clock_for(*stamps):
    return StepClock(list(stamps))


class FakeTokenizer:
    vocab_size = 151936


def fake_access(*, generation=None, fail_at=None, block_seconds=0.0):
    """A stand-in for every model-library and GPU call, with call accounting."""

    class FakeAccess:
        def __init__(self):
            self.calls = []

        def reset_peak_counters(self, plan):
            self.calls.append("reset_peak_counters")
            if fail_at == "reset_peak_counters":
                raise RuntimeError("simulated CUDA initialization failure")

        def load_tokenizer(self, plan):
            self.calls.append("load_tokenizer")
            if fail_at == "load_tokenizer":
                raise RuntimeError("simulated tokenizer failure")
            return FakeTokenizer()

        def load_model(self, plan, tokenizer):
            self.calls.append("load_model")
            if fail_at == "load_model":
                raise RuntimeError("simulated CUDA out of memory")
            return object()

        def describe_device(self, plan):
            self.calls.append("describe_device")
            return {"device": plan.device, "device_name": "fake-gpu", "cuda_available": True}

        def generate(self, plan, model, tokenizer):
            self.calls.append("generate")
            if block_seconds:
                time.sleep(block_seconds)  # a stage that blocks inside the interpreter
            return generation or {
                "input_token_count": 5,
                "output_token_ids": [1, 2, 3],
                "output_text": GENERATED_TEXT,
                "logits_all_finite": True,
                "stop_reason": "max_new_tokens",
            }

    return FakeAccess()


def sentinel_access():
    """Any call means the unapproved path reached the model; it must never happen."""

    class SentinelAccess:
        def __init__(self):
            self.calls = []

        def _refuse(self, name):
            self.calls.append(name)
            raise AssertionError(f"unapproved path reached {name}")

        def reset_peak_counters(self, plan):
            return self._refuse("reset_peak_counters")

        def load_tokenizer(self, plan):
            return self._refuse("load_tokenizer")

        def load_model(self, plan, tokenizer):
            return self._refuse("load_model")

        def describe_device(self, plan):
            return self._refuse("describe_device")

        def generate(self, plan, model, tokenizer):
            return self._refuse("generate")

    return SentinelAccess()


def gpu_probe(read):
    return Probe(
        name="nvidia-smi",
        command="nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits",
        kind=SAMPLE,
        units={"vram_used_mib": "MiB"},
        read=read,
    )


def fake_sampler(*, clock, probe=None):
    return ResourceSampler([probe or gpu_probe(lambda: {"vram_used_mib": 900.0})], clock=clock)


def exploding_probe(message="nvidia-smi could not be executed (simulated)"):
    def boom():
        raise FileNotFoundError(message)

    return gpu_probe(boom)


def exploding_sampler(*, clock, message="nvidia-smi could not be executed (simulated)"):
    return fake_sampler(clock=clock, probe=exploding_probe(message))


def flaky_probe(*, read_instants=1):
    """Answers the first ``read_instants`` instants, then fails: the post-load case."""
    seen = {"count": 0}

    def read():
        seen["count"] += 1
        if seen["count"] > read_instants:
            raise OSError("nvidia-smi timed out after the model load (simulated)")
        return {"vram_used_mib": 900.0}

    return gpu_probe(read)


def fake_peak_probe():
    return Probe(
        name="fake torch peak counters",
        command="fake.cuda.max_memory_allocated()",
        kind=PEAK_COUNTER,
        units={"vram_peak_allocated_mib": "MiB"},
        read=lambda: {"vram_peak_allocated_mib": 4096.0},
        basis="reset at run start (fake); covers the whole run",
    )


def plan(**overrides):
    data = {"run_id": "r02-smoke-001", "owner": "eido"}
    data.update(overrides)
    return SmokePlan(**data)


def write_authorization(path, **overrides):
    path.write_text(json.dumps(authorization(**overrides).to_record()), encoding="utf-8")
    return path


def run_smoke(access=None, sampler=None, *, clock_stamps=("2026-09-21T03:00:00Z", "2026-09-21T03:00:01Z"), **plan_overrides):
    return ReadinessSmoke(
        authorization=authorization(),
        plan=plan(**plan_overrides),
        access=access if access is not None else fake_access(),
        sampler=sampler if sampler is not None else fake_sampler(clock=clock_for(*clock_stamps)),
        peak_probe_factory=fake_peak_probe,
        clock=clock_for(*clock_stamps),
    ).run()


class FailClosedTests(unittest.TestCase):
    def test_missing_authorization_raises_before_touching_the_model(self):
        access = sentinel_access()
        with self.assertRaises(GateClosed):
            ReadinessSmoke(authorization=None, plan=plan(), access=access)
        self.assertEqual(access.calls, [])

    def test_ungranted_authorization_raises(self):
        with self.assertRaises(GateClosed):
            ReadinessSmoke(
                authorization=authorization(granted=False), plan=plan(), access=sentinel_access()
            )

    def test_scope_confusion_raises(self):
        with self.assertRaises(GateClosed):
            ReadinessSmoke(
                authorization=authorization(scope=SCOPE_ARTIFACT_FETCH),
                plan=plan(),
                access=sentinel_access(),
            )

    def test_no_model_library_is_imported_by_the_fail_closed_path(self):
        for name in ("torch", "transformers"):
            self.assertNotIn(name, sys.modules)
        with self.assertRaises(GateClosed):
            ReadinessSmoke(authorization=None, plan=plan(), access=sentinel_access())
        deferred_access()  # constructing the deferred layer imports nothing either
        for name in ("torch", "transformers"):
            self.assertNotIn(name, sys.modules)

    def test_access_contract_is_explicit(self):
        self.assertEqual(
            set(ModelAccess.__dataclass_fields__),
            {
                "reset_peak_counters",
                "load_tokenizer",
                "load_model",
                "describe_device",
                "generate",
            },
        )

    def test_no_owner_constant_is_hardcoded(self):
        import scripts.r02_smoke as smoke

        self.assertFalse(hasattr(smoke, "OWNER"))

    def test_module_import_is_model_library_free(self):
        script = (
            "import sys; sys.path.insert(0, 'scripts'); import r02_smoke; "
            "print('torch' in sys.modules, 'transformers' in sys.modules)"
        )
        completed = subprocess.run(
            [sys.executable, "-c", script], cwd=ROOT, capture_output=True, text=True, check=True
        )
        self.assertEqual(completed.stdout.strip(), "False False")


class SmokeRunTests(unittest.TestCase):
    def test_happy_path_records_a_valid_manifest(self):
        access = fake_access()
        record = ReadinessSmoke(
            authorization=authorization(),
            plan=plan(),
            access=access,
            sampler=fake_sampler(
                clock=clock_for("2026-09-21T03:00:00Z", "2026-09-21T03:00:23Z")
            ),
            peak_probe_factory=fake_peak_probe,
            clock=clock_for(
                "2026-09-21T03:00:00Z",
                "2026-09-21T03:00:01Z",
                "2026-09-21T03:00:20Z",
                "2026-09-21T03:00:21Z",
                "2026-09-21T03:00:22Z",
                "2026-09-21T03:00:23Z",
            ),
            resource_interval_seconds=5.0,
        ).run()

        self.assertEqual(
            access.calls,
            ["reset_peak_counters", "load_tokenizer", "load_model", "describe_device", "generate"],
        )
        self.assertEqual(record["exit_status"], STATUS_OK)
        self.assertEqual(record["failure"]["kind"], UNSET)
        self.assertEqual(record["owner"], "eido")
        self.assertEqual(validate_smoke_record(record), [])
        self.assertEqual(
            record["generation"]["output_text_sha256"],
            hashlib.sha256(GENERATED_TEXT.encode()).hexdigest(),
        )
        self.assertEqual(record["generation"]["output_token_count"], 3)
        self.assertNotIn("output_text", record["generation"])
        self.assertNotIn("first_output_token_id", record["generation"])
        self.assertEqual(record["timing"]["cold_load_seconds"], 20.0)
        self.assertEqual(record["timing"]["warm_inference_seconds"], 1.0)
        self.assertIn(
            record["timing"]["cap_enforcement"], (CAP_ENFORCEMENT_ARMED, CAP_ENFORCEMENT_DETECTION)
        )
        self.assertTrue(record["readiness"]["readiness_ok"])
        self.assertFalse(record["retried"])
        self.assertEqual(record["model"]["device_reported"], "fake-gpu")
        claim = record["resources"]["peak_claims"]["vram_peak_allocated_mib"]
        self.assertEqual(claim["value"], 4096.0)
        self.assertIn("reset at run start", claim["basis"])
        self.assertEqual(record["resources"]["method"]["interval_seconds"], 5.0)
        self.assertEqual(len(record["samples_pre"]), 1)
        self.assertEqual(len(record["samples_post"]), 2)

    def test_the_peak_counter_is_reset_before_any_load(self):
        access = fake_access()
        run_smoke(access=access)
        self.assertEqual(access.calls[0], "reset_peak_counters")
        self.assertLess(
            access.calls.index("reset_peak_counters"), access.calls.index("load_tokenizer")
        )
        self.assertLess(access.calls.index("reset_peak_counters"), access.calls.index("load_model"))

    def test_peak_reset_failure_is_a_recorded_failure(self):
        record = run_smoke(access=fake_access(fail_at="reset_peak_counters"))
        self.assertEqual(record["exit_status"], STATUS_FAILED)
        self.assertEqual(record["failure"]["stage"], "peak-counter-reset")
        self.assertEqual(validate_smoke_record(record), [])

    def test_first_failure_is_recorded_once_and_not_retried(self):
        access = fake_access(fail_at="load_model")
        record = run_smoke(access=access)
        self.assertEqual(record["exit_status"], STATUS_FAILED)
        self.assertEqual(record["failure"]["stage"], "model-load")
        self.assertEqual(record["failure"]["kind"], "RuntimeError")
        self.assertIn("simulated CUDA out of memory", record["failure"]["message"])
        self.assertEqual(access.calls.count("load_model"), 1)
        self.assertFalse(record["retried"])
        self.assertEqual(validate_smoke_record(record), [])

    def test_a_failing_pre_load_probe_is_a_recorded_failure_with_no_model_load(self):
        access = fake_access()
        record = run_smoke(
            access=access, sampler=exploding_sampler(clock=clock_for("2026-09-21T03:00:00Z"))
        )
        self.assertEqual(record["exit_status"], STATUS_FAILED)
        self.assertEqual(record["failure"]["kind"], "resource-probe-unavailable")
        self.assertEqual(record["failure"]["stage"], "resource-sample-pre")
        self.assertEqual(access.calls, ["reset_peak_counters"])  # nothing was loaded
        self.assertEqual(validate_smoke_record(record), [])
        self.assertEqual(record["resources"]["status"], STATUS_DEGRADED)
        self.assertEqual(record["resources"]["peak_claims"]["vram_used_mib"]["value"], UNSET)
        self.assertEqual(record["samples_pre"][0]["status"], "error")
        self.assertEqual(record["samples_pre"][0]["value"], UNSET)
        self.assertEqual(len(record["probe_errors"]), 1)

    def test_a_failing_post_load_probe_is_recorded_and_keeps_the_generation_measurements(self):
        sampler = fake_sampler(clock=clock_for("2026-09-21T03:00:00Z", "2026-09-21T03:00:01Z"), probe=flaky_probe())
        record = run_smoke(access=fake_access(), sampler=sampler)
        self.assertEqual(record["exit_status"], STATUS_FAILED)
        self.assertEqual(record["failure"]["kind"], "resource-probe-unavailable")
        self.assertEqual(record["failure"]["stage"], "resource-sample-post")
        self.assertEqual(validate_smoke_record(record), [])
        self.assertEqual(record["generation"]["output_token_count"], 3)
        self.assertEqual(record["resources"]["status"], STATUS_DEGRADED)

    def test_readiness_check_failure_is_a_failed_run(self):
        access = fake_access(
            generation={
                "input_token_count": 5,
                "output_token_ids": [],
                "output_text": "",
                "logits_all_finite": False,
                "stop_reason": "eos",
            }
        )
        record = run_smoke(access=access)
        self.assertEqual(record["exit_status"], STATUS_FAILED)
        self.assertEqual(record["failure"]["kind"], "readiness-check-failed")
        self.assertIn("model_produced_output_tokens", record["failure"]["message"])
        self.assertIn("logits_all_finite", record["failure"]["message"])


class WallClockTests(unittest.TestCase):
    @unittest.skipUnless(hasattr(signal, "SIGALRM"), "SIGALRM is POSIX-only")
    def test_the_guard_aborts_a_blocking_stage_at_the_cap(self):
        started = time.monotonic()
        with self.assertRaises(WallClockCapExceeded):
            with wall_clock_guard(1) as label:
                self.assertEqual(label, CAP_ENFORCEMENT_ARMED)
                time.sleep(5)
        self.assertLess(time.monotonic() - started, 3.0)

    @unittest.skipUnless(hasattr(signal, "SIGALRM"), "SIGALRM is POSIX-only")
    def test_an_armed_run_that_exceeds_the_cap_still_produces_a_record(self):
        started = time.monotonic()
        record = run_smoke(access=fake_access(block_seconds=4), wall_clock_cap_seconds=1)
        elapsed = time.monotonic() - started
        self.assertLess(elapsed, 3.5)  # aborted at the cap, not after the 4s stage returns
        self.assertEqual(record["exit_status"], STATUS_FAILED)
        self.assertEqual(record["failure"]["kind"], "wall-clock-cap-exceeded")
        self.assertEqual(record["failure"]["stage"], "generate")
        self.assertEqual(record["failure"]["enforcement"], CAP_ABORTED)
        self.assertEqual(validate_smoke_record(record), [])

    def test_a_cap_breach_detected_after_a_stage_returned_is_labelled_as_detection_only(self):
        stamps = (
            "2026-09-21T03:00:00Z",
            "2026-09-21T03:00:00Z",
            "2026-09-21T03:00:05Z",
            "2026-09-21T03:25:00Z",
            "2026-09-21T03:25:01Z",
            "2026-09-21T03:25:02Z",
        )
        record = ReadinessSmoke(
            authorization=authorization(),
            plan=plan(wall_clock_cap_seconds=1200),
            access=fake_access(),
            sampler=fake_sampler(clock=clock_for("2026-09-21T03:00:00Z", "2026-09-21T03:25:02Z")),
            peak_probe_factory=fake_peak_probe,
            clock=clock_for(*stamps),
            enforce_wall_clock_cap=False,
        ).run()
        self.assertEqual(record["exit_status"], STATUS_FAILED)
        self.assertEqual(record["failure"]["kind"], "wall-clock-cap-exceeded")
        self.assertIn("every stage had returned", record["failure"]["message"])
        self.assertIn("not interrupted", record["failure"]["enforcement"])
        self.assertEqual(record["timing"]["cap_enforcement"], CAP_ENFORCEMENT_DETECTION)

    def test_the_guard_is_not_armed_off_the_main_thread(self):
        labels = []

        def worker():
            with wall_clock_guard(1) as label:
                labels.append(label)

        thread = threading.Thread(target=worker)
        thread.start()
        thread.join()
        self.assertEqual(labels, [CAP_ENFORCEMENT_DETECTION])


class RunTargetTests(unittest.TestCase):
    def test_accepts_the_layout_the_recipe_assigns(self):
        self.assertEqual(
            validate_run_target(run_id="r02-smoke-001", run_dir="results/R02/r02-smoke-001"), []
        )
        self.assertEqual(
            validate_run_target(
                run_id="r02-smoke-017", run_dir="/abs/root/results/R02/r02-smoke-017"
            ),
            [],
        )

    def test_rejects_a_run_id_off_the_convention(self):
        problems = validate_run_target(run_id="smoke-1", run_dir=None)
        self.assertTrue(any("r02-smoke-" in problem for problem in problems))

    def test_rejects_an_off_layout_run_dir(self):
        problems = validate_run_target(run_id="r02-smoke-001", run_dir="/tmp/run")
        self.assertTrue(any("results/R02/r02-smoke-001" in problem for problem in problems))

    def test_run_dir_must_match_the_run_id(self):
        self.assertTrue(
            validate_run_target(run_id="r02-smoke-001", run_dir="results/R02/r02-smoke-002")
        )


class RecordShapeTests(unittest.TestCase):
    def test_validator_flags_missing_keys(self):
        errors = validate_smoke_record({"kind": "r02-readiness-smoke"})
        self.assertTrue(any("missing key" in error for error in errors))

    def test_validator_flags_raw_generated_text(self):
        record = _minimal_record()
        record["generation"]["output_text"] = "raw model output"
        self.assertTrue(any("must not carry" in error for error in validate_smoke_record(record)))

    def test_validator_flags_token_ids(self):
        record = _minimal_record()
        record["generation"]["output_token_ids"] = [1, 2, 3]
        self.assertTrue(any("output_token_ids" in error for error in validate_smoke_record(record)))

    def test_validator_flags_a_missing_owner(self):
        record = _minimal_record()
        record["owner"] = UNSET
        self.assertTrue(any("owner" in error for error in validate_smoke_record(record)))

    def test_validator_flags_wrong_authorization_scope(self):
        record = _minimal_record()
        record["authorization"]["scope"] = SCOPE_ARTIFACT_FETCH
        self.assertTrue(any("scope" in error for error in validate_smoke_record(record)))

    def test_validator_flags_a_failed_record_without_a_failure_kind(self):
        record = _minimal_record()
        record["exit_status"] = STATUS_FAILED
        self.assertTrue(any("failure kind" in error for error in validate_smoke_record(record)))

    def test_validator_flags_a_successful_record_that_names_a_failure(self):
        record = _minimal_record()
        record["failure"]["kind"] = "readiness-check-failed"
        self.assertTrue(
            any("must not name a failure" in error for error in validate_smoke_record(record))
        )

    def test_validator_flags_a_resources_record_of_the_wrong_kind(self):
        record = _minimal_record()
        record["resources"] = {"kind": "something-else"}
        self.assertTrue(any("resources" in error for error in validate_smoke_record(record)))

    def test_every_failure_record_shape_validates(self):
        scenarios = {
            "pre-load probe": dict(sampler=exploding_sampler(clock=clock_for("2026-09-21T03:00:00Z"))),
            "model load": dict(access=fake_access(fail_at="load_model")),
            "peak reset": dict(access=fake_access(fail_at="reset_peak_counters")),
            "post-load probe": dict(
                sampler=fake_sampler(
                    clock=clock_for("2026-09-21T03:00:00Z", "2026-09-21T03:00:01Z"), probe=flaky_probe()
                )
            ),
        }
        for name, kwargs in scenarios.items():
            with self.subTest(scenario=name):
                record = run_smoke(**kwargs)
                self.assertEqual(record["exit_status"], STATUS_FAILED, name)
                self.assertEqual(validate_smoke_record(record), [], name)

    def test_the_record_carries_output_identity_not_output(self):
        record = _minimal_record()
        self.assertNotIn("output_text", record["generation"])
        self.assertNotIn("first_output_token_id", record["generation"])
        self.assertEqual(validate_smoke_record(record), [])


def _minimal_record():
    return {
        "kind": "r02-readiness-smoke",
        "run_id": "r02-smoke-001",
        "owner": "eido",
        "authorization": authorization().to_record(),
        "model": {
            "repo_id": "Qwen/Qwen2.5-1.5B",
            "revision": "a" * 40,
            "precision": "bfloat16",
            "device": "cuda:0",
        },
        "plan": {"seed": 0},
        "timing": {"cold_load_seconds": 1.0, "warm_inference_seconds": 0.5},
        "tokenizer": {"input_token_count": 5, "vocab_size": 151936},
        "generation": {
            "output_text_sha256": "b" * 64,
            "output_token_count": 3,
            "logits_all_finite": True,
            "stop_reason": "max_new_tokens",
        },
        "resources": {"kind": RESOURCE_KIND},
        "started_at_utc": "2026-09-21T03:00:00Z",
        "finished_at_utc": "2026-09-21T03:00:05Z",
        "exit_status": STATUS_OK,
        "failure": {"stage": UNSET, "kind": UNSET, "message": UNSET, "enforcement": UNSET},
    }


class SmokeCliTests(unittest.TestCase):
    def test_cli_without_authorization_file_exits_closed_before_imports(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "results" / "R02" / "r02-smoke-001"
            completed = subprocess.run(
                [
                    sys.executable,
                    "scripts/r02_smoke.py",
                    "--run-id",
                    "r02-smoke-001",
                    "--owner",
                    "eido",
                    "--run-dir",
                    str(run_dir),
                    "--authorization-file",
                    str(Path(tmp) / "absent.json"),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 2)
            self.assertIn("gate closed", completed.stderr)
            self.assertFalse(run_dir.exists())
            self.assertNotIn("torch", completed.stdout)

    def test_dry_run_reports_the_plan_and_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            auth_path = write_authorization(Path(tmp) / "authorization.json")
            run_dir = Path(tmp) / "results" / "R02" / "r02-smoke-001"
            completed = subprocess.run(
                [
                    sys.executable,
                    "scripts/r02_smoke.py",
                    "--run-id",
                    "r02-smoke-001",
                    "--owner",
                    "cassie",
                    "--run-dir",
                    str(run_dir),
                    "--authorization-file",
                    str(auth_path),
                    "--dry-run",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 0)
            payload = json.loads(completed.stdout)
            self.assertTrue(payload["dry_run"])
            self.assertEqual(payload["plan"]["owner"], "cassie")
            self.assertEqual(payload["plan"]["cache_state"], UNSET)
            self.assertEqual(payload["plan"]["repo_id"], "Qwen/Qwen2.5-1.5B")
            self.assertIn("wall_clock_cap", payload)
            self.assertFalse(run_dir.exists())

    def test_an_off_layout_run_dir_is_rejected_before_anything_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            auth_path = write_authorization(Path(tmp) / "authorization.json")
            run_dir = Path(tmp) / "somewhere-else"
            completed = subprocess.run(
                [
                    sys.executable,
                    "scripts/r02_smoke.py",
                    "--run-id",
                    "r02-smoke-001",
                    "--owner",
                    "eido",
                    "--run-dir",
                    str(run_dir),
                    "--authorization-file",
                    str(auth_path),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 2)
            self.assertIn("run target rejected", completed.stderr)
            self.assertFalse(run_dir.exists())

    def test_a_probe_failure_writes_a_validated_failure_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            auth_path = write_authorization(Path(tmp) / "authorization.json")
            run_dir = Path(tmp) / "results" / "R02" / "r02-smoke-001"
            with redirect_stderr(io.StringIO()):
                code = main(
                    [
                        "--run-id",
                        "r02-smoke-001",
                        "--owner",
                        "vesper",
                        "--run-dir",
                        str(run_dir),
                        "--authorization-file",
                        str(auth_path),
                        "--no-wall-clock-guard",
                    ],
                    sampler_factory=lambda: exploding_sampler(
                        clock=clock_for("2026-09-21T03:00:00Z"),
                        message="nvidia-smi failed: token=abc123def",
                    ),
                    access_factory=fake_access,
                )
            self.assertEqual(code, 1)
            record = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
            self.assertTrue((run_dir / "resource-samples.json").is_file())
            self.assertEqual(record["exit_status"], STATUS_FAILED)
            self.assertEqual(record["failure"]["kind"], "resource-probe-unavailable")
            self.assertEqual(record["owner"], "vesper")  # from the plan, not a constant
            self.assertEqual(validate_smoke_record(record), [])
            self.assertNotIn("abc123def", record["failure"]["message"])
            self.assertIn("REDACTED", record["failure"]["message"])

    def test_main_returns_gate_closed_in_process(self):
        errors = io.StringIO()
        with redirect_stderr(errors):
            code = main(
                ["--run-id", "r02-smoke-001", "--owner", "eido", "--authorization-file", "/absent.json"]
            )
        self.assertEqual(code, 2)
        self.assertIn("gate closed", errors.getvalue())


if __name__ == "__main__":
    unittest.main()
