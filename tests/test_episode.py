import math
import unittest

from smolmodelcompany import Episode, __version__, canonical_json


def make_episode(**overrides):
    data = {
        "protocol_version": "r03-v1",
        "family": "records",
        "split": "development",
        "seed": 73,
        "input_state": {"records": [{"id": "r-01", "score": 4}]},
        "rendered_input": {"records": [{"name": "Ada", "score": 4}]},
        "support": [],
        "query": {"instruction": "return the score"},
        "answer": [{"score": 4}],
        "latent_program": {"op": "project", "fields": ["score"]},
        "structure_signature": "project(record:int)",
        "presentation_variant": {"surface": "symbolic"},
        "difficulty": {"operations": 1},
        "provenance": {"generator_version": "r03-v1"},
    }
    data.update(overrides)
    return Episode(**data)


def all_keys(value):
    if isinstance(value, dict):
        yield from value
        for child in value.values():
            yield from all_keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from all_keys(child)


class PackageTests(unittest.TestCase):
    def test_version(self):
        self.assertEqual(__version__, "0.1.0")


class CanonicalJSONTests(unittest.TestCase):
    def test_key_order_does_not_change_serialization(self):
        self.assertEqual(canonical_json({"b": [2, 1], "a": {"z": True}}), '{"a":{"z":true},"b":[2,1]}')

    def test_rejects_non_json_values(self):
        with self.assertRaises(TypeError):
            canonical_json({"unsupported": {1, 2}})
        with self.assertRaises(TypeError):
            canonical_json({1: "not-a-string-key"})
        with self.assertRaises(ValueError):
            canonical_json({"not-finite": math.nan})


class EpisodeTests(unittest.TestCase):
    def test_hash_is_stable_across_input_mapping_order(self):
        first = make_episode(input_state={"b": 2, "a": 1})
        second = make_episode(input_state={"a": 1, "b": 2})
        self.assertEqual(first.record_hash(), second.record_hash())

    def test_record_freezes_nested_json(self):
        source = {"records": [{"score": 4}]}
        episode = make_episode(input_state=source)
        source["records"][0]["score"] = 99
        self.assertEqual(episode.scorer_record()["input_state"]["records"][0]["score"], 4)
        with self.assertRaises(TypeError):
            episode.input_state["new"] = "field"  # type: ignore[index]

    def test_candidate_payload_omits_scorer_side_fields(self):
        payload = make_episode().candidate_payload({"wall_seconds": 10})
        self.assertEqual(payload["family"], "records")
        self.assertIn("task_id", payload)
        self.assertEqual(payload["input"], {"records": [{"name": "Ada", "score": 4}]})
        self.assertEqual(payload["declared_budget"], {"wall_seconds": 10})
        forbidden = {"answer", "latent_program", "seed", "input_state", "split", "provenance"}
        self.assertTrue(forbidden.isdisjoint(set(all_keys(payload))))

    def test_candidate_id_does_not_track_hidden_scorer_state(self):
        baseline = make_episode()
        changed_hidden_state = make_episode(
            split="final",
            seed=999,
            input_state={"unrendered": "different"},
            answer=[{"score": 999}],
            latent_program={"op": "derive", "field": "score"},
            provenance={"generator_version": "different"},
        )
        self.assertNotEqual(baseline.record_hash(), changed_hidden_state.record_hash())
        self.assertEqual(baseline.candidate_id(), changed_hidden_state.candidate_id())
        self.assertEqual(
            baseline.candidate_payload({"wall_seconds": 10})["task_id"],
            changed_hidden_state.candidate_payload({"wall_seconds": 10})["task_id"],
        )

    def test_candidate_visible_json_and_budget_reject_reserved_keys(self):
        with self.assertRaises(ValueError):
            make_episode(rendered_input={"nested": {"answer": "leak"}})
        with self.assertRaises(ValueError):
            make_episode(query={"steps": [{"seed": 42}]})
        with self.assertRaises(ValueError):
            make_episode().candidate_payload({"limits": {"provenance": "leak"}})

    def test_candidate_payload_is_a_fresh_transport_object(self):
        episode = make_episode()
        payload = episode.candidate_payload({"wall_seconds": 10})
        payload["input"]["records"][0]["score"] = 999
        self.assertEqual(episode.candidate_payload({"wall_seconds": 10})["input"]["records"][0]["score"], 4)

    def test_protocol_constraints_are_validated(self):
        with self.assertRaises(ValueError):
            make_episode(family="unknown")
        with self.assertRaises(ValueError):
            make_episode(split="preview")
        with self.assertRaises(TypeError):
            make_episode(seed=True)


if __name__ == "__main__":
    unittest.main()
