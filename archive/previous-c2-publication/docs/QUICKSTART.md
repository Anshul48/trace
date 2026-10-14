# Quickstart Guide

This guide walks you through setting up, ingesting, querying, and verifying evidence with **Trace** and the **Cortical Substrate**.

---

## 1. Installation

Trace supports Python 3.12+ on both Linux and Windows.

### Lightweight Local Core (Phase 1)
```bash
pip install trace-local
```

### Full Cortical Substrate & Production Suite
```bash
pip install "trace-local[production]"
```

Or install from source:
```bash
git clone https://github.com/Anshul48/trace.git
cd trace
pip install -e ".[production,test]"
```

---

## 2. CLI Walkthrough

### Initialize a Local Workspace
Trace is local-first and requires an explicit storage directory. No background servers or cloud accounts are needed:

```bash
trace init --data-dir ./my-trace-data
```
This initializes a transactional SQLite database, content-addressed blob storage, and external FTS5 indexes.

### Ingesting Normalized Records
Trace takes normalized JSONL lines as input. Each line represents a single immutable source atom:

```bash
cat << 'JSONL' > records.jsonl
{"record_id": "doc-001", "document_name": "Storage_Architecture.md", "file_uri": "file:///docs/storage.md", "content": "The storage substrate guarantees total-hot disk footprint under 3.0x raw admitted text.", "metadata": {"author": "Systems Team", "component": "storage"}}
{"record_id": "doc-002", "document_name": "Retrieval_Pipeline.md", "file_uri": "file:///docs/retrieval.md", "content": "Tier 1 lexical short-circuit executes in under 5ms using external FTS5 and lex_sig bloom signatures.", "metadata": {"author": "Search Team", "component": "retrieval"}}
JSONL

trace ingest --data-dir ./my-trace-data ./records.jsonl
```

### Querying Evidence
Trace returns raw supporting evidence atoms rather than hallucinating an answer:

```bash
trace query --data-dir ./my-trace-data "storage substrate 3.0x"
```

Output:
```json
{
  "query": "storage substrate 3.0x",
  "evidence": [
    {
      "atom_id": "atom-001-...",
      "document_name": "Storage_Architecture.md",
      "matched_span": "The storage substrate guarantees total-hot disk footprint under 3.0x raw admitted text.",
      "score": 0.892,
      "offsets": [0, 88],
      "content_hash": "sha256-..."
    }
  ],
  "status": "grounded"
}
```

If no relevant evidence exists in the corpus, Trace will **never invent information**. It returns fail-closed `insufficient_evidence`:

```bash
trace query --data-dir ./my-trace-data "quantum teleportation algorithms"
```
```json
{
  "query": "quantum teleportation algorithms",
  "evidence": [],
  "status": "insufficient_evidence"
}
```

### Inspecting System Status & Storage
View real-time physical on-disk storage metrics, memory consumption, and index health:

```bash
trace status --data-dir ./my-trace-data
```

---

## 3. Python SDK Walkthrough

### Basic Ingestion and Search
```python
from trace_local import Trace

with Trace.open("./my-trace-data") as trace:
    # 1. Ingest an atom
    atom = trace.ingest({
        "record_id": "adr-042",
        "document_name": "ADR 042 - Concurrency.md",
        "file_uri": "file:///eng/adr/042.md",
        "content": "Windows Epoch RCU uses active reader leases to prevent WinError 32 file-locking crashes during generation pointer swaps.",
        "metadata": {"type": "architecture_decision"},
    })
    print(f"Ingested Atom ID: {atom['atom_id']}")

    # 2. Query for evidence
    results = trace.query("Epoch RCU reader leases")
    for hit in results["results"]:
        print(f"Matched: {hit['document_name']}")
        print(f"Span: {hit['matched_span']}")
        print(f"Hash: {hit['content_hash']}")
```

---

## 4. Advanced: Cortical Substrate V2 API

The Cortical Substrate introduces hierarchical macro-clustering, lateral inhibition, and multi-tier retrieval:

```python
from trace.v2.store import LocalStore
from trace.v2.retrieval import RetrievalCoordinator, RetrievalConfig
from trace.v2.index_manager import IndexManager

# Open transactional store
store = LocalStore("./my-trace-data/store.db")
index_mgr = IndexManager("./my-trace-data/indexes")

# Configure 3-Tier Retrieval Cascade
coordinator = RetrievalCoordinator(
    store=store,
    index_manager=index_mgr,
    config=RetrievalConfig(
        tier1_enabled=True,
        tier2_enabled=True,  # Hierarchical TOC beam search
        tier3_enabled=True,  # Hybrid dense/BM25 fallback
        grounding_strict=True,
    ),
)

# Execute 3-Tier query
query_result = coordinator.retrieve("Explain Epoch RCU pointer swap")
print(f"Executed Path: {query_result.resolution_tier}")
print(f"Latency: {query_result.latency_ms:.2f} ms")
print(f"Grounding Status: {query_result.grounding_decision}")
```

---

## 5. Next Steps

- Explore the detailed [Cortical Substrate Architecture](CORTICAL_SUBSTRATE.md).
- Review the [Benchmark & Qualification Guide](BENCHMARKS.md) to inspect live 100k qualification results.
- Read [CONTRIBUTING.md](../CONTRIBUTING.md) to learn how to add features and run verification tests.
