# Evaluation protocol

Status: proposed contract. No benchmark or scorer has been implemented yet.

## Questions and task families

Measure separately: rule induction from examples; composition of known operations in unseen structures; solution-length/depth extrapolation; robustness to irrelevant presentation changes; and transfer to new domains. A gain on one axis does not establish all five.

Start with compositional data transformations, finite-state tracking/planning, and small rule-induction tasks. Include natural-language versions so purely symbolic competence is not confused with understanding user requests. Validate generators against an independent reference implementation or hand-audited exhaustive small cases. Examine degenerate cases, duplicate answers, impossible instances, and unintended shortcuts.

Later add held-out practical code/data, grounded local-document, and constrained multi-step tasks. Keep a small language/instruction regression set. Open-ended quality needs a stated rubric and human review; an LLM judge is secondary evidence and its cost/version must be disclosed.

## Splits and leakage

1. Training: fit weights, libraries, retrievers, or representation translators.
2. Development: tune prompts, hyperparameters, search/recurrence limits, and stopping rules.
3. Final: compare frozen candidates once under the frozen protocol.

Split by latent rules/program structure and family, not just by random surface strings. Include a composition holdout built from seen primitives and a separate depth/length extrapolation holdout. Deduplicate across splits using both canonical structure and surface similarity. Record what cannot be audited in pretrained model corpora.

All training-time teacher traces and discovered abstractions must originate in the training split. Permitted support examples for adaptation are explicitly part of each test task, distinct from its hidden query answers. Reset adaptive weights, caches, skill updates, and task memory between independent episodes. A persistent-learning evaluation requires its own chronological protocol.

Final evaluation is protected by process until an access-control mechanism is actually implemented. Do not call a file sealed merely because of its name or hash. Never import another project's sealed set as a convenient baseline.

## Baselines and fairness

- Same base checkpoint, direct answering with a competent development-tuned prompt.
- Same checkpoint with comparable extra compute (sampling/search or iterations as appropriate).
- Simple deterministic or non-neural baseline where the task permits it.
- Stronger feasible local checkpoint at a comparable total deployment budget, when available.
- Necessary component ablations and an oracle condition only as a clearly labeled upper-bound diagnostic.

Report parameter-matched and compute-matched experiments separately where both matter. Account for different training data, tokenizer, pretraining history, precision, and kernel support. Do not attribute an existing-checkpoint comparison solely to architecture when these are uncontrolled.

Include tool, verifier, retrieval, library, translation, adaptation, and loading costs. Compare fixed wall-time budgets for practical conclusions; use measured FLOPs/tokens as additional scientific controls where justified. More samples or more recurrent steps are extra inference work.

## Metrics

Primary: task-level correct completion on each declared generalization axis. Report number correct/total, invalid outputs, timeouts, OOMs, verifier errors, and abstentions. Failures count as non-completions for the end-to-end rate and are also broken out separately. Report selective accuracy and coverage if abstention is supported.

Secondary: pass@1, verified success under a declared search budget, adaptation gain, cross-task interference, p50/p95 latency, cold load, peak VRAM/RAM, stored footprint, training compute, and dollar cost. An oracle pass@k score is not equivalent to successful deployed selection: the selection/verifier accuracy must be measured.

Use the same task instances for paired candidate comparisons. Confidence intervals should resample at the independently generated task-family/template level when examples share structure; bootstrapping individual correlated rows can exaggerate confidence. For trained candidates report results across at least three seeds before claiming a robust training effect, or explicitly label fewer seeds as exploratory.

## Pilot and promotion rule

Suggested development pilot: 50–100 instances spread across relevant families, followed by an error and throughput audit. It diagnoses feasibility, not statistical significance. Select final family/sample counts after the pilot, using a stated minimum useful effect, estimated variance/correlation, and compute envelope. Freeze them before final outcomes are seen.

Default proposed minimum useful effect: +5 percentage points in task completion at comparable end-to-end latency/memory, or at least 20% lower latency/peak memory while ruling out more than a 2-point quality loss. These are project decision thresholds, not scientific constants; revise before the final run if the baseline/task makes them inappropriate. For quality improvement, require a paired 95% interval excluding zero and report whether the interval supports the minimum useful effect. For quality non-inferiority, require the lower confidence bound on the candidate-minus-baseline difference to exceed -2 points. Avoid optional stopping; report inconclusive results as inconclusive.

Promote only after independent reproduction and no unexplained collapse on the other declared splits or language regression checks. Multiple development candidates are exploratory; confirm only the frozen finalist or apply an explicitly specified multiple-comparison procedure.

## Claim levels

Feasibility → development signal → controlled final result → independently reproduced result → practical local transfer. Label every result with its level, domain, baseline, and resource envelope. A toy algorithmic result cannot skip directly to a claim about general assistant capability.
