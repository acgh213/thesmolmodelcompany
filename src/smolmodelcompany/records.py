"""Deterministic compositional-record tasks for R03 Family A.

The generator executor and reference evaluator intentionally do not call each
other.  Their agreement is an audit result, not an implementation shortcut.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import random
from typing import Any, Iterable

from .episode import Episode

Record = dict[str, Any]
Program = tuple[dict[str, Any], ...]


@dataclass(frozen=True, slots=True)
class RecordTask:
    seed: int
    records: tuple[Record, ...]
    program: Program


# This audit intentionally enumerates 4 thresholds × 2 directions × 3 limits
# over one fixed three-record fixture. It is a regression audit, not exhaustive
# coverage of Family A's full grammar.
SMALL_CASE_AUDIT_CASES = 24


def _require_stable_id(rows: Iterable[Record]) -> None:
    if any("id" not in row for row in rows):
        raise ValueError("sort requires an explicit stable id; project must retain it")


def _copy_rows(rows: Iterable[Record]) -> list[Record]:
    return [dict(row) for row in rows]


def canonical_program(program: Program) -> list[dict[str, Any]]:
    """Return plain JSON program data without sharing mutable operation objects."""
    return deepcopy(list(program))


def generator_execute(records: Iterable[Record], program: Program) -> list[Record]:
    """Generator-side imperative executor used when constructing an episode."""
    rows = _copy_rows(records)
    for operation in program:
        kind = operation["kind"]
        if kind == "filter":
            field, comparator, literal = operation["field"], operation["comparator"], operation["literal"]
            if comparator == "eq":
                rows = [row for row in rows if row[field] == literal]
            elif comparator == "gt":
                rows = [row for row in rows if row[field] > literal]
            elif comparator == "lt":
                rows = [row for row in rows if row[field] < literal]
            else:
                raise ValueError(f"unknown comparator: {comparator}")
        elif kind == "derive":
            source, output = operation["source"], operation["output"]
            multiplier, offset = operation["multiplier"], operation["offset"]
            for row in rows:
                row[output] = row[source] * multiplier + offset
        elif kind == "project":
            fields = operation["fields"]
            rows = [{field: row[field] for field in fields} for row in rows]
        elif kind == "sort":
            field = operation["field"]
            _require_stable_id(rows)
            # Stable two-pass ordering preserves ascending immutable-ID ties even
            # when the primary field is descending, as R03 requires.
            rows.sort(key=lambda row: row["id"])
            rows.sort(key=lambda row: row[field], reverse=operation["direction"] == "desc")
        elif kind == "take":
            rows = rows[: operation["count"]]
        elif kind == "group":
            field, source, aggregate, output = (operation[key] for key in ("field", "source", "aggregate", "output"))
            buckets: dict[Any, list[Record]] = {}
            for row in rows:
                buckets.setdefault(row[field], []).append(row)
            grouped: list[Record] = []
            for key in sorted(buckets, key=str):
                values = [row[source] for row in buckets[key]]
                if aggregate == "count":
                    value = len(values)
                elif aggregate == "sum":
                    value = sum(values)
                elif aggregate == "min":
                    value = min(values)
                elif aggregate == "max":
                    value = max(values)
                else:
                    raise ValueError(f"unknown aggregate: {aggregate}")
                grouped.append({"id": f"group:{key}", field: key, output: value})
            rows = grouped
        else:
            raise ValueError(f"unknown operation: {kind}")
    return rows


def _reference_apply(operation: dict[str, Any], rows: tuple[tuple[tuple[str, Any], ...], ...]) -> tuple[tuple[tuple[str, Any], ...], ...]:
    """Independent, functional reference interpreter over tuple-encoded rows."""
    thawed = [dict(row) for row in rows]
    kind = operation["kind"]
    if kind == "filter":
        comparator = {"eq": lambda a, b: a == b, "gt": lambda a, b: a > b, "lt": lambda a, b: a < b}[operation["comparator"]]
        result = [row for row in thawed if comparator(row[operation["field"]], operation["literal"])]
    elif kind == "derive":
        result = [
            row | {operation["output"]: row[operation["source"]] * operation["multiplier"] + operation["offset"]}
            for row in thawed
        ]
    elif kind == "project":
        result = [{field: row[field] for field in operation["fields"]} for row in thawed]
    elif kind == "sort":
        _require_stable_id(thawed)
        by_id = sorted(thawed, key=lambda row: row["id"])
        result = sorted(by_id, key=lambda row: row[operation["field"]], reverse=operation["direction"] == "desc")
    elif kind == "take":
        result = thawed[: operation["count"]]
    elif kind == "group":
        grouped: dict[Any, tuple[Any, ...]] = {}
        for row in thawed:
            key = row[operation["field"]]
            grouped[key] = grouped.get(key, ()) + (row[operation["source"]],)
        reducers = {"count": lambda xs: len(xs), "sum": sum, "min": min, "max": max}
        result = [{"id": f"group:{key}", operation["field"]: key, operation["output"]: reducers[operation["aggregate"]](grouped[key])} for key in sorted(grouped, key=str)]
    else:
        raise ValueError(f"unknown operation: {kind}")
    return tuple(tuple(sorted(row.items())) for row in result)


def reference_execute(records: Iterable[Record], program: Program) -> list[Record]:
    """Reference evaluator, intentionally separate from ``generator_execute``."""
    state = tuple(tuple(sorted(dict(row).items())) for row in records)
    for operation in program:
        state = _reference_apply(operation, state)
    return [dict(row) for row in state]


def structure_signature(program: Program) -> str:
    """Normalize literals/names away while retaining operation and type shape."""
    parts: list[str] = []
    for operation in program:
        kind = operation["kind"]
        if kind == "filter":
            parts.append(f"filter(int,{operation['comparator']},int)")
        elif kind == "derive":
            parts.append("derive(int,int*small+int)")
        elif kind == "project":
            parts.append(f"project({len(operation['fields'])})")
        elif kind == "sort":
            parts.append(f"sort({operation['direction']})")
        elif kind == "take":
            parts.append("take(int)")
        elif kind == "group":
            parts.append(f"group(label,{operation['aggregate']},int)")
        else:
            raise ValueError(kind)
    return "records:" + ">".join(parts)


def generate_task(seed: int, record_count: int = 5) -> RecordTask:
    """Generate one deterministic, nonempty compositional records task."""
    if not 2 <= record_count <= 12:
        raise ValueError("record_count must be in [2, 12]")
    rng = random.Random(seed)
    teams = ("amber", "blue", "copper")
    records = tuple(
        {"id": f"r{index:02d}", "team": teams[rng.randrange(len(teams))], "score": rng.randrange(1, 10), "active": bool(rng.randrange(2))}
        for index in range(record_count)
    )
    threshold = rng.randrange(1, 7)
    program: list[dict[str, Any]] = [
        {"kind": "filter", "field": "score", "comparator": "gt", "literal": threshold},
        {"kind": "derive", "source": "score", "output": "weighted", "multiplier": rng.randrange(1, 4), "offset": rng.randrange(-2, 3)},
    ]
    if rng.randrange(2):
        program.append({"kind": "sort", "field": "weighted", "direction": ("asc", "desc")[rng.randrange(2)]})
        program.append({"kind": "take", "count": rng.randrange(1, min(4, record_count) + 1)})
        program.append({"kind": "project", "fields": ["id", "team", "weighted"]})
    else:
        program.append({"kind": "group", "field": "team", "source": "weighted", "aggregate": ("count", "sum", "min", "max")[rng.randrange(4)], "output": "aggregate"})
        program.append({"kind": "sort", "field": "aggregate", "direction": "desc"})
    task = RecordTask(seed, records, tuple(program))
    if not generator_execute(task.records, task.program):
        # Deterministic retry keeps every retained episode nonempty. The returned
        # task carries its effective seed, so manifests can reproduce it exactly.
        return generate_task(seed + 1, record_count)
    return task


def generate_episode(seed: int, *, split: str = "development") -> Episode:
    task = generate_task(seed)
    answer = generator_execute(task.records, task.program)
    reference = reference_execute(task.records, task.program)
    if answer != reference:
        raise AssertionError("generator and reference disagree")
    rendered = {"records": list(task.records), "operations": canonical_program(task.program)}
    return Episode(
        protocol_version="r03-v1",
        family="records",
        split=split,
        seed=task.seed,
        input_state={"records": list(task.records)},
        rendered_input=rendered,
        support=[],
        query={"task": "apply the provided record operations"},
        answer=answer,
        latent_program={"pipeline": canonical_program(task.program)},
        structure_signature=structure_signature(task.program),
        presentation_variant={"surface": "symbolic"},
        difficulty={"operations": len(task.program), "records": len(task.records)},
        provenance={"generator": "records-v1"},
    )


def small_case_audit() -> list[dict[str, Any]]:
    """Enumerate small filter/sort/take cases and return any disagreement rows."""
    base = ({"id": "a", "score": 1}, {"id": "b", "score": 2}, {"id": "c", "score": 3})
    failures: list[dict[str, Any]] = []
    for threshold in range(0, 4):
        for direction in ("asc", "desc"):
            for count in (1, 2, 3):
                program: Program = (
                    {"kind": "filter", "field": "score", "comparator": "gt", "literal": threshold},
                    {"kind": "sort", "field": "score", "direction": direction},
                    {"kind": "take", "count": count},
                )
                generated, reference = generator_execute(base, program), reference_execute(base, program)
                if generated != reference:
                    failures.append({"program": canonical_program(program), "generator": generated, "reference": reference})
    return failures
