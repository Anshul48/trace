# L1 / TL1 — Trace-Lite Candidate/Active Lifecycle Foundation

> **Role:** Trace-Lite engineer
> **State:** Queued — requires F0a/F0c review and a pinned TL worktree
> **DAG node:** L1 / TL1

## Objective

Ensure derived Trace-Lite projections are built as isolated candidates, fully
validated, atomically activated for ordinary reads, and rollbackable to the
previous verified active state.

## Broad scope

- map current projection lifecycle, build ownership, active selection, and
  query visibility;
- stage candidate derived state with a release/build identity;
- prevent candidate/partial/stale rows from ordinary reads;
- validate required source/provenance/topology integrity before activation;
- preserve prior verified state on failure and record rollback behavior.

## Explicit non-goals

- no new graph scoring strategy, bio-inspired mechanism, or PPR-budget policy;
- no Alpha runtime path;
- no evaluator, benchmark, Trace, data, or consumer integration rewrite;
- no destructive migration without a separately approved plan.

## Required inputs before preparation

- F0c TL repository record and protected dirty paths;
- F0a evaluation requirements relevant to release identity;
- exact code/test paths and compatibility constraints;
- independent verifier assignment and negative test outline.

## Acceptance outline

- failed build leaves the prior active projection readable;
- normal reads cannot select candidate rows;
- activation changes a single visible release identity;
- basic rollback/restart/provenance cases have reproducible evidence.

## Stop

## Detailed prepared-packet requirements

L1 begins with a current release/read-write map. Do not assume existing Beta
tests prove every projection is isolated.

### Required map

| Structure | Writer | Candidate identity | Active selector | Normal read filter | Validation | Failure | Retention/rollback |
| --- | --- | --- | --- | --- | --- | --- | --- |
| lexical index | current code | <...> | <...> | <...> | <...> | <...> | <...> |
| vector index | current code | <...> | <...> | <...> | <...> | <...> | <...> |
| hierarchy/tree | current code | <...> | <...> | <...> | <...> | <...> | <...> |
| graph/affinity | current code | <...> | <...> | <...> | <...> | <...> | <...> |
| summaries/routing | current code | <...> | <...> | <...> | <...> | <...> | <...> |

### Required lifecycle semantics

1. Pin source/Spine input identity.
2. Create candidate build/release identity before derived writes.
3. Build covered derived artifacts under candidate.
4. Validate structural, source/provenance, topology, active-read integrity.
5. Atomically replace one ordinary-read active identity after validation.
6. Retain prior verified identity for pointer rollback.
7. Crash/failure/validation failure/restart leave reads on predecessor and keep
   diagnostics.
8. Diagnostics/evidence bundles include active release/build identity.

### Acceptance cases

- failed build preserves prior active result;
- candidate cannot appear in ordinary query;
- partial build cannot erase predecessor;
- activation has one visible handover;
- restart/retry is idempotent or fails closed;
- rollback selects predecessor without mutating source;
- provenance hashes/offsets remain intact.

### Out of scope

L1 never selects term caps, edges per atom, PPR depth, degree, graph scoring,
or bio-inspired association. Those await P-002/TL2.

Keep graph degree/co-occurrence parameterization in L2. If lifecycle repair
requires a schema/data migration outside this packet, stop and request an
amendment.
