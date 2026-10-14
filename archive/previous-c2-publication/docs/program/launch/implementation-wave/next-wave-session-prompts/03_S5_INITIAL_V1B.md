# Session 3 - S5 Initial V1b Lifecycle and Release Verification

Read the shared bootstrap prompt first, then the L1 and TR1 handoffs and the
V1b packet. You are an independent verifier: never repair code, alter tests,
or use implementation-owned databases, caches, or result paths.

## Mission

Independently verify only the sub-gates presently ready:

- V1b-TL lifecycle at the frozen L1 commit;
- V1b-Trace release lifecycle at the frozen TR1 commit.

## Direction

- Create fresh verifier worktrees and separate scratch roots for Trace-Lite
  and Trace.
- Capture source, dependency, database, and environment identities before
  running tests.
- Attack candidate visibility, interrupted build/recovery, validation failure,
  atomic activation, predecessor retention, rollback, stale derived state,
  replay/idempotency, workspace isolation, and external-promotion failure.
- Inspect observable read paths as well as table contents.
- Report SQLite/local proof separately from PostgreSQL/RLS, external-index, or
  deployment claims that could not be independently exercised.

## Explicit exclusions

Do not certify graph budgets, PPR caps, valid-time, revocation, erasure, or
full historical semantics. Those remain blocked on P-002/TL2 and P-004/TR2.

## Suggested subagents

Use two isolated verifier helpers: one for Trace-Lite lifecycle and one for
Trace release lifecycle. They must use distinct worktrees/scratch roots and
return raw receipts; you reconcile them without editing either implementation.

## Exit

Write one V1b handoff with separately labeled sub-gate results, exact commands,
source identities, limitations, and accept/reject/blocked recommendations.

## Fault matrix

At minimum, build an independent matrix covering:

- crash before candidate writes;
- crash after partial hierarchy, affinity, prior, vector, or graph writes;
- validation failure and attempted activation;
- restart and replay after interruption;
- source arrival during a build;
- stale candidate and stale graph rows;
- pointer handover and predecessor rollback;
- cross-workspace candidate access;
- external index promotion failure and compensation;
- evidence bundle/release identity on ordinary reads.

Where a fault cannot be injected honestly in the available environment, record
the missing capability and the exact claim it prevents. Do not call a mocked
exception an infrastructure recovery proof.

## Separate verifier work

The Trace-Lite verifier should start from the exact L1 worktree commit and
independent local stores/vector directories. Inspect query selectors and
returned evidence, not only row counts. The Trace verifier should start from
the exact TR1 commit and test the release root, component membership, atomic
pointer, rollback, workspace, and alias-compensation behavior. If PostgreSQL,
RLS, or an external index is unavailable, preserve the local contract result
but mark the deployment claim unverified.

Each verifier subagent returns its own source manifest, command log, raw
receipts, result inventory, and limitations. The S5 owner must reconcile
conflicts without editing the candidates.

## Required handoff evidence

Include predecessor/candidate/successor release or build IDs, source and
projection hashes, active-read observations, restart/fault timing where
measured, database/runtime versions, cleanup status, and unsupported
environments. State explicitly that P-002 graph budgets and P-004 temporal
semantics were not closed by this session.
