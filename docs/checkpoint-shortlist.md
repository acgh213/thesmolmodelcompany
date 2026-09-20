# R01 — checkpoint shortlist and recurrence feasibility

**Task:** R01 (issue #4)  
**Status:** source audit / design proposal; no model weights downloaded and no runtime or memory measurement performed  
**Sources consulted:** 2026-09-20 UTC  
**Claim levels:** published evidence is labelled **Published**; local engineering judgments are **Assumption**; proposed tests are **Hypothesis / proposal**.

## Executive decision

Recommend **`Qwen/Qwen2.5-1.5B` base** at revision `8faed761d45a263340a0528343f099c05c9a4323` as the ordinary baseline. It is inside the planning band, Apache-2.0, explicitly a pretrained (not instruction-tuned) checkpoint, uses a mainstream Transformers implementation, and is large enough to be a useful baseline without making the first host-fit test a 2.7B edge case. This is a selection for the first feasibility recipe, not a claim that it is the strongest model in the band. [4][5][6]

The shortlist is deliberately heterogeneous enough to expose confounds, not to support an architecture leaderboard. Differences in pretraining data and duration, tokenizer, context length, precision, post-training, and kernel/runtime support mean that an existing-checkpoint comparison cannot isolate architecture. The controlled E02 mechanism probe is the causal architecture test.

## 1. Exact checkpoint shortlist

All revisions below are immutable Hugging Face commit SHAs observed from the model API on the consultation date. The `README.md`, `config.json`, and `tokenizer_config.json` links are pinned to the same SHA. Memory figures are **estimates, not measurements**.

### Assumptions used for estimates

- Weight estimates use decimal parameter counts × bytes per parameter: 2 bytes for BF16/FP16, 4 for FP32, and 1 for an idealized INT8 packed weight. They exclude framework overhead, allocator fragmentation, temporary buffers, and quantization metadata.
- KV estimates are batch 1, 2,048 tokens, BF16 K/V, and the standard `2 × layers × KV heads × head dimension × sequence length × bytes` formula. They are a lower-level estimate, not a host measurement. They are not directly comparable across runtimes that page, quantize, or share caches.
- The optimizer figure is a rough **lower bound** for full-parameter AdamW-style training at 14 bytes/parameter (BF16 gradient plus FP32 master weights and two FP32 moments), excluding activations, dataloader, and framework state. It is not a recommendation to train any listed checkpoint.
- “Runtime support” means what the pinned primary model card documents. It does not mean that R00 has loaded the checkpoint on Eido’s host.

| Candidate (exact revision) | Architecture / status | Tokenizer | License / source | Documented runtime and precision | Estimated memory (not measured) |
|---|---|---|---|---|---|
| [`Qwen/Qwen2.5-0.5B`](https://huggingface.co/Qwen/Qwen2.5-0.5B/tree/060db6499f32faf8b98477b0a26969ef7d8b9987)  `060db6499f32faf8b98477b0a26969ef7d8b9987` | Qwen2 causal LM; **0.49B** parameters, 24 layers; **base / pretraining**, not instruction-tuned. Tied embeddings. [1][2] | `Qwen2Tokenizer`, vocab 151,936; pinned tokenizer config and tokenizer files in the same repo revision. [3] | Apache-2.0; official Qwen organization checkpoint. [1] | Transformers; model card requires Transformers ≥4.37.0 for Qwen2 support. Config advertises BF16; FP16/INT8 are engineering options requiring validation. [1][2] | Weights: **~0.98 GB BF16**, ~0.49 GB idealized INT8. KV: **~24 MiB** at 2k tokens. AdamW lower-bound: **~6.4 GiB**. |
| **`Qwen/Qwen2.5-1.5B`**  `8faed761d45a263340a0528343f099c05c9a4323` | Qwen2 causal LM; **1.54B** parameters, 28 layers; **base / pretraining**, not instruction-tuned. Tied embeddings. [4][5] | `Qwen2Tokenizer`, vocab 151,936; same tokenizer family as the 0.5B candidate, pinned at this revision. [6] | Apache-2.0; official Qwen organization checkpoint. [4] | Transformers; model card requires Transformers ≥4.37.0. Config advertises BF16; FP16/INT8 require validation. [4][5] | Weights: **~3.08 GB BF16**, ~1.54 GB idealized INT8. KV: **~56 MiB** at 2k tokens. AdamW lower-bound: **~20.1 GiB**. |
| [`HuggingFaceTB/SmolLM2-1.7B`](https://huggingface.co/HuggingFaceTB/SmolLM2-1.7B/tree/effd688a12921b4cc83e3312b6feb579f70f9c71)  `effd688a12921b4cc83e3312b6feb579f70f9c71` | Llama-style decoder Transformer; **1.7B**; **base / pretrained** checkpoint. The paired instruct model is SFT+DPO, so do not substitute it. Tied embeddings, 24 layers. [7][8] | `GPT2Tokenizer`, vocab 49,152; max position 8,192. [9] | Apache-2.0; official Hugging Face TB checkpoint. [7] | Transformers example; card documents full precision, BF16, and FP16 loading. Training used BF16 and nanotron, but that is not local runtime evidence. [7] | Weights: **~3.4 GB BF16**, ~1.7 GB idealized INT8. KV: **~384 MiB** at 2k tokens. AdamW lower-bound: **~22.2 GiB**. |
| [`allenai/OLMo-1B-0724-hf`](https://huggingface.co/allenai/OLMo-1B-0724-hf/tree/d7cbab742d80589e714b1a2d7f838dcd21cbe143)  `d7cbab742d80589e714b1a2d7f838dcd21cbe143` | OLMo decoder Transformer; **about 1B** (configuration implies roughly 1.2B); 16 layers; **base / pretrained**, not instruction-tuned. Untied embeddings. [10][11] | `GPTNeoXTokenizer`, vocab 50,304; max position 4,096 in the model config. [12] | Apache-2.0 for code and model; official Allen Institute for AI checkpoint. [10] | Model card says direct use with Transformers ≥4.40 and documents FP32 loading plus optional `bitsandbytes` 8-bit quantization. The config’s default dtype is FP32; lower precision is an option to validate, not a measured result. [10][11] | At the configuration-implied ~1.2B: weights **~4.8 GB FP32** or ~2.4 GB FP16; idealized INT8 ~1.2 GB. KV: **~256 MiB** at 2k tokens. AdamW lower-bound: **~15.6 GiB**. |
| [`microsoft/phi-2`](https://huggingface.co/microsoft/phi-2/tree/810d367871c1d460086d9f82db8696f2e0a0fcd0)  `810d367871c1d460086d9f82db8696f2e0a0fcd0` | Phi decoder Transformer; **2.7B**; **base / pretrained**, not RLHF or instruction-finetuned. The card explicitly warns that it is unreliable for intricate instruction following. [13][14] | `CodeGenTokenizer`, vocab 51,200; context 2,048. [15] | MIT; official Microsoft checkpoint. Training data includes synthetic NLP text and filtered web data, a major data/source confound. [13] | Transformers ≥4.37.0; card documents `torch_dtype="auto"` and warns of FP16 attention overflow. `trust_remote_code` is needed with older Transformers; do not assume that requirement is absent from every environment. [13] | Weights: **~5.4 GB FP16**, ~2.7 GB idealized INT8. KV: **~640 MiB** at 2k tokens. AdamW lower-bound: **~35.2 GiB**. |

### Runtime and kernel caveats

The cards establish framework-level support, not a portable kernel contract. Qwen's documented path is Transformers and does not promise a particular fused-attention kernel; SmolLM2 documents Transformers inference while its pretraining used nanotron; OLMo documents Transformers plus optional bitsandbytes quantization; Phi-2 documents PyTorch/DeepSpeed/FlashAttention for its training stack and an FP16 attention-overflow caveat; Huginn requires its custom model/cache code and the pinned repository's integration. No `llama.cpp`, vLLM, FlashAttention, Windows-native, or WSL2 path is counted as supported unless R00 verifies that exact combination. [1][7][10][13][16][20]

### Baseline choice and non-choices

Use **Qwen2.5-1.5B base** for the first ordinary local baseline. Qwen 0.5B is a useful low-memory fallback; SmolLM2-1.7B is a credible alternative with a different tokenizer and data mixture; OLMo is valuable for openness and training provenance; Phi-2 is a capacity-near-upper-band option with a particularly visible data and FP16 caveat. None should be silently mixed into a claim about recurrence.

For E01 or assistant-facing prompt tests, an instruction-tuned checkpoint may be useful, but it is a different baseline condition. Do not compare an instruct model against the selected base model and attribute the difference to architecture. If an instruct baseline is later added, it needs its own exact revision and separately reported post-training status.

## 2. E02 recurrence feasibility

### 2.1 Mechanism probe — train from scratch, 10–100M planning band

**Published foundation.** Geiping et al. describe a decoder architecture with a prelude, a shared recurrent block, and a coda; training samples a variable recurrence count and uses truncated backpropagation, while test-time recurrence can be increased. Their demonstrated model is 3.5B parameters trained on 800B tokens, not a local recipe. [19] The official implementation exposes the model shape and training/inference code, but it is an AMD Frontier-scale reference rather than evidence of Eido-host fit. [20]

**Proposal / hypothesis.** Start with a throughput pilot, then choose one configuration in the 10–100M band. A concrete first candidate to cost out is:

- byte-level task serialization with a fixed small vocabulary (roughly 256 byte values plus reserved delimiters), so tokenizer differences do not enter the mechanism comparison;
- an 8-block decoder layout: 2 unshared prelude blocks, 4 recurrent core blocks reused for `r` iterations, and 2 unshared coda blocks;
- an ordinary 8-block decoder control with the same hidden size, vocabulary, positional encoding, optimizer, initialization family, and **unshared** block count;
- a pilot hidden size chosen to land near **25–60M total parameters**, then fixed before comparing variants. The exact size is a proposal pending measured throughput, not a committed result;
- recurrence counts sampled during training from a declared bounded distribution, with `r=1, 4, 8` interpolation and `r=16, 32` extrapolation candidates only if the pilot remains stable;
- at least three seeds for a confirmatory training effect; fewer seeds are exploratory and must be labelled that way.

**Parameter-matched comparison.** The recurrent model stores one copy of the 4-block core; the ordinary control stores one copy of each of its 8 blocks. Both have the same stored parameter count by construction. Report stored parameters and effective unrolled depth separately. Compare recurrence at fixed `r` to the ordinary control at the same parameter budget; extra recurrent FLOPs are not free and must be reported.

**Training-compute-matched comparison.** Use the measured forward/backward work and wall time from the pilot to select ordinary-control updates or sequence lengths that match total training compute. Do not call equal optimizer steps equal compute when recurrence counts differ. Also report the resulting token exposure, because matching compute can change data exposure.

**Inference-budget comparison.** Plot correct completion by measured wall-time and peak memory for recurrent steps, ordinary direct decoding, and additional sampled candidates. Candidate selection/verifier cost is included. An oracle-selected sample is diagnostic only, not a deployed result.

**Splits.** Train on bounded solution depths; use separate interpolation, longer-depth extrapolation, and held-out task-family splits. Do not use longer input context as a proxy for longer required reasoning. The task generator, scorer, and final split remain Research B’s reviewed evaluation surface.

**What is reusable vs must be trained.** The experiment may reuse a standard Transformer implementation, optimizer implementation, and deterministic task generator. The recurrent block, ordinary control, tokenizer/serialization, initialization, and all weights must be trained or initialized under the same protocol. No existing language-model checkpoint should be used in the mechanism probe: doing so would import tokenizer, data, and post-training confounds.

### 2.2 Practical probe — existing recurrent-depth checkpoint

The only concrete existing recurrent-depth checkpoint found in the bounded search of the paper, its official code repository, and the linked model release is **`tomg-group-umd/huginn-0125`**, pinned at `bb6621b65e90b6a4b9b29ef88dc83866d450470c`. It is Apache-2.0 and has an official Transformers-compatible implementation with `trust_remote_code=True`, configurable `num_steps`, custom `HuginnDynamicCache`, and an official vLLM integration in the referenced repository. [16][17][18][20]

**Published facts.** Huginn has 3.5B parameters and was trained for 800B tokens; the model card says the recurrent component is about 1.5B parameters, with about 1.5B in non-recurrent layers plus 0.5B embedding parameters. It recommends BF16 inference and says it was trained on AMD MI250X systems. [16] The pinned config reports an 8-layer layout with 2 prelude, 4 recurrent, and 2 coda layers, hidden width 5,280, 55 attention/KV heads, head dimension 96, mean recurrence 32, and Transformers 4.44.2 metadata. [17]

**Engineering estimate, not a measurement.** The stored BF16 weights are approximately `3.5B × 2` = **7.0 GB** before framework overhead. If a runtime retains K/V entries for every recurrent iteration, the config implies an upper-bound estimate of roughly **0.32 GiB at one step, 0.81 GiB at four, 2.74 GiB at 16, and 5.32 GiB at 32 steps** for a 2,048-token batch-1 BF16 cache. The model card documents cache-sharing modes that can reduce this, but their actual memory behavior on Eido’s runtime is unknown. The model card’s “materialized parameters” guideline is a compute/unrolling heuristic, not a VRAM measurement. [16][17]

**Decision.** Do **not** schedule Huginn as a practical E02 candidate yet. Historical project context mentions a 10,240 MiB RTX 3080, but R00 must remeasure free VRAM, driver, WSL/native runtime, and contention; that historical number is not current evidence. Given ~7 GB estimated BF16 weights, custom remote code, recurrent-cache growth, and allocator/activation overhead, a useful `num_steps=16–32` run is **not cleared within the present budget**. This is a clean negative feasibility gate, not a claim that Huginn cannot run on every 10 GB setup. Re-open only if R00 measures enough headroom and Eido’s bounded smoke test demonstrates load plus one inference batch at a declared context and step count. No other existing recurrent-depth checkpoint was established as a lower-risk practical candidate within this audit boundary.

## 3. Cheapest experiment that could falsify the recurrence advantage

The highest-value cheap test is a **pre-registered, parameter-matched synthetic depth extrapolation gate**, not a language-model benchmark:

1. Train an ordinary 8-block decoder and the 2+4-recurrent+2 model above, each targeting roughly **25M parameters**, from scratch for a fixed **50M training tokens per model per seed** (300M tokens across three paired seeds) on the same byte-level serialization, task generator revision, optimizer, initialization, and sequence length. The 50M-token cap is a proposed cost envelope, not a measured runtime.
2. Use three independently seeded pairs for the confirmatory gate. A one-seed run may be used only as an implementation smoke test and cannot establish a negative or positive training effect.
3. Freeze the protocol before seeing final answers: training solution depths 1–8; development only for recurrence limit/stopping choices; final splits for interpolation (1–8), extrapolation (16 and 32 if stable), and one held-out task family. Use at least 1,000 paired final instances per declared depth/family cell only if the pilot shows that the generator is learnable; otherwise record the pilot as a feasibility failure rather than quietly shrinking the claim.
4. Compare at equal stored parameter count and separately at equal measured training compute. At inference, report recurrent `r=1,4,8,16,32` against the ordinary model and against extra sampled candidates under matched wall-time envelopes. Record completion, invalid outputs, timeouts, peak VRAM/RAM, and elapsed time.
5. Predeclare the falsification rule: recurrence fails to demonstrate the proposed advantage if its paired 95% interval is below the project’s +5 percentage-point minimum useful effect on the held-out longer-depth axis at comparable end-to-end cost, **and** it does not achieve the alternative resource win of at least 20% lower latency or peak memory without more than a 2-point quality loss. If the interval is too wide to make that determination, call the result inconclusive rather than a win.

This is cheap because it avoids model downloads, 3.5B pretraining, natural-language data, and a large benchmark harness while directly testing the mechanism’s promised axis: reuse of computation for unfamiliar solution depths. It can fail cleanly in three ways—no extrapolation gain, no gain after compute matching, or unstable states at higher recurrence. The exact wall-time/GPU-hour cost must come from Eido’s R00 throughput audit; no published speed number is imported as a local estimate.

## 4. Confounds and claim boundary

- **Pretraining data and exposure:** the shortlist models were trained on different corpora, filtering, token counts, and synthetic data. Huginn’s 800B-token mixture and the ordinary baselines are not matched. [7][10][13][16]
- **Tokenizer and vocabulary:** Qwen, SmolLM2, OLMo, Phi-2, and Huginn use different tokenizers and vocabulary sizes. A practical result cannot be attributed to recurrence without controlling or explicitly limiting that claim. [3][6][9][12][15][18]
- **Post-training status:** the selected candidates are base models; SmolLM2 also publishes an instruct model trained with SFT and DPO, and Huginn was not post-trained despite including instruction data during pretraining. These are distinct conditions. [7][16]
- **Precision and kernels:** BF16/FP16/FP32 choices, attention overflow behavior, quantization, FlashAttention availability, custom cache code, and WSL/native driver support can change both memory and speed. The cards document options and caveats, not Eido-host measurements. [1][7][10][13][16]
- **Context and cache policy:** context lengths and KV-head counts differ; recurrent cache retention/sharing is a mechanism-specific memory confound. All memory figures here are estimates.
- **Search boundary:** the practical recurrence search covered Geiping et al. v2, the official `seal-rg/recurrent-pretraining` repository at commit `1ea7220ec7eb42d13e89db0663df254d0bcdc28e`, and its linked Huginn release. It was not an exhaustive survey of every looped, universal-transformer, recurrent-state, or unpublished checkpoint. No novelty claim follows.

## 5. Handoff

- **Task / experiment ID:** R01.
- **Branch:** `docs/r01-checkpoint-recurrence-audit`.
- **What changed:** this source-backed shortlist, baseline recommendation, E02 mechanism/practical feasibility proposal, and pre-registered cheap falsification gate.
- **Exact evidence path:** `docs/checkpoint-shortlist.md`; pinned source URLs in the Sources section; metadata-only inspection commands were used, with no model downloads or execution.
- **What was verified:** repository instructions and issue scope read; pinned model-card/config/tokenizer metadata retrieved; official Huginn paper/model/code sources consulted; estimates recomputed from declared formulas. `python3 scripts/check_docs.py` is the required repository check before PR.
- **Resource usage:** documentation-only; no GPU, no model download, no paid compute, no measured VRAM/RAM, and no billed cost.
- **Remaining uncertainty:** R00 has not yet measured Eido’s current host; the shortlist’s lower-precision loading and Huginn cache behavior remain untested; the exact 10–100M mechanism-probe size and final sample counts await throughput and generator pilots.
- **Next owner / action:** Eido should use R00 to measure host/runtime fit for Qwen2.5-1.5B and, only if headroom exists, a bounded Huginn smoke test. Pyrrha should review the E02 split, paired metrics, and falsification rule before R05 freezes the recipe.

## Sources

[1] https://huggingface.co/Qwen/Qwen2.5-0.5B/resolve/060db6499f32faf8b98477b0a26969ef7d8b9987/README.md
[2] https://huggingface.co/Qwen/Qwen2.5-0.5B/resolve/060db6499f32faf8b98477b0a26969ef7d8b9987/config.json
[3] https://huggingface.co/Qwen/Qwen2.5-0.5B/resolve/060db6499f32faf8b98477b0a26969ef7d8b9987/tokenizer_config.json
[4] https://huggingface.co/Qwen/Qwen2.5-1.5B/resolve/8faed761d45a263340a0528343f099c05c9a4323/README.md
[5] https://huggingface.co/Qwen/Qwen2.5-1.5B/resolve/8faed761d45a263340a0528343f099c05c9a4323/config.json
[6] https://huggingface.co/Qwen/Qwen2.5-1.5B/resolve/8faed761d45a263340a0528343f099c05c9a4323/tokenizer_config.json
[7] https://huggingface.co/HuggingFaceTB/SmolLM2-1.7B/resolve/effd688a12921b4cc83e3312b6feb579f70f9c71/README.md
[8] https://huggingface.co/HuggingFaceTB/SmolLM2-1.7B/resolve/effd688a12921b4cc83e3312b6feb579f70f9c71/config.json
[9] https://huggingface.co/HuggingFaceTB/SmolLM2-1.7B/resolve/effd688a12921b4cc83e3312b6feb579f70f9c71/tokenizer_config.json
[10] https://huggingface.co/allenai/OLMo-1B-0724-hf/resolve/d7cbab742d80589e714b1a2d7f838dcd21cbe143/README.md
[11] https://huggingface.co/allenai/OLMo-1B-0724-hf/resolve/d7cbab742d80589e714b1a2d7f838dcd21cbe143/config.json
[12] https://huggingface.co/allenai/OLMo-1B-0724-hf/resolve/d7cbab742d80589e714b1a2d7f838dcd21cbe143/tokenizer_config.json
[13] https://huggingface.co/microsoft/phi-2/resolve/810d367871c1d460086d9f82db8696f2e0a0fcd0/README.md
[14] https://huggingface.co/microsoft/phi-2/resolve/810d367871c1d460086d9f82db8696f2e0a0fcd0/config.json
[15] https://huggingface.co/microsoft/phi-2/resolve/810d367871c1d460086d9f82db8696f2e0a0fcd0/tokenizer_config.json
[16] https://huggingface.co/tomg-group-umd/huginn-0125/resolve/bb6621b65e90b6a4b9b29ef88dc83866d450470c/README.md
[17] https://huggingface.co/tomg-group-umd/huginn-0125/resolve/bb6621b65e90b6a4b9b29ef88dc83866d450470c/config.json
[18] https://huggingface.co/tomg-group-umd/huginn-0125/resolve/bb6621b65e90b6a4b9b29ef88dc83866d450470c/tokenizer_config.json
[19] https://arxiv.org/html/2502.05171v2
[20] https://github.com/seal-rg/recurrent-pretraining/tree/1ea7220ec7eb42d13e89db0663df254d0bcdc28e
