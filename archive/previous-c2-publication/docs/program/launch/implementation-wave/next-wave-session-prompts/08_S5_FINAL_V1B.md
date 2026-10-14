# Session 8 - S5 Final V1b Graph and Temporal Verification

Read the shared bootstrap prompt first. Start only after TL2 and TR2 each have
immutable implementation handoffs and fresh verifier leases.

## Mission

Independently close, reject, or block the remaining V1b sub-gates:

- V1b-TL graph boundedness;
- V1b-Trace temporal/revocation conformance.

## Direction

- Use fresh verifier worktrees, environments, databases, and caches; do not
  reuse implementation or prior-verifier mutable state.
- Verify the actual P-002 bounds under adversarial high-DF and work-budget
  conditions, including observability and overflow behavior.
- Verify the actual P-004 contract for system/valid time, supersession,
  revocation, tombstones, erasure, policy, and historical query selection.
- Maintain independent results for graph and temporal sub-gates. A pass in one
  cannot cover the other.
- Do not repair code, change thresholds, or substitute a weaker environment.

## Suggested subagents

Use two isolated verifier helpers, one for each sub-gate. Require raw receipts,
source identities, and direct selector/behavior evidence from each.

## Exit

Produce a final V1b handoff that consolidates initial and final sub-gates while
preserving their separate claim boundaries and all unresolved infrastructure
limitations.

## Graph verification matrix

Use adversarial real or admitted fixtures to verify common-term filtering,
degree caps, deterministic neighbor selection, edge deduplication, graph
identity scoping, PPR node/edge/depth/work limits, timeout/cancellation,
overflow diagnostics, replay, incremental/full parity, and candidate
visibility. Inspect actual query behavior and resource telemetry; edge counts
alone do not prove bounded query work.

## Temporal verification matrix

Verify the accepted P-004 contract for event/system-time reconstruction,
valid-time filtering, revision/supersession, contradiction retention,
revocation, tombstones, privacy erasure, historical authorization, historical
release selection, missing historical projection, and evidence-bundle release
and source-revision identity. Confirm that current projections cannot silently
satisfy a historical query.

## Independence and result handling

Start from the exact post-TL2 and post-TR2 commits, not a developer checkout.
Use fresh databases, caches, migrations, and provider/index configuration.
Record separate result roots and manifests for graph and temporal sub-gates.
If a fault requires PostgreSQL, RLS, an external index, or deployment
infrastructure unavailable to the verifier, mark only that claim blocked.

An unexpected pass on a forbidden behavior is a verifier failure and must
produce a repair request. Do not modify candidate code, expected outcomes,
decision records, or thresholds while collecting evidence.

## Final handoff

Link initial lifecycle/release evidence to the final graph/temporal evidence,
show exact input identity for every sub-gate, summarize changed versus
unchanged invariants, and state whether the combined V1b result is accepted,
rejected, or blocked at each claim level.
