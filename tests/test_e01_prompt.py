"""Tests for the frozen E01 prompt renderer (issue #24)."""

import hashlib
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from scripts.e01_prompt import (
    INSTRUCTION,
    OUTPUT_HEADER,
    PROMPT_FIELDS,
    PROMPT_RENDERER_REVISION,
    PROMPT_SET_SEPARATOR,
    TASK_HEADER,
    PromptError,
    find_forbidden_keys,
    instruction_sha256,
    payloads_from_manifest,
    prompt_set_sha256,
    prompt_sha256,
    render_prompt,
    task_subset,
)

# The reviewed text, repeated here as a literal so a change to the module cannot
# quietly satisfy its own test.
REVIEWED_INSTRUCTION = "You are a deterministic JSON transformation executor. Apply the primitive operations to the supplied records. Return only one JSON array of result records, with no explanation or markdown."


def payload(**overrides):
    base = {
        "task_id": "abc123",
        "family": "records",
        "input": {"records": [{"id": "r00", "points": 3}]},
        "support": [],
        "query": {"return": "all records with points > 1"},
        "declared_budget": {"max_new_tokens": 256, "time_cap_seconds": 1200},
        "presentation_variant": {"surface": "symbolic"},
    }
    base.update(overrides)
    return base


def expected_bytes(pl):
    """Independently reproduce the frozen serialisation contract."""
    task = {name: pl[name] for name in ("family", "input", "query")}
    canonical = json.dumps(task, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return REVIEWED_INSTRUCTION + "\n\nTASK JSON:\n" + canonical + "\n\nOUTPUT JSON:\n"


class FrozenTextTests(unittest.TestCase):
    def test_instruction_is_byte_for_byte_the_reviewed_text(self):
        self.assertEqual(INSTRUCTION, REVIEWED_INSTRUCTION)

    def test_headers_are_exactly_as_frozen(self):
        self.assertEqual(TASK_HEADER, "\n\nTASK JSON:\n")
        self.assertEqual(OUTPUT_HEADER, "\n\nOUTPUT JSON:\n")

    def test_renderer_revision_is_versioned(self):
        self.assertEqual(PROMPT_RENDERER_REVISION, "e01-prompt-v1")

    def test_rendered_prompt_is_exactly_the_frozen_bytes(self):
        self.assertEqual(render_prompt(payload()), expected_bytes(payload()))

    def test_rendered_prompt_starts_with_the_instruction_and_ends_with_the_header(self):
        rendered = render_prompt(payload())
        self.assertTrue(rendered.startswith(REVIEWED_INSTRUCTION))
        self.assertTrue(rendered.endswith("\n\nOUTPUT JSON:\n"))

    def test_instruction_sha256_is_the_digest_of_the_frozen_text(self):
        self.assertEqual(
            instruction_sha256(), hashlib.sha256(REVIEWED_INSTRUCTION.encode("utf-8")).hexdigest()
        )


class SerialisationTests(unittest.TestCase):
    def test_only_three_fields_reach_the_prompt(self):
        self.assertEqual(PROMPT_FIELDS, ("family", "input", "query"))
        self.assertEqual(
            sorted(task_subset(payload())), ["family", "input", "query"]
        )

    def test_declared_budget_is_not_rendered(self):
        rendered = render_prompt(payload())
        self.assertNotIn("declared_budget", rendered)
        self.assertNotIn("time_cap_seconds", rendered)
        self.assertNotIn("256", rendered)

    def test_control_and_surface_fields_are_not_rendered(self):
        rendered = render_prompt(payload())
        for absent in ("task_id", "support", "presentation_variant", "symbolic", "abc123"):
            self.assertNotIn(absent, rendered)

    def test_serialisation_is_canonical_compact_and_sorted(self):
        rendered = render_prompt(payload())
        body = rendered.split(TASK_HEADER, 1)[1].split(OUTPUT_HEADER, 1)[0]
        self.assertNotIn(": ", body)
        self.assertNotIn(", ", body)
        self.assertEqual(body, json.dumps(json.loads(body), separators=(",", ":"), sort_keys=True))

    def test_rendering_is_deterministic(self):
        self.assertEqual(render_prompt(payload()), render_prompt(payload()))

    def test_key_insertion_order_does_not_change_the_bytes(self):
        first = payload()
        second = {
            "query": first["query"],
            "input": first["input"],
            "family": first["family"],
            "declared_budget": first["declared_budget"],
        }
        self.assertEqual(render_prompt(first), render_prompt(second))

    def test_non_ascii_survives_unmangled(self):
        rendered = render_prompt(payload(query={"return": "caf\u00e9 records"}))
        self.assertIn("caf\u00e9", rendered)


class ForbiddenFieldTests(unittest.TestCase):
    def test_each_reserved_key_is_rejected(self):
        for key in ("answer", "latent_program", "seed", "input_state", "split", "provenance"):
            with self.subTest(key=key):
                with self.assertRaises(PromptError):
                    render_prompt(payload(query={key: "x"}))

    def test_nested_reserved_key_is_rejected(self):
        pl = payload(input={"records": [{"id": "r00", "nested": {"answer": [1]}}]})
        with self.assertRaises(PromptError):
            render_prompt(pl)

    def test_reserved_key_inside_a_list_is_rejected(self):
        pl = payload(query={"items": [{"provenance": {"generator": "x"}}]})
        with self.assertRaises(PromptError):
            render_prompt(pl)

    def test_find_forbidden_keys_reports_paths(self):
        found = find_forbidden_keys({"a": {"seed": 1}, "b": [{"split": "final"}]})
        self.assertEqual(sorted(found), ["a.seed", "b[0].split"])

    def test_missing_field_is_rejected(self):
        pl = payload()
        del pl["query"]
        with self.assertRaises(PromptError):
            render_prompt(pl)

    def test_unset_field_is_rejected(self):
        with self.assertRaises(PromptError):
            render_prompt(payload(family="UNSET"))

    def test_null_field_is_rejected(self):
        with self.assertRaises(PromptError):
            render_prompt(payload(input=None))

    def test_non_object_payload_is_rejected(self):
        for value in ([], "x", 3, None):
            with self.subTest(value=value):
                with self.assertRaises(PromptError):
                    render_prompt(value)


class PromptSetDigestTests(unittest.TestCase):
    def setUp(self):
        self.payloads = [payload(query={"return": f"query {n}"}) for n in range(3)]

    def test_set_digest_is_deterministic(self):
        self.assertEqual(
            prompt_set_sha256(self.payloads), prompt_set_sha256(self.payloads)
        )

    def test_set_digest_is_hex_sha256(self):
        digest = prompt_set_sha256(self.payloads)
        self.assertEqual(len(digest), 64)
        self.assertTrue(all(c in "0123456789abcdef" for c in digest))

    def test_set_digest_covers_the_whole_set(self):
        # It must be the digest of the rendered prompts, framed one per episode,
        # not the digest of the instruction text alone.
        expected = hashlib.sha256(
            b"".join(render_prompt(p).encode("utf-8") + PROMPT_SET_SEPARATOR for p in self.payloads)
        ).hexdigest()
        self.assertEqual(prompt_set_sha256(self.payloads), expected)
        self.assertNotEqual(prompt_set_sha256(self.payloads), instruction_sha256())

    def test_set_digest_changes_with_one_prompt(self):
        changed = list(self.payloads)
        changed[2] = payload(query={"return": "a different request"})
        self.assertNotEqual(prompt_set_sha256(self.payloads), prompt_set_sha256(changed))

    def test_set_digest_is_order_sensitive(self):
        self.assertNotEqual(
            prompt_set_sha256(self.payloads), prompt_set_sha256(list(reversed(self.payloads)))
        )

    def test_per_episode_digest_matches_the_rendered_prompt(self):
        self.assertEqual(
            prompt_sha256(self.payloads[0]),
            hashlib.sha256(render_prompt(self.payloads[0]).encode("utf-8")).hexdigest(),
        )

    def test_empty_set_is_hashable(self):
        self.assertEqual(len(prompt_set_sha256([])), 64)


class ManifestTests(unittest.TestCase):
    def test_payloads_are_taken_in_manifest_order(self):
        rows = [{"index": i, "payload": payload(query={"return": f"q{i}"})} for i in range(4)]
        payloads = payloads_from_manifest(rows)
        self.assertEqual([p["query"]["return"] for p in payloads], ["q0", "q1", "q2", "q3"])

    def test_row_without_a_payload_is_rejected(self):
        with self.assertRaises(PromptError):
            payloads_from_manifest([{"index": 0}])

    def test_candidate_surface_of_a_real_episode_renders(self):
        # The prompt must render the actual frozen generator's candidate payload.
        from scripts.e01_records import build

        candidates, _, _ = build({"development": [1000], "final": []})
        rendered = render_prompt(candidates[0]["payload"])
        self.assertTrue(rendered.startswith(REVIEWED_INSTRUCTION))
        self.assertEqual(prompt_sha256(candidates[0]["payload"]), prompt_sha256(candidates[0]["payload"]))
        # E01 records carry no support, and the budget must stay out of the prompt.
        self.assertNotIn("declared_budget", rendered)


class BoundaryTests(unittest.TestCase):
    def test_renderer_imports_no_model_library(self):
        self.assertNotIn("torch", sys.modules)
        self.assertNotIn("transformers", sys.modules)


if __name__ == "__main__":
    unittest.main()
