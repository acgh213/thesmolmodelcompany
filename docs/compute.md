# Compute and environment policy

## Targets

Primary execution target: Eido's Windows desktop, using WSL2 where the selected software supports it.

**Measured 2026-09-20 (R00, issue #3)** — these replace the previous historical figures. Re-audit before any reserved run; they are a snapshot of a daily-driver desktop and they move.

| Quantity | Measured |
|---|---|
| GPU | RTX 3080, driver 616.92, CUDA UMD 13.4 |
| Free VRAM | **7.33 GiB** (7,506 MiB, WSL sample); ~2.6 GiB held by the normal desktop |
| Available RAM | **11.73 GiB** of 31.93 GiB total |
| CPU | Ryzen 7 3700X, 8 physical / 16 logical |
| WSL2 | Ubuntu 24.04.4, kernel 5.15.167.4; GPU passthrough verified working |
| PyTorch | Not present in any checked interpreter |

Plan against **7.33 GiB, not 10 GiB**. Per [decision 0002](decisions/0002-measured-host-envelope.md) this host supports inference and parameter-efficient adaptation; full-parameter training above roughly 562M parameters does not fit. Native Windows support is a measured deployment goal, not an assumption about Linux research kernels.

Per-process GPU memory reports as `N/A` under WDDM, so model residency cannot be established programmatically. A human must confirm LM Studio is not holding a model before a reserved run.

Cloud is available as an option, with an explicit total spending cap and termination mechanism. No paid resources have been provisioned and no rental budget has been specified.

## Environment acceptance

Record OS/WSL distribution, driver, GPU identity, available/peak VRAM, Python/runtime, exact dependency versions, model/tokenizer revisions and hashes, license, and launch command. Choose supported combinations from upstream documentation and validate on the actual host. A lockfile generated elsewhere is not evidence that the Windows/WSL installation works.

First prove model loading, one inference batch, resource recording, and clean termination. For training, also prove one optimizer step, finite loss/gradients, checkpoint save/reload, and resumed-step equivalence within a stated numerical tolerance. Do not claim an inference fit demonstrates training fit.

## Proposed initial execution limits

These limits take effect only when adopted in the implementation plan. They are maximums, not required durations.

| Run class | Wall-time cap | Other limit |
|---|---|---|
| Host audit | 15 minutes | Read-only; no model/package installation |
| Local smoke | 20 minutes | One candidate, one GPU process; stop after the relevant check succeeds |
| Local pilot | 2 hours | Exact token/step and output limits stated before launch |
| Confirmatory run | Per-protocol after pilot | Projected cost from measured throughput; checkpoint/restart design |
| Rental | No spending authorized | Requires provider/SKU, rate, total cap, runtime cap, storage cost, teardown verification |

Respect interactive desktop use and other project jobs. Record a GPU reservation in the queue. Do not stop someone else's process. If free memory is insufficient, reduce the proposed workload or reschedule; do not silently change batch size or precision inside a comparison.

Stop on the first OOM, non-finite training state, invalid scorer output, exhausted budget, or failed artifact save. Diagnose before restarting; retain the failure. A checkpointed restart receives a linked run ID.

## Measurements

Report cold load time separately from warm inference; end-to-end latency (p50/p95), throughput with batch/context/output sizes, peak VRAM and CPU RAM, disk footprint, and total GPU time. Include loading/offloading, tokenization, representation building, retrieval, verification, and adaptation in the relevant system metric.

Energy is optional until a meter or appropriate telemetry is available. State sampling method and whether a value describes the GPU or the whole desktop. Do not infer whole-system energy from GPU power alone.

Count external teacher/API generation as research cost and any remote inference as deployment dependency. The initial target is a fully local candidate at inference time.

## Cloud request format

Experiment ID; why local execution is inadequate; verified provider offer and timestamp; all-in estimated cost; hard spending/runtime cap; model/data transfer requirements; checkpoint location; automatic shutdown plan; and evidence that the completed instance and billable storage were released. Selecting a provider in a document does not authorize purchasing it.
