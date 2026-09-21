"""Tests for the R02 pinned fetch-and-hash helpers (issue #17).

Every transport here is a pure in-memory fake: no test in this file touches the
network, downloads a weight, installs a package, or reserves a GPU.
"""

import hashlib
import inspect
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from scripts.r02_artifacts import (
    DECLARED_FILES,
    KIND_MANIFEST,
    REVISION,
    ArtifactError,
    HfHttpTransport,
    build_parser,
    declared_manifest,
    fetch_and_hash,
    main,
    validate_manifest,
)
from scripts.r02_gate import REDACTED
from scripts.r02_preflight import UNSET

PAYLOADS = {path: (path.encode() + b"-payload") for path, _ in DECLARED_FILES}
OTHER_REVISION = "0" * 40


class FakeTransport:
    """The contract a real transport must satisfy, with nothing outside memory."""

    def __init__(self, payloads=None, resolved=REVISION, failure=None):
        self.payloads = dict(payloads if payloads is not None else PAYLOADS)
        self.resolved = resolved
        self.failure = failure
        self.downloads = []
        self.revisions_requested = []

    def resolve_revision(self, repo_id, requested_revision):
        self.revisions_requested.append((repo_id, requested_revision))
        return self.resolved

    def download(self, repo_id, revision, path, destination):
        self.downloads.append(path)
        if self.failure is not None:
            raise self.failure
        if path not in self.payloads:
            raise ArtifactError(f"missing artifact {path}")
        target = Path(destination)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(self.payloads[path])
        return len(self.payloads[path])


class DeclaredManifestTests(unittest.TestCase):
    def test_pin_is_a_full_commit_sha(self):
        manifest = declared_manifest()
        self.assertRegex(manifest["requested_revision"], r"^[0-9a-f]{40}$")
        self.assertEqual(manifest["requested_revision"], REVISION)

    def test_measurements_are_explicitly_unset(self):
        manifest = declared_manifest()
        self.assertEqual(manifest["kind"], KIND_MANIFEST)
        self.assertEqual(manifest["resolved_revision"], UNSET)
        self.assertEqual(manifest["license"], UNSET)
        self.assertEqual(manifest["totals"]["observed_bytes"], UNSET)
        for entry in manifest["files"]:
            self.assertEqual(entry["expected_sha256"], UNSET)
            self.assertEqual(entry["expected_bytes"], UNSET)
            self.assertEqual(entry["observed_sha256"], UNSET)
            self.assertTrue(entry["required"])

    def test_scaffold_passes_validation(self):
        self.assertEqual(validate_manifest(declared_manifest()), [])

    def test_validation_flags_a_non_sha_revision(self):
        manifest = declared_manifest()
        manifest["requested_revision"] = "main"
        self.assertTrue(any("commit SHA" in err for err in validate_manifest(manifest)))

    def test_validation_flags_an_undeclared_path(self):
        manifest = declared_manifest()
        manifest["files"].append({"path": "extra.safetensors", "expected_sha256": UNSET})
        self.assertTrue(any("undeclared" in err for err in validate_manifest(manifest)))

    def test_validation_flags_a_malformed_hash(self):
        manifest = declared_manifest()
        manifest["files"][0]["expected_sha256"] = "not-a-hash"
        self.assertTrue(any("SHA-256" in err for err in validate_manifest(manifest)))


class FetchTests(unittest.TestCase):
    def test_first_fetch_records_observation_without_claiming_a_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            transport = FakeTransport()
            report = fetch_and_hash(transport=transport, destination=tmp, env={})
            self.assertEqual(report["status"], "ok")
            self.assertEqual(report["resolved_revision"], REVISION)
            self.assertEqual(report["error"], UNSET)
            self.assertEqual(len(report["files"]), len(DECLARED_FILES))
            for entry in report["files"]:
                self.assertEqual(entry["status"], "first-observation")
                self.assertEqual(entry["observed_sha256"], hashlib.sha256(PAYLOADS[entry["path"]]).hexdigest())
            manifest = report["manifest"]
            self.assertEqual(manifest["resolved_revision"], REVISION)
            self.assertEqual(manifest["totals"]["observed_files"], len(DECLARED_FILES))
            self.assertEqual(
                manifest["totals"]["observed_bytes"], sum(len(p) for p in PAYLOADS.values())
            )
            self.assertEqual(validate_manifest(manifest), [])

    def test_expected_manifest_hash_mismatch_is_reported(self):
        expected = declared_manifest()
        expected["files"][0]["expected_sha256"] = "a" * 64
        expected["files"][0]["expected_bytes"] = len(PAYLOADS[expected["files"][0]["path"]])
        with tempfile.TemporaryDirectory() as tmp:
            report = fetch_and_hash(
                transport=FakeTransport(), destination=tmp, expected_manifest=expected, env={}
            )
            self.assertEqual(report["status"], "verify-failed")
            self.assertEqual(report["mismatches"], [f"{expected['files'][0]['path']}: sha256-mismatch"])
            statuses = {entry["path"]: entry["status"] for entry in report["files"]}
            self.assertEqual(statuses[expected["files"][0]["path"]], "sha256-mismatch")

    def test_expected_manifest_match_is_reported_as_match(self):
        expected = declared_manifest()
        for entry in expected["files"]:
            entry["expected_sha256"] = hashlib.sha256(PAYLOADS[entry["path"]]).hexdigest()
            entry["expected_bytes"] = len(PAYLOADS[entry["path"]])
        with tempfile.TemporaryDirectory() as tmp:
            report = fetch_and_hash(
                transport=FakeTransport(), destination=tmp, expected_manifest=expected, env={}
            )
            self.assertEqual(report["status"], "ok")
            self.assertTrue(all(entry["status"] == "match" for entry in report["files"]))

    def test_moved_revision_pin_stops_before_any_download(self):
        transport = FakeTransport(resolved=OTHER_REVISION)
        with tempfile.TemporaryDirectory() as tmp:
            report = fetch_and_hash(transport=transport, destination=tmp, env={})
        self.assertEqual(report["status"], "failed")
        self.assertIn("revision pin mismatch", report["error"])
        self.assertEqual(transport.downloads, [])

    def test_ambient_credential_variable_fails_closed_before_download(self):
        transport = FakeTransport()
        with tempfile.TemporaryDirectory() as tmp:
            report = fetch_and_hash(
                transport=transport, destination=tmp, env={"HF_TOKEN": "hf_secretvalue123456"}
            )
        self.assertEqual(report["status"], "failed")
        self.assertIn("HF_TOKEN", report["error"])
        self.assertNotIn("hf_secretvalue123456", report["error"])
        self.assertEqual(transport.downloads, [])

    def test_transport_errors_are_redacted_in_the_report(self):
        transport = FakeTransport(
            failure=ArtifactError("HTTP 403 for https://example.invalid/x?token=abc123def")
        )
        with tempfile.TemporaryDirectory() as tmp:
            report = fetch_and_hash(transport=transport, destination=tmp, env={})
        self.assertEqual(report["status"], "failed")
        self.assertIn(REDACTED, report["error"])
        self.assertNotIn("abc123def", report["error"])

    def test_invalid_expected_manifest_stops_the_fetch(self):
        transport = FakeTransport()
        with tempfile.TemporaryDirectory() as tmp:
            report = fetch_and_hash(
                transport=transport,
                destination=tmp,
                expected_manifest={"kind": KIND_MANIFEST, "files": []},
                env={},
            )
        self.assertEqual(report["status"], "failed")
        self.assertEqual(transport.downloads, [])


class TransportBoundaryTests(unittest.TestCase):
    def test_http_transport_never_sets_an_authorization_header(self):
        headers = {name.lower() for name in HfHttpTransport().headers()}
        self.assertNotIn("authorization", headers)
        self.assertNotIn("token", headers)

    def test_http_transport_offers_no_credential_parameter(self):
        parameters = " ".join(inspect.signature(HfHttpTransport.__init__).parameters)
        self.assertNotIn("token", parameters.lower())

    def test_revision_is_resolved_then_compared(self):
        seen = {}

        def opener(request, timeout=None):
            seen["url"] = request.full_url
            seen["headers"] = {name.lower(): value for name, value in request.header_items()}
            return io.BytesIO(json.dumps({"sha": REVISION}).encode())

        transport = HfHttpTransport(opener=opener)
        self.assertEqual(transport.resolve_revision("Qwen/Qwen2.5-1.5B", REVISION), REVISION)
        self.assertIn("/revision/" + REVISION, seen["url"])
        self.assertNotIn("authorization", seen["headers"])


class CliBoundaryTests(unittest.TestCase):
    def test_no_option_mentions_a_credential(self):
        parser = build_parser()
        forbidden = ("token", "secret", "password", "credential", "api-key", "apikey")
        option_strings: list[str] = []
        for action in parser._actions:
            option_strings.extend(action.option_strings)
            choices = getattr(action, "choices", None)
            if isinstance(choices, dict):
                for sub_parser in choices.values():
                    for sub_action in sub_parser._actions:
                        option_strings.extend(sub_action.option_strings)
        self.assertTrue(option_strings)
        for option in option_strings:
            self.assertFalse(
                any(word in option.lower() for word in forbidden), f"credential-shaped flag {option}"
            )

    def test_plan_subcommand_transfers_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "artifact-manifest.json"
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                self.assertEqual(main(["plan", "--out", str(out)]), 0)
            manifest = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(validate_manifest(manifest), [])
            self.assertEqual(buffer.getvalue(), "")

    def test_fetch_without_authorization_file_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / "artifacts"
            errors = io.StringIO()
            with redirect_stderr(errors):
                code = main(
                    [
                        "fetch",
                        "--destination",
                        str(destination),
                        "--manifest-out",
                        str(Path(tmp) / "manifest.json"),
                        "--authorization-file",
                        str(Path(tmp) / "absent.json"),
                    ]
                )
            self.assertEqual(code, 2)
            self.assertIn("gate closed", errors.getvalue())
            self.assertFalse(destination.exists())
            self.assertFalse((Path(tmp) / "manifest.json").exists())


if __name__ == "__main__":
    unittest.main()
