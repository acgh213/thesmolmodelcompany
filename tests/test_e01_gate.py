"""Tests for the E01 execution gate (issue #21)."""

import json
import tempfile
import unittest
from pathlib import Path

from scripts.e01_gate import (
    EXPERIMENT_ID,
    KNOWN_SCOPES,
    SCOPE_E01_EXECUTION,
    AuthorizationError,
    GateClosed,
    OperatorRecord,
    expected_run_dir,
    require_e01_authorization,
    validate_run_target,
)

RUN_ID = "e01-pilot-001"


def make_record(**overrides):
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
    return OperatorRecord.from_mapping(data)


class OperatorRecordTests(unittest.TestCase):
    def test_matching_grant_is_returned(self):
        record = make_record()
        self.assertIs(require_e01_authorization(record, run_id=RUN_ID), record)

    def test_missing_grant_fails_closed(self):
        with self.assertRaises(GateClosed):
            require_e01_authorization(None, run_id=RUN_ID)

    def test_ungranted_record_fails_closed(self):
        with self.assertRaises(GateClosed):
            require_e01_authorization(make_record(granted=False), run_id=RUN_ID)

    def test_readiness_smoke_scope_does_not_open_the_execution_gate(self):
        # The merged R02 grant is explicitly "Not authorization for training,
        # tuning, evaluation, or any experiment". It must not be spendable here.
        with self.assertRaises(AuthorizationError):
            make_record(scope="r02-readiness-smoke")

    def test_unknown_scope_is_rejected(self):
        with self.assertRaises(AuthorizationError):
            make_record(scope="e01-everything")

    def test_only_the_declared_scope_is_known(self):
        self.assertEqual(KNOWN_SCOPES, (SCOPE_E01_EXECUTION,))

    def test_record_naming_another_run_does_not_cover_this_one(self):
        record = make_record(run_id="e01-pilot-002")
        with self.assertRaises(GateClosed) as ctx:
            require_e01_authorization(record, run_id=RUN_ID)
        self.assertIn("e01-pilot-002", str(ctx.exception))

    def test_record_without_a_run_id_is_rejected(self):
        for value in ("UNSET", "", None):
            with self.subTest(value=value):
                with self.assertRaises(AuthorizationError):
                    make_record(run_id=value)

    def test_record_with_a_malformed_run_id_is_rejected(self):
        with self.assertRaises(AuthorizationError):
            make_record(run_id="pilot-001")

    def test_record_naming_another_experiment_is_rejected(self):
        with self.assertRaises(AuthorizationError):
            make_record(experiment="E03")

    def test_missing_operator_go_is_rejected(self):
        with self.assertRaises(AuthorizationError):
            make_record(operator_go="UNSET")

    def test_missing_operator_timestamp_is_rejected(self):
        with self.assertRaises(AuthorizationError):
            make_record(operator_go_received_before_utc="")

    def test_reviewer_only_flag_is_required(self):
        # Without it the file could read as though the reviewer authorized the run.
        for value in (False, "true", None):
            with self.subTest(value=value):
                with self.assertRaises(AuthorizationError):
                    make_record(procedure_reviewer_only=value)

    def test_missing_base_field_is_rejected(self):
        with self.assertRaises(AuthorizationError):
            OperatorRecord.from_mapping(
                {
                    "granted": True,
                    "scope": SCOPE_E01_EXECUTION,
                    "reference": "issue #21",
                    "approved_by": "vesper",
                    "experiment": EXPERIMENT_ID,
                    "run_id": RUN_ID,
                    "operator_go": "cassie",
                    "operator_go_received_before_utc": "2026-09-22T00:10:00Z",
                    "procedure_reviewer_only": True,
                }
            )

    def test_non_boolean_granted_is_rejected(self):
        with self.assertRaises(AuthorizationError):
            make_record(granted="yes")

    def test_unset_reference_is_rejected(self):
        with self.assertRaises(AuthorizationError):
            make_record(reference="UNSET")

    def test_extra_fields_are_carried_into_the_record(self):
        record = make_record(procedure_review="PR review 43")
        self.assertEqual(record.to_record()["procedure_review"], "PR review 43")

    def test_record_round_trips_through_json(self):
        # The UNSET sentinel is compared by value, so a JSON round trip is safe.
        record = make_record()
        reloaded = OperatorRecord.from_mapping(json.loads(json.dumps(record.to_record())))
        self.assertEqual(reloaded.run_id, record.run_id)

    def test_from_file_reads_a_json_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "operator-record.json"
            path.write_text(json.dumps(make_record().to_record()), encoding="utf-8")
            self.assertEqual(OperatorRecord.from_file(path).run_id, RUN_ID)

    def test_from_file_missing_path_fails_closed(self):
        with self.assertRaises(GateClosed):
            OperatorRecord.from_file("/nonexistent/operator-record.json")

    def test_from_file_malformed_json_is_a_gate_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "operator-record.json"
            path.write_text("{not json", encoding="utf-8")
            with self.assertRaises(AuthorizationError):
                OperatorRecord.from_file(path)


class RunTargetTests(unittest.TestCase):
    def test_named_run_directory_is_the_only_layout(self):
        self.assertEqual(expected_run_dir(RUN_ID), "results/E01/e01-pilot-001")

    def test_valid_target_has_no_problems(self):
        self.assertEqual(
            validate_run_target(run_id=RUN_ID, run_dir=expected_run_dir(RUN_ID)), []
        )

    def test_matching_target_without_a_directory_has_no_problems(self):
        self.assertEqual(validate_run_target(run_id=RUN_ID), [])

    def test_off_layout_directory_is_rejected(self):
        problems = validate_run_target(run_id=RUN_ID, run_dir="results/R02/r02-smoke-001")
        self.assertTrue(problems)
        self.assertIn("off the layout", problems[0])

    def test_run_id_form_is_enforced(self):
        for value in ("e01-pilot-1", "e01-pilot-0001", "e01-001", "", None):
            with self.subTest(value=value):
                self.assertTrue(validate_run_target(run_id=value))


if __name__ == "__main__":
    unittest.main()
