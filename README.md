# Trace V2

Trace V2 is a headless, text-first memory substrate. It accepts disorganized source material, preserves the source as immutable evidence, and builds queryable projections around that evidence. The system is intentionally documentless internally: a document is an ingress envelope or a generated view, never the owner of a memory atom.

The canonical truth is an append-only Atom/Event Spine. Graph relations, lexical indexes, dense vectors, hierarchy summaries, schemas, salience, caches, and generated reports are projections. Projections may be replaced, replayed, or pruned without deleting source evidence.

The public runtime is mounted only under `/v2`. The previous document/project API is not loaded by [main_api.py](main_api.py), and the old frontend is not an architectural dependency.

## Current implementation boundary

The repository contains a complete embedded V2 foundation and the interfaces needed to move the projections to distributed services:

| Area | Implemented now | Production boundary |
|---|---|---|
| Canonical Spine | Transactional SQLite event store with immutable records | PostgreSQL event ledger and adjacency tables |
| Raw evidence | Content-addressed private local object store | S3-compatible private object storage |
| Ingestion | Text, Markdown, code, transcripts, HTML, UTF-8 files, and PDF text extraction | Policy-controlled adapter workers for more formats and URLs |
| Atomization | Paragraph-first, independent bullets, bounded sentence splitting, source offsets | Same deterministic contract, distributed workers |
| Fast retrieval | Workspace/time/facet/privacy filtering and lexical ranking | OpenSearch BM25 plus Qdrant ANN and reranking providers |
| Consolidation | Bounded local lexical-neighbor proposals; no automatic semantic promotion | ANN/lexical/graph neighborhoods and model-backed proposal workers |
| Durable fan-out | Transactional outbox and lease-based at-least-once worker | NATS JetStream adapter |
| Working state | Rebuildable hot inbox and SQLite projection revisions | Redis TTL state and sharded materialized indexes |

The embedded path is designed for correctness, replay drills, and local development. It is not a claim that a single SQLite file is the 10-million-chunk deployment profile.

## Core invariants

Trace V2 enforces these rules at the storage boundary:

1. A source atom version is never overwritten or deleted during ordinary operation. An edit appends a successor version.
2. `as_of_event` and history reads can select the exact earlier version, while default reads select the latest version visible at the requested time.
3. A merge is represented as an `alias_of` edge. A split creates child atoms with `CHILD_OF` lineage. Neither operation replaces the parent evidence.
4. Trusted semantic relations and promoted derived nodes require one or more evidence anchors to exact atom-version IDs.
5. Structural `NEXT` edges are immutable facts. Their ranking influence may change, but the evidence is not decayed away.
6. Generated synthesis is noncanonical. It becomes memory only through an evidence-backed proposal and an explicit promotion decision.
7. Idempotency keys are checked against the event payload hash. Re-delivery with the same content returns the original durable result; reuse with different content is a conflict.
8. Projection rebuilds can delete derived rows, but cannot make a Spine atom or its attachment unreachable.

## Quick start

Install the locked environment:

```powershell
uv sync
```

Start the API:

```powershell
uv run uvicorn main_api:app --reload
```

Or use the small operational entry point:

```powershell
uv run python main.py serve --host 127.0.0.1 --port 8000
```

The default embedded paths are:

```text
TRACE_DB_PATH=.trace/trace_v2.db
TRACE_OBJECT_ROOT=.trace/objects
```

Set those environment variables to place the database and private objects elsewhere. Do not expose the object root as a static web directory.

Check that the application is running:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/v2/health
```

## Capture material

`POST /v2/ingestions` accepts normalized text plus a source envelope. The source envelope can identify a Markdown file, transcript, code file, URL adapter, or upstream parser. The core does not fetch arbitrary URLs; a URL connector must fetch and policy-filter the material before sending its normalized text while retaining the original artifact privately.

```powershell
$body = @{
  workspace_id = "research"
  text = "A source paragraph.\n\n- An independently addressable bullet."
  actor = "analyst"
  visibility = "private"
  source = @{
    title = "notes.md"
    uri = "memory://research/notes.md"
    media_type = "text/markdown"
    adapter = "markdown"
  }
  idempotency_key = "research-notes-2026-08-03"
} | ConvertTo-Json -Depth 8

Invoke-RestMethod http://127.0.0.1:8000/v2/ingestions `
  -Method Post -ContentType application/json -Body $body
```

The response is `202 Accepted` after the event transaction and hot lexical projection are durable. It includes the ingestion ID, atom count, event offsets, parsing status, lexical status, and pending consolidation status.

For files, use `POST /v2/ingestions/upload` as multipart form data:

```powershell
curl.exe -X POST http://127.0.0.1:8000/v2/ingestions/upload `
  -F "workspace_id=research" `
  -F "actor=analyst" `
  -F "file=@notes.md;type=text/markdown"
```

The upload path keeps the original bytes as the attachment. HTML is converted to parser text with scripts and styles removed. PDFs use `pypdf` extraction; the PDF bytes remain the source attachment. If line endings or adapter parsing changes the text, the normalized parser artifact is retained as a second private object so source offsets remain reproducible.

## Atomization and source order

The atomizer in [atomizer.py](src/trace/v2/atomizer.py) applies a deterministic policy:

- split on blank-line paragraph boundaries;
- split bullet and numbered-list items independently;
- keep ordinary multi-line paragraphs together;
- split unusually long material at sentence boundaries, falling back to a bounded character cut when no sentence boundary is available;
- store `start`, `end`, `ordinal`, and `parser_location` offsets in the atom version properties.

Each atom receives a stable node identity and an immutable version. Consecutive atoms from one ingestion receive a trusted `NEXT` edge. Reconstructing source order therefore requires only the attachment, atom offsets, and structural edges; no generated document is authoritative.

## Query and synthesis

`POST /v2/queries` takes:

- `query`: user text;
- `workspace_id`: tenant/workspace scope;
- `as_of_event`: optional event offset for historical retrieval;
- `facets`: optional generic facet requirements;
- `privacy_context`: allowed visibility values or other policy inputs;
- `retrieval_budget`: `fast`, `standard`, `graph`, `hierarchy`, or `deep` mode plus candidate limits.

The embedded control path tokenizes the query, filters current atom versions, scores lexical matches, applies phrase and temporal signals, and stores an evidence bundle. A result contains:

```json
{
  "atom_version_id": "...",
  "node_id": "...",
  "excerpt": "...",
  "source_location": {
    "attachment_id": "...",
    "start": 0,
    "end": 42,
    "parser_location": "char:0-42"
  },
  "temporal_status": "current",
  "channel_scores": {"lexical": 2.1, "dense": 0.0, "hot_inbox": 1.0},
  "graph_paths": []
}
```

The bundle ends in one of three states:

- `answerable`: selected evidence supports a response;
- `ambiguous`: multiple candidates are too close to choose confidently;
- `insufficient_evidence`: no selected atom supports the query.

`POST /v2/syntheses` accepts only an evidence bundle ID. It returns a disposable rendering and citations back to atom versions; it does not write an answer into canonical memory. A caller should preserve the bundle ID with any report so a reviewer can reproduce the evidence selection.

## Self-organization and proposals

Consolidation is deliberately slower and reversible. `POST /v2/ingestions/{id}/consolidate` compares changed atoms with a bounded local neighborhood and creates low-confidence `edge` proposals for review. It does not assign a semantic cluster at write time and does not create a trusted relation merely because two texts share words.

Proposals contain:

- workspace and proposal type;
- candidate edge/derived-node properties;
- one or more evidence atom-version IDs;
- confidence and model version;
- pending/promoted/rejected status;
- event offsets for creation and decision.

Promotion validates workspace and evidence scope, then materializes either a versioned edge or a generic derived node such as a Holon, schema, claim, or summary. The derived object receives evidence anchors before the `proposal.promoted` decision is appended. Rejection records the reason without deleting the candidate.

## Versions, aliases, and historical reads

Edit an atom without destroying its prior version:

```powershell
$edit = @{ content = "The corrected source statement."; actor = "reviewer"; idempotency_key = "edit-42" } |
  ConvertTo-Json
Invoke-RestMethod http://127.0.0.1:8000/v2/nodes/<node-id> -Method Patch `
  -ContentType application/json -Body $edit
```

Use `GET /v2/nodes/{node_id}/history` for all versions. Use `GET /v2/nodes/{node_id}?as_of_event=<offset>` to recover the version visible at a historical event boundary. Aliases and splits have dedicated endpoints and append lineage relations rather than mutating source rows.

## Durable outbox and recovery

Every canonical event and its outbox row are written in one SQLite transaction. `OutboxWorker` leases pending rows, calls a publisher, and marks the event published only after success. A failed worker releases the lease; a later worker may deliver the same immutable `event_id` again. Consumers must deduplicate by event ID.

Operational endpoints include:

| Endpoint | Purpose |
|---|---|
| `GET /v2/admin/replay?workspace_id=...` | Fold Spine event payloads independently and compare canonical nodes, versions, edges, anchors, and attachments. |
| `POST /v2/admin/projections/reconcile` | Rebuild the hot inbox from current immutable versions. |
| `GET /v2/admin/projections` | Inspect projection revision and last-applied event offsets. |
| `POST /v2/admin/snapshots` | Record an event offset and deterministic state hash. |
| `POST /v2/admin/reindex` | Register an index revision and rebuild the embedded hot projection. |
| `POST /v2/admin/models` | Register provider/model purpose and version. |
| `POST /v2/admin/experiment-manifests` | Record corpus, code, model, index, and parameter versions. |
| `GET /v2/admin/events` | Inspect an auditable event range. |
| `POST /v2/admin/compaction` | Log a safe compaction pass; embedded policy retains Spine evidence. |

## Production topology and scale plan

The V2 API and service layer do not expose database handles to clients. For a distributed deployment, retain the same contracts behind purpose-built adapters:

| Responsibility | Target service |
|---|---|
| append-only ledger, canonical IDs, policies, adjacency, jobs | PostgreSQL |
| original blobs, parser artifacts, attachments | private S3-compatible storage |
| lexical retrieval and exact terms | OpenSearch |
| versioned dense namespaces | Qdrant |
| durable event fan-out | NATS JetStream |
| TTL working memory and query cache | Redis |

The migration path is snapshot-plus-delta replay: register a new index/model namespace, backfill from a Spine snapshot, replay later events, validate parity, and gradually move traffic. Do not replace an active vector namespace in place.

The 10M-chunk gate requires workspace/time partitioning, bounded local organization, no all-pairs clustering, ANN recall checks against sampled exact search, projection parity monitoring, orphan-vector detection, and load tests at 100K, 1M, and 10M chunks. Target latency gates are fast p95 <= 2 seconds, standard p95 <= 5 seconds, and separately budgeted deep p95 <= 90 seconds. Quality gates are workload-specific evidence contracts, not universal recall claims.

## Verification

Run the dependency-independent foundation suite:

```powershell
.\.venv\Scripts\python.exe -m unittest -v tests\test_v2_foundation.py
```

The tests cover:

- duplicate ingestion and idempotency conflicts;
- paragraph/bullet atomization and structural `NEXT` reachability;
- raw attachment retention and HTML/file adapters;
- immutable edit history and historical reads;
- evidence-backed semantic promotion;
- replay validation and projection reconciliation;
- auditable query bundles and explicit insufficient-evidence abstention.

Run the lock consistency check before packaging:

```powershell
uv lock --check
```

See [docs/v2-architecture.md](docs/v2-architecture.md) for the deeper design contract and [src/trace/v2](src/trace/v2) for the implementation boundary.

## Production controls

The V2 service now exposes a durable workflow ledger at `POST /v2/jobs`,
`GET /v2/jobs/{id}`, and the cancel/retry actions. Long-running hierarchy,
schema, benchmark, consolidation, reindex, and replay routes honor
`Prefer: respond-async` (or `TRACE_ASYNC_WORKFLOWS=true`) and return a job ID;
the synchronous embedded response remains available for local compatibility.
Completion callbacks can be registered under `/v2/webhooks`; secrets are
shown only at creation/rotation and completion requests carry an HMAC
signature.

Set `TRACE_AUTH_REQUIRED=true` in production. Requests then require an OIDC
JWT (`TRACE_JWT_SECRET` for HS256 or a pinned `TRACE_OIDC_JWKS_JSON` for
RS256) or a scoped API key. Workspace, visibility, model, and actor scope is
derived from the authenticated principal; caller-supplied escalation is
rejected. `X-Request-ID`, structured problem responses, rate/payload limits,
opaque page cursors, and `/v2/ready`/`/v2/metrics` are built into the API.

Install the optional infrastructure adapters with `uv sync --extra
production`. Select `TRACE_REPOSITORY=postgres`, `TRACE_OBJECT_STORE=s3`,
`TRACE_OPENSEARCH_INDEX`, `TRACE_QDRANT_COLLECTION`, `TRACE_NATS_URL`, and
`TRACE_REDIS_URL` as appropriate. The default path remains a replayable local
control adapter; projections and indexes are still rebuildable and never
replace raw atom versions or private attachments as factual truth.
