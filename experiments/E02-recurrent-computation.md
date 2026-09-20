# E02 — Recurrent computation under controlled budgets

Status: proposed; owner Research A; reviewer Research B; compute Eido.

## Hypothesis

Reusing a small computational block can improve transfer to longer reasoning chains under a limited parameter budget, with a useful inference-cost trade-off compared with ordinary depth or additional sampled solutions.

## Two separate studies

Mechanism probe: train a small recurrent model and ordinary transformer controls on the same generated finite-state/graph execution tasks. Plan within the 10–100M range only after a throughput pilot. Fix tokenizer, training distribution, optimizer family, and token budget where compatible. Report shared-parameter and unshared-parameter counts.

Practical probe: evaluate an existing recurrent language-model checkpoint only if its official runtime fits Eido's measured resources. Compare to an ordinary local checkpoint, while disclosing uncontrolled pretraining and tokenizer differences. This study cannot independently prove an architectural advantage.

**Status: closed on the current host.** [Decision 0002](../docs/decisions/0002-measured-host-envelope.md) records a 1.93 GiB deficit at `num_steps=16` and 4.51 GiB at `num_steps=32` against measured free VRAM, before activations — assuming BF16 weights and a full-retention cache. E02 proceeds as the mechanism probe only. Re-open on a change to measured headroom, cache policy, runtime, or precision, and only via a bounded smoke test proving load plus one inference batch.

## Comparisons

1. Parameter-matched recurrence versus ordinary depth: extra computation is allowed but measured.
2. Training-compute-matched comparison: adjust token/step budgets explicitly and disclose the resulting data-exposure difference.
3. Inference-budget curves: recurrence steps versus direct decoding and additional sampled candidates under the same wall-time envelope.
4. Fixed recurrence versus an adaptive stopping rule fitted only on development data.

Train on bounded solution depths and evaluate both interpolation and longer-depth extrapolation. Hold task-family structure out as a separate axis. Do not conflate longer input context with longer required reasoning.

## Measurements

Correct completion by required solution depth, recurrence count, actual elapsed time, peak memory, training cost, stability across seeds, and failure modes. Include sampled-candidate selection cost and accuracy; oracle choice is only a diagnostic bound.

## Falsification / stop

Stop or revise if the advantage disappears under the declared compute comparison, if extra iterations degrade state stability, if adaptive stopping adds no benefit over a tuned fixed count, or if recurrence only memorizes the training depth range. A useful parameter/storage trade-off may survive without a speed advantage; report it as such.

## Recipe decisions before execution

R05 specifies architecture, initialization, data/compute budgets, training checks, seed count, exact extrapolation bands, and iteration limits after R00/R02 establish host throughput. No published large-model pretraining claim is a local run estimate.
