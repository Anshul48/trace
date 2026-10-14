# S0 R1 - Control-Plane Reconciliation

> **State:** In progress
> **Role:** S0 Coordinator / sole cross-lane control-plane writer
> **Authority:** C0 administrative reconciliation only

## Execution note

This packet supersedes neither D0 nor any implementation or verifier packet.
It refreshes their live identities, separates implementation completion from
independent verification, and prepares the exact next sessions. The primary
source is `01_S0_R1_RECONCILIATION.md`; nearby launch documents are used only
to resolve its required fields and dependency rules.

## Objective

Reconcile the completed implementation wave into the honest program state:
`implementation_complete / independent_verification_pending`.

## Allowed paths

- `docs/program/FOUNDATION_STATUS.md`
- `docs/program/07_RISK_REGISTER.md`
- `docs/program/COMPONENT_REGISTRY.md`
- `docs/program/CONTROL_PLANE_LOCK.json`
- `docs/program/inbox/s0-r1-reconciliation-20260819/`

Read-only inspection is permitted for the named component roots, external
staging root, prior packets, and launch documents. No other path is mutable.

## Protected and forbidden paths

- Trace product source, migrations, tests, benchmarks, and the dirty user snapshot.
- Trace-Lite user checkout and its protected untracked program/benchmark paths.
- The trace-bench implementation checkout except for read-only identity inspection.
- Raw and verified external data under `C:\Users\anshu\AppData\Local\trace-bench-data\`.
- Provider configuration, credentials, databases, caches, and result directories.
- P-002, P-004, and P-005 decision authority.

## Inputs and expected outputs

The live identities, packet hashes, dependency classifications, and pre-write
control-plane snapshot are pinned in `input-manifest.json`. The packet will
produce a repository state record, task/risk reconciliation, source identity
manifest, downstream classification, fresh leases/assignments, command log,
and a complete handoff.

## Acceptance checks

- Every source identity is refreshed from the live root and reproducible.
- The untracked `trace-bench/uv.lock` is an explicit V1a blocker.
- V1b is split into TL lifecycle, Trace release, TL graph, and Trace temporal.
- Every next executable session has an owner, safe base, unique path, lease,
  hard dependency, claim level, safe default, and handoff destination.
- The original Trace and Trace-Lite checkouts and all raw data remain unchanged.
- P-002, P-004, and P-005 remain deferred.
- Post-write control-plane hashes and all packet artifact hashes are recorded.

## Stop conditions

Do not dispatch a session whose identity or dependency is unclear. Preserve
the last verified derived state and mark the affected session blocked. Do not
repair B1, L1, TR1, D2a, or any verifier packet in this session.

## Delegation

No subagents were used. S0 retains all control-plane decisions and reviews all
observations directly.
