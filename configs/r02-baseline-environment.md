# R02 baseline environment recipe

Owner: `eido` (compute). Reviewer: `vesper` (research-a).
Task: [issue #7](https://durandal.exe.xyz/smolmodelco/thesmolmodelcompany/issues/7).
Status: **preflight — not yet executed.** No package has been installed, no
model or tokenizer artifact has been retrieved, and no smoke run has been
performed under this recipe. This document is the reproducibility boundary
submitted for review; the run is authorized only after that review.
Follow-up gate: [issue #17](https://durandal.exe.xyz/smolmodelco/thesmolmodelcompany/issues/17)
owns the executable procedures this design defers. [PR #19](https://durandal.exe.xyz/smolmodelco/thesmolmodelcompany/pulls/19)
is that executable pull request, and it is the binding review gate for them.

## Purpose

Define one minimal environment that another agent can rebuild from this file
alone — without this agent's shell history, warm caches, or working tree — and
then reproduce a single baseline smoke: load the pinned model, run one
inference, terminate cleanly, and record a manifest.

This is a smoke baseline, not an experiment. No dataset, split, generator,
reference, or scorer belongs in it.

## Execution target

WSL2 on the Windows desktop, per [compute.md](../docs/compute.md). Windows-side
interpreters are out of scope for this recipe. The environment is built and the
run is executed from inside the WSL distribution named below.

### Host observation, 2026-09-21T00:36:29Z

Decision [0002](../docs/decisions/0002-measured-host-envelope.md) recorded a
7.33 GiB free-VRAM envelope on 2026-09-20. That remains the historical
observation of record for the conclusions drawn there; it is not restated or
amended here. The following is a **new, independently timestamped observation**
from the WSL execution target, recorded because `compute.md` requires a fresh
audit before a reserved run and states these figures move.

| Quantity | Observed | Command |
|---|---|---|
| GPU | NVIDIA GeForce RTX 3080, driver 616.92 | `nvidia-smi --query-gpu=name,driver_version,memory.total,memory.used,memory.free --format=csv,noheader,nounits` |
| VRAM total | 10,240 MiB | as above |
| VRAM used | 993 MiB | as above |
| VRAM free | **9,061 MiB (8.85 GiB)** | as above |
| RAM available | **23,331 MiB (22.8 GiB)** | `free -m` |
| RAM total | 24,037 MiB | `free -m` |
| CPU | AMD Ryzen 7 3700X, 12 logical cores visible to WSL | `/proc/cpuinfo`, `nproc` |
| Distribution | Ubuntu 24.04.4 LTS | `/etc/os-release` |
| Kernel | 5.15.167.4-microsoft-standard-WSL2 | `uname -r` |
| Filesystem headroom | 931 GiB available on `/` | `df -h` |

Two readings taken minutes apart during this same preflight differed by 231 MiB
of free VRAM (8,830 then 9,061). Treat any single figure as a sample of a
daily-driver desktop, not a constant. The run manifest records its own readings
taken immediately before and after the run rather than reusing these.

These numbers are **larger** than the 0002 envelope, which widens headroom
rather than narrowing it. They do not reopen any conclusion in 0002: that
decision closed the E02 practical probe and full-parameter training on
arithmetic whose margins are far outside this drift, and re-opening it requires
the bounded smoke test that decision specifies, not a more favourable reading.

WSL RAM is governed by `.wslconfig` on the Windows side and does not equal the
Windows host's available RAM. The 22.8 GiB above is what the execution target
sees, which is the figure that constrains this run.

## Pinned baseline

| Item | Pin |
|---|---|
| Model | `Qwen/Qwen2.5-1.5B` |
| Revision | `8faed761d45a263340a0528343f099c05c9a4323` |
| Source | Hugging Face Hub |
| Precision | bfloat16 |
| Device | `cuda:0` |

The revision is a full commit SHA, not a tag or branch name. Fetching by
revision is mandatory: a tag can be moved, a commit SHA cannot.

### Artifact retrieval and hashing

Base weights are **not** stored by this project. They are upstream inputs with
a durable public home, and `coordination.md` requires a reproducing agent to
re-fetch and hash-verify them rather than assume they are present. Keeping a
private copy would weaken that check while consuming roughly 3 GiB.

At run time the recipe records, for every file actually loaded:

- repository ID and the resolved commit SHA;
- each file's path, byte size, and SHA-256 computed locally after download;
- the tokenizer files, hashed on the same terms as the weights.

The first execution establishes these hashes and writes them into the run
manifest. A later reproduction compares against the manifest and fails loudly
on mismatch. Because no artifact has been retrieved yet, this recipe states the
hashing procedure; it does not yet state the hash values, and no placeholder is
recorded in their place.

## Interpreter and dependencies

A dedicated virtual environment is built for R02. The existing
`~/ml/.venv` on this host belongs to an unrelated project and must not be
reused: reusing it would make the environment unrebuildable from this file.

| Component | Pin |
|---|---|
| Interpreter | CPython 3.12.3, the Ubuntu 24.04.4 system `python3` |
| Environment | `python3 -m venv` at `~/ml/projects/smolmodelco/.venv-r02` |
| Package installer | `pip`, upgraded inside the environment before any install |

Dependency versions are pinned to the set already proven to work with CUDA on
this host:

```
torch==2.14.0+cu126
transformers==5.17.0
tokenizers==0.23.2
safetensors==0.8.0
accelerate==1.15.0
huggingface-hub==1.32.0
numpy==2.5.3
```

`torch` is installed from the CUDA 12.6 wheel index. The GPU is compute
capability 8.6; the `cu126` build targets it directly.

These versions are **observed on this host in another environment**, not yet
installed into the R02 environment. The install is part of the authorized run,
not of this preflight. If any version fails to resolve for the pinned
interpreter, that failure is recorded as a result and the recipe is amended
before the run proceeds — it is not silently floated to a working version.

The exact resolved set, including transitive dependencies, is captured with
`pip freeze` into the run directory at execution time. That freeze output, not
this table, is the authoritative dependency record for reproduction.

## Review boundary

This document is the design half of R02: the pins, the artifact-identity
requirements, the persistence decision, the clean-state expectations, and the
manifest fields. The executable half is
[issue #17](https://durandal.exe.xyz/smolmodelco/thesmolmodelcompany/issues/17),
implemented by [PR #19](https://durandal.exe.xyz/smolmodelco/thesmolmodelcompany/pulls/19).

**PR #19 is the binding follow-up gate.** Merging this design did not
authorize a run, and merging the executable code does not either: #17 requires an
independent approval from `vesper` of every command path, and only then does the
operator record a go/no-go decision. Package installation, artifact retrieval,
model loading, inference, GPU reservation, and a live persistence check are
consequences of that recorded decision, not of either merge.

### Executable procedure gate added by #17

PR #19 adds five modules that carry the executable paths. They are import-safe: importing any of
them transfers no bytes, imports neither `torch` nor `transformers`, and touches
no GPU. Each entry point that reaches the network, a model library or the GPU --
`r02_artifacts.py fetch`, `r02_smoke.py`, and `r02_release.py round-trip` --
fails closed with exit code 2 unless it is given an approval record matching its
scope. `r02_artifacts.py plan`, `r02_resources.py probe` and
`r02_release.py self-test` are deliberately ungated because they transfer
nothing, import no model library and touch no GPU.

The read-only `probe` is also the one entry point whose documented job is to
fail *with a record* rather than to refuse: on a host without `nvidia-smi` it
prints a sampling record whose affected metrics carry `value: UNSET`,
`status: "error"` and a redacted `error`, and exits 1. It does not raise.

| Module | Responsibility | Entry point |
|---|---|---|
| `scripts/r02_gate.py` | Approval record, scope check, credential-hygiene helpers | imported, not run |
| `scripts/r02_artifacts.py` | Fetch the pinned inputs, hash them, compare, record | `python3 scripts/r02_artifacts.py plan` / `fetch` |
| `scripts/r02_smoke.py` | Gated tokenizer and model load, one inference, record | `python3 scripts/r02_smoke.py --run-id ID` |
| `scripts/r02_release.py` | Durable release round trip: upload, read back, verify, clean up | `python3 scripts/r02_release.py self-test` / `round-trip` |
| `scripts/r02_resources.py` | Timestamped sampling, sampled values labelled apart from peaks | `python3 scripts/r02_resources.py probe` |

`scripts/r02_preflight.py` is unchanged by #17 and still holds only the
model-free helpers: streaming SHA-256, the explicit-`UNSET` manifest scaffold,
the local test-only persistence round trip, and the `fetch_and_hash` seam that
raises `NotImplementedError` and is never invoked
(`scripts/r02_preflight.py:33-35`). The executable fetch lives in
`scripts/r02_artifacts.py`; the seam stays as the record of what the preflight
deliberately did not do.

### The approval record

Every live step reads a JSON approval record and refuses to start without one:

```json
{
  "granted": true,
  "scope": "r02-readiness-smoke",
  "reference": "issue #17 / executable PR",
  "approved_by": "vesper",
  "approved_at_utc": "2026-09-21T03:00:00Z",
  "operator_go": "cassie"
}
```

The scopes are `r02-artifact-fetch`, `r02-readiness-smoke`, and
`r02-release-round-trip`. A grant for one scope cannot be spent on another, and
`granted: false`, a malformed record, or a missing file all fail closed. The
operator writes the record after `vesper` approves PR #19, and it is
committed with the run so the approval a run executed under is readable next to
its measurements.

### Command paths

```bash
# Identity: fetch the pinned artifacts, hash them, write the artifact manifest.
python3 scripts/r02_artifacts.py fetch \
    --destination "$HOME/ml/models/qwen2.5-1.5b-8faed76" \
    --manifest-out results/R02/<run-id>/artifact-manifest.json \
    --authorization-file results/R02/<run-id>/authorization-fetch.json

# Sequence check for the durable store: in-memory, no credential, no network.
python3 scripts/r02_release.py self-test

# The live persistence round trip, from the WSL execution target.
python3 scripts/r02_release.py round-trip --source <artifact> \
    --run-id <run-id> --authorization-file results/R02/<run-id>/authorization-release.json

# The readiness smoke. --dry-run checks the gate and stops before any import.
python3 scripts/r02_smoke.py --run-id r02-smoke-<nnn> --owner eido \
    --run-dir results/R02/r02-smoke-<nnn> \
    --authorization-file results/R02/<run-id>/authorization-smoke.json
```

No command accepts a token, key, or password as an argument, and the fetch path
refuses to run at all while an ambient Hugging Face token is present, so that
the provenance of the bytes it retrieved cannot be ambiguous.

The smoke's `--run-id` must match `r02-smoke-<nnn>` and `--run-dir` must end
with `results/R02/<run-id>`; anything else is rejected with exit code 2 before
any setup. The owner is supplied on the command line and recorded from the plan
rather than assumed, so a manifest cannot inherit another agent's ownership.

## Clean state and cold cache

Reproduction requires a rebuilt environment, not a reused one.

- The virtual environment is created fresh. If `.venv-r02` exists, it is
  removed before the run rather than reused.
- The Hugging Face cache is **cold for this model** as of this preflight:
  neither `~/.cache/huggingface` nor `~/ml/cache/huggingface` contains any
  `Qwen` entry. The first run therefore measures a genuine cold fetch, and
  cold load time is reported separately from warm inference, per `compute.md`.
- The run records whether the cache was cold or warm. A warm-cache run is a
  valid measurement but is labeled as such and does not substitute for the cold
  figure.
- A human confirms no other process holds the GPU before the run. Per-process
  GPU memory reports as `N/A` under WDDM, so this cannot be established
  programmatically; it was confirmed by the operator for this preflight.
- One GPU owner at a time, per `coordination.md`. The reservation is recorded
  before the run starts and released after it ends.

## Durable artifact storage

**Decision: Forgejo releases on `durandal.exe.xyz`, addressed by URI and
SHA-256.** Artifacts are tiered:

| Class | Where | Why |
|---|---|---|
| Upstream inputs (base weights, tokenizer) | Not stored by us; fetched from Hugging Face by pinned revision | Already durable upstream; re-fetching is what makes a reproduction independent |
| Small derived artifacts (manifests, reports, freezes, hash files) | Committed to the repository | Small, diffable, and part of the review record |
| Large or expensive derived artifacts | Forgejo release assets, referenced by URI and SHA-256 | Durable, reachable by every agent, survives this workstation being off |

Local-only storage was rejected: `coordination.md` states that an agent's
transient workspace must not be the only copy, and artifacts reachable only
from this desktop would block independent reproduction whenever the machine is
off or busy. Hugging Face as a *destination* was rejected for now because this
host is an inference and parameter-efficient-adaptation machine per decision
0002, so the project produces few large weight artifacts, and adding an
external account would widen the credential surface without a present need.
Hugging Face remains the upstream *source*, which the pinned revision requires.

### Persistence check — observed once, not replayable from this PR

Issue #7 requires that persistence be verified before a run whose output cannot
be cheaply reproduced. The check was executed from the WSL execution target on
2026-09-21, because that is where run artifacts will originate:

1. A 1,048,628-byte random probe was created in WSL and hashed locally.
2. It was uploaded as a Forgejo release asset via the API.
3. Its download URL was read back from a **separate** authenticated API call
   rather than reused from the upload response.
4. It was fetched into a clean directory and hashed independently.
5. Source and round-trip digests matched exactly
   (`afd0e448f0af694b0d84f21edc60e2e92417705983bdcc93c6f58bcd39ce7a7c`),
   at identical byte size.
6. The probe release and its tag were deleted; the repository was confirmed to
   hold zero releases afterwards, and local scratch was removed.

No command in this PR performs this check, and nothing from it survives to
inspect: the probe release, its tag, and the local scratch files were all
deleted. The numbered record above is therefore a one-off observation by the
author, not a replayable verification, and it does not close issue #7
deliverable 4.

The durable-storage *decision* above stands as design, and
`scripts/r02_release.py` now supplies the replayable command, the retained
readback URI with digests, and the cleanup confirmation that this section could
only describe. The live round trip has **not** been executed under #17: it
remains an acceptance criterion of the operator's go/no-go step, and
`scripts/r02_release.py self-test` is the credential-free, network-free check
that the sequence is wired correctly in the meantime.

### Credential boundary

The `eido` Forgejo credential is held in the Windows Git Credential Manager,
host-scoped to `durandal.exe.xyz`, and was observed reachable from WSL through
that same store during this preflight, so there is one credential rather than
two. That reachability is a local observation; it is not re-established by any
command in this PR. It is never embedded in a
remote URL, never written to the repository, and never passed on a command
line. API calls pass it through a `curl` configuration file, because process
arguments are readable by other processes on the host.

The credential is deliberately scoped to repository access and does not carry
`read:user`. Identity is therefore established by working repository access
rather than by an account-identity endpoint. This is a narrower credential than
an account-wide token and is kept that way.

## Resource and failure capture

The run records, into `results/R02/<run-id>/manifest.json`, the fields required
by [coordination.md](../docs/coordination.md):

- run ID; UTC start and end; owner;
- code commit and dirty-tree status; config hash;
- model and tokenizer revisions with per-file SHA-256 and byte sizes;
- environment identity: distribution, kernel, driver, interpreter, and the
  full `pip freeze`;
- hardware: GPU name, VRAM total, CPU, RAM available at run time;
- seed; precision; context and output limits;
- elapsed time, separating cold load from warm inference;
- peak VRAM and peak host RAM, each with the basis that earned the peak claim:
  the VRAM peak comes from a device peak counter that is reset at run start, so
  its window covers tokenizer load, model load and generation, and the recorded
  basis says so; host RAM has no peak counter, so it is recorded as a
  `sampled_max` over the sampled instants and the peak field stays `UNSET`;
- **stored footprint and loaded footprint reported separately**, not active
  parameter count alone;
- artifact URIs and hashes; exit status.

Failure handling is explicit, because the acceptance criteria require failures
to be recorded rather than retried away:

- The first OOM, missing file, version mismatch, non-finite value, or failed
  resource probe stops the run, including a failure in the pre-load sampling
  instant: that instant sits inside the same failure boundary as the loads, and
  a probe that cannot be read produces a recorded failure
  (`resource-probe-unavailable`) rather than an exception.
- The failure is written into the run directory as the result, with the command
  and the observed error, and the ledger entry reflects it.
- A retry after a diagnosed fix is a new run ID that links to the prior one. A
  failed run is never overwritten or silently re-attempted until it passes.
- Wall-time cap for a local smoke is 20 minutes per `compute.md`. The cap is
  armed as a `SIGALRM` before the run, so a stage that returns control to the
  interpreter is aborted *at* the cap and still produces a failure record whose
  `failure.enforcement` reads `aborted by the armed guard at the cap`. A stage
  blocked inside a C call is not interrupted by a signal; that case is detected
  only after the call returns, and the record says so instead
  (`detected after the stage returned`). Both outcomes are failures that keep
  their measurements. A run killed from outside (`SIGKILL`, or a supervisor's
  `timeout`) writes nothing: the cap is enforced in-process, and an externally
  killed run is recorded by whoever killed it, not by this procedure.

## Model-free preflight helpers

The model-free `scripts/r02_preflight.py` helpers are described under the gate
section above; they do not retrieve artifacts, execute a model, contact Forgejo,
or claim live persistence, and their tests cover pure local behavior only.

## Run directory, ownership, and replay

One directory per attempt, owned by `eido` (compute) and created only by an
authorized run:

```
results/R02/<run-id>/
    authorization-*.json    # committed: one scoped approval per gated step
    manifest.json           # committed: the run manifest required by coordination.md
    artifact-manifest.json  # committed: per-file revision, byte size, and SHA-256
    resource-samples.json   # committed: the sample series with UTC timestamps
    smoke-report.md         # committed: the readiness report, deliberately not a ledger entry
    raw/                    # git-ignored: full logs and stdout
    predictions/            # git-ignored: raw outputs, never committed
```

`<run-id>` is `r02-smoke-<nnn>`. A failed attempt keeps its own directory: the
first OOM, hash mismatch, probe failure or cap breach stops that run and is
written as its result, with whatever it had already measured. The
`manifest.json` above is therefore written for a failed attempt exactly as it is
for a successful one, and `main` writes it for every outcome it can reach. A
diagnosed retry is a new ID that names the prior one in `manifest.json` rather
than overwriting it. Model weights and tokenizer files never enter Git; an
artifact too large to commit is published to a Forgejo release asset and
referenced in `manifest.json` by URI and SHA-256, with any credential-shaped
part of the readback URI redacted before it is recorded.

A readiness run writes `smoke-report.md`, never a `report.md`:
`scripts/build_results_ledger.py` collects every `results/*/*/report.md` as an
experiment result, and a readiness smoke is not one. A run that does assert a
result is a different kind of run and follows the ledger convention in
[results/README.md](../results/README.md).

Replay, from a rebuilt environment: `scripts/r02_artifacts.py fetch` against the
committed `artifact-manifest.json`, so a mismatch fails loudly instead of
passing silently; then `scripts/r02_smoke.py` under an `authorization-smoke.json`
the reproducing agent obtained for its own run; then
`python3 scripts/build_results_ledger.py --check`, which must stay clean.

## What this recipe does not establish

- Until `r02-smoke-001`, nothing had been installed, downloaded, loaded, or
  executed under this recipe. That run installed the pinned set without floating
  a version, fetched and hashed the artifacts, and completed the smoke; the
  record is in `results/R02/r02-smoke-001/`. The versions are therefore verified
  **by execution on this host**, which is not the same as a guarantee that they
  resolve for another host or interpreter.
- The dependency set was carried over from a working environment for a different
  project on the same host. `r02-smoke-001` showed it resolves and installs
  exactly as pinned in a freshly created 3.12.3 environment on this host, so for
  this host it is no longer only a starting point; for another host or
  interpreter it still is.
- "It fits and runs here, once" is all that `r02-smoke-001` shows. It is a
  readiness result on one prompt at one precision, not a fit claim for other
  settings, longer contexts, batches, or training.
- The artifact hash values are now recorded as **first observations**
  (`results/R02/r02-smoke-001/artifact-manifest.json`). They are not yet
  confirmed by an independent reproduction; that is what a reproduction
  compares against.
- An inference fit would not demonstrate a training fit, and this recipe makes
  no training claim.
- The executable paths were exercised for the first time by `r02-smoke-001`
  (2026-09-21): the pinned artifacts were fetched and hashed, a probe release
  was uploaded, read back, verified and cleaned up, and the model was loaded and
  answered one inference. See
  [the run report](../results/R02/r02-smoke-001/smoke-report.md). That run
  establishes readiness and nothing else: no experiment result, no ledger entry,
  and no claim about a candidate.
- The artifact-hash, VRAM-peak, and cold-load fields in a run manifest stay
  `UNSET` until a run measures them. A sampled maximum is recorded as a sampled
  maximum, never relabelled a peak.
