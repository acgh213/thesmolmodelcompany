# 0003 — Forgejo is the canonical collaboration forge; GitHub is a public mirror

Date: 2026-09-20. Decided by: Cassie. Status: accepted.

## Context

Decision 0001 made the GitHub repository public so a free account could enforce
branch protection. That exposed a structural limitation: Pyrrha, Vesper, and
Eido all acted through Cassie's single GitHub account. A review could change a
document, but GitHub recorded it as a comment rather than a distinct approval.
Required approvals therefore had to remain zero.

Cassie operates Forgejo at `https://durandal.exe.xyz`. The instance supports
separate accounts, teams, pull-request approvals, branch protection, and
Forgejo Actions without paid seats. The organization `smolmodelco` and its
canonical repository `smolmodelco/thesmolmodelcompany` were created there.

## Decision

**Canonical forge.** All active issues, task claims, branches, pull requests,
reviews, and merges occur at:

<https://durandal.exe.xyz/smolmodelco/thesmolmodelcompany>

**Public mirror.** The existing GitHub repository remains public at:

<https://github.com/acgh213/thesmolmodelcompany>

It is a discoverability and read-only mirror of canonical `main`, not the task
queue or review surface. Do not open active work items or pull requests there.
Its historical issues and pull requests remain evidence for the work that
predated this decision.

**Identity and review.** Forgejo accounts `pyrrha`, `vesper`, and `eido` are
separate identities. They are organized into `research-b`, `research-a`, and
`compute` teams respectively. `main` rejects direct pushes and requires:

1. one approval from a different Forgejo identity;
2. a passing `checks / documentation integrity (pull_request)` status for the
   pull request head; and
3. dismissal of stale approvals after new commits, with rejected reviews
   blocking merge.

The direct-push and approval gates were exercised end to end: a Pyrrha push to
`main` was rejected; a Pyrrha PR could not merge before Vesper approved it; it
merged after that approval. The test content was subsequently reverted through
the same gated workflow.

**Credential boundary.** Agent credentials are per-account and scoped. They
are never committed, pasted into issues, or transmitted through agent chat.
The current public endpoint is HTTPS; its advertised SSH clone URL is not
usable because port 22 is reserved by the VM access service. Agents use HTTPS
with a local secure credential mechanism until that hosting configuration
changes.

## Consequences

- The reviewer identity is now mechanically distinct from the author identity.
  This makes the separation-of-duties rule enforceable for repository changes.
- CI has a real runner on the Forgejo host; the existing documentation check
  workflow runs there and has succeeded on canonical `main`.
- GitHub remains useful to outside readers without being trusted as the source
  of operational state.
- Decision 0001 remains historical evidence of the GitHub setup. This decision
  supersedes its statements about the active forge, required approval count,
  and shared identity.

## What this does not authorize

This changes collaboration and credential boundaries only. It does not
authorize model downloads, paid compute, training, experiment execution, or a
change to the research questions or evaluation protocol.
