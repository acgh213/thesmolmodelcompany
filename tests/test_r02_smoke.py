"""Tests for the R02 approval-gated readiness smoke (issue #17).

Nothing here imports ``torch`` or ``transformers``, loads a model, downloads a
weight, or reserves the GPU: the access layer is always a pure fake, and the
fail-closed tests assert that the fake is never reached.
"""

import hashlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path

from scripts.r02_gate import SCOPE_ARTIFACT_FETCH, SCOPE_READINESS_SMOKE, Authorization, GateClosed
from scripts.r02_preflight import UNSET
from scripts.r02_resources import PEAK_COUNTER, SAMPLE, Probe, ResourceSampler
from scripts.r02_smoke import (
    STATUS_FAILED,
    STATUS_OK,
    ModelAccess,
    ReadinessSmoke,
    SmokePlan,
    deferred_access,
    main,
    validate_smoke_record,
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


def fake_access(*, generation=None, fail_at=None):
    """A stand-in for every model-library and GPU call, with call accounting."""

    class FakeAccess:
        def __init__(self):
            self.calls = []

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

        def load_tokenizer(self, plan):
            return self._refuse("load_tokenizer")

        def load_model(self, plan, tokenizer):
            return self._refuse("load_model")

        def describe_device(self, plan):
            return self._refuse("describe_device")

        def generate(self, plan, model, tokenizer):
            return self._refuse("generate")

    return SentinelAccess()


def fake_sampler(*, clock):
    return ResourceSampler(
        [
            Probe(
                name="fake-nvidia-smi",
                command="nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits",
                kind=SAMPLE,
                units={"vram_used_mib": "MiB"},
                read=lambda: {"vram_used_mib": 900.0},
            )
        ],
        clock=clock,
    )


def fake_peak_probe():
    return Probe(
        name="fake torch peak counters",
        command="fake.cuda.max_memory_allocated()",
        kind=PEAK_COUNTER,
        units={"vram_peak_allocated_mib": "MiB"},
        read=lambda: {"vram_peak_allocated_mib": 4096.0},
    )


def plan(**overrides):
    data = {"run_id": "r02-smoke-test-001"}
    data.update(overrides)
    return SmokePlan(**data)


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
        fields = set(ModelAccess.__dataclass_fields__)
        self.assertEqual(
            fields, {"load_tokenizer", "load_model", "describe_device", "generate"}
        )

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
        runner_clock = clock_for(
            "2026-09-21T03:00:00Z",
            "2026-09-21T03:00:01Z",
            "2026-09-21T03:00:20Z",
            "2026-09-21T03:00:21Z",
            "2026-09-21T03:00:22Z",
            "2026-09-21T03:00:23Z",
        )
        sample_clock = clock_for("2026-09-21T03:00:00Z", "2026-09-21T03:00:23Z")
        access = fake_access()
        record = ReadinessSmoke(
            authorization=authorization(),
            plan=plan(),
            access=access,
            sampler=fake_sampler(clock=sample_clock),
            peak_probe_factory=fake_peak_probe,
            clock=runner_clock,
            resource_interval_seconds=5.0,
        ).run()

        self.assertEqual(
            access.calls, ["load_tokenizer", "load_model", "describe_device", "generate"]
        )
        self.assertEqual(record["exit_status"], STATUS_OK)
        self.assertEqual(record["failure"]["kind"], UNSET)
        self.assertEqual(validate_smoke_record(record), [])
        self.assertEqual(
            record["generation"]["output_text_sha256"],
            hashlib.sha256(GENERATED_TEXT.encode()).hexdigest(),
        )
        self.assertEqual(record["generation"]["output_token_count"], 3)
        self.assertEqual(record["timing"]["cold_load_seconds"], 20.0)
        self.assertEqual(record["timing"]["warm_inference_seconds"], 1.0)
        self.assertTrue(record["readiness"]["readiness_ok"])
        self.assertFalse(record["retried"])
        self.assertEqual(record["model"]["device"], "cuda:0")
        self.assertEqual(record["model"]["device_reported"], "fake-gpu")
        self.assertIn("vram_peak_allocated_mib", record["resources"]["peak_claims"])
        self.assertEqual(record["resources"]["method"]["interval_seconds"], 5.0)
        self.assertEqual(len(record["samples_pre"]), 1)
        self.assertEqual(len(record["samples_post"]), 2)

    def test_first_failure_is_recorded_once_and_not_retried(self):
        access = fake_access(fail_at="load_model")
        record = ReadinessSmoke(
            authorization=authorization(),
            plan=plan(),
            access=access,
            sampler=fake_sampler(clock=clock_for("2026-09-21T03:00:00Z", "2026-09-21T03:00:01Z")),
            peak_probe_factory=fake_peak_probe,
            clock=clock_for("2026-09-21T03:00:00Z", "2026-09-21T03:00:01Z"),
        ).run()
        self.assertEqual(record["exit_status"], STATUS_FAILED)
        self.assertEqual(record["failure"]["stage"], "model-load")
        self.assertEqual(record["failure"]["kind"], "RuntimeError")
        self.assertIn("simulated CUDA out of memory", record["failure"]["message"])
        self.assertEqual(access.calls.count("load_model"), 1)
        self.assertFalse(record["retried"])
        self.assertEqual(validate_smoke_record(record), [])

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
        record = ReadinessSmoke(
            authorization=authorization(),
            plan=plan(),
            access=access,
            sampler=fake_sampler(clock=clock_for("2026-09-21T03:00:00Z", "2026-09-21T03:00:01Z")),
            peak_probe_factory=fake_peak_probe,
            clock=clock_for("2026-09-21T03:00:00Z", "2026-09-21T03:00:02Z"),
        ).run()
        self.assertEqual(record["exit_status"], STATUS_FAILED)
        self.assertEqual(record["failure"]["kind"], "readiness-check-failed")
        self.assertIn("model_produced_output_tokens", record["failure"]["message"])
        self.assertIn("logits_all_finite", record["failure"]["message"])

    def test_wall_clock_cap_breach_is_recorded(self):
        stamps = [
            "2026-09-21T03:00:00Z",
            "2026-09-21T03:00:00Z",
            "2026-09-21T03:00:05Z",
            "2026-09-21T03:25:00Z",
            "2026-09-21T03:25:01Z",
            "2026-09-21T03:25:02Z",
        ]
        record = ReadinessSmoke(
            authorization=authorization(),
            plan=plan(wall_clock_cap_seconds=1200),
            access=fake_access(),
            sampler=fake_sampler(clock=clock_for("2026-09-21T03:00:00Z", "2026-09-21T03:25:02Z")),
            peak_probe_factory=fake_peak_probe,
            clock=clock_for(*stamps),
        ).run()
        self.assertEqual(record["exit_status"], STATUS_FAILED)
        self.assertEqual(record["failure"]["kind"], "wall-clock-cap-exceeded")
        self.assertGreater(record["timing"]["wall_clock_seconds"], 1200)

    def test_sampler_failure_after_inference_is_recorded(self):
        class ExplodingProbe:
            name = "exploding"
            command = "explode"
            kind = SAMPLE
            units = {"vram_used_mib": "MiB"}

            def __init__(self):
                self.calls = 0

            def read(self):
                self.calls += 1
                if self.calls > 1:
                    raise RuntimeError("simulated sampling failure")
                return {"vram_used_mib": 900.0}

        sampler = ResourceSampler(
            [ExplodingProbe()], clock=clock_for("2026-09-21T03:00:00Z", "2026-09-21T03:00:01Z")
        )
        record = ReadinessSmoke(
            authorization=authorization(),
            plan=plan(),
            access=fake_access(),
            sampler=sampler,
            peak_probe_factory=fake_peak_probe,
            clock=clock_for("2026-09-21T03:00:00Z", "2026-09-21T03:00:02Z"),
        ).run()
        self.assertEqual(record["exit_status"], STATUS_FAILED)
        self.assertEqual(record["failure"]["stage"], "resource-sample")


class RecordShapeTests(unittest.TestCase):
    def test_validator_flags_missing_keys(self):
        errors = validate_smoke_record({"kind": "r02-readiness-smoke"})
        self.assertTrue(any("missing key" in error for error in errors))

    def test_validator_flags_raw_generated_text(self):
        record = _minimal_record()
        record["generation"]["output_text"] = "raw model output"
        self.assertTrue(any("raw generated text" in error for error in validate_smoke_record(record)))

    def test_validator_flags_wrong_authorization_scope(self):
        record = _minimal_record()
        record["authorization"]["scope"] = SCOPE_ARTIFACT_FETCH
        self.assertTrue(any("scope" in error for error in validate_smoke_record(record)))

    def test_validator_flags_a_failed_record_without_a_failure_kind(self):
        record = _minimal_record()
        record["exit_status"] = STATUS_FAILED
        self.assertTrue(any("failure kind" in error for error in validate_smoke_record(record)))

    def test_the_manifest_never_carries_the_prompt_or_output_text(self):
        record = _minimal_record()
        self.assertNotIn("output_text", record["generation"])
        self.assertEqual(validate_smoke_record(record), [])


def _minimal_record():
    return {
        "kind": "r02-readiness-smoke",
        "run_id": "r02-smoke-test-001",
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
            "first_output_token_id": 1,
            "logits_all_finite": True,
            "stop_reason": "max_new_tokens",
        },
        "resources": {"kind": "r02-resource-sampling"},
        "started_at_utc": "2026-09-21T03:00:00Z",
        "finished_at_utc": "2026-09-21T03:00:05Z",
        "exit_status": STATUS_OK,
        "failure": {"stage": UNSET, "kind": UNSET, "message": UNSET},
    }


class SmokeCliTests(unittest.TestCase):
    def test_cli_without_authorization_file_exits_closed_before_imports(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "results" / "R02" / "r02-smoke-test-001"
            completed = subprocess.run(
                [
                    sys.executable,
                    "scripts/r02_smoke.py",
                    "--run-id",
                    "r02-smoke-test-001",
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
            auth_path = Path(tmp) / "authorization.json"
            auth_path.write_text(json.dumps(authorization().to_record()), encoding="utf-8")
            run_dir = Path(tmp) / "run"
            completed = subprocess.run(
                [
                    sys.executable,
                    "scripts/r02_smoke.py",
                    "--run-id",
                    "r02-smoke-test-001",
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
            self.assertEqual(payload["plan"]["cache_state"], UNSET)
            self.assertEqual(payload["plan"]["repo_id"], "Qwen/Qwen2.5-1.5B")
            self.assertFalse(run_dir.exists())

    def test_main_returns_gate_closed_in_process(self):
        errors = io.StringIO()
        with redirect_stderr(errors):
            code = main(["--run-id", "r02-smoke-test-001", "--authorization-file", "/absent.json"])
        self.assertEqual(code, 2)
        self.assertIn("gate closed", errors.getvalue())


if __name__ == "__main__":
    unittest.main()
