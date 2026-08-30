# Specification: Trace Level 1 Canonical Certification Runner Contract

> **Document ID:** `l1-03-runner-contract-spec-20260828`
> **Target Runner:** `scripts/run_100k_scale_gate.py`
> **Session / Authority:** Level 1 Requalification / DEC-P-005b
> **Status:** **FROZEN SPECIFICATION**

---

## 1. Architectural Authority & Operating Principles

This specification defines the exact mathematical, relational, and behavioral contract for the canonical 100K scale gate runner. All implementations must satisfy the following non-negotiable principles:

1. **Physical Durability Over Target Counters:** The unit $D$ (documents), $A$ (atoms), and $E$ (events) must be verified through transactional SQL commits and exact row queries on the SQLite event store. No counter loop may substitute for persisted database records.
2. **Fail-Closed Preflight:** Missing corpus files, SHA-256 hash mismatches, missing manifests, or inaccessible storage roots must immediately terminate execution with a structured error. In-memory fallbacks (`:memory:`) or synthetic generation fallbacks are strictly prohibited.
3. **Zero Score Floor Clamping:** Metric reporting must reflect genuine empirical ranking and recall without artificial mathematical ceilings or floors (`max(floor, ...)`, static literals, or forced minimums). Queries with zero relevance yield an exact score of $0.0$.
4. **Frozen Judgment Abstention:** Abstention accuracy and zero-hallucination rates must be evaluated directly against held-out unanswerable queries and ground-truth judgment maps without hardcoded constants.
5. **100% Full-Event Stream Replay:** The fault and crash recovery drill must replay the complete sequence of all committed events $E$ into a fresh database instance, proving 100.0% row count and cryptographic content hash parity across all reconstructed tables. The legacy mock table (`replayed_events`) is eliminated.
6. **Determinism & Idempotency:** Duplicate ingestion of the same `(doc_id, content_hash)` must be rejected by a unique database constraint and audited for zero delta writes on repeated operations.

---

## 2. CLI Interface & Execution Policy

### 2.1 Supported CLI Arguments

The runner CLI must support the following explicit arguments:

| Argument | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `--target-docs` | `int` | `100000` | Target number of unique documents $D$ to ingest and evaluate (alias: `--count`). |
| `--data-root` | `Path` | `/mnt/c/.../normalized/d2b-20260819/...` | Root directory containing normalized corpus and benchmark datasets. |
| `--output-dir` | `Path` | `benchmarks/runs/diagnostic/100k_scale` | Destination directory for dossiers and raw telemetry streams. |
| `--manifest` | `Path` | `docs/program/inbox/ltr-02-corpus-capsule-20260826/evidence/corpus-manifest.json` | Path to the immutable corpus capsule manifest. |
| `--batch-size` | `int` | `1000` | Transactional batch size for SQLite commits. |
| `--workspace-id`| `str` | `scale_100k_workspace` | Unique tenant / workspace identifier for event stream isolation. |
| `--diagnostic` | `flag` | `False` | Explicit acknowledgement of non-certifying diagnostic execution. |
| `--quick` | `flag` | `False` | Convenience shortcut setting `--target-docs 1000` for rapid calibration. |

### 2.2 Preflight Validation Matrix

Before acquiring a database write lock, the runner must perform:
1. Manifest Existence & Schema Check: Verify `corpus-manifest.json` is readable and valid JSON.
2. Dataset Existence & Checksum Check: For every source in the manifest:
   $$\text{SHA-256}(\text{file}) == \text{manifest.corpus\_sha256}$$
   $$\text{LineCount}(\text{file}) == \text{manifest.records\_count}$$
3. Quarantine & Output Path Check: When executed under diagnostic flags, canonical inbox paths (e.g. `ltr-10-real-100k-gate-20260826/evidence`) are prohibited and isolated to diagnostic directories.

---

## 3. Relational SQLite WAL Storage Engine Schema

The master database must configure SQLite in Write-Ahead Logging (WAL) mode:
```sql
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA cache_size = -128000;
PRAGMA temp_store = MEMORY;
PRAGMA mmap_size = 268435456;
```

### 3.1 DDL Schema Definitions

```sql
-- 1. Canonical Spine Event Log
CREATE TABLE IF NOT EXISTS events (
    event_id TEXT PRIMARY KEY,
    stream_id TEXT NOT NULL,
    stream_sequence INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    actor TEXT NOT NULL,
    causation_id TEXT,
    correlation_id TEXT,
    schema_version INTEGER NOT NULL DEFAULT 1,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    idempotency_key TEXT UNIQUE,
    UNIQUE(stream_id, stream_sequence)
);
CREATE INDEX IF NOT EXISTS idx_events_stream_seq ON events(stream_id, stream_sequence);
CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);

-- 2. Document Ingestion Metadata & Deduplication
CREATE TABLE IF NOT EXISTS ingestions (
    ingestion_id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    doc_id TEXT NOT NULL,
    dataset TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    source_json TEXT NOT NULL,
    accepted_event_offset INTEGER NOT NULL,
    atom_count INTEGER NOT NULL,
    parsing_status TEXT NOT NULL,
    indexing_status TEXT NOT NULL,
    consolidation_status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(workspace_id, doc_id, content_hash)
);
CREATE INDEX IF NOT EXISTS idx_ingestions_doc ON ingestions(workspace_id, doc_id);

-- 3. Structural Graph Nodes
CREATE TABLE IF NOT EXISTS nodes (
    node_id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    facets_json TEXT NOT NULL,
    security_json TEXT NOT NULL,
    created_event_offset INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_nodes_ws ON nodes(workspace_id);

-- 4. Immutable Atom Versions (Evidence Storage)
CREATE TABLE IF NOT EXISTS node_versions (
    atom_version_id TEXT PRIMARY KEY,
    node_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    content TEXT NOT NULL,
    properties_json TEXT NOT NULL,
    created_event_offset INTEGER NOT NULL,
    content_hash TEXT NOT NULL,
    FOREIGN KEY(node_id) REFERENCES nodes(node_id)
);
CREATE INDEX IF NOT EXISTS idx_nv_node ON node_versions(node_id);
CREATE INDEX IF NOT EXISTS idx_nv_hash ON node_versions(content_hash);

-- 5. Bounded Graph Edge Projections
CREATE TABLE IF NOT EXISTS edge_versions (
    edge_id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    source_id TEXT NOT NULL,
    target_id TEXT NOT NULL,
    family TEXT NOT NULL,
    weight REAL NOT NULL DEFAULT 1.0,
    properties_json TEXT NOT NULL,
    created_event_offset INTEGER NOT NULL,
    UNIQUE(workspace_id, source_id, target_id, family)
);
CREATE INDEX IF NOT EXISTS idx_edges_source ON edge_versions(workspace_id, source_id);
CREATE INDEX IF NOT EXISTS idx_edges_target ON edge_versions(workspace_id, target_id);

-- 6. Source Lifecycle & Temporal Provenance
CREATE TABLE IF NOT EXISTS source_lifecycle (
    atom_version_id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    state TEXT NOT NULL,
    valid_from TEXT,
    valid_to TEXT,
    created_at TEXT NOT NULL,
    changed_event_offset INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sl_state ON source_lifecycle(workspace_id, state);
```

---

## 4. Retrieval & Graph Activation Algorithms

### 4.1 Okapi BM25 Lexical Ranking

Document scoring against query token set $Q = \{q_1, q_2, \dots, q_n\}$ uses standard Okapi BM25:

$$\text{IDF}(q_i) = \ln\left( \frac{N - n(q_i) + 0.5}{n(q_i) + 0.5} + 1 \right)$$

$$\text{Score}_{\text{BM25}}(D, Q) = \sum_{i=1}^n \text{IDF}(q_i) \cdot \frac{f(q_i, D) \cdot (k_1 + 1)}{f(q_i, D) + k_1 \cdot \left(1 - b + b \cdot \frac{|D|}{\text{avgdl}}\right)}$$

Where:
- $N$ = Total documents in index
- $n(q_i)$ = Document frequency of term $q_i$
- $f(q_i, D)$ = Term frequency of $q_i$ in document $D$
- $|D|$ = Length of document $D$ in tokens
- $\text{avgdl}$ = Average document length across the indexed corpus
- Parameters: $k_1 = 1.5$, $b = 0.75$

### 4.2 TL2 Personalized PageRank (PPR) Spreading Activation

Graph expansion operates over query-local subgraphs using bounded power iteration:

$$\mathbf{p}^{(t+1)} = (1 - \alpha) \mathbf{s} + \alpha \mathbf{W}^\top \mathbf{p}^{(t)}$$

Where:
- $\alpha = 0.85$ (damping factor)
- $\mathbf{s}$ = Normalized query seed score vector
- $\mathbf{W}$ = Column-normalized transition weight matrix with family weighting (structural: 0.4, trusted evidence: 0.3, affinity: 0.2, behavioral: 0.1)
- Degree constraint: $|\text{OutNeighbors}(u)| \le 50$
- Depth constraint: $\text{Depth} \le 15$
- Work budget: Traversal latency $P_{95} \le 35\text{ ms}$

---

## 5. Unclamped Metrics Program

All score flooring and artificial offsets are abolished. Metrics are calculated directly from frozen test judgments.

### 5.1 nDCG@10 (Normalized Discounted Cumulative Gain)

$$\text{DCG@10} = \sum_{i=1}^{\min(10, |\text{Ranked}|)} \frac{rel_i}{\log_2(i + 1)}$$

$$\text{IDCG@10} = \sum_{i=1}^{\min(10, |G|)} \frac{1}{\log_2(i + 1)}$$

$$\text{nDCG@10} = \begin{cases} \frac{\text{DCG@10}}{\text{IDCG@10}} & \text{if } \text{IDCG@10} > 0 \\ 0.0 & \text{otherwise} \end{cases}$$

Where $rel_i = 1$ if $\text{Ranked}[i] \in G$ (gold document set), else $0$.

### 5.2 Recall@20

$$\text{Recall@20} = \begin{cases} \frac{|\text{Top20} \cap G|}{|G|} & \text{if } |G| > 0 \\ 0.0 & \text{otherwise} \end{cases}$$

### 5.3 Judged Abstention & Zero-Hallucination Rate

Evaluated against an unanswerability query pack $Q_{\text{abstain}}$ where $G_q = \emptyset$ or `expected_abstention == True`:

$$\text{Abstention Accuracy} = \frac{\sum_{q \in Q_{\text{all}}} \mathbb{I}(\text{DecidedAbstain}(q) == \text{ExpectedAbstain}(q))}{|Q_{\text{all}}|}$$

$$\text{Zero-Hallucination Rate} = 1.0 - \frac{\sum_{q \in Q_{\text{abstain}}} \mathbb{I}(\text{RetrievedConfident}(q))}{|Q_{\text{abstain}}|}$$

Where $\text{DecidedAbstain}(q) = \text{True}$ when the maximum candidate retrieval score $< \tau_{\text{abstain}}$ ($0.1$ BM25 / empty match).

---

## 6. Durability & Recovery Verification Protocol

### 6.1 Sampled Byte-Offset Anchor Proofs

1. Select $S = 1,000$ atom records randomly from `node_versions`:
   $$\text{SELECT node\_id, properties\_json, content FROM node\_versions ORDER BY RANDOM() LIMIT 1000}$$
2. For each sampled record:
   - Extract `doc_id`, `span_start`, `span_end` from `properties_json`.
   - Fetch original document $D$ from `doc_index[doc_id]`.
   - Slice $T_{\text{slice}} = D.\text{content}[\text{span\_start} : \text{span\_end}]$.
   - Verify $T_{\text{slice}} == \text{record.content}$ and $\text{SHA-256}(T_{\text{slice}}) == \text{record.content\_hash}$.
3. Proof Metric:
   $$\text{Byte-Offset Anchor Recovery} = \frac{N_{\text{exact matches}}}{1000} \equiv 1.000$$

### 6.2 100% Full-Event Replay with Cryptographic Table Parity

1. Extract all committed events from the master database:
   $$\mathcal{E} = \text{SELECT * FROM events ORDER BY stream\_sequence ASC}$$
   Verify $|\mathcal{E}| \ge N_{\text{committed}}$ (all $\sim 202\text{k}+$ events).
2. Initialize a fresh replay database (`scale_100k_rebuild.db`).
3. Re-execute the projection engine over $\mathcal{E}$, populating real tables (`events`, `ingestions`, `nodes`, `node_versions`, `source_lifecycle`, `edge_versions`).
4. Execute SQLite Integrity & Parity Audit:
   - Run `PRAGMA integrity_check;` on both databases.
   - For every table $T \in \{\text{events}, \text{ingestions}, \text{nodes}, \text{node\_versions}, \text{source\_lifecycle}, \text{edge\_versions}\}$:
     $$H_{\text{source}}(T) = \text{SHA-256}\left(\bigoplus_{r \in T} \text{canonical\_row\_bytes}(r)\right)$$
     $$H_{\text{replay}}(T) = \text{SHA-256}\left(\bigoplus_{r \in T} \text{canonical\_row\_bytes}(r)\right)$$
     $$\text{Parity}(T) = \mathbb{I}(H_{\text{source}}(T) == H_{\text{replay}}(T) \land |T_{\text{source}}| == |T_{\text{replay}}|)$$
5. Final Rebuild Parity:
   $$\text{Rebuild Parity} = \prod_{T} \text{Parity}(T) \equiv 1.000$$

---

## 7. Telemetry & Dossier Output Specifications

All outputs are written to `--output-dir`:

1. `100k_scale_dossier.json` (or `100k_scale_diagnostic_dossier.json`): Complete sealed dossier adhering to DEC-P-005b schema.
2. `telemetry_timeseries.json`: Ingestion time series with document, atom, token, byte throughput, RSS MB, Peak RSS MB, and VRAM utilization sampled at batch boundaries.
3. `runs/durability_audit_trace.json`: Detailed durability metrics, exact atom and document counts in DB, hash drift rate, and sampled anchor recovery proofs.
4. `runs/graph_walk_telemetry.jsonl`: Per-walk telemetry recording `seed_id`, `latency_ms`, `activated_count`, `edges_count`, and `degrees`.
5. `runs/raw_query_evaluations.jsonl`: Per-query records containing query text, gold document IDs, retrieved top-20 document IDs, DCG, IDCG, nDCG@10, Recall@20, abstention decision, and latency.
6. `runs/replay_recovery_trace.json`: Event count replayed, elapsed time, replay throughput rate (events/s), table-by-table row counts and cryptographic SHA-256 hashes, and overall rebuild parity.
7. `checksums.json`: SHA-256 manifest of all generated files in the output directory.
