#!/usr/bin/env python3
"""R02.1 execution and credential gates.

Issue https://durandal.exe.xyz/smolmodelco/thesmolmodelcompany/issues/17.

Two boundaries live here, and both fail closed.

1. **Authorization.** A live step -- artifact fetch, readiness smoke, or release
   round trip -- runs only when the caller supplies an authorization record with
   ``granted: true`` *and* an exact scope match. Every entry point evaluates
   this gate before importing a model library, opening a socket, or touching
   the GPU, so an unapproved invocation cannot produce a side effect.

2. **Credential hygiene.** ``redact_secrets`` makes text safe to log or record,
   and ``credential_environment_conflicts`` refuses a public-artifact fetch
   while an ambient Hugging Face token is present, because that fetch must be
   able to show it used no credential at all.

Nothing in this module reads a credential: redaction only removes material that
is already in a string. The only secret this repository handles is the Forgejo
token, and it is read by ``r02_release.py`` through the pre-provisioned Git
Credential Manager helper, never here.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

try:  # bare script (sys.path[0] is scripts/) or scripts/ already on sys.path
    from r02_preflight import UNSET
except ModuleNotFoundError:  # imported as scripts.<module> from the repository root
    from scripts.r02_preflight import UNSET

SCOPE_ARTIFACT_FETCH = "r02-artifact-fetch"
SCOPE_READINESS_SMOKE = "r02-readiness-smoke"
SCOPE_RELEASE_ROUND_TRIP = "r02-release-round-trip"

KNOWN_SCOPES = (SCOPE_ARTIFACT_FETCH, SCOPE_READINESS_SMOKE, SCOPE_RELEASE_ROUND_TRIP)

FIELDS = ("granted", "scope", "reference", "approved_by", "approved_at_utc")

AMBIENT_CREDENTIAL_VARS = (
    "HF_TOKEN",
    "HUGGING_FACE_HUB_TOKEN",
    "HUGGINGFACE_TOKEN",
    "HF_HUB_TOKEN",
)

EXIT_OK = 0
EXIT_STEP_FAILED = 1
EXIT_GATE_CLOSED = 2

REDACTED = "REDACTED"

# Scheme words that introduce the real secret, as in "Authorization: Bearer X"
# or "Authorization: token X". The scheme word is kept; the secret is not.
_SCHEME_WORDS = {"bearer", "token", "basic", "apikey", "api_key", "key"}

_KEY_VALUE = re.compile(
    r"(?i)\b(token|api[_-]?key|password|passwd|secret|authorization|bearer)\b"
    r"(\s*[:=]\s*)"
    r"(\"?)([^\s\"'&,;]+)"
    r"(?:\s+([A-Za-z0-9._\-]{6,}))?"
)
# "Bearer <secret>" and "token <secret>" without a colon, as in a header line
# that was flattened. Bounded to long token-shaped values so ordinary prose is
# left alone: "authorization file not found" must not become "authorization
# REDACTED not found", which would corrupt the error a reader needs.
_SCHEME_VALUE = re.compile(r"(?i)\b(bearer|token)\s+([A-Za-z0-9._\-]{8,})")
_BARE_TOKEN = re.compile(r"\bhf_[A-Za-z0-9]{8,}\b")


class GateClosed(RuntimeError):
    """A live step was attempted without a matching authorization record."""


class AuthorizationError(GateClosed):
    """An authorization record was present but malformed or inconsistent."""


@dataclass(frozen=True)
class Authorization:
    """The approval a live step is executed under.

    ``scope`` names exactly one step so a grant for one step cannot be spent on
    another; ``reference`` names the review that produced it.
    """

    granted: bool
    scope: str
    reference: str
    approved_by: str
    approved_at_utc: str
    extra: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any], *, source: str = "mapping") -> "Authorization":
        if not isinstance(data, Mapping):
            raise AuthorizationError(f"{source}: authorization must be a JSON object")
        missing = [name for name in FIELDS if name not in data]
        if missing:
            raise AuthorizationError(f"{source}: missing field(s): {', '.join(missing)}")
        granted = data["granted"]
        if not isinstance(granted, bool):
            raise AuthorizationError(f"{source}: 'granted' must be true or false, not {granted!r}")
        scope = data["scope"]
        if scope not in KNOWN_SCOPES:
            raise AuthorizationError(
                f"{source}: unknown scope {scope!r}; expected one of {', '.join(KNOWN_SCOPES)}"
            )
        for name in ("reference", "approved_by", "approved_at_utc"):
            value = data[name]
            if not isinstance(value, str) or not value.strip() or value.strip() == UNSET:
                raise AuthorizationError(f"{source}: '{name}' must name the approval, not {value!r}")
        extra = {k: v for k, v in data.items() if k not in FIELDS}
        return cls(
            granted=granted,
            scope=scope,
            reference=data["reference"].strip(),
            approved_by=data["approved_by"].strip(),
            approved_at_utc=data["approved_at_utc"].strip(),
            extra=extra,
        )

    @classmethod
    def from_file(cls, path: str | Path) -> "Authorization":
        candidate = Path(path)
        if not candidate.is_file():
            raise GateClosed(f"authorization file not found: {candidate}")
        try:
            data = json.loads(candidate.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise AuthorizationError(f"{candidate}: not valid JSON ({exc.msg})") from exc
        return cls.from_mapping(data, source=str(candidate))

    def to_record(self) -> dict[str, Any]:
        record: dict[str, Any] = {name: getattr(self, name) for name in FIELDS}
        record.update(self.extra)
        return record


def require_authorization(authorization: Authorization | None, *, scope: str) -> Authorization:
    """Return the grant for ``scope`` or raise before any side effect happens."""
    if authorization is None:
        raise GateClosed(
            f"no authorization supplied for {scope!r}: this step runs only under an "
            "approval record naming its reviewer"
        )
    if not isinstance(authorization, Authorization):
        raise AuthorizationError("authorization must be an Authorization record")
    if not authorization.granted:
        raise GateClosed(f"authorization for {scope!r} is not granted")
    if authorization.scope != scope:
        raise GateClosed(
            f"authorization scope {authorization.scope!r} does not cover {scope!r}"
        )
    return authorization


def is_unset(value: Any) -> bool:
    """True when ``value`` is the ``UNSET`` marker.

    Value equality, not identity: a manifest that has been through a JSON round
    trip carries a different ``str`` object with the same text, and identity
    comparison would silently treat it as a real measurement.
    """
    return isinstance(value, str) and value == UNSET


def _redact_key_value(match: "re.Match[str]") -> str:
    key, separator, quote, value = match.group(1), match.group(2), match.group(3), match.group(4)
    if value.lower() in _SCHEME_WORDS:
        # Drop the scheme word's value as well; it is the credential.
        return f"{key}{separator}{value} {REDACTED}"
    return f"{key}{separator}{quote}{REDACTED}"


def redact_secrets(text: Any, secrets: tuple[str, ...] | list[str] = ()) -> str:
    """Return ``text`` with credential-shaped substrings replaced.

    Used for every error message and log line that could carry a URL, a header,
    or a credential the caller already holds. Redaction is conservative: a key
    such as ``token=`` or ``Authorization:`` always has its value replaced even
    when that value is harmless.
    """
    out = str(text)
    for secret in secrets:
        if secret:
            out = out.replace(str(secret), REDACTED)
    out = _KEY_VALUE.sub(_redact_key_value, out)
    out = _SCHEME_VALUE.sub(lambda m: f"{m.group(1)} {REDACTED}", out)
    out = _BARE_TOKEN.sub(REDACTED, out)
    return out


def credential_environment_conflicts(env: Mapping[str, str] | None = None) -> list[str]:
    """Names of ambient credential variables that make an anonymous fetch unprovable.

    Only names are returned; values are never read into a record, a log, or an
    error message.
    """
    environment = os.environ if env is None else env
    return [name for name in AMBIENT_CREDENTIAL_VARS if environment.get(name)]


def parse_authorization_argv(argv: list[str] | None = None) -> tuple[Authorization, str]:
    """CLI helper: ``--authorization-file`` -> (Authorization, path).

    Kept here so every entry point resolves the gate the same way. Raises
    ``GateClosed`` when the flag is absent, which is the fail-closed path.
    """
    import argparse

    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--authorization-file", required=True)
    args, _ = parser.parse_known_args(argv)
    return Authorization.from_file(args.authorization_file), args.authorization_file
