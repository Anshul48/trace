# S1 B1.1 — Benchmark Identity Refresh

```yaml
packet_id: "b1-1-benchmark-identity-20260819"
session: "S1"
role: "Benchmark Identity Owner"
status: "completed"
authority_level: "C1"
started_utc: "2026-08-20T02:19:30.6469566Z"
completed_utc: "2026-08-20T02:46:21.5523102Z"
worktree_path: "C:\\Users\\anshu\\AppData\\Local\\trace-worktrees\\trace-bench-b11-20260819"
worktree_lease_id: "lease-s1-b1-1-benchmark-identity-20260819"
base_commit: "0b01de5e49dcb18d43876b0b6004da58b35b72aa"
verifier_id: "v1a-runner-integrity-20260819"
```

## Objective

Resolve the untracked `uv.lock` and stale source-manifest coverage so V1a can
receive one clean, reproducible benchmark source/dependency identity. Preserve
historical B1 commit `0b01de5e...` and make only the lease-scoped identity
change.

## Current preflight discrepancy

The canonical checkout is at `0b01de5e49dcb18d43876b0b6004da58b35b72aa` with
only untracked `uv.lock` (`fd4bbc4107d965f570493afb2a425b0482363b126532d023744e0a7d46745c50`).
The assigned worktree path did not exist at preflight, so no source mutation
has begun. The exact leased worktree must be materialized from the pinned base
before implementation proceeds.

## Scope lock

Allowed mutable paths in the leased worktree:

- `uv.lock`
- `SOURCE_MANIFEST.json`
- `pyproject.toml`
- `README.md`
- `.gitignore`

Packet-local outputs are limited to this directory under
`docs/program/inbox/b1-1-benchmark-identity-20260819/`.

Forbidden paths include `src/`, `tests/`, `benchmarks/`, Trace, Trace-Lite,
raw data, providers, datasets, certification results, and all other program
control-plane files.

## Acceptance

- The chosen lock decision is recorded with lock hash, uv/Python/platform,
  package metadata identity, and source-manifest coverage.
- A superseding clean full commit exists without rewriting B1.
- A clean clone with no prior cache reproduces the declared dependency state
  from pinned inputs and runs the existing B1 suite without editable/product
  imports.
- The handoff records exact commands, counts, hashes, skipped/unavailable
  checks, clean Git status, V1a input manifest, and that no dataset/provider or
  certification run occurred.

## Stop conditions

Stop as blocked if the lock cannot be deterministically reproduced, the exact
lease cannot be materialized, package resolution requires an unapproved
fallback or insecure transport, or the B1 test suite cannot be run under the
declared clean environment.
