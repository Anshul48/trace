# V0 - Independent Verifier Plan and Packet-Integrity Review

> **Role:** Independent verifier
>
> **DAG node:** V0
>
> **Packet state:** Prepared for read-only work only
>
> **Evidence level on completion:** Observed planning/packet evidence, not
> runtime verification

## 1. Objective

Create the immutable independent-verification plan required before any
foundation implementation may be accepted. Review F0/B1/L1/T1 packet
completeness and define the negative cases, evidence format, and independence
conditions for V1a and V1b.

## 2. Current input boundary

Read:

1. Program Charter, Invariants, Shared Contracts, Evaluation Protocol, Decision
   Log, Risk Register, Foundation Release/Status, Gate Dossier, and Session
   Operating Manual.
2. Component Registry and all current F0/B1/L1/T1 packets.
3. Templates for verifier reports, error receipts, input manifests, repository
   state, worktree leases, evidence index, and capability matrix.
4. Current F0a/F0b/F0c handoffs only if they exist. They are evidence inputs,
   not automatically accepted claims.

Current known constraints:

- Trace-Lite and Trace user worktrees are protected/dirty snapshots.
- trace-bench is unversioned and cannot yield certifying evaluator evidence.
- observed evaluator fallback paths and Trace candidate isolation paths require
  independent runtime testing later.

## 3. Allowed work

- read documents/source/packets and inspect task-local artifact presence;
- build a verification matrix and packet-completeness report;
- create only files under this V0 task directory;
- identify missing prerequisites, impossible claims, and required infrastructure.

## 4. Forbidden work

- no product/benchmark source edit;
- no data download, provider call, certification execution, migration, or
  mutable worktree creation;
- no repair of a candidate implementation;
- no changing decision thresholds, evaluator policy, or source identity;
- no claim that a static source finding is independently reproduced.

## 5. Required artifacts

1. evidence/verifier-plan.md containing two separately frozen matrices:
   - V1a evaluator integrity matrix;
   - V1b TL/Trace lifecycle and temporal matrix.
2. evidence/packet-completeness.md covering F0a/F0b/F0c/B1/L1/T1:
   inputs, identity, scope, authority, test, verifier, handoff, and stop
   condition.
3. evidence/independence-requirements.md defining clean verifier worktree,
   environment capture, fixture ownership, and limits of fake/in-memory
   evidence.
4. input-manifest.json completed for this read-only packet.
5. repository-state.json for docs/program and any inspected component
   boundaries.
6. commands.md, handoff.md, and verification.md.

## 6. Required V1a matrix

For each case, define precondition, action, expected receipt/status,
certification eligibility, retained evidence, and exact future command:

- missing/unpinned evaluator source identity;
- mock provider selected/defaulted;
- synthetic dataset creation/substitution;
- forced or flat retrieval fallback;
- missing dataset/license/checksum/evidence mapping;
- indexing or query exception;
- empty retrieval result;
- metric attempt after failed stage;
- TLS validation failure/retry;
- result write failure.

The expected outcome is a blocked non-certifying receipt. It is never a score,
automatic abstention success, fallback result, or continuation with reduced
integrity.

## 7. Required V1b matrix

Plan separate cases for:

- crash before candidate writes;
- crash after partial hierarchy writes;
- crash after candidate affinity/activation-prior writes;
- validation failure;
- policy change during build;
- external component activation failure;
- restart/retry after interruption;
- source arrival during build;
- cross-workspace candidate access;
- pointer rollback;
- as_of_event release selection;
- valid-time/revocation behavior after TR2.

The plan must distinguish what can be tested in SQLite/in-memory, what needs a
disposable PostgreSQL/RLS environment, and what needs an external-index
adapter. Do not let a smaller test claim the larger infrastructure property.

## 8. Acceptance

V0 is complete only if it supplies a stable future verifier contract and
identifies exactly why current broad packets are not yet mutable. It is not
complete merely because every listed case sounds reasonable.

## 9. Stop conditions

Stop as blocked if a required component identity, source path, or packet is
missing; if verification would require direct edit of candidate; or if a
decision P-001 through P-008 must be assumed. Record the missing prerequisite.

## 10. Handoff disposition

Return one of:

- verifier plan complete; packets remain blocked pending named prerequisites;
- packet repair requested;
- source boundary insufficient for independent verification;
- deferred pending human decision.
