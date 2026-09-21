#!/usr/bin/env python3
"""R02.1 pinned artifact identity: fetch and hash the exact baseline inputs.

Issue https://durandal.exe.xyz/smolmodelco/thesmolmodelcompany/issues/17.

This implements the retrieval half of ``configs/r02-baseline-environment.md``:
each pinned upstream file is fetched by immutable revision, hashed locally, and
compared with a recorded manifest. It answers "which bytes?" and nothing else --
storage is ``r02_release.py``, model execution is ``r02_smoke.py``.

Boundaries held deliberately:

* **No credential.** ``Qwen/Qwen2.5-1.5B`` is a public repository, so the
  transport sets no authentication header and offers no parameter for a token.
  If an ambient Hugging Face token is present in the environment the fetch fails
  closed rather than leaving it ambiguous whether the bytes were fetched
  anonymously.
* **No model library.** Only the standard library is imported, so these helpers
  run in a fresh virtual environment with nothing installed.
* **No implicit work.** Importing this module transfers nothing. A fetch happens
  only through the ``fetch`` subcommand of ``main()``, which requires an
  authorization file. Resolving the pin is a metadata ``GET``; no artifact
  *content* is requested until the manifest, the credential environment and the
  revision pin have all passed, and a manifest that names another repository,
  source, precision or revision is refused before the transport is called.

Usage, from the repository root:

    python3 scripts/r02_artifacts.py plan
    python3 scripts/r02_artifacts.py fetch --destination DIR \\
        --manifest-out FILE --authorization-file FILE [--expected-manifest FILE]

Exit codes: 0 completed, 1 a step or a hash check failed, 2 the gate is closed.
"""

from __future__ import annotations

import argparse
import copy
import datetime as _dt
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol, Sequence

try:  # bare script (sys.path[0] is scripts/) or scripts/ already on sys.path
    from r02_gate import (
        EXIT_GATE_CLOSED,
        EXIT_OK,
        EXIT_STEP_FAILED,
        SCOPE_ARTIFACT_FETCH,
        Authorization,
        GateClosed,
        credential_environment_conflicts,
        is_unset,
        parse_authorization_argv,
        redact_secrets,
        require_authorization,
    )
    from r02_preflight import UNSET, sha256_stream
except ModuleNotFoundError:  # imported as scripts.<module> from the repository root
    from scripts.r02_gate import (
        EXIT_GATE_CLOSED,
        EXIT_OK,
        EXIT_STEP_FAILED,
        SCOPE_ARTIFACT_FETCH,
        Authorization,
        GateClosed,
        credential_environment_conflicts,
        is_unset,
        parse_authorization_argv,
        redact_secrets,
        require_authorization,
    )
    from scripts.r02_preflight import UNSET, sha256_stream

REPO_ID = "Qwen/Qwen2.5-1.5B"
REVISION = "8faed761d45a263340a0528343f099c05c9a4323"
SOURCE = "huggingface"
PRECISION = "bfloat16"
LICENSE = UNSET  # recorded from the upstream card at the first authorized fetch

# Every manifest field that states *which* artifact is being fetched is a pin.
# A caller-supplied manifest may not quietly widen any of them.
PINNED_FIELDS = {
    "repo_id": REPO_ID,
    "source": SOURCE,
    "precision": PRECISION,
    "requested_revision": REVISION,
}

KIND_MANIFEST = "r02-artifact-manifest"
KIND_FETCH = "r02-artifact-fetch"

REVISION_PATTERN = re.compile(r"\A[0-9a-f]{40}\Z")
SHA256_PATTERN = re.compile(r"\A[0-9a-f]{64}\Z")

RESOLVE_URL = "https://huggingface.co/api/models/{repo_id}/revision/{revision}"
DOWNLOAD_URL = "https://huggingface.co/{repo_id}/resolve/{revision}/{path}"
USER_AGENT = "smolmodelcompany-r02-artifact-fetch/0.1 (+repo: thesmolmodelcompany)"

# The exact inputs the recipe pins: the weight file, the model config, and the
# tokenizer's own files. Every entry is required; a missing one is a recorded
# failure and an amendment to the recipe, not a silent fallback.
DECLARED_FILES: tuple[tuple[str, str], ...] = (
    ("config.json", "model-config"),
    ("generation_config.json", "generation-config"),
    ("model.safetensors", "weights"),
    ("tokenizer.json", "tokenizer"),
    ("tokenizer_config.json", "tokenizer"),
    ("vocab.json", "tokenizer"),
    ("merges.txt", "tokenizer"),
)

STATUS_DECLARED = "declared"
STATUS_FIRST_OBSERVATION = "first-observation"
STATUS_MATCH = "match"
STATUS_SHA_MISMATCH = "sha256-mismatch"
STATUS_SIZE_MISMATCH = "size-mismatch"

FETCH_OK = "ok"
FETCH_VERIFY_FAILED = "verify-failed"
FETCH_FAILED = "failed"


def _utc_now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class ArtifactError(RuntimeError):
    """A retrieval step failed. Message text is already redacted."""


class ArtifactTransport(Protocol):
    """Everything that reaches the network, injected so tests never do."""

    def resolve_revision(self, repo_id: str, requested_revision: str) -> str:
        """Return the commit SHA ``requested_revision`` resolves to."""

    def download(self, repo_id: str, revision: str, path: str, destination: Path) -> int:
        """Write one file and return the number of bytes written."""


class HfHttpTransport:
    """Read-only public HTTPS transport for the pinned repository.

    It deliberately cannot carry a credential: the only headers it ever sets are
    ``User-Agent`` and ``Accept``, and no parameter accepts a token.
    """

    def __init__(
        self,
        *,
        opener: Callable[..., Any] = urllib.request.urlopen,
        timeout: float = 60.0,
    ) -> None:
        self._opener = opener
        self._timeout = timeout

    def headers(self) -> dict[str, str]:
        return {"User-Agent": USER_AGENT, "Accept": "*/*"}

    def _get(self, url: str) -> bytes:
        request = urllib.request.Request(url, headers=self.headers())
        try:
            with self._opener(request, timeout=self._timeout) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            raise ArtifactError(
                redact_secrets(f"HTTP {exc.code} for {url}: {exc.reason}")
            ) from exc
        except urllib.error.URLError as exc:
            raise ArtifactError(redact_secrets(f"transport error for {url}: {exc.reason}")) from exc

    def resolve_revision(self, repo_id: str, requested_revision: str) -> str:
        url = RESOLVE_URL.format(repo_id=repo_id, revision=requested_revision)
        payload = json.loads(self._get(url).decode("utf-8"))
        resolved = payload.get("sha", UNSET)
        if not isinstance(resolved, str) or not REVISION_PATTERN.match(resolved):
            raise ArtifactError(
                redact_secrets(f"upstream returned no commit SHA for {repo_id}@{requested_revision}")
            )
        return resolved

    def download(self, repo_id: str, revision: str, path: str, destination: Path) -> int:
        url = DOWNLOAD_URL.format(repo_id=repo_id, revision=revision, path=path)
        request = urllib.request.Request(url, headers=self.headers())
        destination.parent.mkdir(parents=True, exist_ok=True)
        written = 0
        try:
            with self._opener(request, timeout=self._timeout) as response:
                with destination.open("wb") as handle:
                    while True:
                        chunk = response.read(1024 * 1024)
                        if not chunk:
                            break
                        handle.write(chunk)
                        written += len(chunk)
        except (urllib.error.HTTPError, urllib.error.URLError) as exc:
            destination.unlink(missing_ok=True)
            raise ArtifactError(
                redact_secrets(f"download failed for {path} at revision {revision}: {exc}")
            ) from exc
        return written


def declared_manifest() -> dict[str, Any]:
    """The manifest scaffold: pins stated, every measurement explicitly UNSET."""
    return {
        "kind": KIND_MANIFEST,
        "repo_id": REPO_ID,
        "source": SOURCE,
        "requested_revision": REVISION,
        "resolved_revision": UNSET,
        "precision": PRECISION,
        "license": LICENSE,
        "declared_at_utc": UNSET,
        "recorded_at_utc": UNSET,
        "files": [
            {
                "path": path,
                "role": role,
                "required": True,
                "expected_sha256": UNSET,
                "expected_bytes": UNSET,
                "observed_sha256": UNSET,
                "observed_bytes": UNSET,
                "status": STATUS_DECLARED,
            }
            for path, role in DECLARED_FILES
        ],
        "totals": {
            "file_count": len(DECLARED_FILES),
            "observed_files": 0,
            "expected_bytes": UNSET,
            "observed_bytes": UNSET,
        },
    }


def validate_manifest(manifest: Mapping[str, Any]) -> list[str]:
    """Structural checks for an artifact manifest; returns a list of problems."""
    errors: list[str] = []
    if manifest.get("kind") != KIND_MANIFEST:
        errors.append(f"kind must be {KIND_MANIFEST!r}")
    revision = manifest.get("requested_revision")
    if not isinstance(revision, str) or not REVISION_PATTERN.match(revision):
        errors.append("requested_revision must be a full 40-character commit SHA")
    for field_name, pinned in PINNED_FIELDS.items():
        if manifest.get(field_name) != pinned:
            errors.append(
                f"{field_name} must be the pinned value {pinned!r}, not {manifest.get(field_name)!r}"
            )
    files = manifest.get("files")
    if not isinstance(files, list) or not files:
        errors.append("files must be a non-empty list")
        return errors
    declared_paths = {path for path, _ in DECLARED_FILES}
    seen: set[str] = set()
    for entry in files:
        if not isinstance(entry, Mapping):
            errors.append("every files entry must be an object")
            continue
        path = entry.get("path")
        if path not in declared_paths:
            errors.append(f"undeclared artifact path {path!r}")
        seen.add(path)
        for field_name in ("expected_sha256", "observed_sha256"):
            value = entry.get(field_name, UNSET)
            if not is_unset(value) and not (isinstance(value, str) and SHA256_PATTERN.match(value)):
                errors.append(f"{path}: {field_name} must be UNSET or a lowercase SHA-256")
        for field_name in ("expected_bytes", "observed_bytes"):
            value = entry.get(field_name, UNSET)
            if not is_unset(value) and not (isinstance(value, int) and value >= 0):
                errors.append(f"{path}: {field_name} must be UNSET or a non-negative integer")
    missing = sorted(declared_paths - seen)
    if missing:
        errors.append(f"manifest is missing declared path(s): {', '.join(missing)}")
    return errors


def classify_file(
    entry: Mapping[str, Any], *, observed_sha256: str, observed_bytes: int
) -> str:
    """Compare one observation against the recorded expectation."""
    expected_sha = entry.get("expected_sha256", UNSET)
    expected_bytes = entry.get("expected_bytes", UNSET)
    if is_unset(expected_sha) and is_unset(expected_bytes):
        return STATUS_FIRST_OBSERVATION
    if not is_unset(expected_bytes) and int(expected_bytes) != observed_bytes:
        return STATUS_SIZE_MISMATCH
    if not is_unset(expected_sha) and expected_sha != observed_sha256:
        return STATUS_SHA_MISMATCH
    return STATUS_MATCH


def apply_observation(
    manifest: Mapping[str, Any],
    path: str,
    *,
    observed_sha256: str,
    observed_bytes: int,
) -> dict[str, Any]:
    """Return a copy of ``manifest`` with one file observed."""
    updated = copy.deepcopy(dict(manifest))
    for entry in updated["files"]:
        if entry["path"] != path:
            continue
        entry["observed_sha256"] = observed_sha256
        entry["observed_bytes"] = observed_bytes
        entry["status"] = classify_file(entry, observed_sha256=observed_sha256, observed_bytes=observed_bytes)
        break
    observed = [e for e in updated["files"] if not is_unset(e["observed_sha256"])]
    updated["totals"]["observed_files"] = len(observed)
    updated["totals"]["observed_bytes"] = sum(int(e["observed_bytes"]) for e in observed)
    if all(e["status"] in (STATUS_MATCH, STATUS_FIRST_OBSERVATION) for e in updated["files"]):
        expected_total = [e["expected_bytes"] for e in updated["files"]]
        if all(not is_unset(value) for value in expected_total):
            updated["totals"]["expected_bytes"] = sum(int(value) for value in expected_total)
    return updated


def inherit_expectations(
    manifest: Mapping[str, Any], expected_manifest: Mapping[str, Any]
) -> tuple[dict[str, Any], list[str]]:
    """Copy recorded hashes from an earlier manifest so a reproduction can compare."""
    errors = validate_manifest(expected_manifest)
    merged = copy.deepcopy(dict(manifest))
    if errors:
        return merged, errors
    by_path = {entry["path"]: entry for entry in expected_manifest["files"]}
    for entry in merged["files"]:
        source = by_path.get(entry["path"], {})
        for field_name in ("expected_sha256", "expected_bytes"):
            value = source.get(field_name, UNSET)
            if not is_unset(value):
                entry[field_name] = value
    return merged, []


def _failed_report(
    *, destination: str, manifest: Mapping[str, Any], error: str, started_at: str, clock: Callable[[], str]
) -> dict[str, Any]:
    return {
        "kind": KIND_FETCH,
        "status": FETCH_FAILED,
        "repo_id": manifest.get("repo_id", REPO_ID),
        "requested_revision": manifest.get("requested_revision", REVISION),
        "resolved_revision": manifest.get("resolved_revision", UNSET),
        "destination": destination,
        "started_at_utc": started_at,
        "finished_at_utc": clock(),
        "files": [],
        "mismatches": [],
        "missing": [],
        "error": redact_secrets(error),
        "manifest": dict(manifest),
    }


def fetch_and_hash(
    *,
    transport: ArtifactTransport,
    destination: str | Path,
    manifest: Mapping[str, Any] | None = None,
    expected_manifest: Mapping[str, Any] | None = None,
    clock: Callable[[], str] = _utc_now,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Fetch every declared file at the pinned revision, hash it, and compare.

    Order is deliberate: structure, credentials, then the revision pin, and only
    then a byte of transfer. Any of those failing means zero requests for
    artifact content.
    """
    destination_path = Path(destination)
    working = copy.deepcopy(dict(manifest)) if manifest is not None else declared_manifest()
    started_at = clock()

    errors = validate_manifest(working)
    if errors:
        return _failed_report(
            destination=str(destination_path),
            manifest=working,
            error="invalid artifact manifest: " + "; ".join(errors),
            started_at=started_at,
            clock=clock,
        )

    if expected_manifest is not None:
        working, errors = inherit_expectations(working, expected_manifest)
        if errors:
            return _failed_report(
                destination=str(destination_path),
                manifest=working,
                error="invalid expected manifest: " + "; ".join(errors),
                started_at=started_at,
                clock=clock,
            )

    conflicts = credential_environment_conflicts(env)
    if conflicts:
        return _failed_report(
            destination=str(destination_path),
            manifest=working,
            error=(
                "refusing to fetch with ambient credential variable(s) set: "
                + ", ".join(conflicts)
                + " -- this fetch must be unauthenticated; re-run with those variables removed"
            ),
            started_at=started_at,
            clock=clock,
        )

    try:
        resolved = transport.resolve_revision(working["repo_id"], working["requested_revision"])
    except Exception as exc:  # transport failures are recorded, not retried
        return _failed_report(
            destination=str(destination_path),
            manifest=working,
            error=f"revision resolution failed: {exc}",
            started_at=started_at,
            clock=clock,
        )

    if resolved != working["requested_revision"]:
        return _failed_report(
            destination=str(destination_path),
            manifest=working,
            error=(
                f"revision pin mismatch: requested {working['requested_revision']} "
                f"but upstream resolved {resolved}"
            ),
            started_at=started_at,
            clock=clock,
        )

    working["resolved_revision"] = resolved
    working["declared_at_utc"] = started_at
    working["recorded_at_utc"] = clock()

    mismatches: list[str] = []
    files: list[dict[str, Any]] = []
    try:
        for entry in working["files"]:
            target = destination_path / entry["path"]
            transferred = transport.download(working["repo_id"], resolved, entry["path"], target)
            digest = sha256_stream(target)
            observed_bytes = target.stat().st_size
            working = apply_observation(
                working, entry["path"], observed_sha256=digest, observed_bytes=observed_bytes
            )
            status = next(e["status"] for e in working["files"] if e["path"] == entry["path"])
            if status in (STATUS_SHA_MISMATCH, STATUS_SIZE_MISMATCH):
                mismatches.append(f"{entry['path']}: {status}")
            files.append(
                {
                    "path": entry["path"],
                    "role": entry["role"],
                    "transferred_bytes": transferred,
                    "observed_bytes": observed_bytes,
                    "observed_sha256": digest,
                    "status": status,
                }
            )
    except Exception as exc:
        report = _failed_report(
            destination=str(destination_path),
            manifest=working,
            error=f"retrieval stopped on the first failure: {exc}",
            started_at=started_at,
            clock=clock,
        )
        report["files"] = files
        report["mismatches"] = mismatches
        return report

    return {
        "kind": KIND_FETCH,
        "status": FETCH_VERIFY_FAILED if mismatches else FETCH_OK,
        "repo_id": working["repo_id"],
        "requested_revision": working["requested_revision"],
        "resolved_revision": resolved,
        "destination": str(destination_path),
        "started_at_utc": started_at,
        "finished_at_utc": clock(),
        "files": files,
        "mismatches": mismatches,
        "missing": [],
        "error": UNSET,
        "manifest": working,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Fetch and hash the pinned R02 baseline artifacts. Retrieval is "
            "unauthenticated by design; no credential is accepted on the command line."
        )
    )
    sub = parser.add_subparsers(dest="command", required=True)

    plan = sub.add_parser("plan", help="print the declared artifact manifest; transfers nothing")
    plan.add_argument("--out", default=None, help="write the manifest here instead of stdout")

    fetch = sub.add_parser("fetch", help="fetch, hash and compare the declared artifacts")
    fetch.add_argument("--destination", required=True, help="directory to place the fetched files")
    fetch.add_argument("--manifest-out", required=True, help="path for the updated artifact manifest")
    fetch.add_argument("--report-out", default=None, help="path for the fetch report JSON")
    fetch.add_argument("--expected-manifest", default=None, help="earlier manifest to verify against")
    fetch.add_argument("--authorization-file", required=True, help="approval record for this step")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "plan":
        payload = json.dumps(declared_manifest(), indent=2, sort_keys=True) + "\n"
        if args.out:
            Path(args.out).write_text(payload, encoding="utf-8")
        else:
            sys.stdout.write(payload)
        return EXIT_OK

    try:
        authorization, authorization_path = parse_authorization_argv(
            ["--authorization-file", args.authorization_file]
        )
        require_authorization(authorization, scope=SCOPE_ARTIFACT_FETCH)
    except GateClosed as exc:
        sys.stderr.write(f"gate closed: {redact_secrets(exc)}\n")
        return EXIT_GATE_CLOSED

    expected = None
    if args.expected_manifest:
        expected = json.loads(Path(args.expected_manifest).read_text(encoding="utf-8"))

    report = fetch_and_hash(
        transport=HfHttpTransport(),
        destination=args.destination,
        expected_manifest=expected,
    )

    manifest_out = Path(args.manifest_out)
    manifest_out.parent.mkdir(parents=True, exist_ok=True)
    manifest_out.write_text(
        json.dumps(report["manifest"], indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    report_out = Path(args.report_out) if args.report_out else manifest_out.with_name("fetch-report.json")
    report_out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    summary = {
        "status": report["status"],
        "resolved_revision": report["resolved_revision"],
        "files": [entry["status"] for entry in report["files"]],
        "mismatches": report["mismatches"],
        "error": report["error"],
        "authorization": authorization.to_record(),
        "authorization_file": authorization_path,
        "manifest_out": str(manifest_out),
    }
    sys.stdout.write(json.dumps(summary, indent=2, sort_keys=True) + "\n")

    if report["status"] == FETCH_OK:
        return EXIT_OK
    return EXIT_STEP_FAILED


if __name__ == "__main__":
    raise SystemExit(main())
