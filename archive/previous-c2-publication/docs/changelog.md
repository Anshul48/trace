# Changelog

## 2.0.0 - Trace V2 foundation

### Added

- Replaced the active runtime entry point with a versioned headless `/v2` FastAPI surface.
- Added an append-only event Spine with event IDs, stream sequences, causation/correlation metadata, payload hashes, idempotency keys, and transactional outbox rows.
- Added generic workspace nodes, immutable node versions, versioned edges, evidence anchors, security metadata, and projection revisions.
- Added paragraph-first atomization, independent list items, exact parser offsets, structural `NEXT` relations, attachment retention, and replay validation.
- Added text, Markdown, code, transcript, HTML, file, and PDF adapter boundaries while preserving original private attachments.
- Added atom editing, history, `as_of_event` reads, aliases, splits, lineage, saved queries, frozen queries, and evidence-bundle synthesis.
- Added lexical retrieval with explicit sufficiency/abstention states and a documented extension boundary for OpenSearch, Qdrant, reranking, and deep synthesis.
- Added bounded local-neighbor consolidation and reversible evidence-backed proposals for edges and generic derived nodes.
- Added outbox leasing, at-least-once delivery primitives, projection reconciliation, snapshots, replay reports, model/index registries, experiment manifests, and safe compaction logging.
- Added a dependency-independent unittest foundation suite covering capture, adapters, versions, proposals, replay, retrieval, and abstention.

### Compatibility boundary

The former project/document API, agent event bus, generated Markdown workflow,
watcher, and frontend remain historical prototype material in the working tree.
They are not mounted or loaded by the V2 runtime. No legacy API or data
migration is promised by this release.

### Production control boundary

Added repository protocols plus optional PostgreSQL event/outbox schema,
tenant-prefixed encrypted S3, OpenSearch BM25, Qdrant dense, NATS JetStream,
and Redis adapters. Added durable workflow jobs with leases, cancellation,
retry metadata, signed completion webhooks, OIDC/API-key identity and tenant
scope enforcement, opaque pagination, readiness, metrics, and model-gateway
redaction/audit policy. SQLite and the private local object store remain the
embedded correctness adapter; the production services are selected through
environment configuration and the optional `production` dependency extra.

## Historical prototype releases

Pre-V2 releases built a document-oriented project UI, LLM extraction agents,
SQLite/Chroma projections, Obsidian serializers, and filesystem reverse-sync.
Those records are retained here only as historical context. Their schemas,
endpoints, and generated files are not canonical Trace V2 contracts.
