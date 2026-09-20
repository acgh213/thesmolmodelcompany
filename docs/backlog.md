# Initial backlog

Status: proposed work packages, not claims of implementation or active assignments. The written design must be reviewed before the implementation plan and execution phase. Read-only source/host audits and protocol proposals may start now.

| ID | Owner | Task | Depends on | Acceptance evidence |
|---|---|---|---|---|
| ~~R00~~ | Eido | Read-only host and contention audit | None | **Done** (issue #3). Measured envelope in [decision 0002](decisions/0002-measured-host-envelope.md) |
| ~~R01~~ | Research A | Baseline and recurrence candidate source audit | None | **Done** (PR #6). Baseline: Qwen2.5-1.5B `8faed761`; see [checkpoint-shortlist.md](checkpoint-shortlist.md) |
| R02 | Eido | Minimal reproducible baseline environment and smoke | R00, R01, implementation plan | Actual model load/inference; resource log; termination; exact environment and command |
| R03 | Research B; A reviews | [Task generators, scorer, and split protocol](R03-generator-scorer-split-protocol.md) — specification in review | Design and implementation plan | Independent ground-truth validation, duplicate/shortcut audit, held-out access plan |
| R04 | Research B; A reviews | E01 representation/skills pilot and frozen protocol | R02, R03 | Factorial comparisons, costs, per-item errors, final sample-size rationale |
| R05 | Research A; B reviews | E02 recurrence **mechanism probe** recipe and pilot | R02, R03 | Parameter/compute controls, extrapolation splits, stability, measured run estimate. Practical probe closed per decision 0002 |
| R06 | Research B; A reviews | E03 adaptation protocol | R04/R05 evidence review | Episode isolation, fair support information, bounded update/reset recipe |
| R07 | Other researcher + Eido | Independent reproduction of strongest result | A completed controlled experiment | Manifest-based rerun in a rebuilt environment per coordination.md; difference analysis; same claim or documented contradiction |
| R08 | Research B + Eido; A reviews | Transfer to local assistant tasks | R07 | Useful completion improvement on held-out practical tasks; full local footprint |

## Decisions assigned before implementation

- Cassie: review written design and priority order; assign the two researcher names when available.
- ~~Eido + Research A: select current supported environment and exact model revisions from primary sources after host audit.~~ Resolved: Qwen2.5-1.5B at `8faed761d45a263340a0528343f099c05c9a4323` (R01). Environment selection remains open pending the implementation plan.
- Research B + reviewer: freeze generators, final split ownership, metrics, sample sizes, and statistical method before confirmatory execution.
- Eido: select durable artifact storage and verify persistence before expensive runs.
- Cassie: establish any paid rental/API cap if a specific experiment needs paid compute. Local design work is not blocked on this.

## Implementation-plan handoff

After design review, write one plan for the minimum apparatus and first experiment. Include exact files, dependency versions, acceptance checks, resource limits, and agent ownership. Keep E02 implementation separate from E01 shared-harness work where possible. Do not build a dashboard, scheduler service, package attestor, or generalized plugin framework as a prerequisite.

Tasks become queued/running/completed only when an owner records that state with a branch and evidence. Do not mark this proposed backlog complete because the documents exist.
