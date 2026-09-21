import unittest

from smolmodelcompany.records import (
    SMALL_CASE_AUDIT_CASES,
    generator_execute,
    generate_episode,
    generate_task,
    reference_execute,
    small_case_audit,
    structure_signature,
)


class RecordsTests(unittest.TestCase):
    def test_generation_is_deterministic(self):
        first, second = generate_task(41), generate_task(41)
        self.assertEqual(first, second)
        self.assertEqual(generator_execute(first.records, first.program), reference_execute(second.records, second.program))

    def test_generated_episode_has_candidate_safe_surface_and_reference_answer(self):
        episode = generate_episode(73)
        self.assertEqual(episode.family, "records")
        record = episode.scorer_record()
        self.assertEqual(
            record["answer"],
            reference_execute(record["input_state"]["records"], tuple(record["latent_program"]["pipeline"])),
        )
        payload = episode.candidate_payload({"wall_seconds": 10})
        self.assertNotIn("answer", payload)
        self.assertNotIn("latent_program", payload)
        self.assertIn("operations", payload["input"])

    def test_small_enumerated_audit_has_no_disagreement(self):
        self.assertEqual(SMALL_CASE_AUDIT_CASES, 24)
        self.assertEqual(small_case_audit(), [])

    def test_sort_rejects_rows_that_lost_stable_identity(self):
        records = ({"id": "r01", "score": 5},)
        program = (
            {"kind": "project", "fields": ["score"]},
            {"kind": "sort", "field": "score", "direction": "asc"},
        )
        with self.assertRaisesRegex(ValueError, "stable id"):
            generator_execute(records, program)
        with self.assertRaisesRegex(ValueError, "stable id"):
            reference_execute(records, program)

    def test_effective_seed_reproduces_retained_episode(self):
        for requested in range(1, 100):
            episode = generate_episode(requested)
            reproduced = generate_episode(episode.seed)
            self.assertEqual(episode.scorer_record(), reproduced.scorer_record())

    def test_descending_sort_keeps_immutable_id_ties_ascending(self):
        records = ({"id": "r02", "score": 5}, {"id": "r01", "score": 5}, {"id": "r03", "score": 4})
        program = ({"kind": "sort", "field": "score", "direction": "desc"},)
        expected = [{"id": "r01", "score": 5}, {"id": "r02", "score": 5}, {"id": "r03", "score": 4}]
        self.assertEqual(generator_execute(records, program), expected)
        self.assertEqual(reference_execute(records, program), expected)

    def test_signature_ignores_literal_values(self):
        first = ({"kind": "filter", "field": "score", "comparator": "gt", "literal": 2},)
        second = ({"kind": "filter", "field": "score", "comparator": "gt", "literal": 9},)
        self.assertEqual(structure_signature(first), structure_signature(second))

    def test_group_pipeline_is_cross_checked(self):
        for seed in range(1, 20):
            task = generate_task(seed)
            self.assertEqual(generator_execute(task.records, task.program), reference_execute(task.records, task.program))


if __name__ == "__main__":
    unittest.main()
