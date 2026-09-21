"""Tests for the E01 execution runner (issue #24).

Every test here uses injected fakes: no model library is imported, no GPU is
touched and no artifact is retrieved.
"""

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

from scripts.build_results_ledger import REQUIRED, parse_front_matter
from scripts.e01_gate import EXPERIMENT_ID, SCOPE_E01_EXECUTION, GateClosed
from scripts.e01_identity import PinError
from scripts.e01_prompt import PROMPT_RENDERER_REVISION
from scripts.e01_records import GENERATOR_REVISION
from scripts.e01_run import (
    CAP_NOT_ARMED,
    RUNNER_REVISION,
    E01Run,
    ModelAccess,
    RunPlan,
    main,
)
from scripts.e01_score import SCORER_REVISION

PIN_DIR = ROOT / "results" / "R02" / "r02-smoke-001"
RUN_ID = "e01-pilot-001"
RUN_DIR = f"results/E01/{RUN_ID}"

PROTOCOL = {
    "experiment": "E01",
    "protocol_version": "e01-records-v1",
    "family": "records",
    "condition": "canonical-representation-with-primitives",
    "claim_tier": "development-signal",
    "generator_revision": GENERATOR_REVISION,
    "task": {"record_count": 5, "development_seeds": [1000, 1001], "final_seeds": [2000]},
    "decoding": {
        "do_sample": False,
        "temperature": 0.0,
        "top_p": 1.0,
        "max_new_tokens": 256,
        "retries": 0,
    },
    "resources": {"time_cap_seconds_per_episode": 1200},
}

EPISODE_COUNT = 3

# Distinguishes "caller did not say" from "caller passed None on purpose".
DEFAULT_AUTHORIZATION = object()


def fixture_plan(directory, *, overrides=None):
    plan = {
        "kind": "e01-execution-plan",
        "experiment": EXPERIMENT_ID,
        "model": {
            "source": "huggingface",
            "repo_id": "Qwen/Qwen2.5-1.5B",
            "precision": "bfloat16",
            "revision": "8faed761d45a263340a0528343f099c05c9a4323",
        },
        "artifacts": {
            "generator_revision": GENERATOR_REVISION,
            "scorer_revision": SCORER_REVISION,
            "prompt_renderer_revision": PROMPT_RENDERER_REVISION,
            "runner_revision": RUNNER_REVISION,
            "episode_manifest_sha256": "0" * 64,
            "reference_answers_sha256": "1" * 64,
            "prompt_sha256": "2" * 64,
        },
    }
    if overrides:
        plan["artifacts"].update(overrides)
    path = Path(directory) / "plan.json"
    path.write_text(json.dumps(plan), encoding="utf-8")
    return path


def authorization(**overrides):
    data = {
        "granted": True,
        "scope": SCOPE_E01_EXECUTION,
        "reference": "fixture: not a real review",
        "approved_by": "vesper",
        "approved_at_utc": "2026-09-21T04:30:21Z",
        "experiment": EXPERIMENT_ID,
        "run_id": RUN_ID,
        "operator_go": "cassie",
        "operator_go_received_before_utc": "2026-09-21T04:30:44Z",
        "procedure_reviewer_only": True,
    }
    data.update(overrides)
    from scripts.e01_gate import OperatorRecord

    return OperatorRecord.from_mapping(data)


class FakeSampler:
    def __init__(self):
        self.instants = 0
        self.probes = 0

    def sample_once(self):
        self.instants += 1
        return []

    def add_probe(self, probe):
        self.probes += 1

    def summary(self, **kwargs):
        return {"kind": "fake", "status": "ok", "instants": self.instants}


def make_access(*, mode="correct", fail_at=None, calls=None, loaded=None):
    """Injected access. Reads the generated reference answers to answer correctly."""
    calls = [] if calls is None else calls
    loaded = loaded if loaded is not None else {"tokenizer": 0, "model": 0}

    def load_tokenizer(plan):
        loaded["tokenizer"] += 1
        return "fake-tokenizer"

    def load_model(plan, tokenizer):
        loaded["model"] += 1
        return "fake-model"

    def generate(plan, model, tokenizer, prompt):
        index = len(calls)
        calls.append(prompt)
        if fail_at is not None and index == fail_at:
            raise RuntimeError("injected generation failure")
        if mode == "malformed":
            return {"text": "not json", "input_token_count": 9, "output_token_count": 2}
        rows = [
            json.loads(line)
            for line in (Path(plan.run_dir) / "inputs" / "reference-answers.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
            if line.strip()
        ]
        return {
            "text": json.dumps(rows[index]["answer"]),
            "input_token_count": 12,
            "output_token_count": 5,
        }

    return (
        ModelAccess(
            reset_peak_counters=lambda plan: None,
            load_tokenizer=load_tokenizer,
            load_model=load_model,
            describe_device=lambda plan: {"device": plan.device, "device_name": "fake-device"},
            generate=generate,
        ),
        calls,
        loaded,
    )


class RunTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self._cwd = os.getcwd()
        os.chdir(self.tmp)
        self.plan_path = fixture_plan(self.tmp)
        self._out, self._err = io.StringIO(), io.StringIO()

    def tearDown(self):
        os.chdir(self._cwd)
        self._tmp.cleanup()

    def plan(self, **overrides):
        return RunPlan(
            run_id=RUN_ID,
            owner="eido",
            repo_id="Qwen/Qwen2.5-1.5B",
            revision="8faed761d45a263340a0528343f099c05c9a4323",
            precision="bfloat16",
            device="cuda:0",
            max_new_tokens=256,
            run_dir=RUN_DIR,
            plan_path=str(self.plan_path),
            protocol_path=str(self.tmp / "protocol.json"),
            r02_record=str(PIN_DIR),
            authorization_file=str(self.tmp / "auth.json"),
            episode_time_cap_seconds=1200,
            code_commit="fixture",
            stop_on_malformed_output=overrides.pop("stop_on_malformed_output", True),
        )

    def build(
        self,
        *,
        access=None,
        preflight=None,
        authorization_record=DEFAULT_AUTHORIZATION,
        sampler=None,
        **plan_overrides,
    ):
        access, calls, loaded = access if isinstance(access, tuple) else make_access()
        self.calls, self.loaded = calls, loaded
        self.sampler = sampler or FakeSampler()
        run = E01Run(
            authorization=(
                authorization()
                if authorization_record is DEFAULT_AUTHORIZATION
                else authorization_record
            ),
            plan=self.plan(**plan_overrides),
            access=access,
            sampler=self.sampler,
            peak_probe_factory=lambda: "fake-probe",
            clock=lambda: "2026-09-21T05:00:00Z",
            preflight_runner=preflight or (lambda argv: 0),
            protocol=PROTOCOL,
        )
        self.preflight_argv = None
        if preflight is None:
            run.preflight_runner = self.capture_preflight
        return run

    def capture_preflight(self, argv):
        self.preflight_argv = list(argv)
        return 0

    def run_dir_path(self):
        return self.tmp / "results" / "E01" / RUN_ID


class GateTests(RunTestCase):
    def test_missing_authorization_fails_closed(self):
        with self.assertRaises(GateClosed):
            self.build(authorization_record=None)

    def test_authorization_naming_another_run_fails_closed(self):
        with self.assertRaises(GateClosed):
            self.build(authorization_record=authorization(run_id="e01-pilot-002"))

    def test_no_directory_is_created_when_the_gate_is_closed(self):
        with self.assertRaises(GateClosed):
            self.build(authorization_record=None)
        self.assertFalse((self.tmp / "results").exists())


class HappyPathTests(RunTestCase):
    def test_run_completes_and_scores_every_episode(self):
        run = self.build()
        record = run.run()
        self.assertEqual(record["exit_status"], "ok")
        self.assertEqual(record["scoring"]["total"], EPISODE_COUNT)
        self.assertEqual(record["scoring"]["correct"], EPISODE_COUNT)
        self.assertEqual(record["scoring"]["accuracy"], 1.0)

    def test_evidence_package_is_written(self):
        run = self.build()
        run.run()
        target = self.run_dir_path()
        for name in (
            "manifest.json",
            "report.md",
            "aggregate.json",
            "errors.json",
            "resource-samples.json",
        ):
            with self.subTest(name=name):
                self.assertTrue((target / name).is_file(), name)
        self.assertTrue((target / "predictions" / "predictions.jsonl").is_file())
        self.assertTrue((target / "inputs" / "episode-manifest.jsonl").is_file())
        self.assertTrue((target / "inputs" / "reference-answers.jsonl").is_file())

    def test_one_attempt_per_episode_and_no_retry(self):
        run = self.build()
        record = run.run()
        self.assertEqual(len(self.calls), EPISODE_COUNT)
        self.assertEqual(record["attempts_per_episode"], 1)
        self.assertEqual(record["retried"], False)
        self.assertEqual(record["decoding"]["retries"], 0)

    def test_preflight_is_invoked_with_the_generated_inputs_before_the_model_loads(self):
        run = self.build()
        run.run()
        argv = self.preflight_argv
        self.assertIsNotNone(argv)
        self.assertIn("--episode-manifest", argv)
        manifest = Path(argv[argv.index("--episode-manifest") + 1])
        self.assertTrue(manifest.is_file())
        self.assertEqual(manifest.name, "episode-manifest.jsonl")
        references = Path(argv[argv.index("--reference-answers") + 1])
        self.assertTrue(references.is_file())
        # The preflight ran before any model-side call.
        self.assertEqual(self.loaded, {"tokenizer": 1, "model": 1})

    def test_record_carries_the_frozen_identities(self):
        run = self.build()
        record = run.run()
        self.assertEqual(record["runner_revision"], RUNNER_REVISION)
        self.assertEqual(record["prompt_renderer_revision"], PROMPT_RENDERER_REVISION)
        self.assertEqual(record["scorer_revision"], SCORER_REVISION)
        self.assertEqual(record["protocol_version"], "e01-records-v1")
        self.assertEqual(record["claim_tier"], "development-signal")
        self.assertEqual(record["frozen"]["prompt_sha256"], "2" * 64)
        self.assertEqual(record["model"]["repo_id"], "Qwen/Qwen2.5-1.5B")
        self.assertEqual(record["model"]["identity_source"], str(PIN_DIR))

    def test_predictions_are_never_committed(self):
        run = self.build()
        record = run.run()
        self.assertFalse(record["predictions_committed"])
        manifest = json.loads((self.run_dir_path() / "manifest.json").read_text())
        self.assertNotIn("text", json.dumps(manifest.get("scoring", {})))
        # The committed manifest points at the raw file rather than embedding it.
        self.assertTrue(manifest["predictions_path"].endswith("predictions.jsonl"))

    def test_report_front_matter_satisfies_the_ledger_contract(self):
        run = self.build()
        run.run()
        text = (self.run_dir_path() / "report.md").read_text(encoding="utf-8")
        fields = parse_front_matter(text)
        self.assertIsNotNone(fields)
        missing = [name for name in REQUIRED if not fields.get(name)]
        self.assertEqual(missing, [])
        self.assertEqual(fields["experiment"], "E01")
        self.assertEqual(fields["run_id"], RUN_ID)

    def test_report_contains_no_reference_answer_or_prediction_text(self):
        run = self.build()
        run.run()
        report = (self.run_dir_path() / "report.md").read_text(encoding="utf-8")
        references = [
            json.loads(line)
            for line in (self.run_dir_path() / "inputs" / "reference-answers.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
            if line.strip()
        ]
        for row in references:
            answer = json.dumps(row["answer"], separators=(",", ":"), sort_keys=True)
            self.assertNotIn(answer, report)
        self.assertNotIn("declared_budget", report)

    def test_error_summary_carries_classes_not_answers(self):
        run = self.build()
        run.run()
        errors = json.loads((self.run_dir_path() / "errors.json").read_text())
        self.assertEqual(len(errors["episodes"]), EPISODE_COUNT)
        for row in errors["episodes"]:
            self.assertEqual(sorted(row), ["correct", "episode_id", "error_class", "split"])

    def test_episode_cap_label_is_recorded(self):
        run = self.build()
        record = run.run()
        self.assertTrue(record["episode_cap_enforcement"])
        for label in record["episode_cap_enforcement"]:
            self.assertIn(label, (CAP_NOT_ARMED, "sigalrm armed: the cap raises inside the interpreter and aborts the episode"))


class FailurePathTests(RunTestCase):
    def test_preflight_failure_stops_before_any_model_call(self):
        access, calls, loaded = make_access()
        run = self.build(access=(access, calls, loaded), preflight=lambda argv: 1)
        record = run.run()
        self.assertEqual(record["exit_status"], "failed")
        self.assertEqual(record["failure"]["kind"], "preflight-failed")
        self.assertEqual(loaded, {"tokenizer": 0, "model": 0})
        self.assertEqual(calls, [])
        self.assertFalse((self.run_dir_path() / "report.md").exists())

    def test_malformed_output_stops_the_run_and_preserves_what_was_produced(self):
        access, calls, _ = make_access(mode="malformed")
        run = self.build(access=(access, calls, make_access()[2]))
        record = run.run()
        self.assertEqual(record["exit_status"], "failed")
        self.assertEqual(record["failure"]["kind"], "malformed-output")
        self.assertEqual(record["failure"]["stage"], "generate")
        self.assertEqual(record["partial"]["predictions_recorded"], 1)
        self.assertTrue((self.run_dir_path() / "predictions" / "predictions.jsonl").is_file())
        self.assertTrue((self.run_dir_path() / "failure.json").is_file())
        self.assertFalse((self.run_dir_path() / "report.md").exists())

    def test_malformed_output_can_be_scored_when_the_plan_allows_it(self):
        access, calls, _ = make_access(mode="malformed")
        run = self.build(access=(access, calls, make_access()[2]), stop_on_malformed_output=False)
        record = run.run()
        self.assertEqual(record["exit_status"], "ok")
        self.assertIn("invalid_json", record["scoring"]["error_counts"])
        self.assertEqual(len(calls), EPISODE_COUNT)

    def test_generation_failure_keeps_earlier_predictions(self):
        access, calls, _ = make_access(fail_at=1)
        run = self.build(access=(access, calls, make_access()[2]))
        record = run.run()
        self.assertEqual(record["exit_status"], "failed")
        self.assertEqual(record["failure"]["kind"], "RuntimeError")
        self.assertEqual(record["partial"]["predictions_recorded"], 1)
        self.assertEqual(len(calls), 2)  # the failing call is not retried

    def test_protocol_mismatch_is_stopped_before_generating(self):
        self.plan_path = fixture_plan(self.tmp, overrides={"runner_revision": "someone-else"})
        access, calls, _ = make_access()
        run = self.build(access=(access, calls, make_access()[2]))
        record = run.run()
        self.assertEqual(record["failure"]["kind"], "protocol-mismatch")
        self.assertEqual(calls, [])

    def test_a_failed_run_still_writes_its_manifest(self):
        access, calls, _ = make_access(fail_at=0)
        run = self.build(access=(access, calls, make_access()[2]))
        record = run.run()
        manifest = json.loads((self.run_dir_path() / "manifest.json").read_text())
        self.assertEqual(manifest["exit_status"], "failed")
        self.assertEqual(manifest["run_id"], RUN_ID)
        self.assertEqual(manifest["attempts_per_episode"], 1)


class BoundaryTests(RunTestCase):
    def test_no_model_library_is_imported_by_a_full_fake_run(self):
        run = self.build()
        run.run()
        self.assertNotIn("torch", sys.modules)
        self.assertNotIn("transformers", sys.modules)

    def test_main_fails_closed_without_an_authorization_file(self):
        argv = [
            "--run-id", RUN_ID, "--owner", "eido",
            "--plan", str(self.plan_path),
            "--protocol", str(self.tmp / "protocol.json"),
            "--r02-record", str(PIN_DIR),
            "--run-dir", RUN_DIR,
            "--authorization-file", str(self.tmp / "absent.json"),
        ]
        with contextlib.redirect_stdout(self._out), contextlib.redirect_stderr(self._err):
            code = main(argv)
        self.assertEqual(code, 2)
        self.assertIn("gate closed", self._err.getvalue())
        self.assertFalse((self.tmp / "results").exists())

    def test_main_fails_closed_on_an_off_layout_run_directory(self):
        auth = self.tmp / "auth.json"
        auth.write_text(json.dumps(authorization().to_record()), encoding="utf-8")
        argv = [
            "--run-id", RUN_ID, "--owner", "eido",
            "--plan", str(self.plan_path),
            "--protocol", str(self.tmp / "protocol.json"),
            "--r02-record", str(PIN_DIR),
            "--run-dir", "results/E01/e01-pilot-009",
            "--authorization-file", str(auth),
        ]
        with contextlib.redirect_stdout(self._out), contextlib.redirect_stderr(self._err):
            code = main(argv)
        self.assertEqual(code, 2)
        self.assertIn("off the layout", self._err.getvalue())
        self.assertFalse((self.tmp / "results").exists())


if __name__ == "__main__":
    unittest.main()
