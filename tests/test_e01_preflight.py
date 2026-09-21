"""Tests for the E01 fail-closed preflight entry point (issue #21)."""

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.e01_gate import EXPERIMENT_ID, SCOPE_E01_EXECUTION
from scripts.e01_preflight import main

ROOT = Path(__file__).resolve().parents[1]
PIN_DIR = ROOT / "results" / "R02" / "r02-smoke-001"
PLAN_PATH = ROOT / "configs" / "e01-execution-plan.json"

RUN_ID = "e01-pilot-001"
RUN_DIR = f"results/E01/{RUN_ID}"


def record(**overrides):
    data = {
        "granted": True,
        "scope": SCOPE_E01_EXECUTION,
        "reference": "issue #21 / protocol PR",
        "approved_by": "vesper",
        "approved_at_utc": "2026-09-22T00:00:00Z",
        "experiment": EXPERIMENT_ID,
        "run_id": RUN_ID,
        "operator_go": "cassie",
        "operator_go_received_before_utc": "2026-09-22T00:10:00Z",
        "procedure_reviewer_only": True,
    }
    data.update(overrides)
    return data


def frozen_plan_file(directory):
    plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
    plan["artifacts"] = {
        "generator_revision": "r03-records-v1",
        "scorer_revision": "r03-records-v1",
        "episode_manifest_sha256": "a" * 64,
        "reference_answers_sha256": "b" * 64,
    }
    path = Path(directory) / "frozen-plan.json"
    path.write_text(json.dumps(plan), encoding="utf-8")
    return path


class PreflightTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self._cwd = os.getcwd()
        os.chdir(self.tmp)
        self.auth = self.tmp / "operator-record.json"
        self.auth.write_text(json.dumps(record()), encoding="utf-8")
        self._out = io.StringIO()
        self._err = io.StringIO()

    def tearDown(self):
        os.chdir(self._cwd)
        self._tmp.cleanup()

    def run_preflight(self, *extra, plan=None):
        argv = [
            "--run-id", RUN_ID,
            "--owner", "eido",
            "--plan", str(plan or PLAN_PATH),
            "--r02-record", str(PIN_DIR),
            "--run-dir", RUN_DIR,
            "--authorization-file", str(self.auth),
        ] + list(extra)
        with contextlib.redirect_stdout(self._out), contextlib.redirect_stderr(self._err):
            return main(argv)

    def assert_created_nothing(self):
        for name in ("results", "predictions", "raw"):
            self.assertFalse((self.tmp / name).exists(), f"{name}/ should not exist")

    def test_valid_record_against_the_unfrozen_plan_refuses_on_the_freeze(self):
        code = self.run_preflight()
        self.assertEqual(code, 1)
        self.assertIn("generator_revision", self._err.getvalue())
        self.assert_created_nothing()

    def test_frozen_plan_passes_and_still_executes_nothing(self):
        code = self.run_preflight(plan=frozen_plan_file(self.tmp))
        self.assertEqual(code, 0)
        report = json.loads(self._out.getvalue())
        self.assertFalse(report["executed"])
        self.assertFalse(report["run_directory_created"])
        self.assertEqual(report["run_id"], RUN_ID)
        self.assertEqual(report["owner"], "eido")
        self.assert_created_nothing()

    def test_missing_authorization_file_fails_closed(self):
        self.auth.unlink()
        code = self.run_preflight()
        self.assertEqual(code, 2)
        self.assertIn("gate closed", self._err.getvalue())
        self.assert_created_nothing()

    def test_readiness_smoke_scope_does_not_open_the_gate(self):
        self.auth.write_text(json.dumps(record(scope="r02-readiness-smoke")), encoding="utf-8")
        code = self.run_preflight()
        self.assertEqual(code, 2)
        self.assert_created_nothing()

    def test_ungranted_record_fails_closed(self):
        self.auth.write_text(json.dumps(record(granted=False)), encoding="utf-8")
        self.assertEqual(self.run_preflight(), 2)

    def test_record_naming_another_run_fails_closed(self):
        self.auth.write_text(json.dumps(record(run_id="e01-pilot-002")), encoding="utf-8")
        code = self.run_preflight()
        self.assertEqual(code, 2)
        self.assertIn("e01-pilot-002", self._err.getvalue())
        self.assert_created_nothing()

    def test_record_without_an_operator_go_fails_closed(self):
        self.auth.write_text(json.dumps(record(operator_go="UNSET")), encoding="utf-8")
        self.assertEqual(self.run_preflight(), 2)

    def test_off_layout_run_id_fails_closed(self):
        argv = [
            "--run-id", "e01-pilot-1",
            "--owner", "eido",
            "--plan", str(PLAN_PATH),
            "--r02-record", str(PIN_DIR),
            "--authorization-file", str(self.auth),
        ]
        with contextlib.redirect_stdout(self._out), contextlib.redirect_stderr(self._err):
            code = main(argv)
        self.assertEqual(code, 2)
        self.assert_created_nothing()

    def test_off_layout_run_directory_fails_closed(self):
        code = self.run_preflight()
        self.assertEqual(code, 1)  # control: this record/target combination gets past the gate
        self._err.truncate(0)
        self._err.seek(0)
        argv = [
            "--run-id", RUN_ID,
            "--owner", "eido",
            "--plan", str(PLAN_PATH),
            "--r02-record", str(PIN_DIR),
            "--run-dir", "results/E01/e01-pilot-007",
            "--authorization-file", str(self.auth),
        ]
        with contextlib.redirect_stdout(self._out), contextlib.redirect_stderr(self._err):
            code = main(argv)
        self.assertEqual(code, 2)
        self.assertIn("off the layout", self._err.getvalue())
        self.assert_created_nothing()

    def test_record_out_under_results_is_refused(self):
        code = self.run_preflight("--record-out", f"{RUN_DIR}/preflight.json")
        self.assertEqual(code, 2)
        self.assertIn("must not write into a run directory", self._err.getvalue())
        self.assert_created_nothing()

    def test_record_out_elsewhere_is_written(self):
        target = self.tmp / "preflight.json"
        code = self.run_preflight("--record-out", str(target), plan=frozen_plan_file(self.tmp))
        self.assertEqual(code, 0)
        written = json.loads(target.read_text(encoding="utf-8"))
        self.assertEqual(written["kind"], "e01-execution-preflight")
        self.assert_created_nothing()

    def test_declared_plan_substituting_the_model_is_refused(self):
        plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
        plan["model"]["revision"] = "main"
        plan["artifacts"] = {
            "generator_revision": "r03-records-v1",
            "scorer_revision": "r03-records-v1",
            "episode_manifest_sha256": "a" * 64,
            "reference_answers_sha256": "b" * 64,
        }
        path = self.tmp / "substituted.json"
        path.write_text(json.dumps(plan), encoding="utf-8")
        code = self.run_preflight(plan=path)
        self.assertEqual(code, 1)
        self.assertIn("revision", self._err.getvalue())

    def test_no_model_library_is_imported(self):
        self.run_preflight(plan=frozen_plan_file(self.tmp))
        self.assertNotIn("torch", sys.modules)
        self.assertNotIn("transformers", sys.modules)


if __name__ == "__main__":
    unittest.main()
