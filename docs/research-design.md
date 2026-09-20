# Research design: small models that reason and adapt

Date: 2026-09-20. Status: proposed written design for review.

## 1. Agreed intent

Cassie wants a three-agent research project studying how much capability can be obtained from smaller local models by optimizing, modifying, adapting, and inventing mechanisms beyond conventional fine-tuning. Eido supplies access to a Windows RTX 3080 desktop or an explicitly budgeted rented instance. Two other agents carry research and evaluation work.

The primary outcome is unusually strong reasoning and adaptation in a small model, with a path to a broadly useful local assistant. The project is broader than the existing Cactus/Needle work. Training is allowed as a research instrument, not assumed to be the answer.

## 2. Scientific question

Under bounded training and inference resources, which allocations of computation, representation, memory, and reusable skills improve transfer to unfamiliar tasks?

Report two distinct outcomes:

1. **Model capability:** improvement attributable to the learned model or its internal computation.
2. **Local-system capability:** improvement of the complete model-plus-memory/search/tools system, including its costs.

Do not relabel a system gain as an intrinsic model gain. Both are valuable.

## 3. Approach and alternatives

Selected proposal: pair practical experiments on existing checkpoints with one controlled architecture track. The practical track starts with structured representations and reusable executable skills (E01). The architecture track starts with recurrent computation (E02). Temporary adaptation (E03) is the first follow-on.

An exclusively application-led approach could deliver a useful assistant quickly, but makes architectural attribution harder. An exclusively from-scratch architecture approach offers more control, but spends scarce compute before establishing practical relevance. The paired approach permits early useful results and small causal experiments.

Initial model-size search bands are approximately 0.3–3B parameters for existing checkpoints, subject to measured fit and license/runtime checks, and 10–100M parameters for controlled mechanism probes. These are planning ranges, not verified feasibility claims. Include the strongest larger baseline that actually fits the same deployment budget when practical.

## 4. Research tracks

### A. Representations and reusable operations

Investigate whether canonical task representations and a library of verified operations improve unseen composition. Compare raw language, a deterministic or model-produced representation, primitive operations, and reusable compound operations. Include a non-neural search baseline and count the representation-building cost.

The first study uses authored primitive operations. A later, separate study may discover compound operations from training solutions. A hand-built library does not establish learned abstraction discovery.

### B. Recurrent computation

Compare a small model that reuses blocks with ordinary depth and additional answer sampling. Separate parameter-matched, training-compute-matched, and inference-budget-matched comparisons. Study length/depth extrapolation and whether an adaptive iteration budget beats a fixed budget.

Tiny synthetic results establish mechanism evidence only. An existing recurrent checkpoint can test practical deployment if supported; reproducing a published large pretraining run is out of scope for the initial budget.

### C. Temporary adaptation

Compare examples in context, retrieval, bounded parameter updates, and rule search. Reset all adaptive state between independent episodes. Later study continual adaptation separately, with interference and forgetting metrics.

### D. Reserve portfolio

Learned memory, state-space/hybrid models, native low-bit inference, adaptive verification, and compression of successful search into reusable skills remain in the literature queue. Promote one only when a specific experiment and hardware path are ready. See research-map.md.

## 5. Evaluation architecture

Use generated task families with independently checked ground truth, public tasks for external comparison, and later human-authored transfer tasks. Initial families: compositional transformations, rule induction, and stateful planning. Extend with small code/data tasks and grounded local-document tasks at transfer time.

Split by latent rule, program structure, and task family rather than by random text row alone. Reserve separate tests for new compositions, longer solutions, presentation changes, and new domains. Use same-instance comparisons wherever possible.

Every run produces a manifest, per-item predictions, failure records, metrics, resource measurements, and a short interpretation. See evaluation.md for the proposed contract and promotion criteria.

## 6. System boundaries

The future harness has five small components: task generator/loader; candidate adapter; independent scorer; resource recorder; report aggregator. A candidate receives only the task and permitted support examples, never the hidden answer. Scoring and aggregation do not modify the candidate. All adaptive state has an explicit episode or session lifetime.

Candidate contract: accept a task ID, payload, permitted support data, resource budget, and seed; return an answer plus trace, artifact IDs, resource use, and termination status. Proposed implementations should keep this interface small; a plugin framework is not required initially.

Timeouts, OOMs, invalid outputs, verifier errors, adaptation divergence, and missing artifacts are explicit outcomes. They cannot disappear from denominators. Restarted runs receive new IDs linked to the failed run.

## 7. Roles and coordination

Eido owns compute execution, environment fit, resource measurements, and export/deployment checks. Research A owns mechanism proposals and the architecture track. Research B owns evaluation and the representation/adaptation track. Both researchers write experiment code after design review and review one another's claims. Eido reproduces runnable candidates on target hardware.

The proposer must not unilaterally change their experiment's scorer or final split. Research B owns scorer releases; if B is the proposer, A reviews the scorer and evaluation protocol. This is separation of duties, not a claim of cryptographic blindness between agents sharing a repository.

## 8. Phases and exit criteria

| Phase | Work | Exit evidence |
|---|---|---|
| 0: apparatus | Verify host; select exact checkpoints; validate generators/scorers; freeze protocol | A reproducible baseline and resource report, including failures |
| 1: mechanisms | E01 and E02 pilots, then confirmatory runs for promising variants | Controlled comparison with uncertainty, costs, and independent review |
| 2: adaptation | E03 or a better-supported reserve proposal | Improvement on a specified unseen-task axis with a realistic latency budget |
| 3: transfer | Use the strongest mechanism in code/data, grounded-document, and multi-step local tasks | Measured retained benefit over the same base model without the mechanism |
| 4: deployment | Package the useful variant and document limits | Offline-capable local reproduction on Eido's desktop within the measured envelope |

No fixed calendar promises are made before throughput is measured. A failed mechanism can close cleanly; the lab need not force every phase into a success narrative.

## 9. Transfer to a local assistant

Maintain language competence and instruction-following checks alongside narrow reasoning tasks. After a mechanism survives independent evaluation, test it in three practical task groups: executable code/data manipulation, answers grounded in a local document set, and multi-step plans with explicit constraints.

Measure task completion, invalid actions, unnecessary steps, factual grounding, time to useful output, peak memory, and offline dependencies. Human usability feedback complements exact scoring where open-ended answers lack a unique ground truth. General chat polish begins after the transfer result; a dashboard is not a prerequisite for research.

## 10. Resource assumptions and unresolved decisions

Prior context reports a 3080 with 10,240 MiB VRAM, Ryzen 3700X, about 32 GiB RAM, and functional WSL2. These are historical reports, not a current host audit. Eido must remeasure free VRAM, driver/runtime compatibility, storage, and contention before selecting a recipe.

Exact checkpoints, package locks, final experiment sample sizes, researcher names, and a rental spending cap are deliberately unresolved. Each has an owner and decision task in backlog.md. No implied default rental budget exists.

## 11. Acceptance of this design

Review the primary objective, the paired E01/E02 start, the three roles, and the evaluation/resource boundaries. After the written design is approved, write the implementation plan from the backlog, including exact files, dependencies, verification, and execution ownership. This design does not assert that the harness or experiments already exist.
