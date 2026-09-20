# R03 — Generator, scorer, and split protocol

Status: proposed specification; owner Research B (Pyrrha); required reviewer
Research A (Vesper). This is a protocol contract, not an implemented harness or
an authorization to run experiments.

## 1. Scope and invariants

R03 specifies three generated task families for E01 and E03:

1. compositional transformations over small structured records;
2. finite-state tracking and bounded planning; and
3. small rule induction from labeled support examples.

Every generated episode has an independently checkable answer, a canonical
structural identity, a declared generalization axis, and deterministic
provenance. A candidate receives only its prompt, permitted support examples,
and the declared budget. It never receives the hidden latent program, answer,
final-split seed, or scoring trace.

This document governs the first implementation. Changes to a family grammar,
reference semantics, split assignment, canonicalization, scoring policy, or
final-split access must use a new version and a decision record; never silently
replace the judge beneath an existing result.

## 2. Episode record and versioning

A generator emits one episode record before surface rendering:

```text
protocol_version       # this document's semantic version
family                 # records | finite-state | rule-induction
split                  # train | development | final
seed                   # deterministic generator seed, retained outside prompts
latent_program         # canonical typed program or rule object; hidden from candidate
structure_signature    # normalized, literal-free latent-program identity
input_state            # records, state graph, or query inputs
support                # labeled examples permitted to the candidate; empty for E01 records
query                  # one or more hidden-answer questions
answer                 # canonical answer(s), never supplied to candidate
presentation_variant   # symbolic | natural-language plus deterministic wording/renaming choices
difficulty             # declared family-specific factors
provenance             # generator/reference versions, hashes, and split-assignment rule
```

`latent_program`, `answer`, and the final-split seed belong only in the
scorer-side artifact. Candidate-facing exports omit them. A public development
example may expose them only after the episode has been explicitly marked as a
development example.

Canonical serializations use UTF-8 JSON with sorted object keys and no
insignificant whitespace. A record hash is SHA-256 of that serialization.
Literal values, entity names, field names, and natural-language wording are not
sufficient split identifiers: `structure_signature` normalizes them away.

## 3. Family A — compositional record transformations

### Latent language

Inputs are lists of 2–12 typed records with 2–5 fields. Field types are bounded
integers, short strings from a generated vocabulary, booleans, and categorical
labels. The initial grammar contains:

- `filter(field, comparator, literal)` for equality and ordered comparisons;
- `project(fields)`;
- `sort(field, direction)`;
- `group(field, aggregate)` where aggregate is `count`, `sum`, `min`, or `max`;
- `take(n)` after an explicitly ordered sequence; and
- `derive(output_field, arithmetic_expression)` over integer fields using a
  bounded expression tree of `+`, `-`, and multiplication by a small literal.

Programs are typed pipelines of 1–5 operations in development/composition
conditions and 6–8 only in the declared depth-extrapolation condition. The
first implementation forbids operations whose order or tie behavior is
underspecified. `sort` breaks equal keys by the immutable generated record ID;
that ID is present in canonical data but may be rendered as a neutral label.
Grouping emits groups in canonical key order.

### Candidate surface

The symbolic surface gives JSON records and the allowed operation vocabulary.
The natural-language surface expresses the same request without exposing an
operation sequence or template ID (for example, “list the teams with the total
points, highest first”). The renderer independently chooses field aliases,
entity names, clause order, and irrelevant descriptive sentences from its seed.
Natural-language rendering must preserve the task semantics exactly; its
renderer is not the answer oracle.

### Ground truth and audit

The generator's pipeline executor is not the scorer. The reference executor is
a separate, deliberately simple interpreter over the typed AST. It consumes the
canonical AST and input state, not generated text. For all configurations with
at most four records, three fields, and three operations, enumerate valid ASTs
and inputs and compare generator executor versus reference executor exactly.
For larger configurations, sample a deterministic audit corpus stratified by
operation sequence and difficulty, then compare both executors.

Reject an episode before assignment when it has an empty answer where the task
wording implies a nonempty selection, duplicate answer alternatives produced by
different semantics, an answer invariant to a designated required operation, or
a solution recoverable from a renderer/template tag. Record rejected-generation
counts and reasons; do not discard them silently.

## 4. Family B — finite-state tracking and bounded planning

### Latent language

A state is a tuple of 2–4 categorical variables, each with 2–5 values. A
transition has an action name, a conjunction of preconditions, and deterministic
assignments. The tracking subfamily supplies an initial state and an action
trace; its query asks for one or more state variables after the trace.

The planning subfamily supplies the same transition system, an initial state,
and a reachable goal predicate. It asks for a shortest valid action sequence
within a declared horizon. Action names have a fixed canonical lexical order;
when multiple shortest plans exist, the reference scorer accepts any plan of
minimum length that executes to a goal, rather than rewarding its tie-breaker.
Unreachable goals are excluded in the first protocol rather than treated as a
language-negotiation task.

Development traces contain 2–6 transitions; the depth split holds out 7–12.
Planning instances contain 2–5 variables and horizons 2–8 initially. These are
resource budgets, not promises that a particular model should solve them.

### Candidate surface

Symbolic surfaces show a compact transition table. Natural-language surfaces
render the same system as concise rules and a scenario; they vary action names,
variable labels, sentence order, and irrelevant narrative flavor while retaining
all preconditions and effects. Neither surface reveals a graph index, generation
seed, or shortest-plan length.

### Ground truth and audit

A reference transition function executes tracking traces. A separate breadth-
first search enumerates planning reachability and minimum plan length. Exhaust
all systems with two binary variables, up to three actions, and horizon four;
compare generator, reference transition, and BFS results. Reject systems with
ambiguous action effects, duplicate actions after canonicalization, unreachable
goals, or a query answer deducible without consuming a required trace action.

## 5. Family C — small rule induction

### Latent language

A latent rule is a typed expression over 1–3 small discrete inputs. The initial
rule DSL contains equality tests, membership in a generated category set,
boolean conjunction/disjunction with bounded nesting, parity, and modular
arithmetic over a declared small domain. Its output is one categorical label or
a bounded integer. Each episode supplies a labeled support set and independent
unlabeled queries generated from the same latent rule.

Support examples are permitted evidence in E03. Query labels are not. All
candidate-adaptive state — adapters, optimizer state, retrieval writes, caches,
and learned task memory — resets at each episode boundary.

To avoid an underdetermined “guess the hidden rule” game, the generator rejects
support sets that leave distinct in-grammar rules with different query answers
consistent with the support. It also rejects support sets that trivially state
all query tuples, or whose answer is constant across every query. The retained
version space is computed by exhaustive enumeration of the small DSL.

### Candidate surface and ground truth

Symbolic surfaces provide a table of examples plus queries. Natural-language
surfaces name inputs and labels, describe the example/query distinction, and
vary nouns and order without inserting rule hints. A separate enumerator checks
support consistency, query answers, uniqueness under the declared DSL, and
whether a simple one-feature heuristic solves every query. It emits the
reference label vector; it does not reuse the generator's evaluator.

## 6. Split construction and leakage audits

Splits are assigned at the latent-program family level before rendering. Random
surface-string splits are prohibited.

| Axis | What is held out | What remains shared |
|---|---|---|
| In-distribution development | parameter combinations of development structures | primitives and grammar version |
| Composition | unseen AST compositions / rule skeletons built from seen primitives | primitive operations and vocabulary types |
| Depth/length | program or trace depths beyond development cap | family and primitive semantics |
| Presentation | renderer aliases, paraphrase choices, clause order, narrative wrapper | same latent task class under a separately generated seed |
| Family | one declared family for later transfer only | none beyond generic output contract |

For every episode, compute a `structure_signature` by alpha-renaming fields,
entities, labels, and literals; sorting commutative children; replacing literal
values by type/range tokens; and retaining typed operation/rule/transition
shape. No identical structure signature may cross train, development, or final
splits unless the episode is explicitly part of the presentation-change paired
evaluation. Paired presentation episodes share only the latent task ID and are
scored as a robustness pair, never as independent rows.

A second audit normalizes rendered text by lowercasing, replacing generated
names/numbers with typed placeholders, and collapsing whitespace. It blocks
exact normalized duplicates across splits. It also writes candidate cross-split
pairs with character-trigram Jaccard similarity at least 0.85 for manual review
before final freeze. The audit report records counts of exact blocks, fuzzy
candidates, reviewed false alarms, and rejected episodes.

Pretraining contamination cannot be proven absent for public checkpoints. The
report must say this plainly. The protocol instead establishes fresh generator
seeds, hidden final seeds, structure-level split boundaries, and no candidate
access to final answers during development.

## 7. Candidate answer contract and scorer

Candidates return one JSON object containing `answer`, optional `abstain`, and
optional machine-readable trace metadata. The scorer reads only `answer` for
correctness. It validates output schema and family-specific types before
checking semantics.

- **Records:** compare canonical JSON output to the reference executor output.
- **Tracking:** compare each requested state variable exactly.
- **Planning:** parse an action list, execute it with the independent reference
  transition function, and accept only a goal-reaching plan at the reference
  minimum length.
- **Rule induction:** compare the ordered query-label vector exactly.

Each attempted episode receives exactly one terminal outcome:

```text
correct | incorrect | invalid_output | abstained | timeout | oom |
verifier_error | adaptation_diverged | missing_artifact
```

End-to-end completion is `correct / all attempted episodes`; every other
outcome is a non-completion and is separately tabulated. A verifier error is
not candidate evidence, but it remains in the denominator and triggers
investigation. Report selective accuracy and coverage if abstention is enabled.
Never discard a row for malformed output, resource exhaustion, or a failed
restart.

Scoring and aggregation are read-only with respect to candidates. They cannot
alter prompts, weights, caches, libraries, search limits, or support selection.
The scorer records the candidate, task ID, attempt ID, protocol version,
reference hash, declared budget, elapsed time, peak memory when available, and
terminal outcome.

## 8. Conditions and fairness matrix

Each family supports the baseline matrix in `docs/evaluation.md`:

1. selected base checkpoint, direct answer with a development-tuned prompt;
2. the same checkpoint with matched additional inference compute;
3. a simple deterministic/non-neural baseline where applicable; and
4. a stronger feasible local checkpoint at comparable deployment budget.

E01 additionally compares raw versus canonical representations and primitive
versus compound verified operations. E03 compares in-context support, retrieval,
bounded parameter-efficient adaptation, and bounded rule/program search.
Conditions receive identical permitted evidence. A representation or adapter
cannot expose hidden latent programs, query answers, final seeds, or a task ID
that encodes structure.

All resource accounting includes prompt/rendering, candidate inference,
interpreter/verifier, retrieval, library, adaptation, loading, and failed
attempts. The final runtime caps, sample counts, prompts, model revision,
precision, and adaptation/search limits remain R04/R06 decisions after the
50–100-instance development pilot and measured throughput audit. They must
freeze before final outcomes are inspected.

## 9. Final-split access plan

Vesper (Research A) holds the final seeds and scorer-side final records for
E01/E03 once the protocol is frozen. Pyrrha (Research B) may develop against
train/development records but does not receive final answers or final error
records before the single confirmatory pass. Eido receives only the runnable
candidate, fixed config, and resource-recording instructions needed for target
hardware execution; any final scoring export exposes aggregate outcomes unless
Vesper explicitly releases diagnostic rows after scoring.

This is a **protocol-controlled** holdout, not a cryptographically sealed set:
repository and host access alone do not form a technical security boundary.
Final artifacts live outside Git with their hash and URI recorded in the run
manifest. Changing holder, access path, or release order is a protocol change.

## 10. Release criteria for the first implementation

Before any candidate run, the implementation must demonstrate:

- deterministic regeneration of a fixed development fixture from its seed;
- generator/reference agreement for each family’s exhaustive small audit;
- recorded rejected-instance and shortcut-audit results;
- no cross-split structure-signature collision and a reviewed fuzzy-similarity
  report;
- scorer fixtures for every terminal outcome, including timeout/OOM/verifier
  error accounting; and
- a frozen protocol version and config hash.

A passing fixture suite establishes apparatus feasibility, not a reasoning
result. Any experiment result remains at the claim level justified by its own
frozen run, controls, resources, and independent reproduction.
