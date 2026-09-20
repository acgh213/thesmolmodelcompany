# Minimum evaluation apparatus implementation plan

> **For Hermes:** Implement in small, reviewed pull requests. Do not begin model
> downloading, training, candidate evaluation, or paid/rented compute as part of
> this plan.

**Goal:** Build the smallest deterministic Python apparatus that proves R03's
three generator families, independent references, split audit, and terminal
scorer outcomes can run reproducibly before any model candidate is connected.

**Architecture:** A stdlib-only Python package under `src/smolmodelcompany/`
holds typed episode records, family generators, independent references, split
audits, and a read-only scorer. A thin CLI creates/rechecks development fixtures
under `tests/fixtures/`; it is not a plugin framework, web service, benchmark
dashboard, or model runtime. Candidate/model integration is deliberately a later
R04/R06 change.

**Tech stack:** Python 3.11+ standard library; `unittest`; existing
`scripts/check_docs.py` and `scripts/build_results_ledger.py`; no ML framework,
network download, database, or new third-party dependency.

---

## Scope locks

- Implement the R03 contract in
  [`docs/R03-generator-scorer-split-protocol.md`](../R03-generator-scorer-split-protocol.md),
  versioned as `r03-v1`.
- Use development seeds and fixtures only. Final seeds, model checkpoints,
  prompt recipes, final sample counts, and resource caps stay out of this plan.
- Keep all task answers and latent programs in scorer-side Python objects or
  local development fixtures; candidate-facing JSON must omit them.
- A passing apparatus fixture establishes **feasibility**, never a reasoning or
  adaptation result.

## Shared conventions

- Package source: `src/smolmodelcompany/`; tests: `tests/`.
- Run all tests with `python3 -m unittest discover -s tests -v`.
- Run documentation checks before every PR: `python3 scripts/check_docs.py` and
  `python3 scripts/build_results_ledger.py --check`.
- Commit only source, tests, tiny generated fixture JSON, manifests, and reports.
  Never commit weights, raw final data, credentials, caches, or prediction dumps.
- Use deterministic `random.Random(seed)` instances passed explicitly; never use
  module-global random state.

## Task 1: Establish the zero-dependency package and test command

**Objective:** Make the first implementation importable and prove the test
command works before adding task semantics.

**Files:**
- Create: `pyproject.toml`
- Create: `src/smolmodelcompany/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/test_package.py`

**Steps:**

1. Create `pyproject.toml` with `setuptools` build metadata, project name
   `smolmodelcompany`, Python requirement `>=3.11`, and `src` package layout.
   Do not declare ML, tokenizer, or GPU dependencies.
2. Add `__version__ = "0.1.0"` in `src/smolmodelcompany/__init__.py`.
3. Write a failing `tests/test_package.py` that imports the package and asserts
   the version string.
4. Run `python3 -m unittest discover -s tests -v`; expected first failure is an
   import error before package configuration is correct.
5. Make the minimum packaging fix; rerun until the test passes.
6. Commit: `build: establish deterministic evaluation package`.

## Task 2: Define canonical episode and candidate-facing exports

**Objective:** Establish one typed, hashable representation with a hard boundary
between scorer-side hidden state and candidate-visible data.

**Files:**
- Create: `src/smolmodelcompany/episode.py`
- Create: `tests/test_episode.py`

**Steps:**

1. Write failing tests for an immutable `Episode` dataclass containing protocol
   version, family, split, seed, input state, support, query, answer, latent
   program, structure signature, presentation variant, difficulty, and
   provenance.
2. Add `canonical_json(value) -> str` using sorted JSON keys, compact separators,
   UTF-8-safe serialization, and rejection of non-JSON values.
3. Add `record_hash()` as SHA-256 of scorer-side canonical JSON.
4. Add `candidate_payload()` and test that it includes only family, task ID,
   rendered input/support/query, declared budget placeholder, and presentation
   metadata; assert it does **not** contain `answer`, `latent_program`, seed, or
   final-split provenance.
5. Run tests; add duplicate-record and nondeterministic-key-order cases.
6. Commit: `feat: add canonical episode records`.

## Task 3: Implement records grammar plus separate reference executor

**Objective:** Demonstrate the first family’s generator and oracle are distinct
implementations that agree on an exhaustive small domain.

**Files:**
- Create: `src/smolmodelcompany/records.py`
- Create: `src/smolmodelcompany/records_reference.py`
- Create: `tests/test_records.py`
- Create: `tests/test_records_reference.py`

**Steps:**

1. Write failing tests for typed record generation and canonical operation ASTs:
   filter, project, sort, group/aggregate, take, and bounded arithmetic derive.
2. Implement `records.py` with a generator-side pipeline executor. Its sort must
   use record ID as the stated stable tie-breaker and grouping must emit canonical
   key order.
3. Implement `records_reference.py` independently: no import of generator
   execution helpers, no shared dispatch table, and no reuse of rendered text.
   It accepts only AST plus canonical input state.
4. Add an exhaustive audit for the small regime specified by R03 (at most four
   records, three fields, three operations). Test it returns zero mismatches on
   a fixed seed list and records every rejected instance/reason.
5. Add negative tests that deliberately mutate a reference answer and require the
   audit to fail; this proves the audit is capable of detecting disagreement.
6. Commit: `feat: add records generator and independent reference`.

## Task 4: Implement finite-state tracking/planning plus independent BFS oracle

**Objective:** Add deterministic transition-system episodes without conflating
transition generation and shortest-plan verification.

**Files:**
- Create: `src/smolmodelcompany/finite_state.py`
- Create: `src/smolmodelcompany/finite_state_reference.py`
- Create: `tests/test_finite_state.py`

**Steps:**

1. Write failing tests for deterministic state tuples, transitions with explicit
   preconditions/effects, tracking queries, and reachable planning goals.
2. Implement generator-side transition construction and rejection of ambiguous
   effects, duplicate canonical actions, and unreachable goals.
3. Implement reference transition execution and a separately written BFS that
   returns reachability, minimum length, and valid plans. Do not import a
   generator search helper.
4. Exhaust all two-binary-variable systems up to three actions/horizon four;
   assert generator/reference/BFS agreement. Include a mutation test that proves
   a wrong transition effect is detected.
5. Test the scorer-facing planning rule: any goal-reaching plan at reference
   minimum length passes; a longer valid plan fails.
6. Commit: `feat: add finite-state generator and BFS reference`.

## Task 5: Implement rule-induction generation and version-space audit

**Objective:** Generate support/query episodes whose query labels are uniquely
constrained under the declared bounded DSL.

**Files:**
- Create: `src/smolmodelcompany/rule_induction.py`
- Create: `src/smolmodelcompany/rule_reference.py`
- Create: `tests/test_rule_induction.py`

**Steps:**

1. Write failing tests for the initial typed DSL: equality, set membership,
   conjunction/disjunction, parity, bounded modular arithmetic, categorical or
   bounded-integer output.
2. Implement a generator that produces support/query partitions and rejects
   constant-query, support-leaks-query, and underdetermined episodes.
3. Implement an independent exhaustive DSL enumerator. Test it identifies every
   rule consistent with support and rejects an episode whenever consistent rules
   disagree on a query answer.
4. Add one-feature shortcut checks and tests with deliberately shortcut-solvable
   fixtures that must be rejected.
5. Commit: `feat: add rule-induction generator and version-space audit`.

## Task 6: Add structural split assignment and leakage reporting

**Objective:** Make split boundaries testable from latent structure rather than
surface rows.

**Files:**
- Create: `src/smolmodelcompany/splits.py`
- Create: `tests/test_splits.py`
- Create: `tests/fixtures/r03-development.json`

**Steps:**

1. Write failing tests for `structure_signature()` covering alpha-renaming,
   literal/type replacement, sorted commutative children, and preserved typed
   operation/rule/transition shape.
2. Implement deterministic split assignment by structural family and declared
   axis: development, composition, depth, and presentation pairs.
3. Implement normalized surface duplicate detection and character-trigram
   Jaccard candidate-pair reporting at the protocol threshold of 0.85. Do not
   silently auto-delete fuzzy pairs; produce an auditable report object.
4. Create a tiny development-only fixture and test: regeneration hash is stable;
   no cross-split signature collision exists; exact duplicates are blocked; a
   known similar pair appears in the fuzzy report.
5. Commit: `feat: add structural split and leakage audit`.

## Task 7: Add read-only scorer and terminal-outcome accounting

**Objective:** Prove every attempted episode yields one counted terminal state.

**Files:**
- Create: `src/smolmodelcompany/scorer.py`
- Create: `tests/test_scorer.py`

**Steps:**

1. Write failing tests for the outcome enum: `correct`, `incorrect`,
   `invalid_output`, `abstained`, `timeout`, `oom`, `verifier_error`,
   `adaptation_diverged`, and `missing_artifact`.
2. Implement family-specific answer validation against the independent references.
   Keep candidate traces optional and non-authoritative for correctness.
3. Implement `summarize_attempts()` with end-to-end completion equal to
   `correct / all attempted`. Assert every non-correct terminal state remains in
   the denominator and separate counts.
4. Test malformed JSON, an abstention, a timeout sentinel, OOM sentinel, a
   verifier exception, a nonminimal but valid plan, and a correct answer.
5. Add an immutability test: scorer input objects and candidate payload are
   unchanged after scoring.
6. Commit: `feat: add terminal-outcome scorer`.

## Task 8: Add fixture CLI and apparatus release check

**Objective:** Give Eido a small, model-free command to verify the apparatus on
target hardware before a candidate environment is attempted.

**Files:**
- Create: `src/smolmodelcompany/cli.py`
- Modify: `pyproject.toml` (console script `smolmodelco-fixtures`)
- Create: `tests/test_cli.py`
- Create: `docs/apparatus-check.md`

**Steps:**

1. Write failing CLI tests for `generate-fixture --seed <n> --out <path>` and
   `check-fixture <path>`.
2. Implement generation of the R03 development fixture, references/audits, and a
   compact canonical JSON report carrying `protocol_version: "r03-v1"`, a hash
   of the canonical fixture configuration, family counts, rejected counts,
   **shortcut-audit results**, reference mismatches, split collisions, fuzzy
   candidates, and scorer-fixture outcomes.
3. Implement `check-fixture` to regenerate/recheck the fixture hash,
   `protocol_version`, canonical configuration hash, reference agreement,
   rejection/shortcut audit report, split report, and terminal-outcome fixture
   coverage without a model/GPU.
4. Document exact command, expected zero-mismatch output, host metadata to log,
   and failure behavior. Explicitly state that it is an apparatus check, not R02
   model smoke or an experiment result.
5. Run the full test suite, existing documentation checks, and the CLI against a
   temp fixture. Commit: `feat: add reproducible apparatus fixture check`.

## Review and integration order

```
Task 1 → Task 2
Task 2 → Tasks 3, 4, 5
Tasks 3, 4, 5 → Task 6
Tasks 3, 4, 5 → Task 7
Tasks 6, 7 → Task 8
```

Review each task in a separate Forgejo PR or a small coherent PR with tests.
Research A reviews changes to generators, references, splits, and scorer
semantics. Eido runs Task 8's apparatus check in the R02 environment only after
this plan and the implementation PRs are accepted. R04/R06 may not attach a
model candidate until Task 8 provides the declared acceptance evidence.
