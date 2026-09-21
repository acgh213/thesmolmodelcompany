"""Tests for the E01 pinned identity and plan checks (issue #21)."""

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from scripts import e01_identity
from scripts.e01_identity import (
    PIN_RECORD_DIR,
    PinError,
    freeze_problems,
    load_pin,
    load_plan,
    validate_declared_identity,
    validate_plan,
)

ROOT = Path(__file__).resolve().parents[1]
PIN_DIR = ROOT / PIN_RECORD_DIR
PLAN_PATH = ROOT / "configs" / "e01-execution-plan.json"


def frozen_plan():
    """A plan whose Research B fields are frozen, for the happy path only."""
    plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
    plan["artifacts"] = {
        "generator_revision": "r03-records-v1",
        "scorer_revision": "r03-records-v1",
        "episode_manifest_sha256": "a" * 64,
        "reference_answers_sha256": "b" * 64,
    }
    return plan


class LoadPinTests(unittest.TestCase):
    def test_pin_is_read_from_the_merged_readiness_record(self):
        pin = load_pin(PIN_DIR)
        self.assertEqual(pin.repo_id, "Qwen/Qwen2.5-1.5B")
        self.assertEqual(pin.revision, "8faed761d45a263340a0528343f099c05c9a4323")
        self.assertEqual(pin.precision, "bfloat16")
        self.assertEqual(pin.source, "huggingface")

    def test_pin_carries_the_recorded_file_digests(self):
        pin = load_pin(PIN_DIR)
        digests = pin.file_digests()
        self.assertEqual(
            digests["model.safetensors"],
            "a961db72e75d52b18e6b0c9d379e51a26973b233385e0e127fdda7d648aec796",
        )
        self.assertEqual(len(pin.files), 7)

    def test_identity_is_exactly_the_pinned_four_fields(self):
        self.assertEqual(
            sorted(load_pin(PIN_DIR).identity()), ["precision", "repo_id", "revision", "source"]
        )

    def test_internally_inconsistent_record_is_not_a_pin(self):
        # The readiness smoke wrote the identity twice; a record whose own two
        # files disagree must not be accepted as a pin.
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "r02-smoke-001"
            shutil.copytree(PIN_DIR, target)
            run_manifest = target / "manifest.json"
            data = json.loads(run_manifest.read_text(encoding="utf-8"))
            data["model"]["repo_id"] = "Qwen/Qwen2.5-7B"
            run_manifest.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaises(PinError) as ctx:
                load_pin(target)
            self.assertIn("internally inconsistent", str(ctx.exception))

    def test_missing_record_fails_closed(self):
        with self.assertRaises(PinError):
            load_pin("/nonexistent/r02-smoke-001")


class DeclaredIdentityTests(unittest.TestCase):
    def setUp(self):
        self.pin = load_pin(PIN_DIR)

    def test_matching_declaration_is_accepted(self):
        self.assertEqual(validate_declared_identity(self.pin.identity(), self.pin), [])

    def test_every_identity_field_is_pinned_not_just_the_revision(self):
        for field in ("source", "repo_id", "precision", "revision"):
            with self.subTest(field=field):
                declared = dict(self.pin.identity())
                declared[field] = "something-else"
                problems = validate_declared_identity(declared, self.pin)
                self.assertTrue(problems)

    def test_unset_field_is_not_a_value(self):
        declared = dict(self.pin.identity())
        declared["revision"] = "UNSET"
        self.assertTrue(validate_declared_identity(declared, self.pin))

    def test_non_hex_revision_is_rejected(self):
        declared = dict(self.pin.identity())
        declared["revision"] = "main"
        problems = validate_declared_identity(declared, self.pin)
        self.assertTrue(any("40-char hex" in p for p in problems))

    def test_identity_survives_a_json_round_trip(self):
        declared = json.loads(json.dumps(self.pin.identity()))
        self.assertEqual(validate_declared_identity(declared, self.pin), [])


class PlanTests(unittest.TestCase):
    def setUp(self):
        self.pin = load_pin(PIN_DIR)

    def test_committed_plan_is_loadable_and_names_the_pinned_model(self):
        plan = load_plan(PLAN_PATH)
        self.assertEqual(plan["kind"], "e01-execution-plan")
        self.assertEqual(validate_declared_identity(plan["model"], self.pin), [])

    def test_committed_plan_is_not_frozen(self):
        # The executable form of "protocol freeze": on the merged main state the
        # generator/scorer revisions are still UNSET, so the gate must not open.
        problems = freeze_problems(load_plan(PLAN_PATH))
        self.assertEqual(len(problems), 4)
        self.assertTrue(any("generator_revision" in p for p in problems))
        self.assertTrue(any("scorer_revision" in p for p in problems))

    def test_committed_plan_fails_validation_on_the_freeze(self):
        problems = validate_plan(load_plan(PLAN_PATH), self.pin)
        self.assertEqual(len(problems), 4)

    def test_frozen_plan_validates_clean(self):
        self.assertEqual(validate_plan(frozen_plan(), self.pin), [])

    def test_plan_naming_another_experiment_is_rejected(self):
        plan = frozen_plan()
        plan["experiment"] = "E03"
        problems = validate_plan(plan, self.pin)
        self.assertTrue(any("names experiment" in p for p in problems))

    def test_plan_substituting_the_model_is_rejected(self):
        plan = frozen_plan()
        plan["model"]["repo_id"] = "Qwen/Qwen2.5-7B"
        problems = validate_plan(plan, self.pin)
        self.assertTrue(any("repo_id" in p for p in problems))

    def test_plan_without_an_artifacts_object_is_rejected(self):
        plan = frozen_plan()
        del plan["artifacts"]
        self.assertTrue(freeze_problems(plan))

    def test_wrong_plan_kind_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "plan.json"
            path.write_text(json.dumps({"kind": "something-else"}), encoding="utf-8")
            with self.assertRaises(PinError):
                load_plan(path)


class BoundaryTests(unittest.TestCase):
    def test_module_defines_no_transport_seam(self):
        # Artifact retrieval is r02_artifacts.py; it is not re-implemented here.
        self.assertFalse(hasattr(e01_identity, "fetch_and_hash"))
        self.assertFalse(hasattr(e01_identity, "ArtifactTransport"))

    def test_importing_the_module_loads_no_model_library(self):
        self.assertNotIn("torch", sys.modules)
        self.assertNotIn("transformers", sys.modules)


if __name__ == "__main__":
    unittest.main()
