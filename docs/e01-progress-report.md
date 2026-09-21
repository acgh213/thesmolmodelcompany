# E01 progress report — protocol complete, run pending

**Report date:** 2026-09-21  
**Program:** The Smol Model Company of New Haven  
**Claim tier:** protocol and readiness record; no experiment result

## Current position

The first controlled E01 baseline is ready to run, but this report deliberately
contains no model score. The reviewed protocol, prompt renderer, and execution
runner are merged into canonical Forgejo. The authorized compute handoff has not
yet produced a reviewable E01 run record, so the results ledger remains empty.

- **R03 apparatus:** merged model-free episode boundary, compositional records,
  and finite-state generator/reference audits.
- **R02 readiness:** pinned `Qwen/Qwen2.5-1.5B` readiness smoke completed on the
  local WSL/GPU environment and was independently reviewed. It verified model
  load, artifact/cache identity, resource capture, and durable release
  round-trip cleanup. It was not an experiment.
- **E01 protocol:** 32 deterministic structured-record episodes: 8 development
  and 24 held-out final. The condition supplies canonical records and explicit
  primitive operations; it does not test hidden-program discovery.
- **E01 execution:** one greedy generation per episode, maximum 256 new tokens,
  no tuning, no retry, no ablation, and explicit error classes for missing,
  invalid, schema-invalid, or mismatched output.
- **Operator record:** the exact `e01-pilot-001` go/no-go is held outside Git;
  its full record is published in Forgejo issue #21 comment [#966](https://durandal.exe.xyz/smolmodelco/thesmolmodelcompany/issues/21#issuecomment-966), after the prompt/runner approval and merge. It remains unspent until the reviewed runner executes.

## Frozen provenance

- E01 protocol merge: `4c1b373`
- Prompt/runner merge: `4f90434`
- Procedure review: Vesper, Forgejo review #51 (protocol freeze) and review #54 (prompt/runner)
- Run authorization: Cassie, exactly `e01-pilot-001`, recorded in issue #21
- Episode manifest SHA-256:
  `ecb832a72bb39c87ba9821c07a31e538d735632acd0cf0b01f39eebc7ac14b7c`
- Reference-answer SHA-256:
  `53f235d147f2da4d922448c44904a3fbcd2916d7ee6f034d35179ec34e144562`
- Prompt-set SHA-256:
  `32f7465f8bad3107a9183dabe7f350ba05d696e2eec54837399cb548e22db05a`

The candidate surface is checked recursively to exclude scorer-side answer,
latent-program, seed, split, and provenance fields. The references are separate
from the candidate manifest and are hashed before model invocation.

## What this report does not claim

No accuracy, quality, reasoning, transfer, throughput, or assistant-capability
claim is made here. No E01 result has entered `docs/results.md`; an empty ledger
is the honest state until the run produces a manifest, aggregate, errors,
resource record, and independently reviewed evidence PR.

The next record will be the E01 run report itself. A failed or incomplete run
will be preserved rather than silently retried or replaced.
