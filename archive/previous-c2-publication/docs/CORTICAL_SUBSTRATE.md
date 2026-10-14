# Cortical Substrate V1.1 — Technical Specification

The **Cortical Substrate** is Trace's core engine for evidence-preserving, high-throughput cognitive retrieval. It balances mathematical rigor, fail-closed verification, and extreme storage efficiency.

---

## 1. Architectural Philosophy

Traditional vector databases and retrieval-augmented systems suffer from four critical pathologies:
1. **Hallucinatory Degradation**: When documents are chunked and summarized, the provenance chain breaks.
2. **Storage Bloat**: Inverted indexes, vector embeddings, and chunk copies typically consume $5\times$ to $10\times$ the raw text volume.
3. **OS Resource Collisions**: On Windows, background index compaction and pointer swaps frequently trigger `WinError 32: The process cannot access the file because it is being used by another process` when readers hold memory mappings.
4. **Graph Oscillation**: Naive spreading activation on knowledge graphs amplifies irrelevant neighboring nodes.

The Cortical Substrate solves these problems through:
- **Byte-exact provenance**: Zero text modification or ungrounded synthesis.
- **External-content single-copy indexing**: SQLite FTS5 referencing canonical text without duplication.
- **Epoch RCU (Read-Copy-Update)**: Concurrency with SQLite active reader leases.
- **Two-Pass Lateral Rectification PPR**: Eliminates graph leakage and stabilizes spreading activation.
- **Hierarchical Macro-Topology (TOC-DAG)**: Bounded spherical clustering that restricts beam search to top-down candidate paths.

---

## 2. Ingestion & Intra-Document Aliasing

The ingestion engine in `src/trace/v2/atomizer.py` operates under strict intra-document boundaries:

```
[Raw Ingestion Document]
        │
        ▼
  Text Normalization (UTF-8, Line endings only)
        │
        ├──► Canonical Source Atom (Stored in SQLite `atom` table)
        │
        └──► Intra-Document Span Clustering
                 ├── A-B-A Duplicate Resolution
                 ├── Disjunctive Lexical/Entity Aliasing
                 └── S^{d-1} Coherence Norm (Diameter >= 0.70)
```

### Invariants
- **Multi-Span Provenance**: Each holon references 1 to 8 exact spans.
  $$\text{span\_text} == \text{normalized}[\text{start}:\text{end}]$$
- **Zero Cross-Document Triples**: Clusters and holons never span multiple document boundaries during initial ingestion.

---

## 3. Storage Substrate & Epoch RCU

Trace structures its physical on-disk footprint into the **4-Number Storage Model**:

| Layer | Component | Target Ratio | Description |
| :--- | :--- | :--- | :--- |
| **1. Durable Spine** | SQLite DB, WAL, SHM | $\le 1.6\times$ raw text | Immutable source atoms, events, outbox, attachments |
| **2. Retrieval-Hot** | `fts_atoms.db` + inverted index | $\le 0.8\times$ raw text | External-content FTS5 (`content='atom'`) |
| **3. Cortex-Hot** | `vectors.bin`, `graph.csr` | $\le 0.6\times$ raw text | Compressed CSR adjacency matrices and quantized vectors |
| **4. Total-Hot** | **Sum of all active files** | **$\le 3.0\times$ raw text** | **Hard Acceptance Gate verified on disk via `Path.stat()`** |

### Windows Epoch RCU & Active Reader Leases
To eliminate `WinError 32` file locking errors on Windows NTFS:
1. Compactions write out a new generation directory: `generations/gen_{epoch}_{timestamp}/`.
2. Pointer swap is an atomic single-row database transaction:
   ```sql
   UPDATE active_generation SET epoch = :new_epoch, generation_dir = :new_dir WHERE id = 1;
   ```
3. Readers acquire an active reader lease in SQLite:
   ```sql
   INSERT INTO active_reader_leases (pid, lease_id, epoch, acquired_at) VALUES (?, ?, ?, ?);
   ```
4. Retired generations enter a 120-second grace period and are only unlinked from disk when zero active reader leases remain for that epoch.

---

## 4. L2 Macro-Topology: Deterministic TOC-DAG

In `src/trace/v2/organization.py`, the Table of Contents Directed Acyclic Graph (TOC-DAG) provides hierarchical macro-structure:

- **Bisecting Spherical 2-Means**: Applied recursively to partition any holon cluster with $|\text{members}| > 64$.
- **Determinism**: Diametrical antipodal seeding with sorted-ID tie-breaking guarantees bit-identical output across repeated seeded runs.
- **Drift Monitoring**: Centroid drift is flagged when:
  $$1 - (\mathbf{c}_0 \cdot \mathbf{c}_{\text{new}}) > 0.25 \times R_{0,\text{eff}}$$
- **Apoptosis Grace**: A 7-day grace period is granted before pruning stale newborn centroids.
- **Overflow Nodes**: Cohesion deadlock partitions are isolated into `DIVERSE_OVERFLOW` nodes and strictly excluded from Tier 2 beam candidacy.

---

## 5. Two-Pass Non-Negative Lateral Rectification PPR

In `src/trace/v2/cortex.py`, graph spreading activation uses a two-pass Personalized PageRank engine:

### Pass 1: Excitatory Power Iteration
Runs standard power iteration over the non-negative weight matrix $\mathbf{W}^+$ for up to 20 iterations or 2,500 steps:
$$\mathbf{s}^{(t+1)} = \alpha \mathbf{s}^{(t)} \mathbf{W}^+ + (1 - \alpha) \mathbf{p}$$

### Pass 2: Inhibitory Lateral Rectification
Suppresses spurious activations by subtracting lateral inhibitory signals from conflicting neighbors:
$$s_{\text{rect}}(u) = \max\left(0, s^+(u) - \beta \max_{v} |w^-(u, v)| \cdot s^+(v)\right)$$
If $\sum s_{\text{rect}}(u) = 0$, the engine falls back safely to $\mathbf{s}^+$ before renormalizing to avoid division by zero:
$$\mathbf{s}^* = \frac{\mathbf{s}_{\text{rect}}}{\|\mathbf{s}_{\text{rect}}\|_1}$$

Guarantees: Zero `NaN`/`Inf` values under all graph densities and execution latency $\le 35\text{ ms}$.

---

## 6. 3-Tier Retrieval Cascade

Implemented in `src/trace/v2/retrieval.py`, retrieval executes in a prioritized tier cascade:

```
                  [Query Received]
                         │
                         ▼
        ┌─────────────────────────────────┐
        │ Tier 1: Lexical Short-Circuit   │  Execution: <= 5 ms
        │ Quoted, UPPER_SNAKE, backtick,  │
        │ traceback exact matching        │
        └────────────────┬────────────────┘
                         │ Exact Match Found?
                         ├─────────► YES: Direct Return
                         ▼ NO
        ┌─────────────────────────────────┐
        │ Tier 2: Top-Down TOC Beam Search│  Execution: <= 35 ms
        │ Hierarchical probe over TOC-DAG │
        │ + Two-Pass PPR spreading        │
        └────────────────┬────────────────┘
                         │ Statistically Uplifted?
                         ├─────────► YES: Evaluated Output
                         ▼ NO / Fallback
        ┌─────────────────────────────────┐
        │ Tier 3: Flat Hybrid Control     │  Execution: <= 25 ms
        │ Dense MiniLM kNN + BM25 Lexical │
        │ Reciprocal Rank Fusion (RRF)    │
        └─────────────────────────────────┘
                         │
                         ▼
        ┌─────────────────────────────────┐
        │ 3-Stage Grounding Verifier      │
        │ 1. Polarity parity              │
        │ 2. Entity containment           │
        │ 3. DeBERTa-v3 Cross-Encoder NLI │
        └─────────────────────────────────┘
```

---

## 7. 3-Stage Grounding Verifier

Before returning any evidence bundle, candidates pass through three verification stages:

1. **Polarity Parity**: Detects negation markers (`not`, `never`, `cannot`, `no`, `neither`) in both the query assertion and candidate span. Mismatches are immediately rejected.
2. **Entity Containment**: Requires named entity overlap recall $\ge 0.80$ between the assertion and the source evidence atom.
3. **Cross-Encoder NLI**: Samples candidate pairs against an NLI cross-encoder (`cross-encoder/nli-deberta-v3-small`). Candidates classified as `CONTRADICTION` are discarded.

If all candidates fail verification, the system returns `insufficient_evidence`.
