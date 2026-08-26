# Trace

Trace is a local-first, evidence-preserving retrieval tool for messy
engineering information. It has two supported product surfaces:

- Phase 1 is the lightweight Apache-2.0 Python SDK and CLI for Windows and
  Linux, with standard-library-only operation.
- Trace V2 is the production service surface for tenant-scoped ingestion,
  revisioned retrieval, and evidence bundles. It remains subject to the
  measured production gates in the V2 runbook; it is not presented as an
  experimental side path.

It stores one immutable source atom for each caller-normalized record, retains
the original text and provenance in a selected local directory, and returns
raw supporting evidence rather than silently replacing it with a summary.
Normal operation has no server, account, telemetry, Docker requirement, or
runtime network access.

## Install

The Phase 1 core uses only the Python standard library.

~~~powershell
pip install trace-local
trace init --data-dir .\my-trace-data
~~~

Choose the data directory explicitly. It contains a transactional SQLite
ledger, content-addressed UTF-8 attachments, and rebuildable lexical state.
Do not put secrets in source records unless that local directory is protected
appropriately for the operator.

The SDK uses the import name trace_local because Python reserves trace for its
own standard-library tracing module; the installed CLI remains trace.

## Trace V2 service

Install the explicit V2 or production dependency set when deploying the
service. The Phase 1 command remains dependency-light.

~~~powershell
pip install "trace-local[production]"
trace-v2 --help
~~~

V2 retains the same evidence-first import/export semantics while adding a
PostgreSQL Spine, private object storage, revisioned external indexes, durable
workers, and replaceable Cortex projections. See the
[V2 architecture](docs/v2-architecture.md) and
[production runbook](docs/production-runbook.md).

## Ingest normalized JSONL

Trace deliberately does not fetch URLs, read a named file, parse a PDF, or run
OCR. The caller supplies normalized text and retains all useful provenance.
Each JSONL line becomes one immutable source atom.

~~~json
{
  "record_id": "adr-017",
  "document_name": "ADR 017 - Event storage.md",
  "file_uri": "file:///C:/Engineering/ADR/ADR%20017.md",
  "content": "The event ledger is local and append-only.",
  "content_hash": "sha256-from-the-caller-or-upstream-parser",
  "metadata": {
    "repository": "platform",
    "source_path": "C:\\Engineering\\ADR\\ADR 017.md"
  },
  "image_descriptions": [
    {
      "source_block": "figure-2",
      "description": "A diagram of the local event ledger."
    }
  ]
}
~~~

Document name, one source URL or file URI, text (content or text), and
metadata are retained as searchable provenance. A caller normally provides a
content hash; if omitted, Trace records a hash of the provided UTF-8 text as a
local convenience. It never rewrites supplied URLs, paths, document names,
metadata values, or image-description blocks.

~~~powershell
trace ingest --data-dir .\my-trace-data .\records.jsonl
trace query --data-dir .\my-trace-data "append-only event ledger"
trace atom --data-dir .\my-trace-data <atom-id>
~~~

Queries use bounded offline SQLite lexical search by default and return source
text, attachment IDs, content hashes, URLs or file URIs, document names, and
metadata with every hit. The state insufficient_evidence is returned instead
of an invented answer when there is no matching source atom.

## SDK

~~~python
from trace_local import Trace

with Trace.open("./my-trace-data") as trace:
    stored = trace.ingest({
        "record_id": "adr-017",
        "document_name": "ADR 017.md",
        "file_uri": "file:///C:/Engineering/ADR/ADR%20017.md",
        "content": "The event ledger is local and append-only.",
        "content_hash": "upstream-sha256",
        "metadata": {"repository": "platform"},
    })

    evidence = trace.query("event ledger")
    assert evidence["results"][0]["source"]["attachment_id"]
~~~

Optional locally installed embedding or reranking plugins are explicit. Trace
does not download or invoke a model by default:

~~~python
evidence = trace.query(
    "event ledger",
    mode="rerank",
    reranker_plugin="my_local_plugins:reranker",
)
~~~

Plugin references use package.module:object syntax. They run only for the
requested query and only over a bounded lexical candidate set. A cloud model
is not a default dependency or a fallback path.

## Derived knowledge and review

Relations, schemas, claims, and feedback-derived topology are proposals with
immutable source-atom anchors. They remain pending until an explicit reviewer
decision:

~~~powershell
trace propose --data-dir .\my-trace-data relation --candidate '{"relation":"depends_on"}' --evidence <atom-a> <atom-b>
trace review --data-dir .\my-trace-data <proposal-id> approved --reviewer alice
~~~

The only automatically published derivation is a navigation summary made of
exact extractive source spans. Trace rejects an auto-published navigation
summary if an excerpt is not present verbatim in its cited atom.

~~~powershell
trace summarize --data-dir .\my-trace-data --atom <atom-a> --atom <atom-b>
~~~

## Resource-aware local operation

~~~powershell
trace status --data-dir .\my-trace-data
trace rebuild --data-dir .\my-trace-data
trace verify --data-dir .\my-trace-data
~~~

Status reports free disk, reserved transactional headroom, database and
attachment growth, lexical-index growth, cache pressure, queue depth,
ingestion rate, and observed query p95 latency. Trace lowers background
concurrency to zero and defers rebuild or organization work under pressure.
It returns a retriable capacity response before accepting a write that could
consume SQLite safety headroom; canonical data is never pruned to make room.

Hardware changes speed and capacity; they are not an installation gate. Report
benchmark hardware, current source-atom count, average tokens per atom, and
immutable-version growth rather than making an unqualified token-capacity
claim.

## Export, import, and recovery

~~~powershell
trace export --data-dir .\my-trace-data .\trace-evidence.zip
trace import --data-dir .\restored-trace-data .\trace-evidence.zip
trace rebuild --data-dir .\restored-trace-data
trace verify --data-dir .\restored-trace-data
~~~

The portable archive contains the event lineage, immutable documents, source
atoms, proposals, navigation summaries, and retained attachment bytes.
Import verifies attachment and event payload hashes, preserves IDs, and
rebuilds lexical state from the canonical atoms. Existing output archives are
not overwritten unless the overwrite option is supplied.

## Pilot acceptance

Phase 1 validation uses public reproducible fixtures and privately run,
owner-approved corpora that never leave the operator's machine. The release
gate requires at least 100 frozen judged queries covering direct lookup,
dependency, contradiction, chronology, navigation, and out-of-scope requests;
at least 80% complete-gold-evidence coverage, 90% citation precision, 70%
reviewer approval of navigation summaries, declared-hardware p95 reporting,
and zero critical provenance, privacy, or destructive-data defects.

See [the local architecture](docs/phase1-local-first.md) and
[the validation contract](docs/phase1-validation.md) for the precise Phase 1
scope and reproducibility requirements. Machine-readable normalized-record and
export-manifest contracts are in [schemas](schemas).

## Development

~~~powershell
python -m unittest -v tests\test_phase1_local.py
python -m trace_local --help
uv lock --check
~~~

V2 deployment and scale certification must reuse this export/event contract;
no production projection may replace source truth semantics.
