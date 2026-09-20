# Experiment result template

Copy to a named run report. Replace instructions with measured facts; unknown or unavailable measurements must remain explicitly labeled.

1. Identity and claim level: experiment/run, frozen protocol, owner, timestamp, commit, manifest.
2. Outcome: primary task completion counts/rates, paired effect and uncertainty, target generalization axis.
3. Baselines and ablations: full comparison, matching controls, confounds, stronger feasible baseline.
4. Failures: invalid outputs, timeouts, OOMs, divergence, verifier errors, resets, excluded items with reasons.
5. Resources: load/warm latency, p50/p95, throughput conditions, VRAM/RAM, disk, training time, external API/rental cost.
6. Evidence: raw predictions/logs, config/data/model hashes, durable artifact locations, exact reproduction command.
7. Interpretation: what the evidence supports, what it contradicts, and what it does not establish.
8. Reproduction: independent agent, host, rerun ID, agreement/disagreement, or explicitly unreplicated.
9. Decision: continue, revise, stop, or transfer; smallest justified next task and owner.
