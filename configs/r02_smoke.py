"""Authorized-gate R02 smoke procedure; no model work without approval."""
from __future__ import annotations
import argparse, json, os, sys
from pathlib import Path
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.r02_preflight import build_manifest

def create_run_directory(root: str | Path, run_id: str) -> Path:
    path=Path(root)/run_id
    if path.exists(): raise FileExistsError(f"run directory already exists: {path}")
    path.mkdir(parents=True); return path

def write_manifest(run_dir: str | Path, **updates: object) -> Path:
    path=Path(run_dir)/"manifest.json"; manifest=build_manifest(); manifest.update(updates)
    path.write_text(json.dumps(manifest, indent=2)+"\n", encoding="utf-8"); return path

def main() -> int:
    p=argparse.ArgumentParser();
    for name in ("run-dir","repo-id","revision","dtype","device"): p.add_argument("--"+name,required=True)
    p.add_argument("--max-new-tokens",type=int,required=True); p.add_argument("--seed",type=int,required=True); a=p.parse_args()
    if os.environ.get("R02_APPROVED") != "1": p.error("model execution requires explicit post-approval gate: R02_APPROVED=1")
    raise NotImplementedError("authorized model runner is intentionally not part of this model-free change")
if __name__ == "__main__": raise SystemExit(main())
