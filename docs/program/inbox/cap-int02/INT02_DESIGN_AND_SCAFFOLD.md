# Node CAP-INT02: 100K Paired Qualification Design & Execution Scaffold

- **Target Gate:** `CAP-GE` (100K Paired Qualification)
- **Lane:** Integration / Scale Qualification (`INT-100K`)
- **Status:** SCAFFOLDED (Unlocked by Gate CAP-GD Human Decision `DEC-CAP-GD`)
- **Governing Directives:** DAG Node `CAP-INT02`, `01_INVARIANTS.md`, `04_EVALUATION_PROTOCOL.md`

---

## 1. Frozen Input Source Binding

Per Gate CAP-GD directive, Node `CAP-INT02` strictly consumes the verified **real 100,000-document corpus capsule**, never synthetic inputs or unverified files:

- **Capsule Manifest Path:** `docs/program/inbox/l1-02-corpus-capsule-20260828/evidence/corpus_manifest.json`
- **Capsule Merkle Root SHA256:** `38d1a1cf980d447edef7bfaa1ebc4d06129386a82bdd2c6f724f45d8624fc530`
- **Total Unique Documents:** 100,000
- **Total Raw Text Bytes:** 65,394,921 bytes (~65.39 MB)
- **Selection Policy:** Deterministic zero-indexed contiguous prefix slicing `[0:N]` per dataset

### Shard Composition Table

| Dataset Name | Available Records | Selected Records (N) | Selection Range | Selected Text Bytes |
|---|---|---|---|---|
| `musique` | 101,962 | 80,047 | `[0, 80047)` | 37,343,384 |
| `beir-fiqa` | 57,600 | 10,575 | `[0, 10575)` | 8,141,714 |
| `beir-scifact` | 5,183 | 5,183 | `[0, 5183)` | 6,807,173 |
| `beir-nfcorpus` | 3,633 | 3,633 | `[0, 3633)` | 10,317,358 |
| `multihop-rag` | 609 | 562 | `[0, 562)` | 2,785,292 |
| **Total** | **168,987** | **100,000** | — | **65,394,921** |

---

## 2. Fail-Closed Invariants & Preflight Verification

1. **Nonexistent Path Prohibition (Hard Invariant):**
   Any reference to `benchmarks/data/corpus_100k_frozen.jsonl` (or any non-existent/invented corpus path) will immediately abort execution with exit code 1 (`PreflightFailure`). The runner verifies capsule manifest existence and Merkle integrity before any database initialization.
2. **Cryptographic Merkle Integrity Check:**
   Before ingestion begins, the runner computes and matches the root hash against `38d1a1cf980d447edef7bfaa1ebc4d06129386a82bdd2c6f724f45d8624fc530`.
3. **No Synthetic / In-Memory Shortcuts:**
   All 100,000 documents must be written to disk through SQLite WAL transactions (`trace_100k_profile*.db`). Mocking or in-memory bypasses are barred.

---

## 3. Three-Profile Separation Architecture

The 100K qualification executes three strictly isolated, independent evaluation profiles to prevent metric confounding:

```text
100K Capsule Manifest (Merkle 38d1a1cf…)
               │
   ┌───────────┼───────────┐
   ▼           ▼           ▼
Profile 1   Profile 2   Profile 3
(Lexical)   (Hybrid)    (Hybrid+Cortex)
```

### Profile Specifications

1. **Profile 1 (Core + Lexical Baseline):**
   - Ingestion: Full 100,000 documents atomized and committed to Spine WAL (`trace_100k_profile1.db`).
   - Retrieval: BM25 / SQLite FTS5 full-text indexing only.
   - Purpose: Establishes the purely lexical retrieval floor and baseline storage footprint.
2. **Profile 2 (Core + Hybrid Retrieval):**
   - Ingestion: Identical Spine WAL commit (`trace_100k_profile2.db`).
   - Retrieval: BM25 + Dense embeddings (`all-MiniLM-L6-v2`, 384-d unit normalized, SHA256 `1110a243…`) + Reciprocal Rank Fusion ($k=60$).
   - Purpose: Verifies hybrid retrieval gains over lexical baseline.
3. **Profile 3 (Core + Hybrid + Shadow Cortex Projections):**
   - Ingestion: Identical Spine WAL commit (`trace_100k_profile3.db`).
   - Projection: Asynchronous local SLM semantic topic holon consolidation on top of Profile 2.
   - Purpose: Evaluates Cortex projection quality without degrading Core ingestion throughput.

---

## 4. Preflight & Runtime Stop Rules

The runner enforces four automated stop rules that halt execution upon violation:

1. **Stop Rule 1 — Profile 2 Retrieval Regression:**
   - Condition: If Profile 2 retrieval nDCG@10 falls below the ratified Gate CAP-GB floors:
     - SciFact < 0.65
     - NFCorpus < 0.32
     - FiQA < 0.38
   - Consequence: Immediate pipeline halt; regression escalated to Coordinator.
2. **Stop Rule 2 — Storage Footprint Multiplier Exceeded:**
   - Condition: Total on-disk storage multiplier $> 3.5\times$ raw text bytes ($3.5 \times 65.39\text{ MB} \approx 228.88\text{ MB}$).
   - Component accounting: Spine WAL + FTS index + Qdrant vector store + SQLite derived graphs.
   - Consequence: Pipeline halt; storage violation recorded in dossier.
3. **Stop Rule 3 — Merkle Verification Failure:**
   - Condition: Any dataset hash or capsule Merkle root mismatch.
   - Consequence: Immediate preflight halt before allocating disk space.
4. **Stop Rule 4 — Queue Depth Runaway:**
   - Condition: Consolidation queue depth $> 5,000$ clusters.
   - Consequence: Immediate halt with alert.

---

## 5. Execution & Verification Command

Per DAG Node `CAP-INT02`, deterministic execution and verification is invoked via:

```bash
python benchmarks/run_100k_qualification.py --compare-profiles --verify-receipts
```

Outputs written to `docs/program/inbox/cap-int02/100k_qualification_dossier.json`.
