"""Importable artifact fetch/hash helper; CLI execution is explicitly opt-in."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
from typing import Callable

def sha256_stream(path: str | Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()

def hash_tree(root: str | Path) -> list[dict[str, object]]:
    base = Path(root)
    return [{"path": str(path.relative_to(base)), "bytes": path.stat().st_size, "sha256": sha256_stream(path)} for path in sorted(p for p in base.rglob("*") if p.is_file())]

def fetch_and_hash(fetch: Callable[[str, str, str], str], repo_id: str, revision: str, out: str | Path) -> dict[str, object]:
    """Fetch through injected transport and hash the resulting local tree."""
    out_path = Path(out)
    root = Path(fetch(repo_id, revision, str(out_path.parent)))
    result = {"repo_id": repo_id, "revision": revision, "files": hash_tree(root)}
    out_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-id", required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--out", required=True)
    parser.error("network artifact retrieval requires an explicitly authorized injected transport")
    return 2
if __name__ == "__main__":
    raise SystemExit(main())
