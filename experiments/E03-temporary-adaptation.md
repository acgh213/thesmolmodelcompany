# E03 — Temporary adaptation to unfamiliar rules

Status: queued proposal; owner Research B; reviewer Research A; compute Eido. Begins after initial baseline evidence and capacity review.

## Hypothesis

A bounded task-specific update improves inference of new rules more efficiently than putting the same examples in context or searching over candidate rules.

## Episodes

Each episode supplies a small labeled support set and separate unlabeled queries from a held-out rule family. Adaptation may use support labels and transformations justified by the task. It cannot access query labels. Generate splits by underlying rule, not merely input strings.

## Conditions

Same base checkpoint with support examples in context; retrieval of training examples; small bounded adapter update; bounded rule/program search. Match permitted evidence and report accuracy-versus-total-time curves. Include an update-disabled control using the identical prompt and support data.

The update condition **must be parameter-efficient** (adapters/LoRA or an equivalently bounded trainable subset). Per [decision 0002](../docs/decisions/0002-measured-host-envelope.md), the measured host has ~7.33 GiB free VRAM, and full-parameter AdamW on the selected 1.5B baseline needs roughly 20.1 GiB. A full-parameter update does not fit and must not be planned for this host.

Reset model/adapters, optimizer, retrieval writes, caches, and persistent state between independent episodes. Capture hashes/checks sufficient to establish reset. Stop an episode on divergence or budget exhaustion and count the failure. Continual learning is a different protocol.

## Measurements

Task completion, adaptation gain over prompting, examples needed, update time, inference time, peak training memory, and seed sensitivity. Check a small unrelated capability set for collateral degradation when relevant. Specify whether adaptation costs amortize over one or multiple queries.

## Falsification / stop

Stop or revise if updates underperform more inference search at the same cost, benefit only familiar rule families, or require a latency/memory budget inconsistent with the local target. Improvement from greater access to support information is not adaptation evidence.

## Recipe decisions before execution

R06 chooses the base checkpoint, trainable subset, update loss, optimizer, maximum steps, reset verification, support/query counts, and final statistical protocol. The large benchmark gains in cited prior work are motivation, not expected outcomes for this project.
