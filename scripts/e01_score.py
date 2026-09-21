#!/usr/bin/env python3
"""Score frozen E01 JSON predictions without consulting the generator."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from smolmodelcompany.episode import canonical_json

SCORER_REVISION = "e01-records-scorer-v1"


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"{path}:{line_number}: row is not an object")
        rows.append(value)
    return rows


def _answer_hash(answer: Any) -> str:
    return hashlib.sha256(canonical_json(answer).encode("utf-8")).hexdigest()


def score(reference_path: Path, prediction_path: Path) -> dict[str, Any]:
    references = {row["episode_id"]: row["answer"] for row in _load_jsonl(reference_path)}
    predictions = {row["episode_id"]: row for row in _load_jsonl(prediction_path)}
    rows: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    for episode_id, answer in references.items():
        if episode_id not in predictions:
            kind = "missing"
            row = {"episode_id": episode_id, "error_class": kind, "correct": False}
        else:
            raw = predictions[episode_id].get("text")
            try:
                parsed = json.loads(raw) if isinstance(raw, str) else raw
            except (json.JSONDecodeError, TypeError):
                parsed = None
                kind = "invalid_json"
            else:
                if not isinstance(parsed, list):
                    kind = "schema_or_parse_error"
                elif parsed == answer:
                    kind = "correct"
                else:
                    kind = "exact_mismatch"
            row = {"episode_id": episode_id, "error_class": kind, "correct": kind == "correct"}
        counts[kind] += 1
        rows.append(row)
    total = len(references)
    correct = counts["correct"]
    return {
        "scorer_revision": SCORER_REVISION,
        "total": total,
        "correct": correct,
        "accuracy": correct / total if total else 0.0,
        "error_counts": dict(sorted(counts.items())),
        "episodes": rows,
        "reference_answers_sha256": hashlib.sha256(reference_path.read_bytes()).hexdigest(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--references", required=True)
    parser.add_argument("--predictions", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    report = score(Path(args.references), Path(args.predictions))
    Path(args.output).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "episodes"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
