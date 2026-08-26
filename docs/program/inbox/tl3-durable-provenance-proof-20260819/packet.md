# TL3 - Durable Memory, Provenance, and Rebuild Proof

> **Role:** Trace-Lite engineer; independent verifier
>
> **DAG node:** L3 / TL3
>
> **State:** Blocked until L1 is independently verified and a prepared clean
> worktree packet identifies exact persistence paths.

## 1. Objective

Prove the supported Trace-Lite local baseline preserves immutable source
evidence while derived Cortex structures can be rebuilt without changing source
truth. Establish evidence for the durable-memory and self-organization portions
of the Foundation contract, not a 100K certification claim.

## 2. Scope

- ingestion idempotency and crash/restart semantics;
- source artifact/atom coverage, exact offsets, content hashes;
- hot inbox/unorganized fail-closed behavior and explicit override path;
- rebuild equivalence from the same source/Spine state;
- incremental versus full organization/projection parity;
- candidate/active release identity in evidence bundles;
- topology/orphan/provenance checks at supported local scale.

## 3. Required evidence model

For each test retain:

1. immutable source snapshot/hash manifest;
2. ingestion operation identifiers and retry sequence;
3. atom/source coverage/offset/hash report;
4. active and predecessor projection identities;
5. rebuild input/config/model fingerprints;
6. comparison rule and allowed nondeterminism statement;
7. normal query evidence samples;
8. crash/failure/recovery observations;
9. independent verifier result.

Do not call two runs equivalent merely because their summary text looks
similar. Compare source coverage, anchor/hash integrity, required topology,
release identity, and retrieval output under frozen query fixtures.

## 4. Acceptance matrix

| Case | Required outcome |
| --- | --- |
| Duplicate ingestion | Same source/event/atom identity or explicit idempotent receipt; no duplicate truth. |
| Restart during ingest | Replay/retry result matches declared durable boundary. |
| Restart during candidate projection build | Prior active release remains readable; candidate is non-queryable. |
| Source hash/offset audit | Every returned evidence anchor resolves exactly or result fails closed. |
| Full rebuild | Rebuild consumes same source snapshot and passes declared equivalence. |
| Incremental update | Result matches full rebuild within frozen declared parity policy. |
| Unorganized capture | Normal trusted retrieval fails closed unless explicit permitted override. |
| Missing/corrupt derived state | Source truth remains recoverable; query returns pending/unavailable/untrusted according to contract. |
| Rollback | Prior verified projection is selected without modifying source evidence. |

## 5. Out of scope

- public benchmark superiority;
- real 100K certification;
- graph parameter policy beyond already accepted TL2;
- authoritative fact extraction;
- provider/model comparison unless separately frozen.

## 6. Required artifacts

- source and projection manifest schemas;
- fixed fault/replay harness plan;
- coverage/topology/provenance report;
- incremental/full comparison report;
- representative evidence bundles;
- unsupported/determinism limitation record;
- V1b report and capability-matrix update.
