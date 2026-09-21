"""Model-free helpers for the R02 reproducibility preflight."""
from __future__ import annotations
import hashlib
import shutil
from pathlib import Path
from typing import Callable
UNSET = "UNSET"
def sha256_stream(path: str | Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()
def build_manifest() -> dict[str, object]:
    return {"model": UNSET, "revision": UNSET, "measurements": {"peak_vram_mib": UNSET, "peak_ram_mib": UNSET, "stored_footprint_bytes": UNSET, "loaded_footprint_bytes": UNSET}, "timing": {"cold_load_seconds": UNSET, "warm_inference_seconds": UNSET}, "bootstrap_resolution": UNSET, "independent_reconstruction": UNSET}
def persistence_round_trip(source: str | Path, storage_dir: str | Path, *, readback: Callable[[Path], bytes] | None = None) -> dict[str, object]:
    source_path, storage = Path(source), Path(storage_dir)
    storage.mkdir(parents=True, exist_ok=True)
    persisted = storage / source_path.name
    shutil.copyfile(source_path, persisted)
    try:
        result = {"source_sha256": sha256_stream(source_path), "source_bytes": source_path.stat().st_size}
        if readback is None:
            result.update(readback_sha256=sha256_stream(persisted), readback_bytes=persisted.stat().st_size)
        else:
            payload = readback(persisted)
            result.update(readback_sha256=hashlib.sha256(payload).hexdigest(), readback_bytes=len(payload))
        return result
    finally:
        persisted.unlink(missing_ok=True)
        try: storage.rmdir()
        except OSError: pass
def fetch_and_hash(*_args: object, **_kwargs: object) -> None:
    """Importable seam, intentionally not invoked."""
    raise NotImplementedError("artifact retrieval is outside the model-free preflight")
