# S5 Initial V1b Execution Note

## Objective

Independently verify the executable V1b-TL lifecycle and V1b-Trace release
lifecycle sub-gates from clean verifier worktrees. Do not repair implementation
code, alter implementation tests, use implementation-owned stores, or exercise
the deferred graph/temporal sub-gates.

## Inputs

- TL implementation commit `7ff40dc46fe3d5e8eef31c485ed0337b8f71602d`.
- Trace implementation commit `454c5aed2200796ac9874e4fbe6e099bdb53f830`.
- Fresh leases `lease-s5-v1b-tl-lifecycle-20260819` and
  `lease-s5-v1b-trace-release-20260819`.
- Packet, S5 prompt, L1/TR1 handoffs, and R1 control-plane identities recorded
  in `input-manifest.json`.

## Allowed paths

- The two fresh verifier worktrees named by the leases, read-only with respect
  to implementation source and tests.
- The two fresh external scratch roots named by the leases.
- This packet directory for manifests, raw receipts, command logs, and the
  final handoff.

## Forbidden paths

- The Trace and Trace-Lite user checkouts.
- The L1 and TR1 implementation worktrees.
- Other packet directories, source code, migrations, implementation-owned
  databases, caches, and result paths.
- Network, provider calls, data downloads, graph-budget choices, and temporal
  policy choices.

## Acceptance checks

- Candidate/partial state is absent from ordinary reads.
- Validation failure does not advance the active pointer.
- Interrupted/replayed builds preserve a usable predecessor and do not create
  mixed release visibility.
- Source-arrival and stale-candidate behavior is observed where the local
  contract exposes it.
- Pointer rollback, workspace isolation, evidence/release identity, and the
  Trace external-promotion failure contract are independently exercised where
  the local environment supports them.
- Unsupported PostgreSQL/RLS, external-index, real crash, or deployment claims
  are explicitly marked blocked or unverified.

## Stop conditions

- Any source, commit, lease, or protected-path drift.
- Any need to mutate implementation code/tests or use implementation-owned
  state.
- A test depends on network, provider, synthetic fallback, or unavailable
  infrastructure.
- A local result is being generalized to PostgreSQL/RLS, external-index,
  distributed, graph, temporal, or certification claims.
