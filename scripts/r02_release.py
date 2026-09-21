#!/usr/bin/env python3
"""R02.1 durable release-asset round trip.

Issue https://durandal.exe.xyz/smolmodelco/thesmolmodelcompany/issues/17.

``coordination.md`` requires that large artifacts live somewhere durable and that
its persistence be *checked* before a run whose output cannot be cheaply
reproduced. The merged preflight recorded one such check as an observation and
explicitly did not leave a replayable command behind. This module is that
command.

The verified sequence, in order:

1. hash and size the local source file;
2. create a **draft** release on the canonical Forgejo repository;
3. upload the file as a release asset;
4. re-read the release with a **separate** ``GET`` -- the download URL is never
   taken from the upload response, which would test nothing;
5. download that URL into a clean directory and hash it independently;
6. compare digest and byte size, recording both;
7. delete the release and its tag, then confirm from a fresh release listing
   that the release is gone -- in a ``finally`` block, so cleanup also happens
   when verification raises.

The transport is injected: ``InMemoryReleaseTransport`` proves the wiring with
no network and no credential, and ``ForgejoTransport`` is the live path. The
live path reads the pre-provisioned Git Credential Manager credential through
``git credential fill`` -- never argv, never a new environment variable, never a
repository file -- and passes it to ``curl`` in a mode-0600 configuration file
that is removed afterwards. Every message it logs or records is passed through
``redact_secrets``.

Usage, from the repository root:

    python3 scripts/r02_release.py self-test
    python3 scripts/r02_release.py round-trip --source FILE --run-id ID \\
        --authorization-file FILE [--retain] [--out FILE]

Exit codes: 0 verified, 1 a step or a comparison failed, 2 the gate is closed.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping, Protocol, Sequence

try:  # bare script (sys.path[0] is scripts/) or scripts/ already on sys.path
    from r02_gate import (
        EXIT_GATE_CLOSED,
        EXIT_OK,
        EXIT_STEP_FAILED,
        SCOPE_RELEASE_ROUND_TRIP,
        Authorization,
        GateClosed,
        redact_secrets,
        require_authorization,
    )
    from r02_preflight import UNSET, sha256_stream
except ModuleNotFoundError:  # imported as scripts.<module> from the repository root
    from scripts.r02_gate import (
        EXIT_GATE_CLOSED,
        EXIT_OK,
        EXIT_STEP_FAILED,
        SCOPE_RELEASE_ROUND_TRIP,
        Authorization,
        GateClosed,
        redact_secrets,
        require_authorization,
    )
    from scripts.r02_preflight import UNSET, sha256_stream

KIND = "r02-release-round-trip"

API_BASE = "https://durandal.exe.xyz/api/v1"
HOST = "durandal.exe.xyz"
REPOSITORY = "smolmodelco/thesmolmodelcompany"
ACCOUNT = "eido"

TAG_PREFIX = "r02-persist"
ASSET_NAME_DIGEST_CHARS = 16
STATE_DRAFT = "draft-prerelease"
READBACK_METHOD = "GET /repos/{repo}/releases/{release_id} (separate call, not the upload response)"


def _utc_now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class ReleaseError(RuntimeError):
    """A release step failed. Message text is already redacted."""


class ReleaseTransport(Protocol):
    """The whole Forgejo surface this module needs, injectable for tests."""

    def create_release(
        self, *, tag: str, name: str, body: str, draft: bool, prerelease: bool
    ) -> Mapping[str, Any]:
        ...

    def upload_asset(self, *, release_id: int, path: Path, name: str) -> Mapping[str, Any]:
        ...

    def read_release(self, *, release_id: int) -> Mapping[str, Any]:
        ...

    def download(self, *, url: str, destination: Path) -> int:
        ...

    def delete_release(self, *, release_id: int) -> None:
        ...

    def delete_tag(self, *, tag: str) -> None:
        ...

    def list_release_ids(self) -> Sequence[int]:
        ...


def new_tag(*, run_id: str, clock: Callable[[], str] = _utc_now, nonce: str | None = None) -> str:
    """A unique tag per attempt, so a failed attempt can never collide with a retry."""
    stamp = clock().replace(":", "").replace("-", "")
    suffix = nonce if nonce is not None else secrets.token_hex(4)
    return f"{TAG_PREFIX}-{run_id}-{stamp}-{suffix}"


def asset_name_for(source: str | Path, sha256: str) -> str:
    """The asset name carries the digest prefix, so a stale asset is visible by name."""
    return f"{Path(source).name}.{sha256[:ASSET_NAME_DIGEST_CHARS]}"


def find_asset(release: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    for asset in release.get("assets") or ():
        if asset.get("name") == name:
            return asset
    raise ReleaseError(
        f"the read-back GET did not return asset {name!r}; refusing to reuse upload-response data"
    )


def round_trip(
    *,
    source: str | Path,
    transport: ReleaseTransport,
    tag: str,
    run_id: str,
    clock: Callable[[], str] = _utc_now,
    workdir: str | Path | None = None,
    retain: bool = False,
) -> dict[str, Any]:
    """Publish, verify by independent readback, and clean up."""
    source_path = Path(source)
    if not source_path.is_file():
        raise ReleaseError(f"source file not found: {source_path}")

    source_sha256 = sha256_stream(source_path)
    source_bytes = source_path.stat().st_size
    asset_name = asset_name_for(source_path, source_sha256)

    scratch = Path(workdir) if workdir is not None else Path(tempfile.mkdtemp(prefix="r02-readback-"))
    scratch.mkdir(parents=True, exist_ok=True)

    record: dict[str, Any] = {
        "kind": KIND,
        "run_id": run_id,
        "tag": tag,
        "asset_name": asset_name,
        "state": STATE_DRAFT,
        "retained": retain,
        "source_path": str(source_path),
        "source_bytes": source_bytes,
        "source_sha256": source_sha256,
        "readback_uri": UNSET,
        "readback_method": READBACK_METHOD.format(repo=REPOSITORY, release_id=UNSET),
        "readback_bytes": UNSET,
        "readback_sha256": UNSET,
        "verified": False,
        "error": UNSET,
        "cleanup": UNSET,
        "started_at_utc": clock(),
        "finished_at_utc": UNSET,
    }

    release_id: int | None = None
    primary_error: str | None = None
    try:
        created = transport.create_release(
            tag=tag,
            name=f"R02 persistence round trip {tag}",
            body=(
                "Draft probe release created by scripts/r02_release.py. It is deleted by the "
                "same command unless --retain is passed."
            ),
            draft=True,
            prerelease=True,
        )
        release_id = int(created["id"])
        record["readback_method"] = READBACK_METHOD.format(
            repo=REPOSITORY, release_id=release_id
        )

        transport.upload_asset(release_id=release_id, path=source_path, name=asset_name)

        # A separate GET, on purpose: reusing the upload response would prove nothing.
        release = transport.read_release(release_id=release_id)
        asset = find_asset(release, asset_name)
        download_url = asset.get("browser_download_url")
        if not isinstance(download_url, str) or not download_url:
            raise ReleaseError("the read-back GET returned no download URL for the asset")
        record["readback_uri"] = download_url

        readback_path = scratch / asset_name
        transport.download(url=download_url, destination=readback_path)
        readback_bytes = readback_path.stat().st_size
        readback_sha256 = sha256_stream(readback_path)
        record["readback_bytes"] = readback_bytes
        record["readback_sha256"] = readback_sha256

        problems: list[str] = []
        if readback_bytes != source_bytes:
            problems.append(f"byte size {readback_bytes} != {source_bytes}")
        if readback_sha256 != source_sha256:
            problems.append("SHA-256 mismatch between source and independent readback")
        if problems:
            raise ReleaseError("; ".join(problems))
        record["verified"] = True
    except Exception as exc:
        primary_error = redact_secrets(exc)
        record["error"] = primary_error
    finally:
        record["cleanup"] = _cleanup(transport, release_id=release_id, tag=tag, retain=retain)
        record["finished_at_utc"] = clock()
        if workdir is None:
            shutil.rmtree(scratch, ignore_errors=True)

    if primary_error is not None:
        record["verified"] = False
    return record


def _cleanup(
    transport: ReleaseTransport, *, release_id: int | None, tag: str, retain: bool
) -> dict[str, Any]:
    """Delete what was created and confirm absence. Never masks the primary error."""
    if retain:
        return {
            "retained": True,
            "release_deleted": False,
            "tag_deleted": False,
            "release_absent": False,
            "errors": [],
        }

    cleanup: dict[str, Any] = {
        "retained": False,
        "release_deleted": False,
        "tag_deleted": False,
        "release_absent": UNSET,
        "errors": [],
    }
    if release_id is not None:
        try:
            transport.delete_release(release_id=release_id)
            cleanup["release_deleted"] = True
        except Exception as exc:
            cleanup["errors"].append(f"delete release: {redact_secrets(exc)}")
    try:
        transport.delete_tag(tag=tag)
        cleanup["tag_deleted"] = True
    except Exception as exc:
        cleanup["errors"].append(f"delete tag: {redact_secrets(exc)}")
    try:
        cleanup["release_absent"] = release_id not in transport.list_release_ids()
    except Exception as exc:
        cleanup["errors"].append(f"confirm absence: {redact_secrets(exc)}")
    return cleanup


class InMemoryReleaseTransport:
    """The reference implementation of the contract: no network, no credential.

    Used by ``self-test`` and by the tests, so the verified sequence can be
    exercised, including corruption and transport failure, without a live forge.
    """

    def __init__(self, *, corrupt_download: bool = False, fail_upload: bool = False) -> None:
        self.releases: dict[int, dict[str, Any]] = {}
        self.assets: dict[int, dict[str, bytes]] = {}
        self.calls: list[str] = []
        self.corrupt_download = corrupt_download
        self.fail_upload = fail_upload
        self._next_id = 1
        self._tags: dict[str, int] = {}

    def create_release(
        self, *, tag: str, name: str, body: str, draft: bool, prerelease: bool
    ) -> Mapping[str, Any]:
        self.calls.append("create_release")
        release_id = self._next_id
        self._next_id += 1
        self.releases[release_id] = {
            "id": release_id,
            "tag_name": tag,
            "name": name,
            "body": body,
            "draft": draft,
            "prerelease": prerelease,
            "assets": [],
        }
        self.assets[release_id] = {}
        self._tags[tag] = release_id
        return self.releases[release_id]

    def upload_asset(self, *, release_id: int, path: Path, name: str) -> Mapping[str, Any]:
        self.calls.append("upload_asset")
        if self.fail_upload:
            raise ReleaseError("upload rejected by the forge (simulated)")
        payload = Path(path).read_bytes()
        self.assets[release_id][name] = payload
        asset = {
            "id": 1000 + len(self.calls),
            "name": name,
            "size": len(payload),
            "browser_download_url": (
                f"{API_BASE}/{REPOSITORY}/releases/download/"
                f"{self.releases[release_id]['tag_name']}/{name}"
            ),
        }
        self.releases[release_id]["assets"].append(asset)
        return asset

    def read_release(self, *, release_id: int) -> Mapping[str, Any]:
        self.calls.append("read_release")
        if release_id not in self.releases:
            raise ReleaseError(f"release {release_id} not found (simulated 404)")
        return self.releases[release_id]

    def download(self, *, url: str, destination: Path) -> int:
        self.calls.append("download")
        target = destination
        target.parent.mkdir(parents=True, exist_ok=True)
        for release_id, assets in self.assets.items():
            for name, payload in assets.items():
                if url.endswith(name):
                    data = payload + (b"corrupted" if self.corrupt_download else b"")
                    target.write_bytes(data)
                    return len(data)
        raise ReleaseError(f"asset not present for URL {url} (simulated 404)")

    def delete_release(self, *, release_id: int) -> None:
        self.calls.append("delete_release")
        self.releases.pop(release_id, None)
        self.assets.pop(release_id, None)

    def delete_tag(self, *, tag: str) -> None:
        self.calls.append("delete_tag")
        self._tags.pop(tag, None)

    def list_release_ids(self) -> Sequence[int]:
        self.calls.append("list_release_ids")
        return sorted(self.releases)


def git_credential_fill(
    *, host: str = HOST, username: str = ACCOUNT, run: Callable[..., Any] = subprocess.run
) -> str:
    """Read the pre-provisioned credential from the configured helper.

    The host/username go in on stdin -- never in argv -- and the interactive
    prompt is disabled so a missing credential fails instead of hanging.
    """
    payload = f"protocol=https\nhost={host}\nusername={username}\n\n"
    environment = dict(os.environ, GIT_TERMINAL_PROMPT="0")
    try:
        completed = run(
            ["git", "credential", "fill"],
            input=payload,
            capture_output=True,
            text=True,
            env=environment,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ReleaseError(f"could not run the configured git credential helper: {exc}") from exc
    if completed.returncode != 0:
        raise ReleaseError(
            "the configured git credential helper returned no credential for "
            f"{host} ({username}); nothing is stored or requested by this script"
        )
    for line in completed.stdout.splitlines():
        if line.startswith("password="):
            return line.split("=", 1)[1]
    raise ReleaseError(f"the credential helper returned no password for {host} ({username})")


class ForgejoTransport:
    """Live transport: REST over the canonical Forgejo instance with ``curl``.

    Authentication comes from the same Git Credential Manager store the Git
    remotes use, on this host reached through the configured helper. The token
    is written only into a mode-0600 ``curl`` configuration file that is removed
    in a ``finally`` block; it never appears in argv, in a URL, or in a log.
    """

    def __init__(
        self,
        *,
        base_url: str = API_BASE,
        repo: str = REPOSITORY,
        host: str = HOST,
        account: str = ACCOUNT,
        credential_source: Callable[[], str] | None = None,
        runner: Callable[..., Any] = subprocess.run,
        log: Callable[[str], None] | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._repo = repo
        self._host = host
        self._account = account
        self._credential_source = credential_source
        self._runner = runner
        self._log_fn = log or (lambda message: None)
        self._secrets: list[str] = []

    def _credential(self) -> str:
        source = self._credential_source
        token = source() if source is not None else git_credential_fill(host=self._host, username=self._account)
        if not token or not token.strip():
            raise ReleaseError("the credential source returned an empty value")
        if token not in self._secrets:
            self._secrets.append(token)
        return token

    def redact(self, text: Any) -> str:
        return redact_secrets(text, self._secrets)

    def log(self, message: str) -> None:
        self._log_fn(self.redact(message))

    @staticmethod
    def curl_argv(
        method: str,
        url: str,
        config_path: str,
        *,
        data_file: str | None = None,
        form_file: str | None = None,
        form_name: str = "attachment",
        out_file: str | None = None,
        extra_args: Sequence[str] = (),
    ) -> list[str]:
        """The exact argv handed to ``curl``. It never contains a credential."""
        argv = ["curl", "-sS", "--fail-with-body", "--config", config_path, "-X", method]
        if data_file:
            argv += ["-H", "Content-Type: application/json", "--data-binary", f"@{data_file}"]
        if form_file:
            argv += ["-F", f"{form_name}=@{form_file}"]
        if out_file:
            argv += ["-o", out_file]
        argv += list(extra_args)
        argv.append(url)
        return argv

    @contextmanager
    def _config_file(self) -> Iterator[str]:
        token = self._credential()
        handle = tempfile.NamedTemporaryFile(
            "w", prefix="r02-curl-", suffix=".conf", delete=False, encoding="utf-8"
        )
        path = handle.name
        try:
            os.chmod(path, 0o600)
            handle.write(f'header = "Authorization: token {token}"\n')
            handle.write('header = "Accept: application/json"\n')
            handle.flush()
            handle.close()
            yield path
        finally:
            try:
                handle.close()
            except Exception:  # already closed
                pass
            Path(path).unlink(missing_ok=True)

    def _call(
        self,
        method: str,
        *,
        path: str | None = None,
        url: str | None = None,
        body: Mapping[str, Any] | None = None,
        form_file: Path | None = None,
        form_name: str = "attachment",
        out_file: Path | None = None,
    ) -> Any:
        target = url if url is not None else f"{self._base_url}{path}"
        data_file: str | None = None
        try:
            with self._config_file() as config_path:
                if body is not None:
                    with tempfile.NamedTemporaryFile(
                        "w", prefix="r02-body-", suffix=".json", delete=False, encoding="utf-8"
                    ) as handle:
                        json.dump(body, handle)
                        data_file = handle.name
                argv = self.curl_argv(
                    method,
                    target,
                    config_path,
                    data_file=data_file,
                    form_file=str(form_file) if form_file else None,
                    form_name=form_name,
                    out_file=str(out_file) if out_file else None,
                )
                environment = dict(os.environ, GIT_TERMINAL_PROMPT="0")
                completed = self._runner(
                    argv, capture_output=True, text=True, env=environment, timeout=300
                )
                if completed.returncode != 0:
                    message = self.redact(
                        f"curl exited {completed.returncode} for {method} {target}: "
                        f"{completed.stderr.strip() or completed.stdout.strip()}"
                    )
                    self.log(message)
                    raise ReleaseError(message)
                if out_file is not None:
                    return None
                if completed.stdout.strip():
                    return json.loads(completed.stdout)
                return None
        except json.JSONDecodeError as exc:
            raise ReleaseError(self.redact(f"unparseable response from {target}: {exc}")) from exc
        finally:
            if data_file:
                Path(data_file).unlink(missing_ok=True)

    def create_release(
        self, *, tag: str, name: str, body: str, draft: bool, prerelease: bool
    ) -> Mapping[str, Any]:
        self.log(f"creating draft release {tag}")
        response = self._call(
            "POST",
            path=f"/repos/{self._repo}/releases",
            body={"tag_name": tag, "name": name, "body": body, "draft": draft, "prerelease": prerelease},
        )
        if not isinstance(response, Mapping) or "id" not in response:
            raise ReleaseError("create release returned no release id")
        return response

    def upload_asset(self, *, release_id: int, path: Path, name: str) -> Mapping[str, Any]:
        self.log(f"uploading asset {name} to release {release_id}")
        return self._call(
            "POST",
            path=f"/repos/{self._repo}/releases/{release_id}/assets?name={name}",
            form_file=Path(path),
        )

    def read_release(self, *, release_id: int) -> Mapping[str, Any]:
        self.log(f"re-reading release {release_id} for the download URL")
        response = self._call("GET", path=f"/repos/{self._repo}/releases/{release_id}")
        if not isinstance(response, Mapping):
            raise ReleaseError("read release returned no object")
        return response

    def download(self, *, url: str, destination: Path) -> int:
        self.log("downloading the read-back URL into a clean directory")
        Path(destination).parent.mkdir(parents=True, exist_ok=True)
        self._call("GET", url=url, out_file=Path(destination))
        return Path(destination).stat().st_size

    def delete_release(self, *, release_id: int) -> None:
        self.log(f"deleting release {release_id}")
        self._call("DELETE", path=f"/repos/{self._repo}/releases/{release_id}")

    def delete_tag(self, *, tag: str) -> None:
        self.log(f"deleting tag {tag}")
        self._call("DELETE", path=f"/repos/{self._repo}/tags/{tag}")

    def list_release_ids(self) -> Sequence[int]:
        response = self._call("GET", path=f"/repos/{self._repo}/releases")
        if not isinstance(response, list):
            raise ReleaseError("release listing did not return a list")
        return [int(item["id"]) for item in response if isinstance(item, Mapping) and "id" in item]


def self_test(*, clock: Callable[[], str] = _utc_now) -> int:
    """Exercise the whole sequence in memory: no credential, no network, no GPU."""
    with tempfile.TemporaryDirectory(prefix="r02-self-test-") as tmp:
        source = Path(tmp) / "probe.bin"
        source.write_bytes(os.urandom(64 * 1024))
        transport = InMemoryReleaseTransport()
        record = round_trip(
            source=source,
            transport=transport,
            tag=new_tag(run_id="self-test", clock=clock, nonce="00000000"),
            run_id="self-test",
            clock=clock,
            workdir=Path(tmp) / "readback",
        )
        record["transport"] = "in-memory (self-test: no credential, no network)"
        sys.stdout.write(json.dumps(record, indent=2, sort_keys=True) + "\n")
        ok = (
            record["verified"]
            and record["cleanup"]["release_absent"] is True
            and record["cleanup"]["release_deleted"]
        )
        return EXIT_OK if ok else EXIT_STEP_FAILED


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Durable artifact round trip against Forgejo release assets. "
            "Publishes, verifies by independent readback, then cleans up."
        )
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("self-test", help="in-memory sequence check; no credential, no network")

    live = sub.add_parser("round-trip", help="live sequence against the canonical forge")
    live.add_argument("--source", required=True)
    live.add_argument("--run-id", required=True)
    live.add_argument("--authorization-file", required=True)
    live.add_argument("--retain", action="store_true", help="keep the release instead of deleting it")
    live.add_argument("--out", default=None)
    live.add_argument("--workdir", default=None)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "self-test":
        return self_test()

    try:
        authorization = Authorization.from_file(args.authorization_file)
        require_authorization(authorization, scope=SCOPE_RELEASE_ROUND_TRIP)
    except GateClosed as exc:
        sys.stderr.write(f"gate closed: {redact_secrets(exc)}\n")
        return EXIT_GATE_CLOSED

    transport = ForgejoTransport(log=lambda message: sys.stderr.write(f"r02_release: {message}\n"))
    record = round_trip(
        source=args.source,
        transport=transport,
        tag=new_tag(run_id=args.run_id),
        run_id=args.run_id,
        retain=args.retain,
        workdir=args.workdir,
    )
    record["authorization"] = authorization.to_record()
    payload = json.dumps(record, indent=2, sort_keys=True) + "\n"
    if args.out:
        Path(args.out).write_text(payload, encoding="utf-8")
    sys.stdout.write(payload)
    return EXIT_OK if record["verified"] else EXIT_STEP_FAILED


if __name__ == "__main__":
    raise SystemExit(main())
