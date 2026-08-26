# Trace V2 data contracts

The source of truth for API validation is [src/trace/v2/models.py](../src/trace/v2/models.py). This page explains the fields in operational terms; it is not a replacement for the Pydantic models.

## Ingestion

`IngestionRequest` requires a non-empty `workspace_id` and normalized `text`.
`source` identifies the adapter and provenance:

```json
{
  "workspace_id": "research",
  "text": "A paragraph of source evidence.",
  "actor": "analyst",
  "visibility": "private",
  "source": {
    "title": "notes.md",
    "uri": "memory://research/notes.md",
    "media_type": "text/markdown",
    "adapter": "markdown",
    "metadata": {"capture_method": "upload"}
  },
  "idempotency_key": "research-notes-001"
}
```

The multipart upload route accepts original bytes and selects HTML/PDF/text
adapters from media type and filename. Original objects and parser artifacts
are private; only bounded excerpts and provenance are returned by retrieval.

## Atom versions

There is no domain-specific `HippocampalTrace` table in V2. An atom is a generic
node with the `atom` facet and a `node_version` containing:

| Field | Meaning |
|---|---|
| `atom_version_id` | immutable evidence version identity |
| `node_id` | stable identity across edits and lineage operations |
| `version` | per-node successor number |
| `content` | parser text for this exact version |
| `content_hash` | normalized content digest |
| `properties.ingestion_id` | capture operation that introduced the atom |
| `properties.attachment_id` | private raw-artifact reference |
| `properties.source_start/end` | offsets into normalized parser text |
| `properties.parser_location` | human-readable offset, currently `char:start-end` |
| `properties.source` | adapter and source provenance |

The `atom` facet is a generic indexable property, not an ontology assertion.
An edit creates a new version; the old content and offsets remain addressable.

## Edges and evidence

`edge_versions` accept only the audited relation contract in
`models.py`/`store.py`. Structural relations are `NEXT`, `CHILD_OF`,
`DERIVED_FROM`, `CONTAINS`, and `alias_of`; reviewed evidence relations are
`supports`, `contradicts`, `depends_on`, `implements`, and `example_of`.
Generic `semantic` links and opaque relation names are rejected on write.
Similarity, clustering, affinity, feedback, and activation are replaceable
Cortex projections, never canonical evidence edges.

Each trusted non-structural edge requires `evidence_atom_version_ids`. The
store expands those IDs into `evidence_anchors` containing:

```json
{
  "target_kind": "edge_version",
  "target_id": "edge-version-id",
  "source_atom_version_id": "atom-version-id",
  "source_start": 0,
  "source_end": 42,
  "parser_location": "char:0-42",
  "quote_hash": "sha256-of-source-content"
}
```

Promoted Holons, schemas, claims, and summaries are generic derived nodes and
receive `node_version` anchors under `target_kind=node_version`.

## Queries and evidence bundles

`QueryRequest` makes retrieval scope explicit:

- `workspace_id`: tenant boundary;
- `as_of_event`: optional historical event offset;
- `facets`: required generic facets;
- `privacy_context`: visibility policy inputs;
- `retrieval_budget`: mode and candidate limits.

`POST /v2/queries` returns a persisted `evidence_bundle_id`, results, source
locations, temporal status, channel scores, graph paths, and one sufficiency
state: `answerable`, `ambiguous`, or `insufficient_evidence`.

The embedded lexical control path reports `dense: 0.0` until a versioned vector
provider is configured. This is intentional: a missing model/index must not be
represented as a fabricated confidence score.

## Proposals

`ProposalCreateRequest` requires at least one evidence atom-version ID and
records `confidence` and `model_version`. Proposal types are `edge`, `holon`,
`schema`, `merge`, `summary`, `contradiction_resolution`, and `claim`.

```text
pending --promote--> promoted + derived edge/node + anchors
pending --reject---> rejected + reason
```

Both transitions append decision events. A proposal is not a fact until the
promotion transaction has validated workspace and evidence scope.

## Versioned query objects

Saved queries preserve query logic and a name in a workspace. Frozen queries
also preserve the selected atom-version IDs, giving a stable historical set
even if default retrieval later prefers successor versions. Generated synthesis
is always a view of a bundle and has no canonical write path.

## Administrative contracts

`IndexRevisionRequest`, `ModelRegistrationRequest`, and
`ExperimentManifestRequest` capture model/provider versions, vector namespaces,
lexical revisions, corpus snapshots, code revisions, and parameters. These
fields make re-indexing and benchmark comparisons reproducible.

The replay endpoint is a validation operation, not a destructive migration. A
failed replay report should stop promotion and trigger investigation; it should
not be “fixed” by deleting the mismatched canonical row.
