#!/usr/bin/env python3
"""Freeze E01 records candidates and independent references deterministically."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from smolmodelcompany.episode import canonical_json
from smolmodelcompany.records import generate_episode

GENERATOR_REVISION = "records-v1"
SCORER_REVISION = "e01-records-scorer-v1"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(canonical_json(row) + "\n" for row in rows), encoding="utf-8")


def build(seed_sets: dict[str, list[int]], record_count: int = 5) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    candidates: list[dict[str, Any]] = []
    references: list[dict[str, Any]] = []
    metadata: list[dict[str, Any]] = []
    index = 0
    for split in ("development", "final"):
        for requested_seed in seed_sets[split]:
            episode = generate_episode(requested_seed, split=split)
            budget = {"max_new_tokens": 256, "time_cap_seconds": 1200}
            payload = episode.candidate_payload(budget)
            episode_id = payload["task_id"]
            candidates.append({"index": index, "episode_id": episode_id, "payload": payload})
            references.append({"index": index, "episode_id": episode_id, "answer": episode.scorer_record()["answer"]})
            metadata.append({
                "index": index,
                "episode_id": episode_id,
                "split": split,
                "requested_seed": requested_seed,
                "effective_seed": episode.seed,
                "record_hash": episode.record_hash(),
                "structure_signature": episode.structure_signature,
            })
            index += 1
    return candidates, references, metadata


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    seed_sets = {"development": config["task"]["development_seeds"], "final": config["task"]["final_seeds"]}
    candidates, references, metadata = build(seed_sets, config["task"]["record_count"])
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    paths = {
        "episode_manifest": output / "episode-manifest.jsonl",
        "reference_answers": output / "reference-answers.jsonl",
        "metadata": output / "episode-metadata.jsonl",
    }
    _write_jsonl(paths["episode_manifest"], candidates)
    _write_jsonl(paths["reference_answers"], references)
    _write_jsonl(paths["metadata"], metadata)
    result = {
        "generator_revision": GENERATOR_REVISION,
        "scorer_revision": SCORER_REVISION,
        "counts": {"development": len(seed_sets["development"]), "final": len(seed_sets["final"]), "total": len(candidates)},
        "files": {name: {"path": str(path), "sha256": _sha256(path), "bytes": path.stat().st_size} for name, path in paths.items()},
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
