# S2 — Trace-Lite Lifecycle Owner

## Mission

Repair and prove Trace-Lite's candidate/active projection lifecycle while
preserving the immutable Spine and the Beta runtime. The first implementation
is L1 candidate/active isolation. TL3 then measures provenance, crash/rebuild,
and incremental/full parity. TL2 graph-bound work begins only after P-002.

## Base and worktree

Use a clean isolated worktree from:

```text
fe66a9eefc8372f7cc021c864d26e62a9d6cc9c1
```

Do not mutate the Trace-Lite user checkout or its existing planning files.
Use a fresh task database and external scratch directory outside OneDrive.

Initial L1 allowed product/test areas are limited to the lifecycle surfaces
identified by F0c, such as the Cortex manifest/forest/vector/database/lattice
modules and lifecycle tests. The packet must list exact paths before editing.
Do not edit Spine modules or `engines/graph.py` during L1.

## L1 lifecycle objectives

Make every derived component resolve through one candidate/active build identity
or an explicitly documented component membership record. At minimum:

- candidate trees/nodes are invisible to normal reads;
- vector/index candidates are isolated from active aliases;
- graph rows cannot leak from a candidate or partial build;
- manifests and index state agree on candidate/active status;
- activation validates integrity, topology, provenance, and source coverage;
- failed or interrupted builds leave the prior active build readable;
- activation keeps a predecessor sufficient for pointer rollback;
- a restarted process can resume, abandon, or safely recover a candidate;
- concurrent source arrival cannot make a partial build look current.

Preserve compatibility with existing Beta APIs where possible. If an additive
schema or manifest field is required, record its migration and replay behavior.
Do not destructively delete the only known-good projection as part of a normal
activation test.

## L1 tests

Test at least:

1. candidate build is absent from normal reads;
2. validation failure does not move the active pointer;
3. crash before, during, and after activation leaves a deterministic state;
4. pointer rollback restores the predecessor without global rebuild;
5. stale graph rows are not visible after a replacement;
6. candidate and active vector/lexical identities cannot cross;
7. invalid/orphan/missing-provenance rows block activation;
8. replay/restart is idempotent;
9. concurrent ingestion is either included under a declared watermark or
   remains pending for the next build;
10. a full rebuild and incremental build produce equivalent source coverage and
    active-read results.

Tests must capture build IDs, active IDs, source watermark, read visibility,
and rollback target. Do not report graph scalability or PPR quality from L1.

## TL3 provenance/rebuild proof

After L1 is stable, measure and document:

- exact source atom coverage and orphan count;
- offsets/hashes preserved through organization and retrieval;
- crash/replay and idempotent ingestion behavior;
- incremental/full rebuild parity;
- clean-install and external-scratch behavior;
- build time, memory, disk, and latency by query class where available.

TL3 may fix adjacent provenance/recovery defects only when they are in its
approved packet scope. It must not turn the internal 320-case fixture into an
external claim.

## P-002 and TL2 boundary

Use TL3 measurements to prepare a decision brief for:

- common-term admission/skip policy;
- maximum term frequency ratio or document frequency;
- per-node/per-term degree cap;
- deterministic neighbor selection;
- PPR node/edge/depth/work budgets;
- memory and latency budgets;
- overflow and observability behavior.

Do not choose or implement those values before P-002 is recorded. TL2 will
implement the accepted bounded graph policy, add adversarial high-DF tests,
and prove no degree explosion.

## Subagents

Use one lifecycle test designer and one source-anchor/provenance reviewer.
They may work read-only or in disjoint test files. Only the primary L1 owner
changes lifecycle code/schema. No helper edits the Spine or graph algorithm.

## Required handoff

Include base/worktree identity, allowed/forbidden paths, schema changes,
candidate/active state model, crash points exercised, test commands/results,
rebuild/parity evidence, unresolved P-002 questions, and explicit claim limits.

## Stop conditions

Stop if the base is dirty, the packet lacks a verifier, a candidate remains
read-visible, activation would destroy the sole predecessor, an additive
migration cannot be distinguished from deployed history, or a requested graph
change requires P-002.
