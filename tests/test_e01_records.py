import json
import tempfile
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

import e01_records
import e01_score


class E01RecordsProtocolTests(unittest.TestCase):
    def test_frozen_manifest_counts_and_hashes(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            candidates, references, _ = e01_records.build(
                {"development": list(range(1000, 1008)), "final": list(range(2000, 2020)) + list(range(2021, 2025))}
            )
            self.assertEqual(len(candidates), 32)
            self.assertEqual(len(references), 32)
            self.assertEqual([row["index"] for row in candidates[:8]], list(range(8)))
            self.assertEqual([row["index"] for row in candidates[8:]], list(range(8, 32)))
            e01_records._write_jsonl(out / "manifest.jsonl", candidates)
            e01_records._write_jsonl(out / "refs.jsonl", references)
            self.assertEqual(e01_records._sha256(out / "manifest.jsonl"), "ecb832a72bb39c87ba9821c07a31e538d735632acd0cf0b01f39eebc7ac14b7c")
            self.assertEqual(e01_records._sha256(out / "refs.jsonl"), "53f235d147f2da4d922448c44904a3fbcd2916d7ee6f034d35179ec34e144562")

    def test_frozen_hash_verification_rejects_tampering(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            candidates, references, _ = e01_records.build(
                {"development": list(range(1000, 1008)), "final": list(range(2000, 2020)) + list(range(2021, 2025))}
            )
            manifest = out / "manifest.jsonl"
            refs = out / "refs.jsonl"
            e01_records._write_jsonl(manifest, candidates)
            e01_records._write_jsonl(refs, references)
            self.assertEqual(
                e01_records.verify_frozen_outputs(ROOT / "configs/e01-execution-plan.json", manifest, refs)["episode_manifest_sha256"],
                "ecb832a72bb39c87ba9821c07a31e538d735632acd0cf0b01f39eebc7ac14b7c",
            )
            manifest.write_text(manifest.read_text() + "tampered\n")
            with self.assertRaises(ValueError):
                e01_records.verify_frozen_outputs(ROOT / "configs/e01-execution-plan.json", manifest, refs)

    def test_candidate_surface_has_no_reserved_scorer_keys(self):
        candidates, _, _ = e01_records.build(
            {"development": [1000], "final": [2000]}
        )
        forbidden = {"answer", "latent_program", "seed", "input_state", "split", "provenance"}

        def visit(value):
            if isinstance(value, dict):
                for key, child in value.items():
                    self.assertNotIn(key, forbidden)
                    visit(child)
            elif isinstance(value, list):
                for child in value:
                    visit(child)

        visit(candidates)

    def test_scorer_is_independent_and_records_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            references = [{"episode_id": "a", "answer": [{"id": "r00"}]}, {"episode_id": "b", "answer": []}]
            predictions = [{"episode_id": "a", "text": "[{\"id\": \"r00\"}]"}, {"episode_id": "b", "text": "not json"}]
            e01_records._write_jsonl(root / "refs.jsonl", references)
            e01_records._write_jsonl(root / "preds.jsonl", predictions)
            report = e01_score.score(root / "refs.jsonl", root / "preds.jsonl")
            self.assertEqual(report["correct"], 1)
            self.assertEqual(report["error_counts"], {"correct": 1, "invalid_json": 1})

    def test_protocol_config_is_frozen(self):
        config = json.loads((ROOT / "configs/e01-protocol.json").read_text())
        self.assertEqual(config["claim_tier"], "development-signal")
        self.assertEqual(config["decoding"]["retries"], 0)
        self.assertEqual(len(config["task"]["final_seeds"]), 24)


if __name__ == "__main__":
    unittest.main()
