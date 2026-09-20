# Experiment protocol template

Copy to a named experiment revision. Replace each instruction with a concrete value before freezing; this template is not a runnable protocol.

- Identity: experiment ID, revision, owner, independent reviewer, status, code branch/commit.
- Claim: one falsifiable hypothesis, intended claim level, and intrinsic-model versus complete-system scope.
- Evidence: primary sources, existing implementation/checkpoint, uncertainty, and novelty limits.
- Task: inputs, allowed support information, outputs, independent ground truth, target generalization axis.
- Splits: generator/data hashes, canonical split unit, duplicates/contamination checks, final access owner.
- Candidates: exact model/tokenizer revisions, precision, adapters, library/retrieval versions.
- Comparisons: strong baseline, necessary ablations, equal-information conditions, matching strategy and residual confounds.
- Procedure: commands/configs, seeds, reset/lifetime rules, resource recorder, artifact location.
- Budgets: pilot/final sample size rationale, time/tokens/steps/search/recurrence caps, peak-memory target, maximum spend and authorization if paid.
- Metrics: primary outcome, failure denominator, uncertainty method, minimum useful effect, secondary costs/regressions.
- Decisions: promotion, falsification, inconclusive, and stop criteria; fixed final analysis with no optional stopping.
- Review: reviewer decision and date; frozen protocol hash; any subsequent changes and why.
