# Three-agent handoff

Roles are assigned in [decision 0001](../docs/decisions/0001-repository-governance.md): **Eido** owns compute, **Vesper** is Research A, **Pyrrha** is Research B. The responsibilities below are unchanged by that assignment; the role names remain the vocabulary used throughout these documents.

## Eido — compute and reproducibility

Read AGENTS.md and docs/compute.md. Own R00 and R02 in the backlog. Start with a read-only host report: GPU identity/VRAM, WSL/native OS, driver, runtime availability, RAM/storage, and current workloads. Report any conflict with other projects. Propose the smallest tested environment for the selected checkpoint; do not install or train as part of the read-only audit.

After design and implementation-plan review, run a bounded smoke test, retain the exact command and environment, and report measured fit and throughput. Own the serialized GPU queue, termination controls, raw logs, checkpoint identities, and local export verification. Reproduce another agent's candidate from its manifest before describing it as deployable.

First handoff: host report, proposed environment, selected baseline feasibility matrix, measured smoke result when execution is authorized, and blockers with the smallest next action.

## Research A — mechanisms and generalization

Read docs/research-map.md and experiments/E02-recurrent-computation.md. Own R01 and R05. Build a shortlist of exact checkpoints and implementations from primary sources. Propose the recurrent study with a parameter count, token budget, training-compute comparison, and extrapolation split. Distinguish what can be reused from what must be trained.

Review Research B's task design and system-level attribution. After implementation planning, implement the recurrence candidate and its necessary controls. Keep synthetic evidence separate from practical language-model evidence.

First handoff: source-backed shortlist, a concrete E02 recipe proposal, estimates with assumptions, and the cheapest experiment that could falsify the proposed advantage.

## Research B — evaluation and composition/adaptation

Read docs/evaluation.md and E01/E03. Own R03 and R04. Design task generators, independently validate ground truth, define structure-based splits, and propose baseline scorers before candidate tuning. Own the first representation/skill experiment and later temporary-adaptation protocol.

Have Research A review the scorer and splits when you propose the candidate. Do not give another candidate a weaker prompt or budget to manufacture a win. Preserve per-item failures and practical language-transfer checks.

First handoff: evaluation specification, representative development examples, split strategy, baseline matrix, and an E01 recipe proposal with a review by Research A.

## Handoff message format

Task/experiment ID; branch and commit; what changed; exact evidence path; what was verified; resource usage; remaining uncertainty; next owner/action. No success claim based solely on an agent's narrative.

## Authority

Cassie sets goals and spending authorization. Agents can resolve routine technical choices within an approved plan and budget. A change to the primary research question, final evaluation split, spending cap, or deployment target must be recorded as a decision. Final-score-driven changes begin a new experiment and disclose the prior feedback.
