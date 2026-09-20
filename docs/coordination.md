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
