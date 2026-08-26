# Trace Scale Hard Problems

> Status: lead-architecture analysis and experiment agenda. Provisional designs
> in this file become binding only through an accepted ADR in
> `SCALE_DECISION_REGISTER.md`.

This file concentrates on the decisions where a plausible local implementation
can become fundamentally wrong at billion or trillion scale. Routine schema
expansion, command examples, dataset inventories, and runbook prose belong to
delegated follow-up packets.

## Current Trace implementation cliff map

The current code is a useful Foundation/100K-to-1M proof substrate, not a blank
slate. It already has bounded retrieval budgets, canonical hit revalidation,
workspace-partitioned events, transactional outboxes, delta-bounded atom index
updates, candidate external-index revisions, and fail-closed release evidence.
The scale program should preserve those contracts while addressing these
specific cliffs:

| Cliff | Current evidence | Architectural destination |
| --- | --- | --- |
| Two organization paths | Normal consolidation still reaches legacy organization that writes derived nodes and trusted `CONTAINS` edges (`src/trace/v2/service.py:862`, `:1889`; `organization.py:161`, `:188`) | Automatic organization converges on revisioned Cortex projections; factual promotion stays reviewed |
| Delta request, global hierarchy work | Hierarchy builds gather the active source-section set, carry unchanged sections, regenerate topics/workspace overview, and insert rows individually (`service.py:1132`, `:1276`, `:1481`; `production.py:2698`) | Partition-local immutable fragments, structural sharing, bulk writes, and manifest composition |
| Hot inbox becomes a second corpus | Every atom enters the inbox and retrieval uses substring scans (`production.py:761`, `:2176`; `migrations/001_trace_production.sql:185`) | Size/age-bounded indexed fresh-tail overlay with explicit release watermark |
| Current and historical index semantics diverge | Full reindex iterates latest node versions (`production.py:393`, `:411`) while query exposes `as_of_event` | Separate current/historical coverage contract and parity tests |
| Projection isolation is incomplete | Affinity reads are not pinned to the active projection run and activation priors are not revision-unique (`production.py:2791`; `migrations/004_cortex_projection_control_plane.sql:148`) | Every derived row/hit is run- and release-scoped; candidate rows are unreachable by default queries |
| Release granularity mismatch | Reindex is workspace-scoped, while physical revision aliases are deployment-global (`service.py:2597`; `production.py:3102`, `:3223`) | Explicit workspace/partition release roots and index namespace mapping |
| Dense vector duplication | PostgreSQL stores JSON vectors while Qdrant also serves them (`migrations/001_trace_production.sql:336`; `service.py:2912`) | One serving representation plus canonical fingerprints and rebuild metadata |
| Replay/snapshot work is whole-workspace | Replay materializes events/canonical rows and snapshots rescan hashes without a restartable state image (`production.py:941`, `:1424`) | Partition checkpoints, immutable snapshot manifests, and snapshot-plus-delta replay |
| Runtime evidence is thinner than gate schema | Release evaluation asks for lag, graph degree, cost, and stale-projection measures while runtime instrumentation is retrieval-heavy (`release.py:73`; `service.py:2277`) | Required gate telemetry emitted continuously and bound into run attestations |

The monthly partition-maintenance function currently expresses direction but
does not create concrete time partitions (`migrations/002_runtime_hardening.sql:190`).
The first scale work therefore completes current contracts before introducing a
distributed data plane.

## HP-0: define the service before scaling it

### Why this is hard

The same token count can describe radically different systems. A static private
archive queried twice a minute is not architecturally equivalent to a
multi-tenant memory receiving continuous revisions and thousands of temporal
queries per second.

### Provisional service classes

Trace should define and benchmark at least three explicit service classes:

| Class | Corpus posture | Serving promise |
| --- | --- | --- |
| Local/reference | Entire corpus on one trusted machine | Full local evidence behavior within declared machine limits |
| Active memory | Material is represented in online lexical/vector/hierarchy projections | Bounded interactive retrieval and declared freshness |
| Archival memory | Canonical source is retained; only coarse/selective indexes must stay hot | Bounded discovery followed by refinement or rehydration |

Each class needs separate query mixes: exact source lookup, lexical fact lookup,
semantic retrieval, multi-hop evidence, temporal/as-of, contradiction/update,
policy-filtered, archive discovery, and export/audit.

### Required decision

`SCALE-001` must freeze the workload vector in the master plan, active/archive
coverage, scale units, tokenizer, update distribution, availability, and cost
ceiling before a distributed topology is selected.

### Falsifying evidence

- Gate labels have no pinned unit or tokenizer.
- A pilot changes corpus shape, query set, or SLA while retaining the same gate
  name.
- Cost excludes replicas, temporary build space, model calls, snapshots,
  network, or operator time.
- Archive discovery and active atom-level retrieval are reported as one metric.

## HP-1: canonical identity and ordering without a global writer

### The trap

A single auto-incrementing event offset and globally mutable tables are useful
at Foundation scale. At large scale they become a serialization point, couple
identity to one database, and make movement between shards dangerous.

PostgreSQL can partition large tables effectively, but a unique or primary-key
constraint on a partitioned table must include its partition key. That is a
useful warning: cross-partition uniqueness and ordering do not appear merely
because all partitions share a SQL parent.

### Provisional model

1. A logical partition is a stable namespace, initially derived from workspace
   and stable source key. It is not a host, database, vector shard, or semantic
   topic.
2. A versioned partition map assigns logical partitions to physical placements.
   Movement changes the map version, never source or atom identity.
3. Each logical partition has a monotonic `partition_sequence`. This is the
   authoritative replay order for that partition.
4. Each event has a globally collision-resistant `event_id` and idempotency key.
   Neither is required to express a total global order.
5. A hybrid logical clock or equivalent causal timestamp records causality close
   to wall time. It does not replace the partition sequence.
6. Source revisions form explicit predecessor chains. Atom versions bind the
   immutable source revision, exact range, content digest, and atomizer contract.
7. A cross-partition release is a named vector of partition watermarks. The
   release root provides the reproducible read cut.
8. A logical operation spanning sources creates a coordination event that names
   child operations and completion state. Normal ingest does not pay for a
   distributed transaction across all affected projections.

```text
event identity  = globally unique and idempotent
event order     = total only inside one logical partition
causal time     = cross-partition diagnostic/dependency information
release cut     = explicit vector of accepted partition watermarks
wall clock      = user-visible time, never sole ordering authority
```

### Decisions that must not be delegated

- logical partition key and split/merge semantics;
- source identity across import, rename, merge, and workspace transfer;
- whether cross-partition operations require atomic visibility or an explicit
  partially-complete state;
- clock-skew assumptions and handling;
- historical-query semantics between release cuts.

### Required experiments

- retry and duplicate ingest before and after commit;
- two writers updating the same source and different sources;
- partition move with reads pinned to old and new map versions;
- split/merge while projection workers lag;
- cross-partition release assembled from unequal watermarks;
- clock regression and large clock skew;
- deterministic replay after coordinator loss.

### Reject or stop if

- any canonical ID changes when data moves;
- correctness requires a cluster-wide sequence allocation on every write;
- semantic reclassification moves canonical truth;
- a historical response cannot name its exact partition watermarks;
- duplicate delivery creates a second canonical revision.

## HP-2: immutable source segments, manifests, and compaction

### The trap

Keeping every atom, source byte, and vector as a mutable relational row is easy
to reason about initially but produces excessive index, vacuum, replica, backup,
and migration cost. Moving raw bytes to object storage without a commit protocol
merely trades database correctness for orphaned or inconsistent objects.

### Provisional storage shape

Use a Trace-native immutable snapshot pattern inspired by mature table formats,
without assuming that Trace must adopt one wholesale:

```text
Spine snapshot root
  -> partition manifests
       -> immutable source-blob objects
       -> immutable atom/event segment manifests
            -> immutable segment files
            -> optional delete/revocation vectors
```

Every object has a cryptographic digest, byte length, format/schema version,
creation context, and encryption-key reference where applicable. A segment
manifest records source/revision ranges, partition sequence bounds, counts,
min/max values, relevant bloom/statistics metadata, and child digests.

### Commit protocol

1. Write a candidate object under a non-addressable staging name.
2. Close, checksum, and independently read enough data to validate format and
   digest.
3. Publish under its immutable content address.
4. Write an immutable manifest that references only verified children.
5. Commit the manifest reference in the canonical metadata transaction or
   compare-and-swap the snapshot pointer.
6. Emit the projection outbox entry in the same metadata transaction.
7. Collect abandoned staged objects only after a conservative grace period.

Object-store listing is not part of correctness. Reachability begins at a
strongly consistent manifest pointer.

### Compaction and structural sharing

- Appends create new small segments and reuse unchanged manifests.
- Compaction writes replacement segments, then publishes a new manifest; it
  never mutates an admitted segment.
- Logical deletes/revocations become visibility overlays or delete vectors
  immediately, then physical purge occurs under retention and legal policy.
- Old manifests and segments remain reachable while an active release,
  historical policy, verifier receipt, reader lease, or rollback window needs
  them.
- Garbage collection operates from manifest reachability plus retention state,
  never by listing age alone.

### Format questions for `SCALE-003`

- Raw source blob envelope and exact-byte preservation.
- Atom/event segment format: Parquet/Arrow/Avro/custom packed format or a narrow
  combination.
- Point lookup versus sequential scan requirements.
- Row-group/segment size from measured update, query, restore, and compaction
  behavior.
- End-to-end checksum and Merkle-root strategy.
- Encryption granularity and key hierarchy.
- Delete-vector, rewrite, and cryptographic-erasure threat models.
- Schema and partition evolution without rewriting historical identity.

### Required experiments

- exact source reconstruction, including encoding and byte offsets;
- interrupted upload at every commit step;
- manifest child corruption and missing object;
- deterministic segment rebuild from the same canonical inputs;
- append and 1% daily churn with compaction debt measurement;
- old/new schema and partition-map coexistence;
- delete propagation and physical collection proof;
- full restore with no trusted derived index.

### Reject or stop if

- source bytes or evidence offsets cannot be reconstructed exactly;
- a manifest can become active before every child is verified;
- compaction changes logical IDs or query meaning;
- garbage collection can remove data reachable by a valid release;
- object-store snapshots are treated as the only audit record.

## HP-3: atomic projection releases across independent stores

### The trap

PostgreSQL, OpenSearch, Qdrant, object storage, and caches do not participate in
one cheap atomic transaction. Sequentially switching each store creates mixed
releases. Treating a search-engine alias as the global commit point also makes
the search engine the owner of release truth.

### Provisional release object

A partition projection manifest should name:

- logical partition and partition-map version;
- source watermark and policy version;
- projection kind and schema version;
- parser, atomizer, embedding, summary, graph, router, and normalization
  fingerprints as applicable;
- immutable fragment/index revision identifiers and checksums;
- expected and observed counts/coverage;
- bounded-work metadata and resource receipts;
- validator identity, result digest, and exclusions;
- parent manifest for structural sharing and rollback.

A workspace release root should name all required partition manifests, the
cross-partition watermark vector, policy and evidence schema, compatibility
constraints, and verifier state.

### Activation protocol

1. Projection workers publish immutable candidate fragments under a candidate
   revision.
2. A verifier reads the candidate through its serving adapter and compares it
   directly with canonical Spine ranges and policy.
3. The candidate partition manifest is marked validated; no default query can
   address it yet.
4. The release coordinator assembles a complete immutable workspace root.
5. One strongly consistent compare-and-swap changes `active_release_root` from
   the expected old digest to the new digest.
6. Queries pin the root digest for their lifetime.
7. Old fragments remain retained until reader leases, rollback, audit, and
   retention permit collection.

External aliases may switch serving revisions atomically within one engine, but
Trace's root determines which alias/revision is valid. A backup snapshot may be
incremental or shard-local and may not be a perfect cross-index point-in-time
view; the Trace manifest must make those limitations explicit.

### Freshness without partial publication

Use a bounded, revisioned fresh-tail overlay. It is included in a release root
with its own watermark and validation rules. New source can be queryable quickly
without mutating the compacted base or exposing unvalidated hierarchy/graph
rows. Compaction later carries the tail into immutable base fragments.

### Required experiments

- failure before and after each external-index write, validation receipt, root
  assembly, root CAS, alias switch, and cleanup;
- two coordinators racing to activate;
- one partition candidate missing, stale, or built from the wrong policy;
- process death with readers pinned to both releases;
- rollback after new source and revocation events;
- restoration when external snapshots are from different times;
- deterministic full rebuild equivalence against an incremental release.

### Reject or stop if

- default queries can observe a candidate by knowing its external index name;
- activation requires destructive deletion of the previous projection;
- a failed graph/hierarchy step can leave vectors or summaries active alone;
- rollback depends on rebuilding the old release;
- the root can point to a fragment lacking a validator receipt.

## HP-4: bounded shard routing without recall collapse

### The trap

Hash sharding balances writes but destroys semantic locality. Semantic physical
sharding improves some queries but makes truth move whenever the model or topic
changes. Broadcasting every query preserves recall but makes latency and cost
grow with shard count.

### Provisional two-level design

Keep physical truth placement stable and make semantic routing a rebuildable
projection.

**Hard pruning signals** run first:

- workspace/tenant and authorization;
- requested time/release/policy;
- source class, language, collection, retention, and explicit scope;
- logical partition ownership and availability.

**Recall-routing signals** then nominate a bounded shard set:

- global/coarse lexical directory and rare-term postings;
- partition centroids or multiple representative vectors;
- coarse hierarchy/topic summaries;
- recent/fresh-tail and explicit source-affinity routes;
- query-class rules;
- a learned router only after it beats fixed controls in shadow mode.

Each selected shard performs local lexical, vector, hierarchy, and sparse-graph
retrieval. The coordinator merges deterministic candidate records. A calibrated
confidence rule may spend a second bounded shard budget; it never expands until
all shards are searched.

### Router evidence must be separate from retriever evidence

For a sampled evaluation set, construct an oracle using exhaustive shard search
or exact known evidence. Report:

- oracle-relevant-shard recall at shard budget `S`;
- end-to-end evidence Recall@K;
- conditional local-retriever recall given the correct shard;
- routing regret versus exhaustive search;
- shards contacted, bytes read, candidates scored, network fan-out, and merge
  cost;
- confidence calibration and expansion rate;
- results by rare/common term, long-tail age, language, query class, update age,
  and policy scope.

This decomposition prevents a weak router from being hidden by a strong local
retriever or by increasing fan-out.

### Index posture

- Lexical search remains a first-class recall and exact-match path.
- Disk-backed ANN, quantization, and custom sharding are candidates, not truth
  contracts. Billion-point research demonstrates feasibility for the vector
  subproblem, not for Trace's provenance, updates, hierarchy, or policy.
- Trace point IDs include or map to canonical atom versions and projection
  revisions; external databases' shard-local uniqueness is insufficient.
- Full-precision source embeddings need not be duplicated in canonical SQL at
  large scale. Retain model/config identity and rebuildability.
- Index shard count and vector physical placement are not identical to logical
  Spine partitions; the mapping is versioned.

### Required experiments

- fixed real-query set as shard count grows while corpus meaning stays stable;
- adversarial cross-domain and rare-term queries;
- temporal and revoked evidence present on non-obvious shards;
- hot-shard and skewed-source workloads;
- physical shard movement and vector-index resharding;
- index unavailable or stale while lexical/source paths remain valid;
- quantization and disk-index recall/latency/cost curves;
- learned router in shadow mode against deterministic routing and exhaustive
  oracle samples.

### Reject or stop if

- p95 shard fan-out grows linearly with shard count;
- routing quality is reported only end to end without oracle decomposition;
- a learned router becomes authoritative before held-out and drift evidence;
- a candidate cannot be revalidated without trusting external payloads;
- tail queries or policy filters bypass the same release semantics.

## HP-5: incremental hierarchy and sparse association under drift

### The trap

A self-organizing system invites global clustering, parent summaries containing
all descendant IDs, and pairwise co-occurrence graphs. These produce attractive
small demos and catastrophic update/build shapes.

### Provisional organization unit

Organization is a projection over bounded logical units, such as one source,
source family, time bucket, or coarse stable namespace. Those units are chosen
for update locality and policy—not as canonical semantic shards.

Each unit has immutable hierarchy fragments:

- leaves reference atom versions rather than copying source text;
- containment memberships use parent/child references, not a descendant list at
  every ancestor;
- fan-out, depth, leaf count, and summary input bytes are explicit budgets;
- an update rewrites the affected path/fragments and structurally shares the
  rest;
- overflow creates a new bounded fragment; background merge/rebalance is a
  budgeted candidate release;
- cross-unit routing summaries are coarse disposable projections.

### Sparse graph contract

Containment and provenance edges form an acyclic structure. Affinity,
co-evidence, temporal, citation, and entity edges may cycle, but they are:

- revision- and policy-scoped;
- generated from bounded candidate neighborhoods;
- capped per node, relation, time window, and source;
- weighted with reproducible evidence;
- pruned/expired through versioned projection releases;
- traversed only under typed seed, edge, hop, iteration, and latency budgets.

Replace all-pairs term co-occurrence with bounded top-k neighbor selection from
inverted postings, local windows, entity/citation evidence, or ANN candidates.
No term with document frequency `df` may create `O(df^2)` edges.

### Summary economics

Generated summaries are optional Cortex artifacts. A trillion-token archive must
not require an LLM summary for every small atom or for repeated global rebuilds.
Use summaries where a measured routing/retrieval gain justifies:

- source or bounded-fragment summaries;
- incremental parent regeneration only on affected paths;
- cached, fingerprinted model outputs;
- active/warm tiers rather than unconditional cold-archive coverage;
- no-summary and extractive controls in evaluation.

Trace-Lite's one-canonical-summary discipline remains useful inside a summary
projection: the validated summary text is the one stored, embedded, displayed,
and propagated. It never becomes source truth.

### Required experiments

- one-atom, one-source, and 1% churn with work-amplification tracing;
- adversarial high-frequency term graph construction;
- incremental/full-rebuild equivalence for coverage and evidence identity;
- topology churn and routing stability under topic drift;
- hierarchy, graph, summary, and fusion leave-one-mechanism-out ablations;
- old/rare evidence recall after energy/usage-based pruning;
- duplicate, late, revoked, and superseding revisions.

### Reject or stop if

- update work is proportional to the complete corpus under normal churn;
- hierarchy identity depends on nondeterministic random node IDs with no
  revision scope;
- graph edges survive the release that created their endpoints;
- summaries are required to reconstruct facts or source evidence;
- a mechanism's benefit disappears against the fixed lexical+dense baseline.

## HP-6: revocation, erasure, retention, and historical truth

### The trap

"Immutable" cannot mean "always visible" or "impossible to delete." A stale
vector hit, cache entry, graph edge, snapshot, or historical-query path can leak
material after the canonical row is hidden.

### Separate four semantics

1. **Supersession** retains old history but current queries prefer the accepted
   successor.
2. **Revocation** immediately denies serving an item under a policy, while audit
   history may remain for authorized contexts.
3. **Logical deletion** removes material from allowed snapshots and projections,
   with physical collection pending.
4. **Physical erasure** removes bytes and eligible derived copies under a stated
   retention, backup, replication, and cryptographic-key policy.

The request and resulting policy event must specify which semantic applies.

### Provisional enforcement path

- Commit the policy/revocation event in the canonical partition first.
- Update the strongly consistent visibility overlay used by every query before
  candidate evidence is returned.
- Enqueue revision-scoped tombstones/delete vectors for all projections.
- Invalidate or version caches; do not rely on best-effort TTL alone.
- Prevent new release roots from referencing affected artifacts unless their
  historical policy explicitly permits it.
- Track purge acknowledgements by store, fragment, snapshot class, replica, and
  backup generation.
- Collect source segments or destroy scoped data keys only after the retention
  and threat model permits it.
- Make historical/as-of access a separate authorization decision. "As of" never
  bypasses current legal or security policy silently.

Cryptographic erasure can reduce physical rewrite cost only if key granularity,
key copies, backups, and metadata leakage satisfy an accepted threat model. It
must not be advertised merely because files are encrypted.

### Required experiments

- revoke while indexes, caches, and projection workers are stale;
- delete during candidate build and during root activation;
- restore an old snapshot after a later revocation;
- historical query by authorized and unauthorized principals;
- per-source key destruction and proof that no recoverable key copy remains;
- compaction of delete vectors/tombstones;
- cross-shard source transfer followed by erasure.

### Reject or stop if

- canonical revalidation can be skipped for latency;
- an old release or snapshot silently restores visibility;
- the system reports physical erasure before all declared stores acknowledge it;
- policy propagation has no measurable lag or completeness receipt;
- deletion semantics are inferred from a generic API verb.

## HP-7: recovery, backpressure, and disaster economics

### The trap

Large systems often serve a benchmark when healthy but cannot catch up after a
failure, rebuild before the next update wave, or restore without a second full
copy of every index.

### Provisional operational model

- Acknowledged source writes require canonical metadata/segment durability, not
  projection completion.
- Projection dispatch is at-least-once; workers are idempotent by projection
  kind, logical partition, input watermark, and configuration fingerprint.
- Every queue and stage has an explicit byte/item/age budget and backpressure
  behavior.
- The last validated release remains serviceable while a candidate lags or
  fails, subject to an explicit freshness warning and policy overlay.
- Portable immutable projection fragments and engine-native snapshots shorten
  recovery, but canonical source replay remains the correctness fallback.
- Recovery is prioritized by policy urgency and active-set value, not blindly by
  global event order.
- Capacity planning includes one failure, one rebuild/compaction, and accepted
  traffic concurrently.

### Required telemetry

- source commit and outbox lag;
- queue depth/bytes/oldest age and retry reason;
- projection watermark and active-release age per partition;
- candidate/active/orphan/stale object counts;
- shard size, QPS, CPU, memory, disk/network I/O, cache hit rate, and skew;
- query fan-out, stage budgets, timeouts, partial/fail-closed outcomes;
- compaction debt and temporary amplification;
- snapshot age, restore throughput, RPO/RTO, and recovery cost;
- policy/revocation propagation lag;
- storage, model-token, compute, network, and operator cost.

### Fault program

Inject process death, duplicate and out-of-order delivery, disk full, object
corruption, checksum mismatch, provider outage, index timeout, lost shard,
network partition, stale partition map, coordinator race, partial release,
snapshot mismatch, and capacity exhaustion at every lifecycle boundary.

### Reject or stop if

- backlog grows faster than steady-state drain capacity;
- recovery requires exposing a candidate or dropping canonical writes;
- RTO is measured without rebuilding/revalidating the affected serving state;
- a one-node or one-zone loss removes both canonical data and its recovery copy;
- observability reports a generic error without redacted stage and object IDs.

## HP-8: an evaluator capable of disproving Trace

### The trap

A synthetic corpus, editable source import, mutable `release_authority` flag, or
moving query file can make a benchmark repeatable while still allowing the
system under test to define what success means.

### Required frozen identities

Trace-Bench must bind six independently checkable artifacts:

1. dataset lock: publisher, release/snapshot, URLs, bytes, checksums, license,
   splits, qrels, and admission;
2. transform lock: input hashes, code/container, arguments, tokenizer,
   normalization, outputs, and deterministic rerun proof;
3. evidence map: reversible upstream source/revision and byte ranges to
   candidate atom/chunk IDs and returned evidence;
4. protocol lock: query set/held-out policy, metrics, cutoffs, hardware,
   concurrency/cache schedule, statistics, faults, thresholds, and claim scope;
5. candidate and baseline releases: commit plus wheel/container/dependency,
   config, model, migration, and adapter identities;
6. run attestation: all preceding hashes, hardware/environment, raw telemetry,
   per-query records, fault receipts, result roots, independent verifier, and
   human decision.

Release authority is an external attestation over those identities. It is not a
dataset field or a property the candidate can set.

### Separate evidence lanes

- **Controlled segmentation** gives every candidate identical canonical atoms,
  isolating retrieval and organization mechanisms.
- **Native ingestion** gives original artifacts and audits candidate-created
  chunks back to canonical byte ranges, testing the full database.
- **ANN infrastructure** uses BigANN-style vectors and ground truth to measure
  vector recall/throughput/memory only.
- **End-to-end memory** combines real retrieval, provenance, temporal,
  organization, policy, and operations protocols. ANN success cannot substitute
  for this lane.
- **Archive integrity** measures manifest coverage, reconstruction, discovery,
  rehydration, restore, retention, and cost separately from active retrieval.

### Metrics that cannot be omitted

- source reconstruction, hash/range validity, mapping coverage, and no candidate
  leakage;
- Recall/nDCG/MRR, complete evidence recovery, citation precision, temporal and
  contradiction correctness, and calibrated abstention;
- hierarchy navigation, summary support, relation evidence, topology churn, and
  update locality where applicable;
- shards, postings/probes, candidates, graph work, model calls/tokens, bytes, and
  deep rounds per query;
- cold/warm tail latency, fixed-concurrency throughput, continuous peak memory,
  I/O, storage amplification, lag, build/restore time, and cost;
- paired, protocol-identical statistical analysis with effect sizes and
  predeclared non-inferiority margins.

Thresholds are selected after real baseline distributions and before held-out
release execution. They are not filled by an implementation agent after seeing
candidate results.

### Reject or stop if

- source, transform, candidate, or protocol identity is incomplete;
- missing organization evidence becomes an assumed perfect score;
- the candidate is imported from an editable checkout;
- a verifier patches the implementation during the verification session;
- a synthetic scale run is reported as real retrieval or release evidence;
- the evaluator's metric cannot mathematically reach its declared threshold on
  the admitted qrels.

## HP-9: native components without a rewrite trap

Python is suitable for the control plane, domain contracts, experiments,
orchestration, evaluators, and reference semantics while the architecture is
changing. Language choice cannot fix unbounded work or the wrong data topology.

A native component is justified only when:

1. a passed real gate and profile identify a stable dominant path;
2. the algorithm and serialized contract are frozen enough for parity tests;
3. the gain is material to the next gate's accepted objective;
4. failure, cancellation, resource, tracing, and version semantics are explicit;
5. the Python/reference implementation and golden fixtures remain authoritative
   for behavior;
6. rollout and rollback do not change evidence or policy semantics.

Likely candidates are packed segment encoding/verification, hashing and parsing,
bounded sparse-graph/PPR kernels, projection serialization, or a high-concurrency
router/worker. Mature databases and object/index systems should own commodity
storage mechanics before Trace invents replacements.

Reject a rewrite proposal whose evidence is only language preference, synthetic
microbenchmarks, or aggregate CPU usage without an end-to-end gate impact.

## HP-10: the trillion-token boundary

### Default architectural interpretation

The first trillion-token target is a tiered archive with bounded active
cognition:

| Tier | Contents | Required service |
| --- | --- | --- |
| T0 control | partition maps, release roots, policy, manifests, source directory | strongly consistent lookup and audit |
| T1 hot | recent/high-value atoms and full active projections | interactive bounded retrieval SLA |
| T2 warm | coarse lexical/metadata indexes, selected vectors/summaries, portable fragments | broader discovery with slower bounded refinement |
| T3 cold | immutable source and atom/event segments, retained history | verified reconstruction, rehydration, retention, and disaster recovery |

Promotion and demotion between tiers changes projection coverage, not canonical
truth. The release root records exactly which coverage and SLA apply.

### Query behavior

1. Search T0/T1 routing and active indexes.
2. Use warm lexical/metadata/centroid summaries to identify a bounded set of cold
   segments when active evidence is insufficient.
3. Read or rehydrate only those segments under an archive budget.
4. Build an ephemeral or retained refinement projection with a declared
   revision.
5. Revalidate and return exact source evidence with the slower service class
   stated explicitly.

### What F6 can claim

- at least the declared trillion tokens are present in verified canonical
  manifests;
- archive discovery and sampled reconstruction meet a frozen protocol;
- the declared active subset meets its interactive retrieval SLA;
- rehydration, deletion, restore, and cost meet their separate objectives.

It cannot claim every cold atom had a current dense vector, global graph
membership, current summary hierarchy, or equal latency.

### When to open the uniformly active research program

Only after F6 and only if a real use case requires it. The decision packet must
justify the active coverage, update/QPS/latency target, expected value, vector and
organization economics, and why tiered refinement is insufficient.

## Research anchors

These sources support design patterns or evaluation methods. None independently
validates Trace.

- [PostgreSQL declarative partitioning](https://www.postgresql.org/docs/current/ddl-partitioning.html): partition pruning and the uniqueness constraints that include partition keys.
- [Logical Physical Clocks paper](https://cse.buffalo.edu/~demirbas/publications/hlc.pdf): causal ordering and consistent snapshots without relying on physical time alone.
- [Apache Iceberg specification](https://iceberg.apache.org/spec/): immutable files, manifests, snapshots, atomic metadata replacement, partition evolution, and delete metadata.
- [Apache Parquet format](https://parquet.apache.org/docs/file-format/) and [modular encryption](https://parquet.apache.org/docs/file-format/data-pages/encryption/): segment layout, metadata, selective reads, and encryption granularity.
- [Git object model](https://git-scm.com/book/en/v2/Git-Internals-Git-Objects.html): a mature content-addressed object/manifest pattern.
- [Consistent Hashing with Bounded Loads](https://research.google/pubs/consistent-hashing-with-bounded-loads/): stable placement with explicit load bounds and limited movement.
- [OpenSearch aliases](https://docs.opensearch.org/latest/api-reference/alias/aliases-api/) and [snapshots](https://docs.opensearch.org/latest/tuning-your-cluster/availability-and-recovery/snapshots/snapshot-restore/): atomic engine-local alias changes and the limits of backup snapshots as cross-system release cuts.
- [Qdrant distributed deployment](https://qdrant.tech/documentation/scaling/distributed_deployment/), [snapshots](https://qdrant.tech/documentation/operations/snapshots/), and [quantization](https://qdrant.tech/documentation/manage-data/quantization/): practical vector sharding, identity, movement, recovery, and recall/storage tradeoffs.
- [DiskANN](https://www.microsoft.com/en-us/research/?p=634449), [SPANN](https://www.microsoft.com/en-us/research/?p=796310), [FreshDiskANN](https://arxiv.org/abs/2105.09613), and [SPFresh](https://www.microsoft.com/en-us/research/publication/spfresh-incremental-in-place-update-for-billion-scale-vector-search/): disk-backed billion-point ANN and the importance of incremental update economics.
- [NeurIPS BigANN results](https://proceedings.mlr.press/v176/simhadri22a.html): recall at throughput plus cost/power-normalized vector evaluation.
- [BEIR](https://arxiv.org/abs/2104.08663): heterogeneous retrieval and strong lexical controls.
- [KILT](https://arxiv.org/abs/2009.02252): retrieval evaluated together with provenance.
- [LongMemEval](https://arxiv.org/abs/2410.10813): temporal, update, multi-session, and abstention diagnostics; it is not a system-scale benchmark.
