# Forgejo collaboration workflow

The canonical forge is
<https://durandal.exe.xyz/smolmodelco/thesmolmodelcompany>. GitHub is a public
mirror; see [decision 0003](decisions/0003-forgejo-canonical-collaboration.md).

## Accounts and roles

| Forgejo account | Team | Research role |
|---|---|---|
| `pyrrha` | `research-b` | Evaluation harness, generators, scorers, splits; E01 and E03 |
| `vesper` | `research-a` | Mechanisms, architecture, E02, checkpoint source audits |
| `eido` | `compute` | Compute execution, host audits, resource measurement, reproduction |

Account identity does not replace the protocol boundaries in
[coordination.md](coordination.md): a reviewer must still read the artifact,
verify the stated checks, and protect held-out evaluation answers.

## Normal change path

1. Claim or create the task in Forgejo Issues. One agent owns one primary task.
2. Branch from canonical `main` using `docs/`, `ci/`, `chore/`, `R01/`, or the
   relevant experiment ID as the prefix.
3. Make the coherent change. Never commit credentials, private host details,
   model weights, datasets, or raw prediction dumps.
4. Run `python3 scripts/check_docs.py`. For a recorded run also run
   `python3 scripts/build_results_ledger.py --check`.
5. Push the branch to Forgejo over HTTPS using a credential mechanism local to
   that agent. Do not embed a token in the remote URL or shell history.
6. Open a Forgejo pull request. Request review from a different role when the
   change affects shared evaluation, a scorer, a generator, a protocol, or a
   result interpretation.
7. Resolve review comments by addressing them, not merely to clear the gate.
   A stale approval is dismissed on each new commit.
8. Merge only after the distinct approval and the
   `checks / documentation integrity (pull_request)` status are both green.
9. Mirror the resulting canonical `main` to GitHub. Do not use a GitHub pull
   request as the approval or task record.

## HTTPS authentication

Forgejo's public endpoint currently supports HTTPS Git. Port 22 belongs to the
VM access service, so the advertised SSH URL is not a usable Git endpoint.

Use a host-scoped secure credential mechanism on the agent's own machine:

- Pyrrha: protected local credential helper backed by her private agent store.
- Vesper: a local browser/vault or in-memory credential cache after operator
  login; never plaintext `credential-store`.
- Eido: Git Credential Manager in the Windows credential store.

A credential grants only the account and repository permissions that agent
needs. Never send passwords or access tokens through issue text, commits,
chat, logs, or A2A.

## Mirror rule

`github` is a backup/public-mirror remote. Mirror only the canonical `main`
after the Forgejo PR is merged. If a mirror push is blocked, fix the mirror
through its own safe PR workflow; do not bypass Forgejo review or rewrite
canonical history to make the mirror convenient.
