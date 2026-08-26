# TR1 - Unified Trace Cortex Release Lifecycle

> **Role:** Trace engineer; independent verifier
>
> **DAG node:** T2 / TR1
>
> **State:** Blocked pending accepted P-003, T1 audit, clean Trace base, and
> prepared verifier plan. Temporal/revocation semantics are excluded.

## 1. Objective

Implement one validated, rollbackable Cortex Release boundary for Trace
derived projections. Normal reads resolve through exactly one active release
and cannot observe candidate affinity, activation priors, hierarchy, or index
state before validation/activation.

## 2. Design contract to implement after P-003

The expected logical resolution is:

~~~text
workspace -> active Cortex Release -> named immutable component revision -> derived rows
~~~

A release carries:

- release/workspace identity and optional parent predecessor;
- pinned Spine event/source watermark and source manifest;
- policy snapshot;
- code/config/model/index fingerprints;
- planned/building/validating/validated/active/retired/failed state;
- component memberships; newly built or validated carried-forward;
- structural/provenance/policy/parity/quality validation receipts;
- activation/retirement event identities;
- failure diagnostics and rollback eligibility.

The active pointer moves only after every required component is validated.

## 3. Required implementation sequence

1. Create additive forward-only release schema in supported adapters.
2. Create candidate release before derived writes.
3. Scope hierarchy, affinity, activation priors, and index-component metadata
   to candidate release.
4. Change affinity uniqueness so candidate same-pair row cannot overwrite
   predecessor active row.
5. Preserve predecessor component references and retention.
6. Persist validation receipts, not only in-process dictionaries.
7. Make normal reads join/select active release only.
8. Atomically hand over active pointer in database transaction.
9. For external index aliases, prepare/validate immutable revision, record old
   alias, compensate on failure, then advance active release only when coherent.
10. Implement pointer rollback to prior validated release.
11. Include release identity in evidence bundles, jobs, diagnostics, and admin
    inspection.
12. Leave legacy hierarchy paths bounded/read-only until separate transition
    packet; never delete user data as part of TR1.

## 4. Required failure semantics

| Failure | Required normal-read outcome |
| --- | --- |
| Candidate write crash | Predecessor active release remains selected. |
| Partial hierarchy/affinity/prior build | Candidate non-queryable; predecessor unmodified. |
| Validation failure | Candidate failed with receipt; no pointer change. |
| Policy snapshot stale/change | Candidate rejected/rebuilt; no policy-mismatched activation. |
| External alias activation failure | Pointer remains predecessor; compensation/receipt retained. |
| Restart/retry | Release state/retry idempotent; no duplicate active state. |
| Rollback | Pointer changes to preserved validated predecessor; Spine unchanged. |

## 5. Acceptance tests

Independently verify:

- candidate affinity/prior never affects ordinary query;
- candidate same-pair affinity cannot overwrite predecessor;
- build/validation/policy failure leaves predecessor unchanged;
- concurrent reads see complete predecessor or complete successor, never mixed;
- multi-tenant release selection remains isolated;
- release state survives restart/retry;
- rollback is pointer operation;
- evidence bundles report active release/component identity.

## 6. Explicit exclusions

TR1 does not choose valid-time, source revocation, deletion law/policy, or
historical read semantics; those are TR2 after P-004. It does not make affinity
factual or replace Trace Spine/event/policy architecture with TL storage.

## 7. Required artifacts

- accepted P-003 record; migration/schema plan;
- release/component/read-resolution design;
- clean worktree lease and implementation identity;
- validation receipt schema;
- external-index compensation plan;
- migration/rollback/legacy compatibility plan;
- test and fault logs;
- V1b verification and capability update.
