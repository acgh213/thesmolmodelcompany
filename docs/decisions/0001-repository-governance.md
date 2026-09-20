# 0001 — Repository governance, visibility, and named research roles

Date: 2026-09-20. Decided by: Cassie. Status: accepted.

## Context

The written research design (PR #1) assigns separation of duties: the proposer of
an experiment must not unilaterally control the scorer or final split that judges
it. That rule was stated in prose with no mechanism behind it.

While preparing the repository we established two facts:

1. `GET /repos/acgh213/thesmolmodelcompany/branches/main/protection` returned
   **HTTP 403 — "Upgrade to GitHub Pro or make this repository public to enable
   this feature."** On a private repository under the free plan there is no
   branch protection, no required review, and no enforced code-owner review.
   Every agent with write access could push directly to `main`.
2. The roles in `agents/README.md` were still the labels *Research A* and
   *Research B*, which cannot be mapped to a reviewer or a code owner.

## Decision

**Visibility.** The repository is public. This enables branch protection at no
cost, and the documents were already written for an outside reader.

**Branch protection on `main`.** Direct pushes are blocked. Changes arrive by
pull request with at least one approving review, the `documentation integrity`
status check passing on the exact head commit, conversation resolution required,
stale approvals dismissed on new commits, and force-push and deletion disabled.
These rules apply to administrators as well.

**Role assignment.**

| Role | Agent | Scope |
|---|---|---|
| Eido | Eido | Compute execution, host audits, resource measurement, reproduction |
| Research A | Vesper | Mechanisms and architecture track; E02; checkpoint source audits |
| Research B | Pyrrha | Evaluation harness, generators, scorers, splits; E01 and E03 |

The responsibilities attached to each role are unchanged from
`agents/README.md`; only the names are now bound.

## Consequences

- Separation of duties is now partly mechanical: a researcher cannot merge a
  change to the shared evaluation contract without another account approving it.
- It is still **not** a security boundary. All three agents hold write access and
  act under Cassie's GitHub identity, so a determined actor could bypass review
  by changing settings. Held-out evaluation data is protocol-controlled, not
  technically sealed, exactly as `docs/coordination.md` states.
- The repository is public from the design stage forward. Nothing secret may be
  committed. Credentials, tokens, and private host details stay out of the tree.
- Research work is visible before it is validated. Every claim must carry its
  claim level so a reader cannot mistake a proposal for a result.

## What this does not authorize

No paid compute, no rental provisioning, no model downloads, no training runs,
and no change to the research question or evaluation protocol. Those remain
governed by `docs/compute.md` and the backlog.
