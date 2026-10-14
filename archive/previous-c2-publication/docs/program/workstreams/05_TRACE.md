# Workstream 05 — Trace V2 Governed Production Foundation

> **Owner:** Trace engineer
> **Status:** Draft outline

## Intended outcome

Give Trace a Cortex lifecycle and temporal/policy foundation that can absorb
proven retrieval mechanisms without allowing derived state to corrupt
evented, source-grounded truth.

## First work packages

1. Verify the current projection-control plane and identify any candidate
   affinity or other derived state visible before activation.
2. Define/complete Cortex Release storage, build metadata, candidate isolation,
   validation, active pointers, retention, and rollback.
3. Ensure all normal reads use active release identity and all derived writes
   are candidate/revision scoped.
4. Advance temporal truth: version chain, supersession, source validity,
   as-of reads, revocation, and deletion/tombstones.
5. Define typed bounded activation and a retrieval-controller framework ready
   for promoted mechanisms.

## Required inputs

- shared contracts and invariants,
- current Trace V2 docs/code/migrations,
- promotion dossier or a generic integration-point packet,
- fixed operational and policy acceptance criteria.

## Expected artifacts

- architecture/migration note,
- isolated implementation and tests,
- replay/activation/rollback proof,
- compatibility and operational-impact report,
- request for independent verification.

## Exit condition

Trace can safely receive an approved mechanism and prove it within its own
release, policy, recovery, and scale boundary.

## Stop conditions

Stop for human review if a design weakens event/version history, policy/RLS,
review-gated facts, source anchors, or rollback behavior.

## Work-package decomposition

### TR1 — Current projection-control audit

Trace the current projection-run APIs, state transitions, derived object
storage, affinity writes, effective/active release lookup, and retrieval
selection. Identify where a candidate row could become query-visible before
complete validation and where legacy compatibility paths need an explicit
transition plan.

### TR2 — Cortex Release contract and migration

Define the exact release aggregate:

- projection family and workspace scope;
- source snapshot/watermark and policy snapshot;
- algorithm/model/configuration fingerprints;
- candidate objects/memberships/edges;
- validation record and evaluator-manifest reference;
- active pointer, supersession, retention, and rollback.

Create a migration and test plan before writing data-plane code. The migration
must be additive and compatible with existing user-owned in-progress changes.

### TR3 — Atomic activation and read isolation

Implement the write/validate/activate sequence so ordinary retrieval sees one
valid release identity. Candidate graph, hierarchy, affinity, and controller
objects cannot be read merely because they were inserted successfully.

### TR4 — Temporal truth and trusted relations

Choose a staged temporal contract. It should make source version/lineage,
effective versus ingestion time, supersession, revocation, deletion/tombstone,
and as-of visibility explicit. Trusted semantic relations need anchors,
provenance, review/policy state, and version behavior.

### TR5 — Typed bounded activation/controller

Define controller profiles and relation families. Structural, trusted evidence,
soft affinity, and behavioral signals receive separate provenance, trust,
degree/work, and decay/revision rules. Mechanism-specific PPR or hierarchy work
enters only through this controller after promotion review.

### TR6 — Production and compatibility proof

Add tests/reports for replay, idempotency, policy/RLS, schema/API compatibility,
outbox/queue behavior where configured, invalid release, rollback, observability,
and external adapter/deployment assumptions.

## Trace release acceptance matrix

| Requirement | Evidence |
| --- | --- |
| Candidate invisibility | Normal retrieval cannot see candidate IDs before activation. |
| Atomic handover | Every related projection family changes active identity coherently. |
| Prior release retention | Failed activation/query uses prior verified state where policy allows. |
| Source anchoring | Result evidence maps to immutable source/version anchors. |
| Policy correctness | Workspace/tenant/redaction/deletion behavior is tested. |
| Temporal correctness | As-of/supersession/revocation semantics are explicit and fixture-tested. |
| Bounded work | Controller captures and respects per-profile resource budgets. |
| Recovery | Replay, restart, and rollback preserve stated invariants. |

## Trace workstream exit

The workstream does not exit when a migration exists or embedded tests pass.
It exits a packet only when the verifier can reproduce the release behavior
under the packet's infrastructure and evidence boundary.
