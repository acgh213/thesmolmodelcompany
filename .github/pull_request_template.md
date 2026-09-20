## Task / experiment ID

<!-- e.g. R03, or E01 run e01-pilot-002. Use the handoff format in agents/README.md. -->

## What changed

<!-- Concrete description of the change. Not a narrative of effort. -->

## Exact evidence path

<!-- Commands run, files produced, manifest or run-report paths. "It works" is not evidence. -->

## What was verified

<!-- What you actually executed and observed, versus what you assumed or reasoned about. -->

## Resource usage

<!-- Wall time, peak VRAM/RAM, GPU time, any billed cost. "N/A — documentation only" is valid. -->

## Remaining uncertainty

<!-- What this change does NOT establish. Required; write "none known" only if you mean it. -->

## Next owner / action

<!-- Who picks this up and what the smallest next step is. -->

---

### Author checklist

- [ ] Claim level is labeled where a result is asserted (see `docs/evaluation.md`).
- [ ] Intrinsic-model gains are not relabeled as complete-system gains.
- [ ] Failures, timeouts, OOMs and invalid outputs are reported, not dropped from denominators.
- [ ] If this touches a shared scorer, generator or split, the other researcher is requested as reviewer.
- [ ] If this is a run, a report exists at `results/<experiment>/<run-id>/report.md` and the ledger was regenerated.
- [ ] No model weights, datasets or raw prediction dumps are committed.
- [ ] No paid compute was provisioned without an authorized cap (`docs/compute.md`).
