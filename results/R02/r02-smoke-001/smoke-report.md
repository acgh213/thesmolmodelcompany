# R02 readiness smoke — run report

**Run ID:** `r02-smoke-001` · **Owner:** `eido` (compute) · **Started (UTC):** 2026-09-21T03:10:07Z ·
**Finished (UTC):** 2026-09-21T03:11:19Z

**Status: `ok` — the readiness smoke completed on its first attempt. No failure,
no retry, no OOM.** This report is deliberately **not** an entry in the results
ledger: it records environment readiness, not an experiment, and it asserts no
quality, capability, or comparison claim. For that reason it is named
`smoke-report.md` rather than `report.md`: `scripts/build_results_ledger.py`
collects every `results/*/*/report.md`, and a `report.md` without front matter
would fail the CI ledger check while one with front matter would register this
smoke as an experiment — which the operator's authorization excludes.

## Authorization

Two separate decisions are involved, and they must not be conflated:

1. **Procedure approval — `vesper`, review #43.** `vesper` reviewed and approved
   the *executable procedure* (PR #19, head
   `43ae50b1590985ef1d4e9fb041a750cf166060b1`, `checks / documentation integrity`
   = success, merged at `dbad39e1b9436ea9a3b70ff94fa2c0e50f494b79`). That review
   approved the code; it did **not** authorize a run, and it is not an execution
   approval.
2. **Operator go/no-go — `cassie`, recorded separately.** The operator
   authorized *this run and nothing else*: the R02 readiness smoke. The decision
   was received before these records were written and is the only authorization
   the run executed under.

The three scoped records therefore carry `approved_by: vesper` **together with**
`procedure_reviewer_only: true`, and their `reference` reads "PR #19 review #43
procedure approval; operator go recorded separately":

| Record | Scope | `procedure_approved_at_utc` | Operator go |
|---|---|---|---|
| `authorization-fetch.json` | `r02-artifact-fetch` | 2026-09-21T02:57:02Z | `cassie`, separate |
| `authorization-smoke.json` | `r02-readiness-smoke` | 2026-09-21T02:57:02Z | `cassie`, separate |
| `authorization-release.json` | `r02-release-round-trip` | 2026-09-21T02:57:02Z | `cassie`, separate |

`approved_at_utc` holds review #43's submitted timestamp, read back from the
Forgejo API — it is the *procedure* approval time, not an execution approval
time. `record_created_at_utc` is when each record was written, and
`operator_go_received_before_utc` marks that the operator decision preceded it.
The gate itself reads `granted`, `scope` and the three reference fields, all of
which were present and unchanged when the run executed.

### Path labels used in this record

Committed evidence carries stable labels instead of the operator's filesystem
layout. The recipe defines the concrete paths:

| Label | Means |
|---|---|
| `<VENV_ROOT>/.venv-r02` | the recipe's environment path |
| `<FETCH_DESTINATION>/qwen2.5-1.5b-8faed76` | the recipe's fetch destination |
| `<HF_CACHE_ROOT>` | the execution target's Hugging Face cache root |
| `<SCRATCH_ROOT>` | a run-local scratch root outside the repository |
| `results/R02/r02-smoke-001/...` | repository-relative, as always |

## Environment

| Component | Value |
|---|---|
| Execution target | WSL2 on the Windows desktop (recipe target) |
| Interpreter | CPython 3.12.3 (`python3 -m venv`) |
| Environment | `<VENV_ROOT>/.venv-r02`, created fresh for this run |
| Package installer | `pip` upgraded inside the environment before any install (pip 26.2.1) |
| Authoritative dependency record | `raw/install.log` (`pip freeze`), not this table |

Installed exactly as pinned, with no version floated:

```
torch==2.14.0+cu126        (from the CUDA 12.6 wheel index)
transformers==5.17.0       tokenizers==0.23.2     safetensors==0.8.0
accelerate==1.15.0         huggingface-hub==1.32.0  numpy==2.5.3
```

`torch.version.cuda` = `12.6`; `torch.cuda.is_available()` = `True`; device
reported by the loaded run = `NVIDIA GeForce RTX 3080`, compute capability
`(8, 6)` — the capability the `cu126` wheel targets. Resolution was checked with
`pip install --dry-run` before any wheel was fetched (`raw/install-resolve-*.log`).

## Artifact identity

Fetched anonymously from the Hugging Face Hub **by immutable revision** — the
requested revision and the revision upstream resolved to are the same commit
SHA. No credential was available to the fetch and none was used: the run's own
stderr contains the Hub's unauthenticated-request notice, and the fetch path
would have failed closed had any of `HF_TOKEN`, `HUGGING_FACE_HUB_TOKEN`,
`HUGGINGFACE_TOKEN`, `HF_HUB_TOKEN` been set.

**Revision:** `8faed761d45a263340a0528343f099c05c9a4323` (resolved = requested)

| File | Bytes | SHA-256 (first observation) |
|---|---|---|
| `config.json` | 684 | `0e8c8aa86468aba09c9d32157ff4bc2301c7e6c50e4398960425b2ea71e66f77` |
| `generation_config.json` | 138 | `8c970692323e3ea0e9b8b0a4dca79388d31226e41f83c9fd6014804280ebf6e8` |
| `model.safetensors` | 3087467144 | `a961db72e75d52b18e6b0c9d379e51a26973b233385e0e127fdda7d648aec796` |
| `tokenizer.json` | 7031645 | `c0382117ea329cdf097041132f6d735924b697924d6f6fc3945713e96ce87539` |
| `tokenizer_config.json` | 7228 | `c91efca15ceff6e9ee9424db58a6f59cd41294e550a86cbd07e3c1fb500b34f9` |
| `vocab.json` | 2776833 | `ca10d7e9fb3ed18575dd1e277a2579c16d108e32f27439684afa0e10b1440910` |
| `merges.txt` | 1671839 | `599bab54075088774b1733fde865d5bd747cbcc7a547c5bc12610e874e26f5e3` |

Total observed: **3,098,955,511 bytes (2.886 GiB)**. Every file is labelled
`first-observation`: no expected hash existed before this run, so these values
*are* the record a reproduction must match. Fetch report:
`artifact-fetch-report.json`; manifest: `artifact-manifest.json`.

### Loaded bytes match the recorded identity

The manifest above describes the fetched copy. The run itself loads through the
Hugging Face cache, so the bytes actually loaded were re-hashed and compared:

```
python3 - <run-dir>   # raw/provenance-crosscheck.log, hf-cache-crosscheck.json
```

All seven snapshot files (hashed through their blob symlinks) match the manifest
digest and byte size; `mismatches: []`, `all_match: true`. The cache layout is
content-addressed: six small files are blobs under the model's cache directory
and `model.safetensors` resolves to a 3,087,467,144-byte blob under the
hub-level `blobs/8b/` store — which is why `du` on the model directory alone
reports ~12 MiB. Measured footprint of the whole cache after the run: 3.2 GiB
(2.9 GiB of it this model; ~231 MiB predates this run and belongs to another
project).

## Durable artifact storage — live round trip

Executed from the WSL execution target against the canonical forge
(`raw/release-round-trip.stderr.log`, `release-round-trip.json`):

1. 1,048,576-byte random probe created locally and hashed
   (`518aea3ad697f6e3b977d5384a8a819ef05d1e51efc170ccc6aa094b83bd76a7`).
2. Draft pre-release `r02-persist-r02-smoke-001-20260921T030947Z-a97305eb`
   created; asset `r02-persist-probe.bin.518aea3ad697f6e3` uploaded to release 3.
3. Download URL re-read with a **separate** `GET` on release 3 — not reused from
   the upload response.
4. URL fetched into a clean directory and hashed independently: digest and size
   both match the source exactly. `verified: true`.
5. Release and tag deleted; a fresh release listing confirms the release is gone
   (`release_deleted`, `tag_deleted`, `release_absent: true`, `errors: []`).

The transport log contains no credential: the token is read by the
pre-provisioned Git Credential Manager helper into a mode-0600 `curl`
configuration file that is removed afterwards, and it never appears in argv, a
URL, or a log line. Readback URI (release since deleted):
`https://durandal.exe.xyz/smolmodelco/thesmolmodelcompany/releases/download/r02-persist-r02-smoke-001-20260921T030947Z-a97305eb/r02-persist-probe.bin.518aea3ad697f6e3`.
The local probe file is retained at
`<SCRATCH_ROOT>/r02-smoke-001/r02-persist-probe.bin` so the recorded
digest stays checkable; it is not in the repository.

## Resource observations

**Method.** `nvidia-smi` (`memory.used`, `memory.total`, `utilization.gpu`, CSV,
no units) and `/proc/meminfo` (`MemAvailable`, `MemTotal`) polled at whole
instants, one system-UTC clock read per instant, 5 s apart; the device peak
counter is `torch.cuda.max_memory_allocated/reserved`, reset at run start before
any load. GPU figures describe the shared desktop GPU; RAM figures describe the
execution target, not the Windows host.

Pre-run host audit (`pre-run-probe.json`, 3 instants at 03:09:37/42/47Z, 0 probe
errors): VRAM used 1248 MiB of 10240 MiB; RAM available **23,193–23,198 MiB**
(exact readings 23,196.00, 23,198.15, 23,192.98 MiB); GPU utilization 0%.
Addressable headroom at that point: 8,992 MiB VRAM.

In-run samples (`resource-samples.json`; 5 samples pre-load, 7 post):

| Metric | Pre | Post | Basis |
|---|---|---|---|
| VRAM used (MiB) | 1248 | 4696 | sampled |
| GPU utilization (%) | — | 15 | sampled |
| RAM available (MiB) | 22,927 | 21,855 | sampled |
| Peak VRAM allocated (MiB) | — | **3003.08** | device peak counter, reset at run start before any load, read after the generation step |
| Peak VRAM reserved (MiB) | — | **3178.0** | same counter, same window |

**Sampled versus peak is kept explicit.** Only the two peak-counter metrics carry
a peak value; every sampled metric's `peak_claims[…]` entry is `UNSET` with the
basis "not measured: only periodic samples are available, so the `sampled_max` is
a lower bound on any peak". The peak window covers tokenizer load, model load and
generation — the counter is reset before the first load, not after it.

## Timing

| Quantity | Value | Note |
|---|---|---|
| Cold load (start → model resident) | **70.0 s** | **includes the 2.886 GiB cold fetch**, because the cache was cold for this model. It is not a disk-cold load time. |
| Tokenizer load | 5.0 s | within the same window |
| Warm inference (generate call) | **2.0 s** | one batch, 5 prompt tokens, 8 new tokens |
| Wall clock, whole run | 72.0 s | cap 1200 s |
| Cap enforcement | `sigalrm armed` | the cap raises in the interpreter; no breach occurred |

Not a throughput measurement: one prompt, one batch, `max_new_tokens=8`,
`do_sample=False`, `seed=0`.

## Model and inference

| Field | Value |
|---|---|
| Model / revision | `Qwen/Qwen2.5-1.5B` @ `8faed761d45a263340a0528343f099c05c9a4323` |
| Precision / device | `bfloat16` / `cuda:0` |
| Tokenizer | vocab_size 151,643; prompt encoded to 5 tokens |
| Output | 8 tokens, `stop_reason: max_new_tokens`, **no raw text recorded** (digest `7bb6c4b1716b6c28056635cc6f1f190f81ac8cb9131b9eae36e17c00eaddde31` only) |
| Logits | all finite: `true` |

Readiness checks — all four passed: tokenizer produced input tokens; model
produced output tokens; logits finite; device matches the plan. `exit_status:
ok`, `failure.kind: UNSET`, `retried: false`.

## What this run does not establish

- Nothing about training fit, throughput of record, or any candidate/experiment
  result. It is one readiness smoke: the pinned model loads, answers once, and
  terminates cleanly on this host.
- The artifact hashes are first observations, not confirmations of an
  independent reproduction. A reproducing agent must re-fetch and match them.
- No per-process GPU attribution is possible under WDDM: the operator confirmed
  no other process held the GPU before the run, and the pre-run sample (1248 MiB
  used, 0% utilization) is a reading, not a guarantee.
- The 70 s cold figure will not repeat: the cache is now warm for this model.

## Notes on procedure

- The operator's authorization excludes a results-ledger entry, so the run report
  is `smoke-report.md`; see the top of this file. The recipe's run-directory
  listing is corrected accordingly in the same pull request.
- Three scoped authorization records are used instead of one `authorization.json`,
  because the gate accepts exactly one scope per record.
- The recipe's environment path `.venv-r02` is not matched by `.gitignore`
  (`.venv/` is), so it appears as untracked in the clone that hosts it. This run
  created it there because the recipe names that absolute path. A future change
  could add `.venv-r02/` to `.gitignore`.
- The fetch destination (`<FETCH_DESTINATION>/qwen2.5-1.5b-8faed76`, 2.9 GiB) and the
  cache copy the model loaded (2.9 GiB) both exist on disk. That duplication is
  deliberate: the recipe keeps base weights out of the repository and the
  reproduction path re-fetches and re-hashes rather than trusting either copy.

## Files in this directory

Committed: `authorization-fetch.json`, `authorization-smoke.json`,
`authorization-release.json`, `artifact-manifest.json`,
`artifact-fetch-report.json`, `hf-cache-crosscheck.json`, `pre-run-probe.json`,
`release-round-trip.json`, `manifest.json`, `resource-samples.json`,
`smoke-report.md`.

Git-ignored raw logs: `raw/install.log`, `raw/install-resolve-torch.log`,
`raw/install-resolve-rest.log`, `raw/artifact-fetch.log`,
`raw/resource-probe.log`, `raw/release-round-trip.stdout.log`,
`raw/release-round-trip.stderr.log`, `raw/smoke.stdout.log`,
`raw/smoke.stderr.log`, `raw/provenance-crosscheck.log`.

## Replay

```bash
# 1. identity: re-fetch and compare against the committed manifest
python3 scripts/r02_artifacts.py fetch \
    --destination "$HOME/ml/models/qwen2.5-1.5b-8faed76" \
    --manifest-out /tmp/artifact-manifest.json \
    --expected-manifest results/R02/r02-smoke-001/artifact-manifest.json \
    --authorization-file results/R02/r02-smoke-001/authorization-fetch.json

# 2. a fresh environment, then the smoke under a new run ID and a new approval
python3 -m venv "$HOME/ml/projects/smolmodelco/.venv-r02"
python3 scripts/r02_smoke.py --run-id r02-smoke-NNN --owner <reproducing-agent> \
    --run-dir results/R02/r02-smoke-NNN \
    --authorization-file results/R02/r02-smoke-NNN/authorization-smoke.json

# 3. ledger check only if the reproducing agent registers an experiment result
python3 scripts/build_results_ledger.py --check
```

## Post-review corrections (review #45, artifact hygiene only)

Review #45 requested changes to artifact hygiene. None of the corrections below
touched the run: nothing was re-executed, no artifact or model was downloaded,
loaded or removed, the GPU was not used, and the results ledger is unchanged
(`0 run(s)`).

1. **RAM range corrected.** The pre-run audit previously wrote
   "23,196–23,198 MiB", which was the first-to-last spread rather than the
   observed range. `pre-run-probe.json` records 23,196.00, 23,198.15 and
   23,192.98 MiB, so the range is **23,193–23,198 MiB** and the exact readings
   are now given. No measured value changed; only the summary of them.
2. **Host-local absolute paths relabelled.** Eight committed files had
   absolute path strings beginning at the operator's home directory were replaced with the labels documented above
   (`<VENV_ROOT>`, `<FETCH_DESTINATION>`, `<HF_CACHE_ROOT>`, `<SCRATCH_ROOT>`,
   and the repository-relative `results/R02/r02-smoke-001/...`). The strings
   changed were identifiers of *where files live*, never a digest, a byte count,
   a timestamp, a status, or any other measured value. Identifiers kept their
   discriminating parts — every blob target still names its full content-addressed
   hash and every snapshot path still names the pinned revision — so each
   artifact stays identifiable without publishing the operator's filesystem
   layout. The ignored `raw/` logs and the local files were **not** altered.
3. **Authorization wording clarified.** The three scoped records now carry
   `procedure_reviewer_only: true` and the `reference` "PR #19 review #43
   procedure approval; operator go recorded separately"; see the Authorization
   section above. `vesper` approved the procedure; `cassie`'s separate operator
   go authorized this run, and no part of this record should be read as `vesper`
   authorizing execution.

One artifact is intentionally **not** rewritten: `manifest.json` was written by
the run itself, and its embedded `authorization` block is the snapshot of the
records as they read when the gate consumed them. Only its
`plan.artifact_manifest_path` was relabelled (item 2). The current wording of the
authorization records — the three files this section describes — is the authority,
and the difference between them is exactly the wording clarification above, not
a change of gate inputs: `granted`, `scope`, `reference`, `approved_by` and
`approved_at_utc` were unchanged by it.
