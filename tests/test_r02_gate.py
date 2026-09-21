"""Tests for the R02 approval and credential gates (issue #17)."""

import json
import tempfile
import unittest
from pathlib import Path

from scripts.r02_gate import (
    KNOWN_SCOPES,
    SCOPE_ARTIFACT_FETCH,
    SCOPE_READINESS_SMOKE,
    Authorization,
    AuthorizationError,
    GateClosed,
    credential_environment_conflicts,
    redact_secrets,
    require_authorization,
)
from scripts.r02_preflight import UNSET


def make_authorization(**overrides):
    data = {
        "granted": True,
        "scope": SCOPE_READINESS_SMOKE,
        "reference": "issue #17 / executable PR",
        "approved_by": "vesper",
        "approved_at_utc": "2026-09-21T03:00:00Z",
    }
    data.update(overrides)
    return Authorization.from_mapping(data)


class AuthorizationTests(unittest.TestCase):
    def test_matching_grant_is_returned(self):
        authorization = make_authorization()
        self.assertIs(
            require_authorization(authorization, scope=SCOPE_READINESS_SMOKE), authorization
        )

    def test_missing_grant_fails_closed(self):
        with self.assertRaises(GateClosed):
            require_authorization(None, scope=SCOPE_READINESS_SMOKE)

    def test_ungranted_record_fails_closed(self):
        with self.assertRaises(GateClosed):
            require_authorization(make_authorization(granted=False), scope=SCOPE_READINESS_SMOKE)

    def test_scope_confusion_fails_closed(self):
        # A grant to fetch artifacts must not be spendable on the model smoke.
        authorization = make_authorization(scope=SCOPE_ARTIFACT_FETCH)
        with self.assertRaises(GateClosed):
            require_authorization(authorization, scope=SCOPE_READINESS_SMOKE)

    def test_non_boolean_granted_is_rejected(self):
        with self.assertRaises(AuthorizationError):
            make_authorization(granted="yes")

    def test_unset_reference_is_rejected(self):
        with self.assertRaises(AuthorizationError):
            make_authorization(reference=UNSET)

    def test_unknown_scope_is_rejected(self):
        with self.assertRaises(AuthorizationError):
            make_authorization(scope="r02-everything")

    def test_missing_field_is_rejected(self):
        data = {
            "granted": True,
            "scope": SCOPE_READINESS_SMOKE,
            "reference": "issue #17",
            "approved_by": "vesper",
        }
        with self.assertRaises(AuthorizationError):
            Authorization.from_mapping(data)

    def test_extra_fields_are_carried_into_the_record(self):
        authorization = make_authorization(operator_go="cassie")
        self.assertEqual(authorization.to_record()["operator_go"], "cassie")

    def test_from_file_reads_a_json_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "authorization.json"
            path.write_text(
                json.dumps({"granted": True, "scope": SCOPE_READINESS_SMOKE,
                            "reference": "issue #17", "approved_by": "vesper",
                            "approved_at_utc": "2026-09-21T03:00:00Z"}),
                encoding="utf-8",
            )
            self.assertTrue(Authorization.from_file(path).granted)

    def test_from_file_missing_path_fails_closed(self):
        with self.assertRaises(GateClosed):
            Authorization.from_file("/nonexistent/authorization.json")

    def test_from_file_malformed_json_is_a_gate_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "authorization.json"
            path.write_text("{not json", encoding="utf-8")
            with self.assertRaises(AuthorizationError):
                Authorization.from_file(path)

    def test_every_known_scope_is_addressable(self):
        for scope in KNOWN_SCOPES:
            require_authorization(make_authorization(scope=scope), scope=scope)


class RedactionTests(unittest.TestCase):
    def test_key_value_credentials_are_redacted(self):
        text = redact_secrets("GET https://example.invalid/x?token=abc123def&y=1")
        self.assertIn("token=REDACTED", text)
        self.assertNotIn("abc123def", text)

    def test_authorization_headers_are_redacted(self):
        text = redact_secrets('header = "Authorization: token ghp_like_value"')
        self.assertIn("REDACTED", text)
        self.assertNotIn("ghp_like_value", text)
        self.assertNotIn("token ghp_like_value", text)

    def test_hugging_face_tokens_are_redacted(self):
        text = redact_secrets("using hf_ABCDEFGHIJKLMNOP in the header")
        self.assertNotIn("hf_ABCDEFGHIJKLMNOP", text)

    def test_signed_url_parameters_are_redacted(self):
        text = redact_secrets(
            "https://forge.invalid/asset?X-Amz-Signature=deadbeefcafe1234"
            "&X-Amz-Credential=AKIAEXAMPLE&name=probe.bin"
        )
        self.assertNotIn("deadbeefcafe1234", text)
        self.assertNotIn("AKIAEXAMPLE", text)
        self.assertIn("name=probe.bin", text)

    def test_bearer_style_values_without_a_colon_are_redacted(self):
        text = redact_secrets("Authorization Bearer abcdef123456 completed")
        self.assertNotIn("abcdef123456", text)

    def test_ordinary_prose_is_not_mangled(self):
        # An error a reader needs must survive redaction intact.
        message = "gate closed: authorization file not found: /tmp/absent.json"
        self.assertEqual(redact_secrets(message), message)

    def test_explicit_secrets_are_removed_verbatim(self):
        text = redact_secrets("curl failed with body secret-token-value", ["secret-token-value"])
        self.assertNotIn("secret-token-value", text)
        self.assertIn("REDACTED", text)

    def test_credential_environment_conflicts_returns_names_not_values(self):
        conflicts = credential_environment_conflicts({"HF_TOKEN": "hf_secret_value", "PATH": "/bin"})
        self.assertEqual(conflicts, ["HF_TOKEN"])
        self.assertNotIn("hf_secret_value", " ".join(conflicts))

    def test_no_conflicts_in_a_clean_environment(self):
        self.assertEqual(credential_environment_conflicts({"PATH": "/bin", "HF_TOKEN": ""}), [])


if __name__ == "__main__":
    unittest.main()
