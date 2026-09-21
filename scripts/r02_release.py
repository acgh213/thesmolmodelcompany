"""Reviewable release persistence procedure using injected transport."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from scripts.r02_preflight import sha256_stream
@dataclass(frozen=True)
class ReleaseRoundTrip:
    source_sha256: str
    readback_sha256: str
    source_bytes: int
    readback_bytes: int
    release_id: str
    asset_id: str

def release_round_trip(source: str | Path, transport: object) -> ReleaseRoundTrip:
    path = Path(source)
    release_id = transport.create_release()
    try:
        asset_id = transport.upload_asset(release_id, path)
        download = transport.read_asset_url(release_id, asset_id)
        payload = transport.download(download)
        result = ReleaseRoundTrip(sha256_stream(path), __import__('hashlib').sha256(payload).hexdigest(), path.stat().st_size, len(payload), release_id, asset_id)
        if result.source_sha256 != result.readback_sha256 or result.source_bytes != result.readback_bytes:
            raise ValueError("release round-trip mismatch")
        return result
    finally:
        transport.delete_release(release_id)
