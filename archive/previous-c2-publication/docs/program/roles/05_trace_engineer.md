# Role 5 — Trace Engineer

## Mission

Evolve Trace into the governed production architecture that safely absorbs
mechanisms which have earned promotion.

## Primary outputs

- Cortex Release migrations and lifecycle implementation,
- active-read and candidate-write isolation,
- temporal Spine and typed-relation design/implementation,
- retrieval-controller integration points,
- recovery, policy, and rollback test evidence.

## Initial work horizon

1. Make Cortex Releases an explicit candidate -> validate -> activate ->
   rollback primitive.
2. Ensure all derived writes are revision scoped and normal reads resolve only
   through the active verified release.
3. Strengthen temporal truth: revisions, supersession, revocation, deletion,
   validity intervals, and as-of reads.
4. Separate structural, trusted evidence, soft-affinity, and behavioral edges.
5. Create a profiled, budgeted retrieval-controller framework.

## Boundaries

- Preserve Trace's event, version, policy, tenant, and recovery foundation.
- Adapt proven TL mechanisms to Trace contracts; do not copy TL's embedded
  runtime or database design.
- Keep factual promotion and query-time affinity separate.

## Prohibited actions

- Do not make candidate Cortex state visible before validation and activation.
- Do not make affinity or generated summaries canonical truth.
- Do not bypass policy, review, rollback, or operational verification for a
  retrieval win.

## Handoff standard

Return migrations, contract changes, exact tests, operational implications,
compatibility risks, and requests for promotion or design review.

## Current audit anchors

Packets should inspect the current Trace V2 implementation and its existing
dirty worktree carefully before changing it:

| Area | Current anchor to inspect | Why it matters |
| --- | --- | --- |
| Cortex lifecycle | src/trace/v2/cortex.py and repository interfaces. | Projection states, activation families, transitions. |
| Release evidence | src/trace/v2/release.py and production controls. | Measured gates versus declarative evidence. |
| Derived storage | repository, store, projections, organization, and migration modules. | Candidate scoping, snapshot/delta behavior, read paths. |
| Retrieval | src/trace/v2/retrieval.py. | Active Cortex selection, controller hooks, evidence output. |
| Contracts | docs/v2-architecture.md, docs/schemas.md, API/service models. | Existing version, evidence, policy, and compatibility semantics. |
| Tests | v2 cortex/release/production control tests. | Current invariants and required regression coverage. |

Because Trace may contain user-owned in-progress changes, a packet must pin a
base commit/worktree and name any overlapping paths before editing.

## Implementation sequence

### A. Cortex Release primitive

Define the release family, state transitions, source snapshot identity,
candidate objects, validation record, active pointer, supersession, retention,
and rollback operation. Treat a release as a validated bundle, not a collection
of independently mutable tables.

### B. Writer and reader isolation

Every derived writer records a candidate release identity. Every ordinary
retrieval path resolves a verified active release before using hierarchy,
affinity, vector, lexical, or controller objects. Backfill/legacy paths are
explicitly labeled and cannot masquerade as an active candidate.

### C. Validation and recovery

Require structural, provenance, policy, quality, and evaluator validation
appropriate to each projection kind. Test interrupted build, invalid object,
failed activation, rollback, replay, and source-snapshot mismatch paths.

### D. Temporal and typed semantics

Extend the Spine/contract deliberately for source versions, effective and
ingestion time, supersession, revocation, deletion/tombstone, and as-of
queries. Keep trusted evidence relations distinct from affinity and behavior.

### E. Retrieval-controller integration

Implement generic profiles and budgets before embedding a particular TL
mechanism. A promoted mechanism plugs into a typed release family and records
its work, evidence contribution, and fallback/abstention behavior.

## Required test categories

- candidate object invisibility before activation;
- active pointer atomicity and prior-release rollback;
- workspace/tenant and policy isolation;
- source snapshot/replay parity;
- temporal/as-of, supersession, revoked, and deleted visibility;
- typed-relation provenance and affinity non-authority;
- bounded activation work and query evidence;
- API/schema compatibility and observability;
- migration forward/backward or retained-data behavior.

## Completion boundary

The Trace engineer may deliver a migration/implementation candidate. Promotion
requires independent verification, a reviewed release-evidence report, and
human acceptance. A feature that passes embedded tests but has no external
database, queue, policy, or recovery evidence remains locally verified only.
