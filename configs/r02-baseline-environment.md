# R02 baseline environment recipe

Owner: `eido` (compute). Reviewer: `vesper` (research-a).
Task: [issue #7](https://durandal.exe.xyz/smolmodelco/thesmolmodelcompany/issues/7).
Status: **preflight — not yet executed.** No package has been installed, no
model or tokenizer artifact has been retrieved, and no smoke run has been
performed under this recipe. This document is the reproducibility boundary
submitted for review; the run is authorized only after that review.

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

This PR is a preflight design only. It records the pinned environment, artifact identity and hashing requirements, persistence decision, clean-state expectations, and the manifest fields that a later authorized execution procedure must implement. It does not contain executable artifact retrieval, model smoke, or release-asset transport commands.

A separate executable-procedure issue/PR must be reviewed and approved before any package installation, artifact retrieval, model loading, inference, GPU reservation, or live persistence check. That follow-up must bind its implementation and tests to this recipe without treating this design review as execution authorization.

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

### Persistence check — performed, not asserted

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

Storage is therefore verified as durable and byte-exact for this path. The
check is repeatable: it is a create, upload, re-read, verify, delete cycle
using only the repository-scoped credential.

### Credential boundary

The `eido` Forgejo credential is held in the Windows Git Credential Manager,
host-scoped to `durandal.exe.xyz`, and is reachable from WSL through that same
store so there is one credential rather than two. It is never embedded in a
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
- peak VRAM and peak host RAM;
- **stored footprint and loaded footprint reported separately**, not active
  parameter count alone;
- artifact URIs and hashes; exit status.

Failure handling is explicit, because the acceptance criteria require failures
to be recorded rather than retried away:

- The first OOM, missing file, version mismatch, non-finite value, or
  non-termination stops the run.
- The failure is written into the run directory as the result, with the command
  and the observed error, and the ledger entry reflects it.
- A retry after a diagnosed fix is a new run ID that links to the prior one. A
  failed run is never overwritten or silently re-attempted until it passes.
- Wall-time cap for a local smoke is 20 minutes per `compute.md`; exceeding it
  is itself a recorded failure.

## Model-free preflight helpers

The repository retains only the model-free `scripts/r02_preflight.py` helpers: streaming SHA-256, an explicit-`UNSET` manifest scaffold, and a local test-only persistence round-trip. These helpers do not retrieve artifacts, execute a model, contact Forgejo, or claim live persistence. Their tests are limited to pure local behavior.

The executable fetch/hash, smoke, and Forgejo-release procedures are intentionally out of scope for this PR and must be introduced under a separate review gate.

## What this recipe does not establish

- Nothing has been installed, downloaded, loaded, or executed under it. Every
  dependency version and the entire retrieval path are **unverified by
  execution** at the time of review.
- The dependency set is carried over from a working environment for a different
  project on the same host. It is a well-founded starting point, not proof that
  these versions resolve together for a freshly created 3.12.3 environment.
- No claim is made that Qwen2.5-1.5B fits, loads, or runs on this host. That is
  precisely what the authorized smoke is for.
- The artifact hash values do not exist yet and cannot until the first fetch.
- An inference fit would not demonstrate a training fit, and this recipe makes
  no training claim.
