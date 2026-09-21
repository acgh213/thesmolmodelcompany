"""Model smoke entry point with explicit manifest scaffolding only."""
from __future__ import annotations
import argparse
import json
import time
from pathlib import Path
from scripts.r02_preflight import build_manifest

def create_run_directory(root: str | Path, run_id: str) -> Path:
    path = Path(root) / run_id
    if path.exists():
        raise FileExistsError(f"run directory already exists: {path}")
    path.mkdir(parents=True)
    return path

def write_manifest(run_dir: str | Path, **updates: object) -> Path:
    path = Path(run_dir) / "manifest.json"
    manifest = build_manifest()
    manifest.update(updates)
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return path

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--repo-id", required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--dtype", required=True)
    parser.add_argument("--device", required=True)
    parser.add_argument("--max-new-tokens", type=int, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.error("model execution requires an explicitly authorized run")
    return 2
if __name__ == "__main__":
    raise SystemExit(main())
