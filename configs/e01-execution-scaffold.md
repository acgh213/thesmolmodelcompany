# E01 execution scaffold — preflight only

Status: scaffold for review. Owner Eido (compute). Reviewer Research A (Vesper).

This is the execution-side seam for the first controlled records baseline
tracked in issue #21. It is a **preflight**: it validates, and it stops. No run
is implemented here, and nothing in this change executes anything.

The boundary this respects is issue #21's ordering:

    protocol freeze -> independent review -> recorded operator go -> execution

The generator, scorer, split and reference-answer apparatus is Research B's and
is deliberately absent from this scaffold. See
[the R03 generator/scorer/split protocol](../docs/R03-generator-scorer-split-protocol.md)
for that contract and [the E01 design](../experiments/E01-representation-and-skills.md)
for the experiment it serves.

## What it does

Three modules and their tests, all standard library only:

| File | Purpose |
|---|---|
| [scripts/e01_gate.py](../scripts/e01_gate.py) | Authorization for the `e01-execution` scope, run-target layout, exit codes |
| [scripts/e01_identity.py](../scripts/e01_identity.py) | Reads the pinned model identity back from the merged readiness record and asserts the declared plan against it |
| [scripts/e01_preflight.py](../scripts/e01_preflight.py) | The fail-closed entry point; gate first, then target, then identity and freeze |

Two properties are worth a reviewer's attention.

**The pin is read, not restated.** Issue #21 fixes the model identity by
reference. `load_pin` reads the merged
[readiness record](../results/R02/r02-smoke-001/manifest.json) and requires its
two files — the run manifest and the artifact manifest — to agree on `source`,
`repo_id`, `precision` and `revision`. A record whose own two files disagree is
not accepted as a pin. There is no module-level constant to drift, and every
identity field is pinned rather than the revision alone, so a plan cannot swap
`precision` or `source` under a matching revision.

**The freeze is executable.** `freeze_problems` refuses while the plan's
`generator_revision`, `scorer_revision`, `episode_manifest_sha256` or
`reference_answers_sha256` is still `UNSET`. The protocol branch freezes all four:
`records-v1`, `e01-records-scorer-v1`, and the byte hashes of the 32-episode
candidate manifest and independent reference-answer file. Resource fields remain
`UNSET` until the authorized run records measurements. The preflight also refuses
any generated files whose bytes do not match those frozen hashes.

## What it does not do

- No dependency install. Standard library only, so it runs in an interpreter
  with nothing installed.
- No artifact retrieval and no transport. There is no client, no URL and no
  `fetch_and_hash` seam; retrieval stays in
  [scripts/r02_artifacts.py](../scripts/r02_artifacts.py) and is not
  re-implemented. A test asserts the seam is absent.
- No model or tokenizer load, no CUDA call, no GPU reservation. Tests assert
  neither `torch` nor `transformers` is imported by a preflight run.
- No generator, scorer, split or reference answers.
- No run directory, authorized or not. Nothing writes under `results/`.
- No training, tuning, prompt search, final-split access or ablation.

## Replay commands

From the repository root, with an interpreter that has nothing installed:

```
python3 scripts/e01_preflight.py --run-id e01-pilot-001 --owner eido \
    --plan configs/e01-execution-plan.json \
    --r02-record results/R02/r02-smoke-001 \
    --run-dir results/E01/e01-pilot-001 \
    --authorization-file /path/to/operator-record.json \
    --episode-manifest /path/to/episode-manifest.jsonl \
    --reference-answers /path/to/reference-answers.jsonl
```

Exit codes: `0` the preflight passed and no run was executed, `1` a check
failed, `2` the gate is closed or the run target is off the layout.

`--record-out FILE` writes the preflight record outside the repository, or
anywhere that is not a `results` path; a `results` path is refused, because the
preflight record is evidence about a run that has not happened. Without the
flag the record goes to stdout and nothing is written at all.

## The operator record

E01 needs two separate decisions, and the record must not read as though the
reviewer authorized the run. The accepted shape:

```json
{
  "granted": true,
  "scope": "e01-execution",
  "reference": "protocol PR <n>, review <id>; operator go recorded separately",
  "approved_by": "vesper",
  "approved_at_utc": "<the procedure review's submitted_at>",
  "experiment": "E01",
  "run_id": "e01-pilot-001",
  "operator_go": "cassie",
  "operator_go_received_before_utc": "<operator decision timestamp>",
  "procedure_reviewer_only": true
}
```

- `scope` must be exactly `e01-execution`. The scope set is closed, so the
  merged `r02-readiness-smoke` grant cannot be spent here — its own note records
  that it was "Not authorization for training, tuning, evaluation, or any
  experiment".
- `run_id` must name the run, which is what issue #21 means by "a separate
  operator go/no-go names the experiment ID".
- `procedure_reviewer_only` must be `true`, so `approved_by` cannot be read as
  the person who authorized the run.
- `approved_at_utc` is the *procedure* review's timestamp, not an execution
  approval time; the operator decision carries its own.

Open review question: `templates/approval-record.json` does not exist on `main`,
so this shape is derived from the merged records under `results/R02/`. If the
repository wants a single canonical authorization schema, this validator is
where the field set should be reconciled.

## Limits of this change

- The scaffold is not wired into any index or workflow. That keeps the diff to
  new files while Research B's protocol PR is in flight, at the cost of
  discoverability.
- The preflight is not a substitute for the run manifest required by
  [the coordination notes](../docs/coordination.md). It records what was checked
  before a run, not what a run produced.
- No run exists, so [the results ledger](../docs/results.md) is untouched and
  stays empty.
- Nothing here has been executed against a real authorization: every gate test
  uses a fixture record, and the only real files read are the committed
  readiness records under `results/R02/`.
