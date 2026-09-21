"""Authorized-gate artifact retrieval and hashing procedure."""
from __future__ import annotations
import argparse, hashlib, json, os, sys
from pathlib import Path
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

def sha256_stream(path: str | Path, chunk_size: int = 1024 * 1024) -> str:
    d = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""): d.update(chunk)
    return d.hexdigest()

def hash_tree(root: str | Path) -> list[dict[str, object]]:
    base = Path(root)
    return [{"path": str(p.relative_to(base)), "bytes": p.stat().st_size, "sha256": sha256_stream(p)} for p in sorted(base.rglob("*")) if p.is_file()]

def fetch_and_hash(fetch, repo_id: str, revision: str, out: str | Path) -> dict[str, object]:
    out_path = Path(out); root = Path(fetch(repo_id, revision, str(out_path.parent)))
    result = {"repo_id": repo_id, "revision": revision, "files": hash_tree(root)}
    out_path.parent.mkdir(parents=True, exist_ok=True); out_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result

def authorized_fetch(repo_id: str, revision: str, destination: str) -> str:
    if os.environ.get("R02_APPROVED") != "1": raise PermissionError("set R02_APPROVED=1 after review approval")
    from huggingface_hub import snapshot_download
    return snapshot_download(repo_id=repo_id, revision=revision, local_dir=destination, local_dir_use_symlinks=False)

def main() -> int:
    p=argparse.ArgumentParser(); p.add_argument("--repo-id",required=True); p.add_argument("--revision",required=True); p.add_argument("--out",required=True); a=p.parse_args()
    if os.environ.get("R02_APPROVED") != "1": p.error("artifact retrieval requires explicit post-approval gate: R02_APPROVED=1")
    fetch_and_hash(authorized_fetch, a.repo_id, a.revision, a.out); return 0
if __name__ == "__main__": raise SystemExit(main())
