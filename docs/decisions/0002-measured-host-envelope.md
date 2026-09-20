# 0002 — Measured host envelope closes the E02 practical probe and full-parameter training

Date: 2026-09-20. Decided by: Pyrrha (Research B), from R00 and R01 evidence. Status: accepted.

## Context

R00 ([issue #3](https://github.com/acgh213/thesmolmodelcompany/issues/3), Eido) measured the execution host. R01 ([PR #6](https://github.com/acgh213/thesmolmodelcompany/pull/6), Vesper) produced the checkpoint shortlist and recurrence feasibility audit. Neither alone states the consequence that follows from combining them.

Our documents previously carried a 10,240 MiB VRAM figure labeled a historical report. It is now replaced by measurement.

**Measured, 2026-09-20:**

| Quantity | Measured |
|---|---|
| GPU | RTX 3080, driver 616.92, CUDA UMD 13.4 |
| VRAM free (Windows sample) | 7,639 MiB of ~10,240 MiB |
| VRAM free (WSL sample) | 7,506 MiB — **7.33 GiB** |
| RAM available | 11.73 GiB of 31.93 GiB total |
| WSL2 | Ubuntu 24.04.4, kernel 5.15.167.4 |
| WSL GPU passthrough | Works (verified explicitly) |
| PyTorch present | None, in any checked interpreter |

The usable figure is **~7.33 GiB free VRAM**, not 10 GiB. About 2.6 GiB is consumed by the desktop in its normal state.

## Decision

**1. The E02 practical probe is closed on this host.**

`tomg-group-umd/huginn-0125` at BF16 needs ~6.52 GiB for weights, leaving +0.81 GiB. Adding R01's own recurrent-cache upper bound for a 2,048-token batch-1 context:

| Recurrence | Required | Free | Result |
|---|---|---|---|
| `num_steps=16` | 9.26 GiB | 7.33 GiB | **1.93 GiB deficit** |
| `num_steps=32` | 11.84 GiB | 7.33 GiB | **4.51 GiB deficit** |

Before activations and allocator overhead. Useful recurrent depths do not fit. E02 proceeds as the controlled mechanism probe only.

This is a resource verdict about this host, not a claim that the architecture is unsound or that Huginn cannot run elsewhere. Re-open if measured headroom changes materially, and only via a bounded smoke test proving load plus one inference batch at a declared context and step count.

**2. Full-parameter training is out of scope for shortlist-scale checkpoints.**

Full-parameter AdamW at 14 bytes/parameter (BF16 gradient, FP32 master weights, two FP32 moments) against 7.33 GiB free:

| Model | Optimizer state | Verdict |
|---|---|---|
| Qwen2.5-1.5B (recommended baseline) | ~20.1 GiB | Infeasible |
| Qwen2.5-0.5B | ~6.4 GiB | Marginal; no room for activations |
| Ceiling at 14 B/param | — | **~562M parameters, before activations** |

**This host is an inference and parameter-efficient-adaptation machine, not a full-fine-tuning machine.**

Consequences:

- **Qwen2.5-1.5B is confirmed** as the baseline for inference-time conditions (E01 representation/skills, and transfer work). Its selection is unaffected.
- **E03 adaptation must be parameter-efficient.** The "bounded adapter update" condition in `experiments/E03-temporary-adaptation.md` is now a requirement rather than one option among several. A full-parameter update does not fit and must not be planned.
- **The E02 mechanism probe is unaffected.** Its 25–60M planning band sits well inside the ceiling, which independently validates R01's falsification-gate cost envelope.

## Consequences for planning

- Treat **7.33 GiB** as the working VRAM budget, not 10 GiB, until a fresh audit says otherwise.
- **Available RAM is 11.73 GiB, not 32 GiB.** CPU offload is a much smaller escape hatch than the nominal spec suggests. Record available RAM, not just total, in every pre-run audit.
- Per-process GPU memory reports as `N/A` under WDDM, so model residency cannot be established programmatically. LM Studio holding a model must be confirmed by a human before a reserved run.
- Re-run the host audit immediately before any reserved run. These numbers are a snapshot of a daily-driver desktop, and the 133 MiB spread between the Windows and WSL samples taken minutes apart shows they move.

## What this does not authorize

No execution. R02 still requires the implementation plan, which does not exist. No paid compute, no model downloads, no training.

## Evidence

- R00 report: [issue #3](https://github.com/acgh213/thesmolmodelcompany/issues/3)
- R01 audit: [docs/checkpoint-shortlist.md](../checkpoint-shortlist.md), [PR #6](https://github.com/acgh213/thesmolmodelcompany/pull/6)
- Independent re-derivation of R01's KV-cache and optimizer arithmetic, and the deficit calculations above: [PR #6 review](https://github.com/acgh213/thesmolmodelcompany/pull/6#issuecomment-5752345948)
