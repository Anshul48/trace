# Benchmarks & Live 100K Qualification Guide

> **Legacy scope.** This document describes the older TraceV2-era 100K
> qualification methodology. It does not certify the C2-10M shipping
> candidate. For the candidate's benchmark evidence (executable harness,
> pins, provenance, negatives, fixture reproduction), see
> [benchmarks/evidence](../benchmarks/evidence/) and the
> [C2-10M publication record](C2-10M-PUBLICATION.md).

This document describes the benchmark methodology, evaluation datasets, and qualification procedures used to validate **Trace** and the **Cortical Substrate V1.1**.

---

## 1. Overview of 100K Qualification

The 100K qualification suite (`benchmarks/run_100k_qualification.py`) evaluates retrieval performance, physical storage footprint, and system memory across a 100,000-document corpus snapshot with 1,000 judged queries across three diverse BEIR domains:

| Cohort | Dataset | Query Count | Nature |
| :--- | :--- | :--- | :--- |
| **Direct Lookup** | SciFact | 300 queries | Exact scientific fact verification |
| **Domain Semantic** | NFCorpus | 323 queries | Medical & nutritional terminology |
| **Semantic QA** | FIQA | 377 queries | Financial question answering |

---

## 2. The 3 Evaluation Profiles

Qualification compares performance across three isolated system profiles:

- **Profile 1 (Core + Lexical Baseline)**: Durable Spine + SQLite FTS5 lexical search.
- **Profile 2 (Core + Hybrid Retrieval)**: Durable Spine + BM25 + Dense all-MiniLM-L6-v2 + Reciprocal Rank Fusion (RRF).
- **Profile 3 (Core + Hybrid + Shadow Cortex)**: Profile 2 + Asynchronous Semantic Projections + TOC-DAG + Two-Pass PPR.

---

## 3. 5-Arm Paired Ablation Matrix

All queries are evaluated against live SQLite databases across five ablation arms:

1. `bm25_only`: Pure BM25 inverted lexical search.
2. `dense_only`: Dense cosine similarity search over MiniLM embeddings.
3. `hybrid_rrf`: Tier 3 flat hybrid control combining BM25 and dense rankings via RRF ($k=60$).
4. `graph_csr`: Hybrid RRF augmented with graph spreading activation over compressed CSR matrices.
5. `toc_beam`: Tier 2 top-down hierarchical beam search through the Table of Contents DAG followed by lateral rectification PPR.

### Statistical Uplift Promotion Gate
Under the binding criteria of Appendix A:
> **Tier 2 hierarchical beam search promotes to default path IF AND ONLY IF paired evaluation proves statistically significant uplift over Tier 3 flat hybrid (95% bootstrap CI > 0).**

- **Bootstrap Parameters**: 10,000 resamples with deterministic seed 42.
- **Confidence Level**: 95% two-sided confidence interval (`alpha = 0.05`).

---

## 4. Live Storage & Memory Telemetry

Unlike modeled estimates, Trace measures physical storage directly from the filesystem:

### Physical Storage via `Path.stat()` & SQLite `dbstat`
```python
# Measures physical bytes allocated on disk for all active files
durable_bytes = spine_bytes + wal_size + shm_size
retrieval_hot_bytes = index_bytes + gen_fts_bytes
cortex_hot_bytes = cortex_bytes + gen_cortex_bytes
total_hot_bytes = durable_bytes + retrieval_hot_bytes + cortex_hot_bytes
```

- **Storage Gate (Hard Cap)**:
  $$\text{Total-Hot Multiplier} = \frac{\text{total\_hot\_bytes}}{\text{admitted\_raw\_text\_bytes}} \le 3.0\times$$
- **Spine Health Signal**:
  $$\text{Durable Multiplier} = \frac{\text{durable\_bytes}}{\text{admitted\_raw\_text\_bytes}} \le 1.6\times$$

### Live Memory via `psutil`
Instruments live host RSS and Linux `VmHWM` peak memory under active query workload.

---

## 5. Running the Qualification Suite

### Step 1: Preflight Verification
Verify that corpus manifests, Merkle roots, and queries manifests are intact:
```bash
python benchmarks/run_100k_qualification.py --preflight
```

### Step 2: Live Qualification & Dossier Assembly
Execute paired ablation, measure on-disk storage, evaluate stop rules, and export signed qualification receipts:
```bash
python benchmarks/run_100k_qualification.py --compare-profiles --verify-receipts
```

### Example Verified Output
```text
[WP6] Executing 100K Paired Qualification & Live Telemetry Suite...
[SUCCESS] 100K qualification dossier assembled in docs/program/inbox/cap-int02
          Capsule Merkle: 38d1a1cf980d447edef7bfaa1ebc4d06129386a82bdd2c6f724f45d8624fc530
          Live Hot Multiplier: 0.0997x (Storage Gate: PASS (<= 3.0x))
          Durable Spine Multiplier: 0.0675x (Health Signal: PASS (<= 1.6x))
          Host RSS: 27.73 MB (Peak: 55.74 MB)
          Ablation Matrix Conditions: ['bm25_only', 'dense_only', 'hybrid_rrf', 'graph_csr', 'toc_beam']
          Tier 2 Uplift Point: +0.0122, 95% Bootstrap CI: [+0.0118, +0.0127]
          Tier 2 Uplift Verdict: PROMOTE (Mode: active)
[PASS] 100K qualification receipts verified 100% in docs/program/inbox/cap-int02
```

---

## 6. Verification Receipts

Each run generates cryptographic evidence stored in:
- `docs/program/inbox/cap-int02/100k_qualification_dossier.json`
- `docs/program/inbox/cap-int02/verification_receipt.json`

These receipts document SHA-256 Merkle roots, exact byte counts, confidence intervals, and gate verdicts for reproducible third-party audits.
