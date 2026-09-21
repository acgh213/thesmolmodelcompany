import unittest
from unittest.mock import patch

import smolmodelcompany.finite_state as finite_state
from smolmodelcompany.finite_state import (
    generate_episode,
    generate_planning_task,
    generate_tracking_task,
    planning_reference,
    small_planning_audit,
    small_state_audit,
    tracking_generate,
    tracking_reference,
    validate_task,
)


class FiniteStateTests(unittest.TestCase):
    def test_tracking_references_agree_on_generated_tasks(self):
        for seed in range(100):
            task = generate_tracking_task(seed)
            self.assertEqual(tracking_generate(task.initial, task.trace), tracking_reference(task.initial, task.trace))
            validate_task(task)

    def test_planning_reference_finds_one_step_goal(self):
        task = generate_planning_task(17)
        self.assertIn(planning_reference(task.initial, task.goal, task.actions), (1, 2))
        validate_task(task)

    def test_tracking_episode_is_candidate_safe(self):
        payload = generate_episode(4, "tracking").candidate_payload({"max_tokens": 32})
        self.assertNotIn("answer", payload)
        self.assertNotIn("seed", payload["input"])

    def test_planning_episode_is_candidate_safe(self):
        payload = generate_episode(4, "planning").candidate_payload({"max_tokens": 32})
        self.assertNotIn("answer", payload)
        self.assertNotIn("shortest_length", payload["input"])

    def test_tracking_generation_is_deterministic(self):
        self.assertEqual(generate_episode(22).scorer_record(), generate_episode(22).scorer_record())

    def test_planning_generation_is_deterministic(self):
        self.assertEqual(
            generate_episode(22, "planning").scorer_record(),
            generate_episode(22, "planning").scorer_record(),
        )

    def test_small_tracking_audit_is_exhaustive_for_declared_fixture(self):
        self.assertEqual(small_state_audit(), [])

    def test_small_planning_audit_is_exhaustive_for_declared_fixture(self):
        self.assertEqual(small_planning_audit(), [])

    def test_planning_audit_does_not_reuse_tracking_reference(self):
        with patch.object(finite_state, "tracking_reference", side_effect=AssertionError("wrong reference")):
            self.assertEqual(small_planning_audit(), [])

    def test_unreachable_planning_goal_returns_none(self):
        initial = (("x", 0), ("y", 0))
        goal = (("x", 1), ("y", 1))
        actions = ({"name": "flip_x", "kind": "flip", "variable": "x"},)
        self.assertIsNone(planning_reference(initial, goal, actions, max_horizon=4))


if __name__ == "__main__":
    unittest.main()
