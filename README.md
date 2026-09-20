# The Smol Model Company

Research small models that reason, compose skills, and adapt to unfamiliar tasks under practical local-compute limits. Transfer successful mechanisms into a useful local assistant.

**Primary goal:** demonstrate stronger reasoning and adaptation, with evidence about where the improvement comes from. **Transfer goal:** preserve those gains in an everyday local system.

Status: research design prepared for Cassie's review. No implementation, model download, training, benchmark result, or rental is included in this change. The research direction is agreed; the written design and numerical experiment budgets are proposals.

## Start here

1. Read [AGENTS.md](AGENTS.md).
2. Read the [research design](docs/research-design.md) and [evaluation protocol](docs/evaluation.md).
3. Select your [agent role](agents/README.md) and claim a task in the [initial backlog](docs/backlog.md).
4. Follow the [compute policy](docs/compute.md) and [coordination protocol](docs/coordination.md).
5. Use the [experiment template](templates/experiment.md) before running a candidate and the [result template](templates/result.md) afterward.

## Initial research portfolio

| Track | Question | Starting experiment |
|---|---|---|
| Representation and reusable skills | Can a small model compose verified operations on unfamiliar problems? | [E01](experiments/E01-representation-and-skills.md) |
| Recurrent computation | Can reusing parameters improve reasoning beyond simply generating more candidates? | [E02](experiments/E02-recurrent-computation.md) |
| Temporary adaptation | Can a bounded update learn a new rule more efficiently than prompting or search? | [E03](experiments/E03-temporary-adaptation.md) |

Maintain at most one main GPU experiment and one CPU/evaluation task concurrently. E03 starts after the first two tracks have produced baseline evidence and a capacity review.

The [research map](docs/research-map.md) records additional directions and primary sources. The [results ledger](docs/results.md) contains no experimental findings and is generated from run reports under [results/](results/README.md). Governance and protocol changes are recorded in [decision records](docs/decisions/README.md).

Existing small-model checkpoints are practical starting points. Tiny controlled training runs test mechanisms. Cactus/Needle is an optional comparison, and the PSTV is an optional later target; neither defines this project's scope.

## Reproducibility and licensing

Record exact code, model, tokenizer, dataset, environment, and hardware identities with every run. Store large weights and datasets outside Git; commit manifests and evidence references. The repository's MIT license does not relicense third-party weights, datasets, or dependencies.
