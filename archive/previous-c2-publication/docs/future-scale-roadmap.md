# Future Scale Roadmap

> Status: architectural direction and decision framework. This document does
> not claim that the current implementation has passed any scale gate, and it
> does not authorize distributed infrastructure, a language rewrite, or a
> production deployment by itself.

## Purpose

Trace is intended to become a headless, self-organizing memory database with a
durable evidence-preserving history and fast, accurate retrieval over very
large corpora. The central contract remains constant at every scale:

~~~text
Immutable Spine = canonical source truth, history, policy, and evidence
Rebuildable Cortex = versioned retrieval and organization projections
~~~

The roadmap separates the work needed to prove this contract at 100K and 1M
from the later work needed for a 10B-token active memory or trillion-token
archive. It prevents a premature distributed rewrite while ensuring current
interfaces do not make future scale impossible.

## Scope language

Token count alone is not a capacity specification. Every scale proposal must
state:

- raw source tokens, documents, attachments, and bytes;
- atom/chunk count and distribution of chunk sizes;
- active versus archival working set;
- ingest/update/delete rate;
- query concurrency, latency objective, and availability target;
- vector dimension/index type, lexical index shape, and graph budget;
- evidence/provenance, policy, retention, and historical-query requirements;
- storage, compute, provider, and operator-cost budget.

For orientation only, 10B source tokens can yield roughly 10M to 40M chunks
with average retrieval chunks of 1,024 to 256 tokens. Its operational cost is
therefore driven by corpus shape, indexing, updates, and QPS rather than the
headline token count alone.

## Non-negotiable invariants

At every scale:

1. Source bytes, atom offsets, hashes, revisions, events, and evidence anchors
   remain canonical and auditable.
2. Hierarchy, vectors, lexical indexes, graph edges, summaries, routing, and
   activation are rebuildable projections, never the sole source of fact.
3. Candidate projections remain invisible until validation and atomic
   activation; a previous validated release remains recoverable.
4. Every query can name the source revision, policy context, projection/release,
   and evidence used.
5. Retrieval is bounded. There is no unbounded graph traversal, all-pairs
   co-occurrence, global mutable cluster, or whole-corpus query expansion.
6. Privacy, revocation, authorization, and erasure behavior propagate through
   source stores, indexes, projections, queues, caches, and evidence bundles.
7. Scale or performance claims require fixed real-corpus protocols and
   independent verification.

## Scale stages and architectural changes

| Stage | Evidence target | Default architecture | Required change before advancing |
| --- | --- | --- | --- |
| Foundation to 100K | Correctness, provenance, candidate isolation, recovery, cost, real retrieval | Local-first service and embedded correctness adapters; external services only where evidence requires them | Eliminate full-rebuild assumptions and prove bounded work/replay |
| 1M | Incremental ingestion/rebuild economics, stable p95, operational state, failure recovery | One powerful machine or a small single-region deployment may still be appropriate | Projection jobs, checkpoints, manifests, outboxes, and indexes operate incrementally and reproducibly |
| 10M to 50M chunks | Partition-aware replay, storage, retrieval, and recovery | Multi-process or multi-node shard pilot in one region | Partitioned Spine metadata, tiered source storage, shard-aware projection jobs and query routing |
| About 10B source tokens | Fast governed retrieval with real update/concurrency needs | Distributed Cortex and likely partitioned Spine if single-node economics or recovery fail | Demonstrate bounded cross-shard retrieval, per-shard replay/rollback, policy propagation, and economic viability |
| 100B to trillion-scale archive | Tiered archival memory plus bounded active cognition | Sharded canonical/event metadata, object storage, distributed indexes, asynchronous projection fabric | Multi-region/disaster recovery, compaction, durable operations, and independently verified large-scale evidence |

The transition is evidence-driven. A static, low-QPS 10B-token archive may
fit a high-memory node or a small cluster; a rapidly updating, low-latency,
multi-tenant 10B-token system likely needs a distributed data plane earlier.

## What evolves at the shard-aware stage

### Spine and archival source layer

- Partition canonical streams by workspace, time, and stable source key; do
  not physically partition by mutable semantic clusters.
- Store large source segments and attachments in private object storage with
  content hashes, manifests, retention policy, and independent verification.
- Use per-partition sequencing, snapshots, replay watermarks, and durable
  outboxes rather than a single global writer or event counter.
- Make cross-partition import/merge explicit, versioned, and reviewable.

### Cortex and projection layer

- Scope every projection to a source/release watermark and partition identity.
- Build hierarchy, vector, lexical, and graph projections asynchronously per
  partition; propagate only validated outputs.
- Use sparse bounded adjacency and bounded expansion; never create a global
  pairwise graph.
- Support carried-forward, rebuildable components and atomic release handover
  per workspace/partition.

### Query and evidence layer

- Route a query to a bounded candidate shard set using metadata, lexical,
  vector, time, policy, and source-routing signals.
- Perform local recall before any cross-shard expansion, with explicit work,
  latency, and cost budgets.
- Return a single evidence bundle that records shard, source revision,
  projection/release, policy, and contribution information.
- Fail visibly when a historical or policy-safe result cannot be assembled;
  never silently substitute a current or weaker result.

### Control plane and operations

- Retain immutable run manifests, benchmark identities, and verifier receipts.
- Make backpressure, projection lag, orphan/stale rows, queue lag, shard
  imbalance, recovery time, and cost first-class telemetry.
- Test loss/retry/duplicate delivery, partial promotion, network partitions,
  replay, restore, policy changes, revocation, and capacity exhaustion.

## Language and low-level optimization policy

Python remains appropriate for the control plane, domain logic, experiment
orchestration, evaluator, policy composition, and reference implementation
while the data contracts and algorithms are still changing.

Do not perform a whole-system Rust or Go rewrite during Foundation, 100K, or
the early 1M work. Instead, design portable boundaries now:

- stable serialized source, event, projection, release, and evidence formats;
- versioned APIs and worker envelopes;
- golden fixtures and parity tests for any replacement implementation;
- explicit resource and tracing interfaces;
- narrow adapters around databases, object stores, lexical/vector engines, and
  queues.

Introduce a native component only after all of the following are true:

1. A real scale run identifies a repeatable hot path or operational bottleneck.
2. The algorithm, data format, and failure semantics are stable enough to test
   independently.
3. The path has a bounded input/output contract and a Python/reference parity
   suite.
4. The expected gain matters for the next accepted scale gate.
5. The new component can preserve the same provenance, policy, rollback, and
   observability contract.

Likely first Rust candidates are compact source/atom encoding, hashing,
ingestion transforms, projection serialization, bounded graph/PPR kernels,
and memory-sensitive batch workers. Go is a possible later fit for shard
routers, network-facing services, and durable high-concurrency workers, but
it is not a default second implementation. Existing mature systems should
carry storage/index/queue responsibilities before Trace reimplements them.

A language change cannot repair a global graph, a full-rebuild design, missing
partitioning, or an unclear evidence contract. Fix computational shape and
data topology first; optimize measured hot paths second.

## Decision triggers

Open a scale-architecture decision packet when one or more measured conditions
occur:

- bounded queries miss their p95/cost objective after algorithmic tuning;
- profiling shows CPU, GIL contention, allocation, serialization, or memory
  layout dominates a stable hot path;
- a single node cannot hold the active index/projection state with recovery
  headroom;
- replay, rebuild, rollback, or restore cannot meet the accepted recovery
  window;
- ingest/projection backlog grows faster than it can be safely drained;
- cross-workspace or cross-time retrieval requires uncontrolled fan-out;
- privacy/revocation/policy propagation cannot be verified across existing
  stores;
- a single failure domain violates the accepted availability or data-loss
  objective.

The response may be an algorithm fix, a data-layout change, an index choice, a
native kernel, a shard pilot, or a service boundary. It is not automatically a
distributed rewrite.

## Research and documentation loop

Architecture documents remain active constraints during Foundation and 100K
work. Deep research is used narrowly to resolve an active decision or observed
failure. After every accepted scale gate, run a documentation-and-research
review that:

1. compares observed behavior, cost, recovery, and retrieval quality with the
   current architecture;
2. records contradictions and removes unsupported assumptions;
3. proposes only the next bounded experiments or decision packets;
4. updates this roadmap and the architecture docs with evidence, not optimism.

Broader graph, hierarchy, bio-inspired association, routing, and model-tiering
research becomes a formal ablation program after the 100K baseline is
trustworthy. It must not change canonical truth or bypass fixed evaluation.

## Required pre-10B program

Before authorizing a 10B-token pilot, create a separate Scale Architecture
Decision Record with:

- exact workload and corpus model;
- 100K and 1M evidence references;
- capacity and cost model;
- partition/shard key and routing design;
- source/event/release/evidence contracts across shards;
- recovery, privacy, revocation, and audit model;
- native-component justification or explicit decision not to use one;
- fault-injection and independent-verifier plan;
- rollout, rollback, and kill criteria.

The 10B program begins only when the owner accepts that record. It is a new
architecture-and-evidence program, not an automatic continuation of 1M.
