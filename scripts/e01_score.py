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
    reference_rows = _load_jsonl(reference_path)
    prediction_rows = _load_jsonl(prediction_path)
    references: dict[str, dict[str, Any]] = {}
    duplicate_references: list[str] = []
    for row in reference_rows:
        episode_id = str(row["episode_id"])
        if episode_id in references:
            duplicate_references.append(episode_id)
        references[episode_id] = row
    predictions: dict[str, dict[str, Any]] = {}
    duplicate_predictions: list[str] = []
    for row in prediction_rows:
        episode_id = str(row["episode_id"])
        if episode_id in predictions:
            duplicate_predictions.append(episode_id)
        predictions[episode_id] = row
    rows: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    if duplicate_references:
        counts.update({"duplicate_reference": len(duplicate_references)})
    split_counts: dict[str, Counter[str]] = {"development": Counter(), "final": Counter()}
    for episode_id, reference in references.items():
        answer = reference["answer"]
        split = str(reference.get("split", "UNSET"))
        if episode_id not in predictions:
            kind = "missing"
            row = {"episode_id": episode_id, "split": split, "error_class": kind, "correct": False}
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
            row = {"episode_id": episode_id, "split": split, "error_class": kind, "correct": kind == "correct"}
        counts[kind] += 1
        split_counts.setdefault(split, Counter())[kind] += 1
        rows.append(row)
    for episode_id in duplicate_predictions:
        counts["duplicate_prediction"] += 1
        rows.append({"episode_id": episode_id, "error_class": "duplicate_prediction", "correct": False})
    for episode_id in sorted(set(predictions) - set(references)):
        counts["unknown_prediction"] += 1
        rows.append({"episode_id": episode_id, "error_class": "unknown_prediction", "correct": False})
    total = len(reference_rows)
    correct = counts["correct"]
    aggregates = {
        split: {
            "total": sum(values.values()),
            "correct": values["correct"],
            "accuracy": values["correct"] / sum(values.values()) if sum(values.values()) else 0.0,
            "error_counts": dict(sorted(values.items())),
        }
        for split, values in split_counts.items()
        if values
    }
    return {
        "scorer_revision": SCORER_REVISION,
        "total": total,
        "correct": correct,
        "accuracy": correct / total if total else 0.0,
        "error_counts": dict(sorted(counts.items())),
        "split_aggregates": aggregates,
        "duplicate_reference_ids": sorted(set(duplicate_references)),
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
