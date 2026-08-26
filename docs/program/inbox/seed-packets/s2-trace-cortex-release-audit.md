# Prepared Packet: S2 Trace — Cortex Release and Active-Read Audit

> **State:** Prepared, unassigned
> **Role:** Trace engineer
> **DAG nodes:** TR1
> **Mutation authority:** Audit/design artifacts only. Do not modify the
> current dirty Trace worktree or migration state during this packet.

## Objective

Map the current Trace V2 projection-control plane and determine the exact
candidate/active release boundary required to prevent derived hierarchy,
affinity, vector, lexical, or controller state from becoming retrieval-visible
before validation and atomic activation.

## Required inputs

- Charter, invariants, contracts, DAG, promotion rubric, decision P-003, risks.
- Trace V2 architecture, schemas, production runbook, current V2 source and
  tests.
- Current dirty-worktree inventory and any relevant user-owned changes.
- Research memo if available; otherwise explicitly separate local audit from
  unresolved architecture choices.

## Audit procedure

1. Map projection-run states, repository interfaces, persistence tables, and
   active/effective release lookup.
2. Trace each derived writer and reader, including affinity/hierarchy/retrieval
   code paths and legacy compatibility behavior.
3. Identify source snapshot, policy snapshot, algorithm/configuration, and
   validation metadata already present or missing.
4. Locate activation, supersession, retention, rollback, replay, and error
   paths.
5. Identify test coverage for candidate invisibility, active pointer behavior,
   invalid build, restart/replay, policy/RLS, and migration compatibility.

## Required output

- current projection-control diagram;
- candidate/active read-write matrix;
- observed leakage/mixed-revision/rollback risks with code anchors;
- minimum Cortex Release data contract and state transition proposal;
- migration/backfill compatibility questions;
- fixed test/fault matrix for the next implementation packet.

## Acceptance criteria

- Existing dirty files are read-only and acknowledged as user-owned.
- The audit separates current implemented behavior from desired architecture.
- Every proposed invariant has a reproducible verification path.
- The output is narrow enough for an additive, reviewable migration packet.

## Stop conditions

Stop if a safe design requires replacing the event/version/policy foundation,
changing tenant authority, destructive migration, or a decision on temporal
semantics not yet accepted.

## Handoff

Return an audit plus an implementation-ready Cortex Release packet outline.
