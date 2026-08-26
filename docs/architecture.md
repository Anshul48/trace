# Trace architecture index

Trace V2 is the active architecture. The detailed design contract is in
[v2-architecture.md](v2-architecture.md); this page is the short orientation
for maintainers and operators.

## Active runtime

```text
client / SDK
    |
    v
FastAPI /v2 router
    |
    v
TraceService (adapter normalization, policy, retrieval, proposals)
    |
    +--> private object store (original and parser artifacts)
    +--> SqliteEventStore (embedded Spine + projections)
    |       |
    |       +--> events + transactional outbox
    |       +--> nodes / immutable node_versions
    |       +--> edge_versions / evidence_anchors
    |       +--> hot_inbox / query bundles / proposals
    |
    +--> OutboxWorker -> provider-specific event fan-out
```

`main_api.py` imports only `trace.v2.api`. It does not initialize the legacy
agent pipeline, filesystem watcher, frontend workflow, SQLite `trace.db`
tables, or Chroma collections. The V2 app is therefore safe to run beside old
artifacts while using separate `.trace/` storage.

## Truth boundary

The event ledger and immutable version records are canonical. `hot_inbox`,
retrieval scores, graph adjacency projections, vector namespaces, summaries,
schemas, salience, caches, and generated output are disposable projections.
Every promoted semantic object carries exact source atom-version anchors. A
projection rebuild may remove a row from a derived index, but it cannot remove
or hide the source version from historical or deep retrieval.

## Main implementation modules

| Module | Responsibility |
|---|---|
| `trace.v2.models` | Pydantic request contracts, retrieval budgets, proposal decisions, registries |
| `trace.v2.adapters` | deterministic text/HTML adapter normalization and binary-adapter boundary |
| `trace.v2.atomizer` | paragraph/bullet atomization with parser offsets |
| `trace.v2.service` | ingestion, retrieval, synthesis, consolidation, graph views, admin orchestration |
| `trace.v2.store` | append-only events, canonical records, anchors, projections, replay, snapshots |
| `trace.v2.worker` | lease-based at-least-once outbox delivery |
| `trace.v2.api` | versioned `/v2` HTTP routes and domain-error mapping |

## Lifecycle summary

1. An adapter retains original bytes and supplies parser text.
2. One transaction appends ingestion, attachment, atom-version, structural-edge, and outbox events.
3. The hot lexical projection is available before the `202` response.
4. Consolidation examines bounded local neighborhoods and emits evidence-backed proposals.
5. Promotion/rejection is explicit and event-logged.
6. Queries persist evidence bundles; synthesis reads only those bundles.
7. Replay validation compares an independent event fold with canonical records.

## Deployment boundary

The embedded `SqliteEventStore` is a correctness and replay adapter. A scale
deployment should keep the public models and service semantics while replacing
storage responsibilities with PostgreSQL, private S3-compatible object
storage, OpenSearch, Qdrant, NATS JetStream, Redis, and policy-controlled model
providers. See the production topology, the 100K baseline, and the 1M gate in
[v2-architecture.md](v2-architecture.md).

## Legacy material

The former `trace.core`, `trace.agents`, `trace.events`, and frontend modules
remain in the working tree as historical prototype material. They are not
loaded by the V2 entry point and are not part of the V2 storage contract.
