# Agent instructions

## Mission and current stage

Optimize for small-model reasoning and adaptation, then test transfer to a useful local assistant. Cassie explicitly selected this priority order on 2026-09-20.

This branch contains a proposed written research design. Read-only research, feasibility audits, and proposed protocol refinements can proceed. Product implementation and experiment execution follow review of this design and a concrete implementation plan. This is the written-design stage of the brainstorming workflow, not evidence that experiments have been implemented.

## Working rules

- Read README.md, docs/research-design.md, docs/evaluation.md, docs/compute.md, docs/coordination.md, and your role in agents/README.md.
- The three operating roles are Eido, Research A, and Research B. The latter two are role labels until Cassie assigns agent names; do not invent identities or contact other agents without the user's authorization.
- Claim one primary task. Work on a task branch with a clear experiment ID. Use a PR for changes to shared evaluation contracts.
- Separate published evidence, engineering assumptions, new hypotheses, and measured results. Cite primary sources and the exact version used.
- Use the strongest feasible cheap baseline. An ablation that removes only a prompt sentence is not sufficient evidence for an architectural claim.
- Count the complete inference system: model weights, caches, retrieval, learned libraries, verifiers, preprocessing, CPU RAM, wall time, and any external service.
- Keep development feedback separate from final evaluation. Do not inspect final answers to improve prompts, libraries, stopping rules, or checkpoints.
- Preserve unsuccessful runs and contradictions. A small clean negative result is a legitimate deliverable.
- Implement only the environment machinery necessary to obtain a reproducible run. Do not expand a dependency problem into a bespoke package-security framework.
- Do not reuse another project's sealed evaluation data or change its running jobs. Eido must coordinate ownership of the shared GPU.
- Repository preparation does not authorize paid rentals or unbounded agent/API expenditure. Follow docs/compute.md.
- Do not report a task as complete without reviewing actual artifacts and the relevant verification output.

## Definition of a completed experiment

A protocol frozen before the confirmatory run; exact artifact identities; baseline and ablation results; raw predictions and error records; total resource costs; uncertainty and limitations; an independent reproduction or an explicit unreplicated label; and a decision to continue, revise, transfer, or stop.

No benchmark score alone establishes broad general intelligence, general-purpose reasoning, or a theorem about generalization.
