# Trace V2 architecture and operating contract

This document describes the implementation under `src/trace/v2`. It separates the guarantees provided by the embedded adapter from deployment targets that require PostgreSQL, OpenSearch, Qdrant, NATS, Redis, or an external model gateway.

## 1. Design stance

Trace is a memory substrate, not a document generator. Ingress text may have a title, path, URL, or adapter metadata, but that envelope does not own the memory. The durable owner is the Atom/Event Spine:

```text
raw ingress artifact
        |
        v
immutable attachment + ingestion events
        |
        v
atom node identities + immutable node versions
        |
        +--> structural NEXT edges
        +--> lexical hot inbox
        +--> vector/index namespaces
        +--> local typed-edge proposals
        +--> promoted graph and generic derived nodes
```

The canonical Spine is the only factual source of truth. The Cortex is the
query-facing navigation/control layer, but any of its hierarchy, affinity,
activation, vector, or summary projections can be rebuilt from Spine events
and source attachments without changing canonical hashes. A generated report
is a view; a report becomes a memory candidate only after it is converted into
an evidence-backed proposal and explicitly promoted.

## 2. Truth layers

| Layer | Records | Purpose | Mutation policy |
|---|---|---|---|
| Spine | `events`, attachments, nodes, node versions, edge versions, evidence anchors | canonical history and provenance | append-only; no ordinary deletes |
| Hot inbox | current atom versions and lexical projection metadata | immediate post-capture visibility | rebuildable; old current rows may be removed |
| Cortex | hierarchy, affinity, activation, vector, and summary projections | navigation and retrieval control plane | revisioned, rebuildable, never factual by itself |
| Archive | old atom versions and topology | historical/deep recall | route out of default ranking, never erase evidence |
| Working memory | query candidates, bundles, temporary state | request-scoped retrieval state | TTL or disposable |
| Procedural memory | model/index revisions and experiment manifests | reproducibility and policy | versioned configuration |

The embedded store currently implements the Spine, hot inbox, proposal, bundle, registry, snapshot, and projection contracts in SQLite. The production services listed in Section 11 are replacement adapters, not additional client APIs.

## 3. Canonical records

### Event envelope

Every durable mutation has:

- an immutable `event_id` and monotonically increasing global `event_offset`;
- a `stream_id` and optimistic per-stream `stream_sequence`;
- `event_type`, UTC timestamp, actor, causation and correlation IDs;
- a schema version, canonical payload JSON, payload hash, and optional idempotency key.

The event payload is deliberately sufficient for replay validation. Node-version events carry content and properties; edge events carry relation fields, model metadata, and evidence atom-version IDs; attachment events carry the content hash and private object key.

### Nodes and versions

`nodes` hold stable identity, workspace, generic facets, and security metadata. `node_versions` hold content, properties, version number, content hash, and the event that created the version. The `atom` facet identifies source atoms; `holon`, `schema`, `claim`, and `summary` are generic derived facets. None is a separate truth table or ontology.

### Edges and anchors

`edge_versions` hold directed relation type, weight, confidence, status, validity bounds, model version, and properties. Trusted evidence edges are rejected unless evidence atom-version IDs are supplied. `NEXT`, `CHILD_OF`, `DERIVED_FROM`, and `CONTAINS` are structural/lineage relations but still record source anchors.

`evidence_anchors` point from a derived edge or node version to an exact source atom version, with source offsets, parser location, and quote hash. Anchor IDs are stable records; they are not inferred at response time.

### Proposals and views

Proposals are candidate derived objects. A proposal has a workspace, type, candidate JSON, evidence IDs, confidence, model version, lifecycle status, and decision event. Evidence bundles pin selected atom-version IDs and excerpts for a query. Saved queries preserve retrieval logic; frozen queries preserve atom-version IDs. Neither makes a generated rendering canonical.

## 4. Ingestion lifecycle

### Adapter boundary

The API accepts normalized text directly or a multipart file. The adapter boundary is responsible for:

1. retaining the original bytes privately;
2. extracting text for parser use;
3. identifying the adapter and media type;
4. supplying source URI/title/metadata;
5. applying policy before an external URL or model is introduced.

The embedded adapters support plain text, Markdown, code, transcripts, HTML, UTF-8 files, and PDF extraction through `pypdf`. HTML scripts, styles, templates, and noscript bodies are excluded. A parser transformation causes a normalized parser artifact to be retained alongside the original.

### Atomic transaction

One ingestion transaction appends and projects:

1. `ingestion.accepted` with workspace, source envelope, and raw content hash;
2. `attachment.recorded` with object key and media metadata;
3. `node.created` and `node.versioned` for every atom;
4. `edge.versioned` for each deterministic adjacent `NEXT` relation;
5. `ingestion.atomized` and the hot-inbox projection revision.

The API returns `202` after these writes are durable. The index-state ledger
reports `hot_ready`, `lexical_ready`/`pending`, and `dense_pending`/`dense_ready`
with the job and revision that own each transition. Queries union bounded hot
candidates with external hits while an externally indexed delta is pending.
Consolidation remains `pending` until its explicit worker/endpoint is run.

### Atomization rules

`atomize()` normalizes line endings, finds paragraph spans, separates bullets and numbered items, and splits long spans at sentence boundaries. Each draft records source start/end offsets and a parser location. A paragraph is not assumed to contain one concept; semantic claim extraction is a later proposal-stage concern.

### Idempotency

The ingestion idempotency key deterministically binds the workspace, source payload, and content hash. The first event is returned for an identical redelivery. A reused key with a different event type or payload hash raises a conflict. Node edits and proposal promotion use the same pattern for their operation events.

## 5. Version and lineage semantics

An edit computes the next version inside the node stream and appends a `node.versioned` event. The previous version remains queryable by history or `as_of_event`. The hot inbox removes only the old projection row; it does not delete the old `node_versions` record.

A split appends a split marker, creates child atom nodes and versions, and creates `CHILD_OF` edges anchored to the parent version. An alias operation creates an `alias_of` edge with evidence. There is no destructive merge operation in the embedded store.

Historical reads constrain the selected node/edge version event offset. Default reads select the highest version currently visible. Source offsets refer to the normalized parser artifact; the attachment metadata points to the original object and, where needed, its normalized parser object.

## 6. Retrieval contract

The request pipeline is:

```text
query + workspace + as_of + facet + privacy filters
    -> current atom candidates
    -> lexical scoring and phrase signal
    -> bounded candidate selection
    -> optional graph-path annotation
    -> sufficiency/abstention gate
    -> persisted evidence bundle
```

Trace V2 now exposes an explicit bounded ladder: Okapi BM25 and a versioned dense provider are fused by reciprocal-rank fusion, a local reranker scores the fused set, then typed-graph Personalized PageRank and hierarchy/deep traversal may be applied. The embedded default dense provider is explicitly labelled `hashing-dense-v1` and can only reinforce sparse evidence; it is an offline control path, not a claimed semantic model. `TRACE_DENSE_MODEL` configures a lazy local SentenceTransformer/BGE-compatible provider, `TRACE_RERANK_MODEL` configures a lazy local cross-encoder, and vectors remain rebuildable `dense_vectors` projections keyed by atom version and provider ID.

`fast` uses hybrid retrieval, `standard` adds reranking, `graph` adds PPR, `hierarchy` retrieves anchored resolutions, and `deep` performs bounded hierarchy selection before expanding back to raw atoms. A cloud deep navigator is created only for a registered `model_id` through the model gateway, after workspace policy and authorization checks; it receives only bounded derived summaries and opaque anchor IDs. A derived node alone is never sufficient evidence.

| Configuration | Effect | Default |
|---|---|---|
| `TRACE_DENSE_MODEL` | local SentenceTransformer/BGE-compatible dense model | deterministic `hashing-dense-v1` control provider |
| `TRACE_RERANK_MODEL` | local SentenceTransformer CrossEncoder | deterministic evidence reranker |
| registered deep `model_id` + `TRACE_MODEL_GATEWAY_URL` | gateway-mediated deep hierarchy selector | bounded heuristic selector |
| registered schema `model_id` + `TRACE_MODEL_GATEWAY_URL` | gateway-mediated review-only schema teacher | deterministic local proposer |
| `TRACE_MODEL_LOCAL_FILES_ONLY` | prohibit model downloads at runtime | `true` |
| `TRACE_DEEP_TOKEN_COST_PER_1K_USD` | cost accounting for configured deep calls | `0` |

### Sufficiency states

- `answerable`: at least one filtered candidate has a nonzero evidence score;
- `ambiguous`: the leading candidates are too close for the configured query shape;
- `insufficient_evidence`: no candidate matches the query after policy and temporal filtering.

Synthesis cannot improve a bundle's evidence state. If the bundle is insufficient, the synthesis response explicitly abstains. Every returned citation includes an atom-version ID and source location.

### Privacy

Node security metadata contains a visibility value and origin/actor fields. The embedded request context can provide `allowed_visibility`. Production authentication and tenant middleware must establish workspace scope, visibility clearance, external-model policy, and attachment access before retrieval. No model gateway should receive raw corpus access; it should receive only bounded, policy-approved excerpts from a bundle.

## 7. Consolidation and cognitive organization

`consolidate_ingestion()` only inspects the changed ingestion and a bounded workspace candidate set. Its deterministic term-overlap generator creates low-confidence typed proposals (`supports`, `contradicts`, `depends_on`, `implements`, or `example_of`); generic `semantic` edges are rejected. It records the shared terms and both source atom versions as evidence, and never auto-promotes an edge.

The intended production worker can add ANN candidates, lexical candidates, structural neighbors, graph neighbors, claim extraction, contradiction/support proposals, Holon summaries, and schema candidates. Each remains a proposal until a policy/reviewer validates evidence and impact. Local rebuilds must not churn unrelated neighborhoods.

Promotion is atomic with its derived object:

```text
pending proposal
    -> validate workspace and evidence IDs
    -> write versioned edge or generic derived node
    -> write evidence anchors
    -> append proposal.promoted
```

Rejection appends `proposal.rejected`, preserving the candidate and reason. Rollback should be implemented as another status/edge event rather than deleting the original decision.

### 7.1 Cognitive retrieval projections

The hierarchy builder makes four replaceable resolutions:

| Resolution | Facet | Source coverage |
|---|---|---|
| canonical evidence | `atom` | original parser span and attachment |
| source section | `section_summary` | bounded contiguous atom group from one ingestion |
| local topic | `topic_holon` | related source sections, grouped transparently by term overlap |
| workspace overview | `workspace_holon` | bounded overview of local topics |

New hierarchy membership is stored in the Cortex projection layer:
`projection_runs`, `projection_objects`, and `projection_memberships`. Each
object records source atom-version coverage, checksum, model/prompt/index/policy
revisions, and regeneration lineage. A hierarchy revision is acyclic, but the
trusted-evidence and affinity families are not forced into one DAG. Legacy
derived nodes remain readable during migration only. An identical run reuses
its revision; a replacement becomes active by reversible revision handover.

Activation is a pure, query-local energy layer over structural, reviewed
evidence, affinity, and behavioral families. Its persisted policy caps family
mass and degree, normalizes rows, and records score contributions and traversed
bridges. Affinity endpoints are atom-version IDs, are expiring/rejectable, and
are never promoted to trusted evidence automatically.

Schema induction creates only pending `schema` proposals containing labels, definitions, positive examples, exclusions, confidence, and source IDs. Reviewers promote them; local classification becomes a soft ranking feature only. Retrieval feedback (`selected`, `opened`, `cited`, `accepted`, `rejected`) is append-only and can influence rank features, but never graph topology or edge trust automatically.

## 8. Outbox and projection recovery

The outbox row is inserted in the same transaction as its event. `OutboxWorker` claims pending rows with a lease, publishes `{event_id,event_offset,payload}`, and marks the row published only after the publisher succeeds. Lease expiry returns an in-flight row to pending. This gives at-least-once delivery; consumers must deduplicate on `event_id` and record their last applied offset.

`reconcile_hot_inbox()` removes only the selected projection rows, folds current atom versions from the canonical tables, rebuilds the inbox, and records a new projection revision. Attachment staging records make object-store writes recoverable if the canonical transaction fails. `replay_report()` independently folds event payloads into an in-memory canonical state and compares node identities, node versions, edge fields, anchors, and attachments against the database. A failed replay report is an integrity incident, not a reason to delete records.

Snapshots hash event IDs and payload hashes through an event offset. Re-indexing registers an embedding/vector/lexical revision before rebuilding traffic. The embedded compaction endpoint logs a safe pass and deletes no Spine evidence.

## 9. API contract map

| Route | Input | Output/side effect |
|---|---|---|
| `POST /v2/ingestions` | JSON `IngestionRequest` | `202`; ingestion ID, counts, offsets, statuses |
| `POST /v2/ingestions/upload` | multipart workspace + file | `202`; original bytes retained and parser text atomized |
| `GET /v2/ingestions/{id}` | ingestion ID | source, attachment metadata, status, projection offsets |
| `POST /v2/ingestions/{id}/consolidate` | optional actor | bounded proposals and consolidation status |
| `GET /v2/nodes/{id}` | optional `as_of_event` | one version with properties and security metadata |
| `GET /v2/nodes/{id}/history` | node ID | every immutable version |
| `PATCH /v2/nodes/{id}` | content/properties/actor/idempotency | successor version plus bounded version-index handoff |
| `POST /v2/nodes/{id}/split` | child parts | child versions, lineage edges, and bounded version-index handoff |
| `POST /v2/nodes/{id}/alias` | target node/evidence | trusted alias edge |
| `POST /v2/queries` | query/scope/privacy/budget/profile | persisted evidence bundle with per-stage diagnostics |
| `POST /v2/retrieval-feedback` | selected/opened/cited/accepted/rejected evidence | append-only soft-rank feedback event |
| `POST /v2/graph/edge-strength-proposals` | feedback threshold and workspace | pending, reviewable edge-version revisions |
| `POST /v2/syntheses` | evidence bundle ID | cited noncanonical rendering |
| `GET|POST /v2/graph/subgraph` | workspace/seeds/depth/policy | filtered nodes, edges, evidence paths |
| `POST /v2/proposals` | candidate + evidence IDs | pending proposal |
| `POST /v2/hierarchy/build` | workspace and hierarchy bounds | anchored section/topic/workspace projections |
| `POST /v2/affinity/rejections` | atom-version pair and reason | durable negative affinity feedback; never a factual edge |
| `POST /v2/schemas/proposals` | workspace and proposal bound | reviewable schema proposals |
| `GET /v2/schemas/classifications` | workspace/atoms | soft labels from accepted schemas |
| `POST /v2/benchmarks/runs` | frozen benchmark and stage list | persisted ablation metrics |
| `GET|PUT /v2/admin/cognitive-policies/{workspace}` | workspace policy | active, revisioned Cortex policy |
| `GET /v2/admin/projection-runs` | workspace/kind/status | revision, inputs, output stats, and lifecycle inspection |
| `POST /v2/admin/projections/rebuild` | bounded atom IDs or event range | durable hierarchy, affinity, or activation rebuild |
| `POST /v2/proposals/{id}/promote` | actor/reason | promoted edge or derived node |
| `POST /v2/proposals/{id}/reject` | actor/reason | rejected proposal decision |
| `POST /v2/saved-queries` | retrieval logic | persistent named query |
| `POST /v2/frozen-queries` | retrieval logic | pinned atom-version IDs |
| `/v2/admin/*` | administrative payloads | replay, reconciliation, snapshots, revisions, registries, events |

All errors use a structured `detail` response. Missing entities return `404`, idempotency conflicts return `409`, invariant violations return `422`, and unexpected failures return a generic `500` without exposing storage internals.

## 10. Testing and research discipline

The foundation and cognitive tests exercise idempotency, atomization, replay, hybrid channels, abstention, hierarchy anchoring/regeneration, typed PPR, deep raw-evidence expansion, schema review/classification, feedback, and benchmark reporting. Production gates also cover worker crashes, duplicate delivery, partial index writes, configured-provider outages, historical retrieval, privacy leakage, ANN recall, citation precision, and corpus-scale latency.

The frozen benchmark runner evaluates lexical, hybrid, rerank, hierarchy, graph, and deep profiles with Recall@5/20, nDCG@10, complete-gold-evidence coverage, citation precision, abstention correctness, p95 latency, local compute, and cloud-token cost. Every run persists a baseline identity containing the corpus checksum, code/policy/model/index/projection revisions, hardware, and measured cost/latency. `benchmarks/technical-docs-v1.json` is a six-case developer fixture only. A release corpus has at least 300 reviewed, tagged cases across direct lookup, chronology, contradiction/revision, cross-domain, global-context, multi-hop, historical-read, and out-of-scope slices.

New cognitive mechanisms remain behind explicit profiles and ablations. HippoRAG-style graph activation, LATTICE-style multi-level navigation, RAPTOR/GraphRAG summaries, RLM synthesis, dynamic schema induction, and plasticity signals may improve a relevant workload, but none may be allowed to create an unanchored fact or hide source evidence. Every experiment records a corpus snapshot, code revision, model versions, index revisions, parameters, and baseline comparison.

## 11. Distributed deployment boundary

The V2 public API is stable across storage adapters. A production implementation should provide:

- PostgreSQL transactions and per-stream optimistic sequencing for canonical data;
- private S3 object keys with retention and encryption policies;
- OpenSearch lexical indexes over atom versions and source locations;
- Qdrant collections/namespaces keyed by embedding model and rollout revision;
- NATS JetStream consumers fed by the PostgreSQL transactional outbox;
- Redis TTL caches and working-memory state;
- policy-aware model gateway calls with bounded excerpts only.

At 100K and 1M atoms, measure event lag, projection parity, orphan vectors, stale index rows, graph degree, storage growth, consolidation backlog, query cost, and ingestion throughput. Partition by workspace/time, use snapshot-plus-delta replay, and forbid global pairwise clustering. The 1M gate requires 300+ reviewed queries, >=80% complete-gold-evidence coverage, >=90% citation precision, zero hot-data blind spots, no critical replay/privacy/destructive-data defect, bounded operational state, fast p95 <= 2 seconds, standard/graph/hierarchy p95 <= 5 seconds, deep p95 <= 90 seconds, and quality within two points of the 100K baseline. A 10M/500-QPS release is a separate later program.

The embedded implementation is the correctness/control layer for these deployments. It labels deterministic hashing/reranking providers honestly, persists their provider IDs in bundle diagnostics, and never silently represents them as ANN, BGE, or cross-encoder results.

The production boundary is implemented in `production.py`: PostgreSQL owns the
event/outbox/job schema and row-policy migration, S3-compatible storage uses
tenant-prefixed encrypted objects, OpenSearch and Qdrant apply workspace and
visibility payload filters, NATS publishes leased outbox envelopes, and Redis
provides TTL coordination. `repository.py` contains the application protocols;
the SQLite adapter remains the embedded implementation of those protocols.
The HTTP layer adds identity middleware, durable jobs, signed webhooks,
idempotency/request controls, opaque pagination, readiness, and metrics. A
deployment still needs to provision partitions, secrets, credentials, and the
projection consumers appropriate to its infrastructure.
