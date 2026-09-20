# Research map and source register

Reviewed for initial design: 2026-09-20. This is a focused starting bibliography, not an exhaustive novelty review. Claims below distinguish published mechanisms from our proposed experiments. Before choosing a runtime or checkpoint, inspect its current official release, license, compatibility, and immutable revision.

| Direction | Published foundation | Proposed project question | Priority |
|---|---|---|---|
| Compositional skills | DreamCoder grows reusable symbolic abstractions with neural-guided program learning | Can small language models use and later discover reusable operations that transfer to new compositions? | E01 |
| Recurrent depth | Repeated latent computation can scale inference work without proportional parameter growth | Is recurrence useful under matched training/inference costs and unfamiliar solution depths? | E02 |
| Temporary adaptation | Per-task updates have improved selected few-shot reasoning benchmarks | When do bounded updates beat prompting and search on genuinely new rules? | E03 |
| Learned working memory | TTT layers learn a hidden state; Titans studies neural long-term memory | Can bounded adaptive memory preserve facts and support decisions in changing streams? | Reserve |
| State-space/hybrid models | Selective state-space models offer a different sequence-modeling trade-off | Which long-running local tasks benefit after kernel and memory costs are counted? | Reserve |
| Native low-bit computation | BitNet provides a native low-bit model and inference implementation | Does the complete low-bit system improve the useful quality/resource frontier here? | Reserve |
| Search-to-skill consolidation | Program libraries and learned search offer precedents | Can expensive verified solutions become cheap reusable competence? | Synthesis after E01 |

## Primary sources

1. Ellis et al., [DreamCoder: Growing generalizable, interpretable knowledge with wake-sleep Bayesian program learning](https://arxiv.org/abs/2006.08381). Published mechanism: learned reusable programs and neural search guidance. Our language-model integration and desktop feasibility are hypotheses.
2. Geiping et al., [Scaling up Test-Time Compute with Latent Reasoning: A Recurrent Depth Approach](https://arxiv.org/abs/2502.05171). Published study uses a 3.5B-parameter model and substantial pretraining. We do not propose reproducing that pretraining budget locally.
3. Akyurek et al., [The Surprising Effectiveness of Test-Time Training for Few-Shot Learning](https://proceedings.mlr.press/v267/akyurek25a.html). Evidence for temporary task-specific parameter adaptation on studied benchmarks; no assumption that all models or tasks benefit.
4. Sun et al., [Learning to (Learn at Test Time): RNNs with Expressive Hidden States](https://arxiv.org/abs/2407.04620). TTT layers make the sequence-model state itself a learner. This architectural mechanism differs from E03's temporary adaptation of an existing model.
5. Behrouz et al., [Titans: Learning to Memorize at Test Time](https://arxiv.org/abs/2501.00663). Neural memory architecture, not a claim that adding a vector database reproduces it.
6. Gu and Dao, [Mamba: Linear-Time Sequence Modeling with Selective State Spaces](https://arxiv.org/abs/2312.00752). Architectural precedent; published speed/quality comparisons must not be imported as desktop measurements.
7. Microsoft, [BitNet b1.58 2B4T model card](https://huggingface.co/microsoft/bitnet-b1.58-2B-4T). Existing native low-bit checkpoint. Distinguish native low-bit training from post-training quantization and packed inference weights from training master weights.

## Connections to other fields: hypotheses to investigate

- **Minimum description length / program induction:** a compact reusable library may capture recurring structure. Test unseen compositions; compression alone is not proof of generalization.
- **Compiler design / invariance:** canonical representations may remove irrelevant variation. Include translator failures and compare a simple deterministic normalizer.
- **Iterative numerical methods / control:** recurrent computation may refine a state, with a stopping rule allocating effort. Establish stability and utility empirically; convergence of one signal does not imply correctness.
- **Bayesian inference / meta-learning:** support examples constrain a new task rule. Compare search and adaptation under equal budgets without asserting posterior calibration.
- **Information bottlenecks / sufficient statistics:** compact state may retain what a task needs. Measure information loss with adversarial updates and decisions that require old facts.

These connections motivate experiments. No generalization theorem has been proved for this project, and no novelty claim is made without a broader prior-art search.

## Checkpoint-selection record required from Research A

For each candidate: immutable revision, architecture/parameter count, tokenizer, pretraining/instruction status, license, source of weights, inference/training runtime support, precision options, approximate weight/cache/optimizer costs, actual host fit when measured, comparable baseline, and known confounds. Choose one ordinary baseline before expanding the roster.
