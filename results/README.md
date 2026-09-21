# Run results

One directory per run:

```
results/<experiment-id>/<run-id>/
    report.md        # YAML front matter + the sections in templates/result.md
    manifest.json    # the run manifest required by docs/coordination.md
```

`docs/results.md` is **generated** from the `report.md` front matter by
`scripts/build_results_ledger.py`. Never hand-edit the ledger table; edit the
run report and regenerate. CI fails if the ledger is stale.

## Required front matter

```yaml
---
experiment: E01
run_id: e01-pilot-001
candidate: "condition D (canonical repr + primitives)"
baseline: "condition A (direct answer)"
split_axis: "unseen composition"
quality: "41/100 vs 33/100; +8pp, 95% CI [1, 15]"
resource_cost: "2.1 GPU-h, peak 7.4 GiB VRAM, $0"
status: "inconclusive — continue to confirmatory"
claim_level: "development signal"
evidence: "results/E01/e01-pilot-001/manifest.json"
date: 2026-10-04
---
```

The values above are a **format illustration only** — they are not measurements
and no run has produced them.

Raw predictions, logs and large outputs are git-ignored. Store them in durable
artifact storage and reference them by URI and hash in `manifest.json`.

## Device-smoke runs (R02)

R02 attempts live under `results/R02/<run-id>/` and carry more than a report:
the approval record the attempt ran under, the artifact manifest with its
per-file revision, size and SHA-256, the timestamped resource samples, the run
manifest, and the run report. `raw/` and `predictions/` stay git-ignored, and a
failed attempt keeps its own directory instead of being overwritten. The layout,
the ownership, and the replay commands are defined in
[the R02 recipe](../configs/r02-baseline-environment.md), which is the
reproducibility boundary for those runs.
