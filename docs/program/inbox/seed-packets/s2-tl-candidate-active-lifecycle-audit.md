# Prepared Packet: S2 Trace-Lite — Candidate/Active Lifecycle Audit

> **State:** Prepared, unassigned
> **Role:** Trace-Lite engineer
> **DAG nodes:** TL1
> **Mutation authority:** Audit/documentation and targeted test proposal only.
> Do not change schema or runtime until this audit is independently reviewed.

## Objective

Map the exact current lifecycle of Trace-Lite source ingestion, pending work,
candidate derived builds, active build activation, tree/vector/graph state,
validation, query reads, and cleanup. Identify whether any derived state can
become visible, stale, or inconsistent outside a verified active-build boundary.

## Required inputs

- Charter, invariants, shared contracts, evaluation protocol, risk register.
- Trace-Lite Beta workstream and local context map.
- Current local anchors: source store, db lifecycle methods, graph generation,
  vector store, query/status paths, relevant tests.
- The evaluation integrity audit if available; otherwise mark related
  assumptions unresolved.

## Audit procedure

1. Trace source capture through pending-state recording.
2. Trace organization/consolidation/reindex paths through candidate creation.
3. Record tree/node, vector collection, graph edge, index-build, and manifest
   writes in chronological order.
4. Identify transaction/handover boundaries and failure windows.
5. Trace normal query behavior, explicit force/hot-inbox behavior, health and
   status reporting.
6. Trace successful/failing cleanup and retention behavior.
7. Inspect graph generation for frequency/degree/all-pair growth risks.

## Required output

- lifecycle sequence diagram;
- read/write matrix keyed by source, candidate build, active build, graph,
  vector, and query state;
- current code/symbol anchors;
- observed risks ranked by invariant impact;
- proposed test matrix for candidate leakage, stale edge, failed build,
  interruption, and high-frequency graph cases;
- a narrowly scoped design question for any required schema/activation change.

## Acceptance criteria

- No implementation is mixed into the audit.
- Every finding is marked observed, inferred, or unresolved.
- The audit identifies the previous verified state and how to compare it after
  failure.
- The audit preserves existing CLI/web behavior as a compatibility concern.
- The result gives the coordinator enough detail to create a safe TL lifecycle
  implementation packet.

## Stop conditions

Stop if a necessary fix requires destructive database migration, changes a
canonical source contract, or overlaps unrelated user-owned modifications.

## Handoff

Return audit artifacts and a recommended next packet: design, implementation,
test-only, or defer.
