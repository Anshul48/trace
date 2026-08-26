# S3 — Trace V2 Cortex Release Owner

## Mission

Freeze the current dirty Trace V2 work into a reproducible isolated snapshot,
then implement the unified Cortex Release lifecycle. The lane must preserve
Trace's stronger event/version/policy architecture. Temporal and revocation
semantics are prepared after TR1 and implemented only after P-004.

## T0 — snapshot before implementation

The current Trace checkout is a protected user snapshot with tracked changes
and untracked V2 files. Do not edit, reset, clean, stash, or commit in that
original checkout.

Create a separately named worktree or snapshot branch from the current commit,
apply only the explicitly selected V2 tracked diff and selected V2 untracked
files listed by the packet, exclude `docs/program` control-plane files, and
commit the resulting implementation base. Record:

- original path/status and diff hash;
- selected file list and per-file hashes;
- excluded file list and reason;
- resulting snapshot commit;
- proof that the original dirty checkout is byte/status unchanged.

TR1 cannot start without this immutable base.

## TR1 — unified Cortex Release

Implement an additive, forward-only release-root design. Do not edit an
existing migration in place when deployment status is unknown. The design must
provide:

1. a release root tied to workspace and Spine event watermark;
2. immutable component membership for hierarchy, vectors, lexical indexes,
   affinity, priors, summaries, and routing metadata;
3. release-scoped derived rows, including affinity and activation priors;
4. candidate status that cannot satisfy active-read selectors;
5. validation receipts for integrity, topology, provenance, parity, and policy;
6. one atomic active-release pointer for relational components;
7. external index alias activation with explicit compensation/failure state;
8. retained predecessor release and pointer rollback;
9. release identity in query results/evidence bundles;
10. auditability of builder, configuration, model, source hashes, and manifest.

The implementation must close the observed leaks: affinity writes must not be
active during build, priors must not mutate global live state, and readers must
resolve rows through the selected active release rather than workspace-only
unique rows.

## TR1 validation and recovery

Test:

- candidate affinity and prior rows are invisible to production reads;
- two concurrent candidates cannot overwrite one active release;
- validation failure leaves the old release active;
- crash at each handover stage produces a recoverable state;
- rollback is a pointer operation to a validated predecessor;
- external vector/lexical activation failure triggers compensation or a clear
  unavailable state, never silent mixed-version reads;
- cross-workspace reads cannot resolve another workspace's release;
- replay and idempotent activation produce the same release state.

Use disposable databases and external scratch. Label SQLite/in-memory results
as local evidence; do not claim PostgreSQL/RLS or external-index production
proof without the required infrastructure.

## P-004 decision brief

After TR1, prepare a focused decision package covering:

- system/event time versus real-world valid/effective time;
- source validity intervals and supersession chains;
- contradiction and revision handling;
- revocation, tombstone, deletion, and retention semantics;
- historical Cortex release selection for `as_of_event`;
- authorization and policy at historical time;
- exact provenance after privacy redaction or erasure;
- behavior when a historical projection is unavailable.

Do not implement or claim a final temporal contract until P-004 is explicitly
accepted. Never silently use the current projection for an historical query.

## TR2 — conditional temporal implementation

Only after P-004, implement the accepted temporal/revocation contract with
additive migrations, as-of selectors, valid-time filters, revision/revocation
events, policy-aware evidence bundles, and negative tests. Preserve source hash
and offset guarantees or document the approved privacy exception explicitly.

## Subagents

Use one snapshot-integrity observer and one schema/migration reviewer. They may
inspect and test in isolated directories. Only S3 owns TR1 migration/code
changes. No helper may touch the original dirty checkout.

## Required handoff

Include T0 snapshot manifest, TR1 commit/migration identity, release schema and
state machine, active-read selectors, rollback/recovery tests, external-index
limits, P-004 decision brief, and the exact V1b input manifest.

## Stop conditions

Stop if the snapshot cannot be reproduced, an existing migration's deployment
state is unknown and an additive path is unavailable, candidate data remains
visible, rollback loses the predecessor, or a temporal/privacy choice is not
human-decided.
