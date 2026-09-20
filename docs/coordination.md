# Coordination and evidence

## Minimal workflow

Propose an experiment → peer-review controls → establish a runnable recipe → reserve compute → pilot on development data → freeze the confirmatory protocol → run → independently check → record continue/revise/stop/transfer.

Use a task branch and PR per coherent change. Freeze the scorer/generator version in the run manifest. Shared evaluation changes require review by the other researcher and cannot retroactively replace scores under the old version.

## Initial queue

| Resource | Reservation | Status |
|---|---|---|
| Eido GPU | None | No experiment running for this project |
| Cloud | None | No spending authorized |
| Final evaluation | None | No dataset or sealed artifact generated yet |

Update reservations with owner, experiment/run ID, host, start time, maximum end time, checkpoint path, and release status. Keep one GPU owner at a time. Research agents can work on source audits and CPU tasks while Eido runs a candidate.

## Independent reproduction

"Independent" has a specific meaning here, because the weak form is easy to
produce by accident. A reproduction qualifies only when all of the following
hold:

- A different agent from the one that produced the original result runs it.
- The environment is rebuilt from the manifest — not reused. A rebuilt
  interpreter, dependency install, and fresh process. Reusing the original
  virtualenv, container layer, or warm caches is a rerun, not a reproduction.
- The command and configuration come from the manifest, not from the original
  agent's shell history or working tree.
- Model and data artifacts are re-fetched and hash-verified against the manifest
  rather than assumed present.
- The reproducing agent records its own resource measurements independently.

Same physical host is acceptable when GPU access is serialized and the software
environment is rebuilt; note it as a limitation. Anything weaker is labeled
**rerun (same environment)** and does not satisfy R07 or the promotion rule in
`evaluation.md`.

Report the outcome as agreement, agreement within a stated tolerance, or a
documented contradiction. A reproduction that fails to run is itself a result:
record it rather than retrying until it works and reporting only the success.

## Proposed artifact layout after implementation planning

- src/: task interfaces, adapters, scorer, resource recorder; create only what the first experiment needs.
- configs/: exact runnable recipes, each naming model and data revisions.
- manifests/: small versioned records pointing to large artifacts.
- results/<experiment>/<run-id>/: small summaries and manifests; large raw outputs reside in persistent artifact storage named by URI and hash.
- docs/decisions/: changes to protocols, models, budgets, and interpretations.

Large-artifact storage must be selected and its persistence checked before a run whose output cannot be faithfully reproduced cheaply. Do not rely on an agent's transient workspace as the only copy.

## Required run manifest

Experiment and run IDs; UTC start/end; owner; code commit and dirty-tree status; config hash; generator/scorer revisions; dataset and split hashes; model/tokenizer revisions and file hashes; environment identity; hardware; seeds; precision; context/output limits; batch size; training steps/tokens if applicable; recurrence/search/adaptation limits; elapsed time; peak VRAM/RAM; billed cost if any; artifact URIs/hashes; exit status; prior run ID if resumed.

Model weights include adapters; system artifacts include skill libraries and retrieval indexes. Report total stored and loaded footprints, not only active parameter count.

## Access to evaluation

Keep hidden answers outside candidate inputs. During development, final-evaluation answers and detailed errors are unavailable to candidate tuning. The first implementation plan must specify who holds the final split and how it is run. Shared repository access is not a security boundary; if access was broad, call the split a held-out protocol-controlled evaluation rather than technically sealed.

After final results influence development, the split is spent for confirmatory purposes. Preserve it for regression testing and generate or obtain a new final split for new claims.
