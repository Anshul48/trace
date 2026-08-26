# S6 Baselines and P-005 Decision Brief Handoff

> **Role:** Evaluation & Promotion Owner (S6)  
> **Session:** Session 9 (Real Baselines and P-005 Decision Brief)  
> **Packet ID:** `s6-baselines-p005-20260825`  
> **Date:** 2026-08-26  
> **Authority Level:** C3 (Empirical Real-Data Baseline Evidence / Decision Proposal)  
> **Status:** **COMPLETE / READY FOR HUMAN GATE B**  

---

## 1. Executive Summary

In Session 9, the Evaluation & Promotion Owner (`S6`) executed reproducible, fail-closed baseline evaluations across all 7 admitted real datasets in the DEC-P-001/DEC-P-002 portfolio using the canonical `trace-bench` harness (commit `c0ea9fbf37bc50c88336f198437be031c18d6f64`), accelerated natively on the **NVIDIA GeForce RTX 5050 Laptop GPU (SM120, CUDA 12.8 / 13.3)**.

All **36,620 real query cases** and **100,000 real vectors** were evaluated end-to-end across 5 baseline algorithms (BM25, GPU Dense with `sentence-transformers/all-MiniLM-L6-v2`, Hybrid RRF, HippoRAG PPR, and BigANN L2 vector ops).

Two independent subagents were spawned:
1. **Query-Class & Statistics Reviewer (`e742f1ed-6051-453d-8ef0-e4bcf948c8e8`)**: Verified 100% denominator integrity, computed 95% bootstrap confidence intervals ($B=10,000$), paired Student's $t$-tests, Wilcoxon signed-rank tests, Cohen's $d$ effect sizes, and audited baseline failure on unanswerable abstentions. (Receipt `rcpt-s6-stats-audit-20260826-0335`: **VERIFIED PASS**).
2. **Manifest & Provenance Reviewer (`019e19b3-1df5-4e20-95dc-9315a2ee598b`)**: Audited dataset SHA-256 hashes against Gate D2b, verified zero mock/fallback paths, confirmed non-editable runner installation, verified strict BigANN vector isolation, and verified the Headless Core & Pluggable Adapter specifications. (Receipt `receipt-s6-manifest-provenance-20260826`: **VERIFIED PASS**).

The formal **P-005 Decision Brief** has been delivered in `evidence/p005-decision-brief.md` for the human owner to establish binding numerical release thresholds at **Human Gate B**.

---

## 2. Context & Invariants Preserved

- **Prerequisites Locked:** Gate V1a (Runner Integrity) closed PASS, Gate D2b (Dataset Normalization) verified across all 7 datasets, Gate V1b verified, Human Gate A (DEC-P-002 / DEC-P-004) recorded in Decision Log.
- **Fail-Closed Execution:** Zero mock/synthetic/fallback paths used; real model weights and exact tokenization instantiated.
- **Strict Lane Separation:** Direct lookup, domain semantic, semantic QA, multi-hop reasoning, complex reasoning, compositional multi-hop, and vector operations lanes evaluated separately.
- **BigANN Vector Scale Isolation:** SIFT100K results are strictly isolated to the operations lane and never blended into text-memory retrieval quality metrics.
- **Certification State:** `certification_eligible: false` invariant strictly maintained awaiting Human Gate B approval and subsequent B3 dossier assembly.
- **Product Code Preservation:** Zero mutations to product code during Session 9 (strictly evaluation and brief synthesis).

---

## 3. Completed Work & Artifact Inventory

### Delivered Files in `docs/program/inbox/s6-baselines-p005-20260825/`:
1. `packet.md` — Session 9 charter, boundaries, and scope lock.
2. `repository-state.json` — Preflight repository commits and hardware/runtime environment.
3. `input-manifest.json` — Cryptographic hash bindings for program documents, prerequisites, and admitted datasets.
4. `commands.md` — Complete chronological record of commands executed during Session 9.
5. `verification.md` — Independent verification and audit record.
6. `handoff.md` — This durable C3 handoff document.
7. `evidence/baseline-evaluation-manifest.json` — Frozen preflight run manifest.
8. `evidence/run_baselines.py` — High-performance GPU-accelerated baseline runner.
9. `evidence/baseline-distributions-summary.json` — Master empirical distributions summary.
10. `evidence/lane-metrics-breakdown.json` — Capability lane breakdown with proposed release floors.
11. `evidence/subagent-verification-receipts.json` — Cryptographic receipts from both subagents.
12. `evidence/checksums.json` — SHA-256 integrity checksums for all 14 evidence files.
13. `evidence/p005-decision-brief.md` — Master P-005 Decision Brief for Human Gate B.
14. `evidence/runs/` — Full immutable per-case evaluation outputs:
    - `beir-scifact_runs.json` (1,109 cases)
    - `beir-nfcorpus_runs.json` (3,237 cases)
    - `beir-fiqa_runs.json` (6,611 cases)
    - `multihop-rag_runs.json` (2,556 cases)
    - `bright_runs.json` (752 cases on 928K docs)
    - `musique_runs.json` (22,355 cases on 102K segments)
    - `bigann_operations_run.json` (100K vectors)

---

## 4. Empirical Distributions & Statistical Summary

```
========================================================================================================================
Capability Lane        Dataset         Evaluated Cases     Superior Baseline    Observed Best Metric   Latency P95 (GPU)
========================================================================================================================
Direct Lookup          beir-scifact    1,109 cases         Hybrid RRF           nDCG@10 = 0.6824       4.69 ms
Domain Semantic        beir-nfcorpus   3,237 cases         Hybrid RRF           nDCG@10 = 0.3367       2.45 ms
Semantic QA (Finance)  beir-fiqa       6,611 cases         GPU Dense            nDCG@10 = 0.3666       0.36 ms (2,767 QPS)
Multi-Hop & Chronology multihop-rag    2,556 cases (301 a) BM25                 nDCG@10 = 0.7370       7.14 ms (BM25)
Complex Reasoning      bright          752 (928K docs)     BM25                 nDCG@10 = 0.0651       1,397.08 ms
Compositional MultiHop musique         22,355 (102K segs)  BM25                 nDCG@10 = 0.4711       62.96 ms
Abstention Lane        multihop-rag    301 unanswerable    All Baselines Failed Accuracy = 0.0%        0.70 ms
Vector Operations      bigann          100K vectors / 1K q GPU L2 Nearest Neigh QPS = 817.76           1.22 ms
========================================================================================================================
```

### Statistical Significance Highlights:
- **FiQA Semantic QA:** Dense outperforms BM25 by **$+0.1354$ nDCG@10** ($p < 10^{-100}$, Cohen's $d = +0.48$).
- **SciFact Direct Lookup:** Hybrid RRF outperforms BM25 by **$+0.0145$ nDCG@10** ($p = 0.00075$) and Dense by **$+0.0477$ nDCG@10** ($p < 10^{-15}$).
- **MultiHop-RAG Graph Drift:** Naive HippoRAG PPR degrades by **$-0.5143$ nDCG@10** vs BM25 ($p < 10^{-100}$, Cohen's $d = -1.54$), proving the necessity of bounded entity resolution.
- **Abstention Void:** Standard retrieval models fail 100% on expected abstentions (force-ranking irrelevant passages for unanswerable questions), validating Trace's dedicated abstention lane.

---

## 5. Proposed P-005 Release Thresholds for Human Gate B

The P-005 Decision Brief (`evidence/p005-decision-brief.md`) proposes the following binding thresholds for Human Gate B review:

1. **Gate 1 (Durable Memory & Provenance):** 100.0% source atom retention, 0.0% content-hash drift, 100.0% byte-offset anchor recovery, $\Delta = 0$ repeat-erasure verification.
2. **Gate 2 (Self-Organization & Representation):** 0.0% orphan atoms, $\ge 0.850$ top-level routing purity, 0.0% duplicate leaf assignment.
3. **Gate 3 (Retrieval Quality by Capability Lane):**
   - Direct Lookup (`beir-scifact`): $\text{nDCG@10} \ge \mathbf{0.7000}$, $\text{Recall@20} \ge \mathbf{0.8800}$, $\text{P95} \le \mathbf{10.0\text{ ms}}$.
   - Medical Semantic (`beir-nfcorpus`): $\text{nDCG@10} \ge \mathbf{0.3500}$, $\text{Recall@20} \ge \mathbf{0.2200}$, $\text{P95} \le \mathbf{15.0\text{ ms}}$.
   - Financial QA (`beir-fiqa`): $\text{nDCG@10} \ge \mathbf{0.4000}$, $\text{Recall@20} \ge \mathbf{0.5500}$, $\text{P95} \le \mathbf{25.0\text{ ms}}$.
   - Multi-Hop (`multihop-rag`): $\text{Complete Coverage@20} \ge \mathbf{0.8800}$, $\text{nDCG@10} \ge \mathbf{0.7500}$, $\text{P95} \le \mathbf{20.0\text{ ms}}$.
   - Complex Reasoning (`bright`): $\text{Recall@20} \ge \mathbf{0.1800}$, $\text{nDCG@10} \ge \mathbf{0.1000}$, $\text{P95} \le \mathbf{100.0\text{ ms}}$.
   - Compositional Multi-Hop (`musique`): $\text{Complete Coverage@20} \ge \mathbf{0.2500}$, $\text{nDCG@10} \ge \mathbf{0.5000}$, $\text{P95} \le \mathbf{50.0\text{ ms}}$.
   - Abstention Lane (`multihop-rag` unanswerable): $\text{Abstention Accuracy} \ge \mathbf{0.8500}$ (Zero-hallucination rate on unsupported queries).
4. **Gate 4 (Bounded Latency, Operations & Adapters):**
   - Ingestion throughput: $\ge \mathbf{500\text{ docs/sec}}$ (GPU/accelerated), $\ge \mathbf{150\text{ docs/sec}}$ (multi-threaded CPU).
   - Retrieval latency budgets: P50 $\le 5\text{ ms}$, P95 $\le 20\text{ ms}$, P99 $\le 50\text{ ms}$.
   - Memory RSS: $\le 512\text{ MB}$ base, $\le 2.0\text{ GB}$ peak for 100K corpus.
   - Storage footprint multiplier: $\le 3.0\times$ raw corpus byte size.
   - HippoRAG PPR graph bounds: Max out-degree $\le 50$, walk depth $\le 15$ steps, execution time $\le 35.0\text{ ms}$.
   - Headless Core Engine contract (`/v2` REST, CLI, SDK) and Pluggable Adapter interfaces (`EmbeddingAdapter`, `VectorStoreAdapter`, `GraphStoreAdapter`).
5. **Gate 5 (100K Real Scale Operations):**
   - BigANN SIFT100K: $\ge \mathbf{5,000\text{ vectors/sec}}$ ingestion, $\ge \mathbf{500\text{ QPS}}$, P95 latency $\le \mathbf{5.0\text{ ms}}$, exact ground-truth candidate agreement.
6. **Statistical Methodology:**
   - Significance threshold: $\alpha = 0.01$ (paired Wilcoxon signed-rank and Student's $t$-test).
   - Minimum practical effect size: $\Delta \ge +0.030$ nDCG@10 or Cohen's $d \ge 0.20$.
   - 95% Bootstrap Confidence Intervals ($B=10,000$ resamples).

---

## 6. Open Items & Immediate Next Actions

1. **Human Gate B Review & Approval (Immediate Next Step):**
   - The human owner reviews the P-005 Decision Brief (`docs/program/inbox/s6-baselines-p005-20260825/evidence/p005-decision-brief.md`).
   - The human owner formally approves and records **`DEC-P-005`** in `docs/program/06_DECISION_LOG.md`.
2. **Session 10 Unblocking:**
   - Upon recording DEC-P-005, the implementation wave proceeds to **Session 10 (S7 Cortex Implementation)**, building out the multi-threaded Cortex projections, pluggable adapters, and headless query interfaces.
