"""Tests for the R02 durable release round trip (issue #17).

Every transport here is in-memory. No test contacts Forgejo, reads a stored
credential, uploads an asset, or downloads anything.
"""

import io
import json
import stat
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace

from scripts.r02_gate import REDACTED
from scripts.r02_release import (
    InMemoryReleaseTransport,
    ReleaseError,
    ForgejoTransport,
    asset_name_for,
    build_parser,
    find_asset,
    git_credential_fill,
    main,
    new_tag,
    round_trip,
    self_test,
)
from scripts.r02_preflight import UNSET, sha256_stream


def fixed_clock(*stamps):
    values = list(stamps)
    last = [values[-1] if values else "2026-09-21T03:00:00Z"]

    def clock():
        if values:
            last[0] = values.pop(0)
        return last[0]

    return clock


class FakeCredentialSource:
    def __init__(self, token):
        self.token = token
        self.calls = 0

    def __call__(self):
        self.calls += 1
        return self.token


class RecordingRunner:
    """Stands in for subprocess.run around curl, capturing argv and the config file."""

    def __init__(self, *, returncode=0, stdout="[]", stderr="", token=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.token = token
        self.argv = None
        self.config_path = None
        self.config_mode = None
        self.config_text = None
        self.config_existed_after = None

    def __call__(self, argv, **kwargs):
        self.argv = list(argv)
        self.config_path = argv[argv.index("--config") + 1]
        self.config_mode = stat.S_IMODE(Path(self.config_path).stat().st_mode)
        self.config_text = Path(self.config_path).read_text(encoding="utf-8")
        return SimpleNamespace(returncode=self.returncode, stdout=self.stdout, stderr=self.stderr)


class RoundTripTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.source = self.tmp / "manifest.json"
        self.source.write_bytes(b'{"run_id": "r02-smoke-001"}\n')

    def tearDown(self):
        self._tmp.cleanup()

    def test_verified_round_trip_reads_back_separately_and_cleans_up(self):
        transport = InMemoryReleaseTransport()
        record = round_trip(
            source=self.source,
            transport=transport,
            tag="r02-persist-run-20260921T030000Z-abc12345",
            run_id="r02-smoke-001",
            clock=fixed_clock("2026-09-21T03:00:00Z", "2026-09-21T03:00:07Z"),
            workdir=self.tmp / "readback",
        )
        self.assertTrue(record["verified"])
        self.assertEqual(record["error"], UNSET)
        self.assertEqual(record["source_sha256"], sha256_stream(self.source))
        self.assertEqual(record["readback_sha256"], record["source_sha256"])
        self.assertEqual(record["readback_bytes"], record["source_bytes"])
        self.assertTrue(record["readback_uri"].startswith("https://durandal.exe.xyz/"))
        self.assertIn("separate call", record["readback_method"])
        # the readback must come from a GET after the upload, never from the upload response
        self.assertLess(
            transport.calls.index("upload_asset"), transport.calls.index("read_release")
        )
        self.assertLess(transport.calls.index("read_release"), transport.calls.index("download"))
        self.assertTrue(record["cleanup"]["release_deleted"])
        self.assertTrue(record["cleanup"]["tag_deleted"])
        self.assertIs(record["cleanup"]["release_absent"], True)
        self.assertEqual(transport.releases, {})
        self.assertEqual(record["finished_at_utc"], "2026-09-21T03:00:07Z")
        json.dumps(record)

    def test_altered_readback_is_a_mismatch_and_still_cleans_up(self):
        transport = InMemoryReleaseTransport(corrupt_download=True)
        record = round_trip(
            source=self.source,
            transport=transport,
            tag="r02-persist-run-20260921T030000Z-abc12345",
            run_id="r02-smoke-001",
            workdir=self.tmp / "readback",
        )
        self.assertFalse(record["verified"])
        self.assertIn("SHA-256 mismatch", record["error"])
        self.assertIn("byte size", record["error"])
        self.assertTrue(record["cleanup"]["release_deleted"])
        self.assertIs(record["cleanup"]["release_absent"], True)

    def test_upload_failure_is_recorded_and_the_release_is_removed(self):
        transport = InMemoryReleaseTransport(fail_upload=True)
        record = round_trip(
            source=self.source,
            transport=transport,
            tag="r02-persist-run-20260921T030000Z-abc12345",
            run_id="r02-smoke-001",
            workdir=self.tmp / "readback",
        )
        self.assertFalse(record["verified"])
        self.assertIn("upload rejected", record["error"])
        self.assertTrue(record["cleanup"]["release_deleted"])
        self.assertEqual(transport.releases, {})

    def test_retain_keeps_the_release_for_the_record(self):
        transport = InMemoryReleaseTransport()
        record = round_trip(
            source=self.source,
            transport=transport,
            tag="r02-persist-run-20260921T030000Z-abc12345",
            run_id="r02-smoke-001",
            workdir=self.tmp / "readback",
            retain=True,
        )
        self.assertTrue(record["verified"])
        self.assertTrue(record["cleanup"]["retained"])
        self.assertFalse(record["cleanup"]["release_deleted"])
        self.assertEqual(len(transport.releases), 1)
        self.assertTrue(record["readback_uri"])

    def test_missing_source_is_refused(self):
        with self.assertRaises(ReleaseError):
            round_trip(
                source=self.tmp / "absent.bin",
                transport=InMemoryReleaseTransport(),
                tag="t",
                run_id="r",
            )

    def test_readback_without_the_asset_is_refused(self):
        release = {"id": 1, "assets": []}
        with self.assertRaises(ReleaseError):
            find_asset(release, "missing.bin")

    def test_asset_name_carries_the_digest_prefix(self):
        digest = "c" * 64
        self.assertEqual(asset_name_for(self.source, digest), f"manifest.json.{'c' * 16}")

    def test_new_tag_is_unique_per_attempt(self):
        first = new_tag(run_id="r", clock=fixed_clock("2026-09-21T03:00:00Z"), nonce="aaaaaaaa")
        second = new_tag(run_id="r", clock=fixed_clock("2026-09-21T03:00:00Z"), nonce="bbbbbbbb")
        self.assertNotEqual(first, second)
        self.assertTrue(first.startswith("r02-persist-r-"))

    def test_self_test_runs_the_sequence_in_memory(self):
        with redirect_stdout(io.StringIO()) as captured:
            self.assertEqual(self_test(clock=fixed_clock("2026-09-21T03:00:00Z")), 0)
        self.assertIn('"verified": true', captured.getvalue())


class SecretSafetyTests(unittest.TestCase):
    TOKEN = "forgejo-token-value-9f8e7d"

    def test_curl_argv_never_contains_the_credential(self):
        argv = ForgejoTransport.curl_argv(
            "GET", "https://durandal.exe.xyz/api/v1/repos/x/y/releases", "/tmp/conf"
        )
        self.assertIn("--config", argv)
        self.assertNotIn(self.TOKEN, " ".join(argv))
        self.assertFalse(any("Authorization" in part for part in argv))
        self.assertEqual(argv[-1], "https://durandal.exe.xyz/api/v1/repos/x/y/releases")

    def test_credential_reaches_curl_only_through_a_private_temporary_config(self):
        source = FakeCredentialSource(self.TOKEN)
        runner = RecordingRunner(stdout="[]")
        transport = ForgejoTransport(credential_source=source, runner=runner)
        token = transport._credential()
        self.assertEqual(token, self.TOKEN)
        self.assertEqual(transport.list_release_ids(), [])
        self.assertEqual(runner.config_mode, 0o600)
        self.assertIn(self.TOKEN, runner.config_text or "")
        self.assertNotIn(self.TOKEN, " ".join(runner.argv))
        self.assertFalse(Path(runner.config_path).exists())  # removed in the finally block

    def test_transport_errors_are_redacted(self):
        source = FakeCredentialSource(self.TOKEN)
        runner = RecordingRunner(returncode=22, stdout="", stderr=f"403 with {self.TOKEN}")
        transport = ForgejoTransport(credential_source=source, runner=runner)
        with self.assertRaises(ReleaseError) as raised:
            transport.list_release_ids()
        self.assertNotIn(self.TOKEN, str(raised.exception))
        self.assertIn(REDACTED, str(raised.exception))
        self.assertFalse(Path(runner.config_path).exists())

    def test_logged_messages_are_redacted(self):
        source = FakeCredentialSource(self.TOKEN)
        runner = RecordingRunner(returncode=1, stdout="", stderr=f"denied {self.TOKEN}")
        lines = []
        transport = ForgejoTransport(
            credential_source=source, runner=runner, log=lines.append
        )
        with self.assertRaises(ReleaseError):
            transport.delete_release(release_id=7)
        self.assertTrue(lines)
        self.assertFalse(any(self.TOKEN in line for line in lines))
        self.assertTrue(any(REDACTED in line for line in lines))

    def test_credential_helper_is_called_without_the_secret_in_argv(self):
        seen = {}

        def runner(argv, **kwargs):
            seen["argv"] = list(argv)
            seen["input"] = kwargs.get("input")
            seen["env"] = kwargs.get("env")
            return SimpleNamespace(returncode=0, stdout="username=eido\npassword=stored-value\n", stderr="")

        self.assertEqual(git_credential_fill(run=runner), "stored-value")
        self.assertEqual(seen["argv"], ["git", "credential", "fill"])
        self.assertIn("host=durandal.exe.xyz", seen["input"])
        self.assertEqual(seen["env"]["GIT_TERMINAL_PROMPT"], "0")

    def test_credential_helper_failure_is_reported_not_retried(self):
        def runner(argv, **kwargs):
            return SimpleNamespace(returncode=128, stdout="", stderr="no helper")

        with self.assertRaises(ReleaseError):
            git_credential_fill(run=runner)

    def test_credential_helper_without_a_password_is_reported(self):
        def runner(argv, **kwargs):
            return SimpleNamespace(returncode=0, stdout="username=eido\n", stderr="")

        with self.assertRaises(ReleaseError):
            git_credential_fill(run=runner)


class CliTests(unittest.TestCase):
    def test_live_round_trip_without_authorization_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "probe.bin"
            source.write_bytes(b"probe")
            code = main(
                [
                    "round-trip",
                    "--source",
                    str(source),
                    "--run-id",
                    "r02-smoke-001",
                    "--authorization-file",
                    str(Path(tmp) / "absent.json"),
                ]
            )
            self.assertEqual(code, 2)

    def test_no_option_mentions_a_credential(self):
        parser = build_parser()
        forbidden = ("token", "secret", "password", "credential", "api-key", "apikey")
        option_strings = [option for action in parser._actions for option in action.option_strings]
        choices = next(
            action.choices for action in parser._actions if isinstance(getattr(action, "choices", None), dict)
        )
        for sub_parser in choices.values():
            option_strings.extend(
                option for action in sub_parser._actions for option in action.option_strings
            )
        self.assertTrue(option_strings)
        for option in option_strings:
            self.assertFalse(any(word in option.lower() for word in forbidden), option)

if __name__ == "__main__":
    unittest.main()
