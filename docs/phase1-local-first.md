# Trace Phase 1 local-first architecture

## Scope

Phase 1 is a public Apache-2.0 PyPI alpha for Windows and Linux. Its job is
to prove that engineering information can be captured locally with complete
provenance, organized through bounded and reviewable derivations, and
retrieved as raw supporting evidence.

It is not a managed availability, tenancy, billing, GCP, 10-million-atom, or
500-QPS certification. Those are Phase 2 concerns and must not be represented
as a property of this embedded alpha.

## Deployment shape

One LocalTrace instance is rooted at one caller-selected directory:

~~~text
selected-data-directory/
  trace.sqlite3             transactional canonical ledger and projections
  trace.sqlite3-wal         SQLite transactional working file when active
  attachments/
    <hash-prefix>/<hash>    retained source UTF-8 bytes
~~~

The normal SDK and CLI do not bind a socket, create an account, send
telemetry, invoke Docker, fetch URLs, parse caller paths, download a model, or
contact a cloud provider. An operator can choose an optional locally installed
embedding or reranking plugin for an individual bounded query.

## Canonical data

The SQLite canonical store contains:

- immutable documents with exact document name, source URL, file URI, caller
  content hash, media type, metadata, image-description blocks, and raw input
  record;
- content-addressed retained attachment bytes and their independently verified
  storage hash;
- one immutable source atom per normalized input record;
- append-only events for ingestion, review decisions, navigation publication,
  projection rebuilds, and imports;
- review proposals with exact source-atom anchors; and
- published navigation summaries with exact extractive spans and anchors.

No public operation edits or deletes an existing source atom. A caller that
needs a correction ingests a new immutable source record and preserves the
original provenance.

The data model is deliberately independent of SQLite row IDs. Stable UUIDs,
event payloads, content hashes, and JSONL export are the portable canonical
contract for a future PostgreSQL or distributed adapter.

## Ingress boundary

Trace receives caller-normalized JSON or JSONL records. A record carries:

- a document name;
- a source URL or file URI;
- normalized text;
- a caller content hash;
- arbitrary JSON metadata; and
- optional caller-provided image-description blocks.

Trace validates structure but does not transform those source values. It does
not infer source content from an identifier, auto-fetch an URL, open a local
path, prune metadata, or replace source text with a model rendering. It
retains the raw text as an attachment before adding it to lexical projection.

An optional caller record ID provides idempotency. Reusing that ID for exactly
the same source record returns the existing atom. Reusing it for different
content is rejected rather than overwriting source evidence.

## Projections and retrieval

The canonical atom is the source of truth. SQLite FTS5 is a replaceable local
lexical projection; a deterministic term projection is used when a Python
SQLite build lacks FTS5. Both index atom text plus document names, URLs, file
URIs, and metadata.

Default retrieval is offline lexical retrieval with an explicit candidate
limit. Query results include raw text and a complete citation object back to
the atom, attachment, hashes, source URL or file URI, document name, metadata,
and image descriptions.

An explicitly requested local embedding plugin or reranker receives only the
bounded lexical candidate set. Trace has no model auto-discovery or cloud
fallback. Plugin identifiers are returned in query diagnostics so a result can
be reproduced.

Projection rebuild deletes and recreates only lexical rows. It compares the
indexed source-atom count and canonical atom hash before reporting parity. A
rebuild cannot delete an event, attachment, document, atom, or proposal.

## Derived knowledge governance

Relations, schemas, factual claims, and feedback-derived topology are stored
as pending proposals. They require one or more immutable source-atom IDs and
an explicit reviewer decision. Retrieval feedback has no direct graph mutation
path.

The one automatic derivation is a navigation-only summary. Every published
section must name an evidence atom and be an exact substring of that atom.
This makes it useful as navigation while preventing an unsupported factual
claim from becoming canonical because it looked plausible.

## Resource adaptation

Trace measures local free disk, database and attachment growth, projection
growth, cache occupancy, queued work, one-minute ingestion rate, and observed
query p95 latency. It computes disk headroom on the selected volume rather
than imposing an installation minimum.

When headroom is tight, it bounds the result cache, sets background concurrency
to zero, and defers projection or organization work. Before an ingest, import,
proposal, or other write, it estimates the necessary WAL and attachment space.
If accepting it would cross the transactional reserve, Trace returns a
retriable capacity error and leaves canonical data intact.

## Portability and recovery

Export is a zip archive containing a manifest, event JSONL, documents,
attachments, atoms, proposals, navigation summaries, and retained attachment
bytes. Import verifies archive member safety, attachment hashes and lengths,
event payload hashes, stable ID conflicts, and source anchor references before
rebuilding the local lexical projection.

The operator can verify provenance and projection parity at any time with the
SDK or CLI. Recovery is therefore import, rebuild, and verify rather than a
best-effort cache restoration.
