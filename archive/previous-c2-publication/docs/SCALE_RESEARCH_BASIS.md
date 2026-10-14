# Trace Scale Research Basis

> Research snapshot: 2026-08-20. This document records architectural evidence,
> not vendor selection. Recheck version-sensitive implementation details when an
> ADR is opened.

## 1. Research method

The scale plan uses primary or official sources for technical claims:

- standards and official format/database documentation for storage behavior;
- peer-reviewed or original research papers for algorithmic feasibility;
- official benchmark papers for evaluation methodology;
- current Trace, Trace-Lite, and Trace-Bench source for repository-specific
  conclusions.

A source can establish that a pattern or subcomponent is feasible. It cannot
establish that Trace has implemented it, that a vendor is the correct choice, or
that an end-to-end Trace gate has passed.

## 2. Evidence matrix

| Area | Primary/official source | Supported conclusion | Important limit | Trace consequence |
| --- | --- | --- | --- | --- |
| Relational partitioning | [PostgreSQL table partitioning](https://www.postgresql.org/docs/current/ddl-partitioning.html) | Partition pruning and subpartitioning can make large logical tables manageable | Unique/primary constraints on a partitioned table must include partition columns; one parent does not create free cross-partition uniqueness | Canonical event identity and logical order must be explicit; do not rely on one global identity column as the future protocol |
| Causal time | [Logical Physical Clocks](https://cse.buffalo.edu/~demirbas/publications/hlc.pdf) and [CockroachDB transaction-layer use](https://www.cockroachlabs.com/docs/stable/architecture/transaction-layer/) | HLC combines causal ordering with timestamps near wall time and is used in a production distributed database | Clock discipline, transaction semantics, and per-key/range consensus still matter; HLC is not a total-order log | Use per-partition sequence for replay, HLC/causal metadata for cross-partition context, and explicit release watermark vectors |
| Immutable snapshots/manifests | [Apache Iceberg specification](https://iceberg.apache.org/spec/) | Immutable files, manifest reuse, snapshot history, partition evolution, delete metadata, and atomic metadata replacement support large evolving datasets | Iceberg is an analytical table format, not automatically Trace's event, point-read, policy, or evidence database | Reuse the manifest/snapshot pattern; prototype a Trace-native segment contract before adopting any table format wholesale |
| Segment layout | [Apache Parquet file format](https://parquet.apache.org/docs/file-format/) | Column chunks, row groups, metadata, and sequential I/O provide an efficient portable segment substrate | Large row groups favor scans and may be poor for point lookup or tiny updates | Benchmark source/atom/event access patterns before choosing segment and row-group sizes |
| Segment security | [Parquet modular encryption](https://parquet.apache.org/docs/file-format/data-pages/encryption/) | Authenticated encryption can protect data/metadata at file or column granularity with external key metadata | Encryption is not erasure unless key scope, copies, backups, and threat model are controlled | Keep encryption/key references in manifests; treat cryptographic erasure as a separate accepted policy design |
| Row-level logical deletion | [Iceberg v3 deletion-vector specification](https://iceberg.apache.org/spec/) | Deletion vectors can make immutable data files logically mutable while retaining snapshot structure | Physical bytes and old snapshots remain until retention/collection; semantics are table-specific | Evaluate tombstone/delete-vector overlays for immediate visibility, then prove physical purge independently |
| Content addressing | [Git object model](https://git-scm.com/book/en/v2/Git-Internals-Git-Objects.html) | Content-addressed immutable objects plus small references give reproducibility and structural sharing | Git's object model is not designed for Trace query or retention workloads | Use content hashes for source/segment/fragment integrity and manifest composition, not Git as the storage engine |
| Stable physical placement | [Consistent Hashing with Bounded Loads](https://research.google/pubs/consistent-hashing-with-bounded-loads/) | Dynamic placement can limit movement while bounding load | Hash locality is not semantic query locality and skewed byte/QPS weights need workload-aware treatment | Separate canonical placement from semantic routing; evaluate weighted load and movement on real source distributions |
| Search-engine release switch | [OpenSearch alias API](https://docs.opensearch.org/latest/api-reference/alias/aliases-api/) | Multiple alias actions can atomically switch an engine-local read name | Atomicity is inside OpenSearch, not across vector, SQL, object, cache, and policy stores | External aliases sit beneath the Trace release-root commit and are validated by revision identity |
| Search-engine backups | [OpenSearch snapshot/restore](https://docs.opensearch.org/latest/tuning-your-cluster/availability-and-recovery/snapshots/snapshot-restore/) | Snapshots are incremental and useful for recovery/migration | They are not instantaneous perfect point-in-time views, and shards can be captured at different times | Record snapshot identities per projection and restore under a Trace manifest; never infer a global release from backup time |
| Vector sharding | [Qdrant distributed deployment](https://qdrant.tech/documentation/scaling/distributed_deployment/) | Distributed vector collections support shards, replicas, custom shard keys, movement, and snapshot/WAL transfer modes | Resharding can be expensive or deployment-specific; custom-shard point IDs are unique only within a shard key | Trace owns canonical point identity and placement mapping; index sharding remains disposable and versioned |
| Vector recovery | [Qdrant snapshots](https://qdrant.tech/documentation/operations/snapshots/) | Engine snapshots can move or restore collection state | Distributed snapshots are node-specific and collection aliases are not included | Build a projection recovery manifest over all needed shard snapshots and aliases |
| Vector compression | [Qdrant quantization](https://qdrant.tech/documentation/manage-data/quantization/) | Scalar, binary, and product quantization trade memory and speed against approximation error | Compression ratios do not guarantee acceptable recall on Trace data | Select precision only through fixed recall/latency/storage curves on admitted corpora |
| Billion-point disk ANN | [DiskANN](https://www.microsoft.com/en-us/research/?p=634449) | A billion-point ANN index can achieve high recall and low latency on SSD with limited RAM in the reported workload | Static vector benchmarks do not include Trace provenance, temporal policy, hierarchy, source revalidation, or update shape | Billion-scale vectors are feasible, but they are one projection lane rather than proof of the database |
| Hybrid memory/disk ANN | [SPANN](https://www.microsoft.com/en-us/research/?p=796310) | In-memory centroids plus disk postings and query-aware pruning can reduce memory/disk work at billion scale | Reported gains depend on datasets, hardware, target recall, and index build strategy | Coarse routing plus disk-resident local indexes is a credible option for `SCALE-006/007`, not a preselected architecture |
| Dynamic graph ANN | [FreshDiskANN](https://arxiv.org/abs/2105.09613) | Billion-point graph ANN can support concurrent inserts, deletes, and search without periodic total rebuild in the reported system | Algorithm behavior and maintenance cost must be reproduced for Trace's data and filtering | Compare fresh-tail plus compaction with dynamic ANN under real update/delete distributions |
| Incremental partition ANN | [SPFresh](https://www.microsoft.com/en-us/research/publication/spfresh-incremental-in-place-update-for-billion-scale-vector-search/) | Local boundary rebalancing can avoid global index rebuild and reduce update resources | It targets vector partitions, not source truth or Trace semantic hierarchy | Require update locality as a first-class metric and avoid global rebuild as the default freshness plan |
| Billion ANN evaluation | [NeurIPS 2021 BigANN results](https://proceedings.mlr.press/v176/simhadri22a.html) | Recall at a throughput threshold, plus cost/power-normalized tracks, is a credible vector-infrastructure evaluation pattern | BigANN does not test source ingestion, organization, evidence, policy, or temporal correctness | Maintain a separate ANN lane and forbid it from certifying end-to-end Trace |
| Heterogeneous retrieval | [BEIR](https://arxiv.org/abs/2104.08663) | Retrieval systems should be evaluated across diverse domains, with lexical baselines remaining important | BEIR is mostly static relevance retrieval and does not prove Trace's lifecycle contracts | Report per-dataset results and compare lexical, dense, reranked, hierarchy, and graph channels under equal protocols |
| Provenance-aware retrieval | [KILT](https://arxiv.org/abs/2009.02252) | Downstream task performance can be evaluated together with retrieved provenance against a common corpus snapshot | Wikipedia task mappings do not cover every private-corpus or operational condition | Use provenance metrics and common-corpus controls as one lane; retain exact Trace byte/hash evidence beyond KILT's page-level mapping |
| Long-term temporal memory | [LongMemEval](https://arxiv.org/abs/2410.10813) | Information extraction, multi-session reasoning, updates, temporal reasoning, and abstention are distinct memory abilities | It is a small conversational benchmark and not infrastructure-scale proof | Use as a diagnostic temporal/abstention lane, never as the 100K/1M/10B scale corpus |

## 3. Research-derived architecture conclusions

### 3.1 The manifest is the portable unit of truth and release

Immutable child objects plus a small atomically replaced root appear repeatedly
in mature versioned systems. For Trace this supports two related but distinct
roots:

- a Spine snapshot/partition manifest naming canonical source and event
  segments;
- a Cortex release root naming validated partition projection manifests over
  exact Spine watermarks.

This gives structural sharing, reproducible reads, rollback, and reachability-
based collection without requiring one distributed transaction across every
serving engine.

### 3.2 Global order should be paid for only where semantics require it

The sources support partitioned/range-local ordering and causal timestamps, not
the idea that every event in a trillion-token memory needs one serial counter.
Trace's normal correctness need is deterministic order within a source/logical
partition and a reproducible multi-partition release cut. Cross-partition atomic
operations should be explicit exceptions.

### 3.3 Semantic locality belongs in routing, not canonical placement

Stable hash/range placement limits data movement; semantic methods improve query
locality but drift when models and topics change. Trace therefore needs a stable
truth partition plus rebuildable semantic routing directories. The router's
recall must be measured against an exhaustive oracle sample.

### 3.4 Billion-point ANN is encouraging but not the main uncertainty

DiskANN, SPANN, FreshDiskANN, SPFresh, and BigANN make the vector subproblem
credible. Trace's harder unknowns are:

- preserving source/policy/release identity through sharding;
- bounding shard fan-out without missing evidence;
- incremental hierarchy and association work;
- current versus historical coverage;
- multi-store release activation and rollback;
- revocation and physical erasure;
- recovery and economics under real churn.

The scale program should use mature ANN systems and focus custom research on
these Trace-specific contracts.

### 3.5 Update locality is a gate metric, not an optimization detail

Incremental ANN research and immutable manifest formats both avoid repeatedly
rewriting the entire dataset. Trace must measure bytes, rows/fragments,
embeddings, summaries, graph edges, model tokens, and wall time touched per
changed source/atom. A system whose update amplification grows with total corpus
size has not earned the next scale gate.

### 3.6 Engine snapshots cannot define a cross-engine release

Search/vector snapshots and aliases are useful recovery and serving mechanisms,
but their scope and timing differ. Trace needs its own immutable release root,
per-engine revision identities, validator receipts, and restoration procedure.

### 3.7 Evaluation must decompose claims

Retrieval relevance, provenance, vector infrastructure, temporal behavior,
organization, operations, and archive integrity require different protocols.
No single benchmark establishes the full self-organizing database claim.
Trace-Bench must bind them under common artifact identities while reporting each
lane separately.

## 4. Questions research has not answered

These require Trace-specific experiments and human decisions:

1. What logical partition key best balances source locality, policy, update
   isolation, and skew for the admitted workload?
2. Should atom/event segments use Parquet, Arrow IPC, Avro, a custom packed
   format, or different formats by access path?
3. What is the smallest strongly consistent control-plane scope: per workspace,
   tenant, region, or release family?
4. Should current and historical retrieval use separate physical indexes,
   selective archival indexes, or query-time segment refinement?
5. Which vector engine/index/precision wins on Trace data after filtering,
   updates, recovery, and total cost are included?
6. Which deterministic routing signals reach acceptable oracle recall before a
   learned router is justified?
7. What hierarchy unit and update algorithm preserve retrieval gain without
   topology churn or global summarization?
8. Which graph relations add held-out value after strict degree and traversal
   budgets?
9. What revocation-to-physical-erasure SLA is required, and what backup/history
   exceptions are lawful and useful?
10. How large must the active tier be, and what archive discovery/rehydration
    latency is acceptable at 100B and 1T?
11. Which RPO/RTO and multi-region topology are economically justified?
12. Which measured hot path, if any, warrants Rust, Go, C++, GPU, or another
    native component?

## 5. Research update policy

- Revisit this file after each accepted real-data gate or when an ADR opens.
- Add sources only when they change an option, experiment, risk, or conclusion.
- Record contradictory and negative evidence; do not curate only supportive
  papers.
- Distinguish peer-reviewed result, official product behavior, benchmark result,
  and Trace-specific inference.
- Pin versions and exact experimental artifacts in the ADR. This overview may
  link current documentation but is not a reproducibility lock.
- A paper result never overrides a failed Trace gate.

