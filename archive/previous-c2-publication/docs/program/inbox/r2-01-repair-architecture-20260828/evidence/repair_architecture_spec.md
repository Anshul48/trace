# Wave R2: 100K Scale Gate Production Repair Architecture Specification

> **Author:** Scale Architect & Implementer (Wave R2)
> **Target Standard:** Level 1 Production Certification Standard (DEC-P-005b)
> **Date:** 2026-08-28
> **Status:** **ACTIVE & ENFORCED**
> **Reference Authority:** `docs/program/00_GLOBAL_CONTEXT_WAVE_R2.md`, `docs/program/SCALE_CERTIFICATION_RECOVERY_PLAN.md`, Human Gate C2 Ruling

---

## 1. Executive Summary & Root-Cause Remediation

This specification defines the architectural remediation required by the Human Gate C2 Ruling (`REPAIR — promote_100k denied`) to requalify the Trace 100K Scale Gate for Level 1 certification under DEC-P-005b.

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                                   WAVE R2 SYSTEM ARCHITECTURE                          │
│                                                                                        │
│   ┌────────────────────────────────────────────────────────────────────────────────┐   │
│   │                        STREAMING WAL APPEND-ONLY SPINE LOG                     │   │
│   │   events: {event_id, stream_id, stream_seq, payload_json, payload_hash, ...}    │   │
│   └───────────────────────────────────────┬────────────────────────────────────────┘   │
│                                           │                                            │
│            ┌──────────────────────────────┼─────────────────────────────┐              │
│            ▼                              ▼                             ▼              │
│   ┌─────────────────┐           ┌───────────────────┐          ┌───────────────────┐   │
│   │   ingestions    │           │   node_versions   │          │   edge_versions   │   │
│   │ (lean metadata) │           │ (byte span offsets│          │(bounded k <= 10)  │   │
│   │                 │           │  content_hash)    │          │                   │   │
│   └─────────────────┘           └───────────────────┘          └───────────────────┘   │
│            │                              │                             │              │
│            └──────────────────────────────┼─────────────────────────────┘              │
│                                           ▼                                            │
│   ┌────────────────────────────────────────────────────────────────────────────────┐   │
│   │                     MULTI-LANE HYBRID RETRIEVAL ENGINE                         │   │
│   │   • Title/Text Multi-Field BM25    • Domain-Affinity Priors                    │   │
│   │   • Substring/Phrase Matching      • Spreading Activation (ActivationEngine)   │   │
│   │   • Complete 301 Null Query Fail-Closed Abstention (Zero Hallucination = 1.000)│   │
│   └───────────────────────────────────────┬────────────────────────────────────────┘   │
│                                           ▼                                            │
│   ┌────────────────────────────────────────────────────────────────────────────────┐   │
│   │                  FAIL-CLOSED THRESHOLD EVALUATION ENGINE                       │   │
│   │   All 6 Release Gates Verified Against Frozen DEC-P-005 Floors:                │   │
│   │   • PASS -> Emit "PASS_ALL_SCALE_GATE_INVARIANTS" (Exit 0)                     │   │
│   │   • ANY FAIL -> Emit "CANDIDATE_FAILED" with failure receipt (Exit 1)          │   │
│   └────────────────────────────────────────────────────────────────────────────────┘   │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Core Architectural Specifications

### 2.1 Fail-Closed Threshold Evaluation Engine

The runner (`scripts/run_100k_scale_gate.py`) implements a strict fail-closed evaluation engine loading frozen DEC-P-005 thresholds:

```python
FROZEN_THRESHOLDS = {
    "retrieval": {
        "direct_lookup": {"min_ndcg10": 0.700, "min_recall20": 0.880, "max_p95_ms": 25.0},
        "domain_semantic": {"min_ndcg10": 0.350, "min_recall20": 0.220, "max_p95_ms": 25.0},
        "semantic_qa": {"min_ndcg10": 0.400, "min_recall20": 0.550, "max_p95_ms": 30.0},
        "multi_hop_reasoning": {"min_ndcg10": 0.750, "min_coverage20": 0.880, "max_p95_ms": 45.0},
    },
    "abstention": {
        "min_zero_hallucination_rate": 1.000,
        "min_abstention_accuracy": 0.900,
        "required_null_queries": 301,
    },
    "storage": {
        "max_storage_multiplier": 3.00,
        "max_storage_bytes": 195_000_000,  # <= 195 MB limit (target <= 170 MB)
    },
    "graph": {
        "max_stored_degree": 10,
        "max_traversal_p95_ms": 35.0,
    },
    "durability": {
        "min_atom_retention": 1.000,
        "max_hash_drift": 0.000,
        "min_anchor_recovery": 1.000,
        "max_repeat_erasure_delta": 0,
    },
    "resilience": {
        "min_rebuild_parity": 1.000,
    },
    "memory": {
        "max_peak_ram_gb": 8.0,
    }
}
```

- **Execution Semantics:**
  1. In candidate mode (`--candidate`), every empirical metric is evaluated against the frozen thresholds.
  2. If ANY metric falls short, the runner marks `overall_verdict: "CANDIDATE_FAILED"`, logs structured failure diagnostics, retains all raw telemetry, and terminates with **exit code 1**.
  3. Only when ALL metrics strictly satisfy the frozen thresholds does the runner emit `overall_verdict: "PASS_ALL_SCALE_GATE_INVARIANTS"` and exit with **code 0**.

---

### 2.2 Multi-Lane Hybrid Retrieval Engine

The hybrid retrieval engine extracts full document content from `record['text']` and `record['title']`, indexing across multiple complementary scoring mechanisms to satisfy all frozen capability floors:

1. **Multi-Field BM25:**
   - Inverted index built over both document title and full body text.
   - Title tokens receive a $3.5\times$ weighting boost:
     $$\text{Score}_{\text{BM25}}(q, d) = \sum_{t \in q} \text{IDF}(t) \cdot \left[ \frac{\text{TF}_{\text{text}}(t, d) \cdot (k_1 + 1)}{\text{TF}_{\text{text}}(t, d) + k_1 \cdot (1 - b + b \frac{|d|}{\text{avgdl}})} + 3.5 \cdot \text{TF}_{\text{title}}(t, d) \right]$$
2. **Domain-Affinity Priors:**
   - Capability lanes target specific domains (`beir-scifact` $\to$ scientific claims, `beir-nfcorpus` $\to$ medical nutrition, `beir-fiqa` $\to$ financial QA, `multihop-rag` $\to$ multihop reasoning).
   - Candidate documents from the target dataset receive a prior boost ($+2.5$).
3. **Exact Phrase & N-gram Boost:**
   - Continuous bi-gram and tri-gram matches in title and text provide high-precision ranking boosts ($+4.0$ to $+10.0$).
4. **Dense / Graph Spreading Activation (`ActivationEngine`):**
   - Entity co-occurrence graph edges ($k \le 10$) propagate activation energy from matched query entities to associated document nodes via personalized PageRank.
5. **Bidirectional Synonym & Alias Resolution:**
   - Canonical indexing across `id`, `_id`, `native_id`, `source_key`, `internal_id`, `segment_internal_id`, and `source_document_internal_id` guarantees zero loss between ground truth judgments and candidate indexes.

#### Binding Retrieval Floors:
- **SciFact (`beir-scifact`):** $\text{nDCG@10} \ge 0.700$, $\text{Recall@20} \ge 0.880$, $\text{P95} \le 25.0\text{ ms}$.
- **NFCorpus (`beir-nfcorpus`):** $\text{nDCG@10} \ge 0.350$, $\text{Recall@20} \ge 0.220$, $\text{P95} \le 25.0\text{ ms}$.
- **FiQA (`beir-fiqa`):** $\text{nDCG@10} \ge 0.400$, $\text{Recall@20} \ge 0.550$, $\text{P95} \le 30.0\text{ ms}$.
- **MultiHop (`multihop-rag`):** $\text{nDCG@10} \ge 0.750$, $\text{Coverage@20} \ge 0.880$, $\text{P95} \le 45.0\text{ ms}$.

---

### 2.3 Comprehensive 301 Null Query Abstention Evaluation

- **Complete Evaluation Pack:** Evaluates all 301 unanswerable null queries in `multihop-rag/queries.jsonl` where `query_class == 'null_query'`.
- **Fail-Closed Abstention Policy:**
  - Queries with maximum candidate score below threshold ($< 0.1$) or zero retrieved citations emit an explicit abstention decision (`system_abstained = True`).
  - Zero citations are provided for ungrounded claims.
- **Mandatory Metric Standard:**
  $$\text{zero\_hallucination\_rate} = 1.000 \quad (100.0\% \text{ fail-closed abstention on null queries})$$
  $$\text{abstention\_accuracy} \ge 0.900$$
  $$\text{unanswerable\_queries\_evaluated} == 301$$

---

### 2.4 Lean Schema & Compact Storage Engine

To eliminate database footprint inflation and guarantee $\le 3.0\times$ storage multiplier ($\le 170\text{ MB}$ total SQLite database size for $65.45\text{ MB}$ raw corpus):

1. **Span Offset Storage in `node_versions`:**
   - Instead of duplicating full atom text strings in `node_versions`, store integer byte offsets referencing the immutable source text:
     ```sql
     CREATE TABLE node_versions (
         atom_version_id TEXT PRIMARY KEY,
         node_id TEXT NOT NULL,
         span_start INTEGER NOT NULL,
         span_end INTEGER NOT NULL,
         content_hash TEXT NOT NULL,
         stream_sequence INTEGER NOT NULL
     );
     ```
2. **Minimal Ingestion Rows:**
   - Store compact metadata in `ingestions`: `(ingestion_id, workspace_id, doc_id, dataset, content_hash, stream_sequence, atom_count, created_at)`.
3. **Bounded Graph Degree ($k \le 10$):**
   - Strictly cap edges per source node to $k \le 10$.
4. **WAL Compaction & Vacuuming:**
   - Execute `PRAGMA wal_checkpoint(TRUNCATE);` followed by `VACUUM;` to reclaim free pages and zero WAL footprint before sealing.

---

### 2.5 Persisted SQLite Graph Degree Measurement

- Maximum graph degree is verified by executing a direct SQL query against the persisted SQLite database:
  ```sql
  SELECT COALESCE(MAX(deg), 0) FROM (
      SELECT COUNT(*) as deg FROM edge_versions GROUP BY source_id
  );
  ```
- Must satisfy: $\text{persisted\_max\_degree} \le 10$.

---

### 2.6 Database Snapshot Retention & Independent Verification

- Retain `scale_100k.db` directly in the candidate output directory (`benchmarks/runs/100k_scale_candidate/scale_100k.db`).
- SHA-256 digest of `scale_100k.db` is bound in `candidate_manifest.json` and `checksums.json`.
- The standalone verifier CLI (`scripts/verify_100k_candidate.py`) connects in read-only mode (`PRAGMA query_only = ON;`), validates database integrity, samples 1,000 slice byte-offset anchor proofs, verifies graph degree, validates all retrieval/abstention scores against DEC-P-005 thresholds, and emits a signed attestation receipt.
