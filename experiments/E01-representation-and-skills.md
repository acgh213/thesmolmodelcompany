# E01 — Representation and reusable skills

Status: proposed; owner Research B; reviewer Research A; compute Eido.

## Hypothesis

A small language model can complete unfamiliar compositions more reliably when given a consistent representation and verified reusable operations, within a comparable end-to-end budget. This initially tests system capability, not new intrinsic model competence.

## Task

Generate transformations over small structured records with a bounded operation language: selection, comparison, sorting, grouping, and simple arithmetic. Include natural-language requests. Separate unseen operation compositions, deeper compositions, and paraphrased/renamed inputs. Ensure test programs cannot be recovered from a superficial template ID. Independent execution supplies ground truth.

## Conditions

A: direct answer from raw request; B: direct answer after canonical representation; C: raw request with executable primitive operations; D: canonical representation plus primitive operations; E: canonical representation plus a small authored compound-operation library. Add bounded non-neural program search under the same grammar.

This factorial core separates representation from tool access. Compare D/E to isolate compound skills. Use identical examples and model checkpoints, with development-tuned prompts and matched total runtime limits. An oracle representation is a diagnostic upper bound only. The deployable representation must be produced from exactly the information available to the other conditions; it cannot expose the hidden generator program.

## Measurements and controls

Primary: unseen-composition correct completion. Secondary: deeper-composition success, representation errors, invalid programs, library size, number of candidates/executions, total latency/VRAM/RAM, and direct-answer regression. Count grammar/interpreter/verification and all failed attempts.

Keep primitive and compound semantics fixed before final evaluation. Final task solutions cannot enter the library. Limit language expressiveness and interpreter execution to the stated research task.

## Falsification / stop

Stop or revise if gains vanish when tool access and runtime are matched, if simple normalization or non-neural search explains the improvement, or if the model fails to transfer beyond surface variants. That is useful evidence, not a failed project.

## Follow-on

Only after the authored-library result, add abstraction discovery from training solutions. Compare learned libraries against an equally sized authored library and simple frequency-based macros. Test held-out structure, not just shorter token sequences.

## Recipe decisions before execution

R01 selects an exact checkpoint. R03 fixes generators/scorers/splits. R04 supplies prompts, operation grammar, runtime caps, sample counts after a pilot, and the full config using templates/experiment.md. No executable recipe exists yet.
