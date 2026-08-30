# Verification Record — S6 Real Baselines and P-005 Decision Brief

**Session:** Session 9 (S6)
**Packet ID:** `s6-baselines-p005-20260825`
**Date:** 2026-08-26
**Status:** `VERIFIED PASS` (C3 Authority Level / Decision Proposal)

## 1. Verification Summary

All baseline evaluations, empirical distribution analyses, and manifest bindings were independently executed and verified:

1. **Preflight & Invariants Verification:**
   - Base commits pinned: `trace-bench` @ `c0ea9fbf37bc50c88336f198437be031c18d6f64`, `trace` @ `f7bd96e9c5e0f9326b53a074024e7ace889f6e36`, `trace-lite` @ `fe66a9eefc8372f7cc021c864d26e62a9d6cc9c1` (verified candidate `3e7e9f0ee460e3af75f3935343f6d6f2089f9f7c`).
   - Prerequisites verified: Gate V1a closed PASS, Gate D2b normalized datasets verified, Gate V1b verified, Human Gate A (DEC-P-002 / DEC-P-004) recorded in Decision Log.
   - Non-editable runner installation and zero mock fallback verified.

2. **Real Dataset Portfolio Evaluation (100% Complete):**
   - **BEIR SciFact** (1,109 cases): BM25 (0.6679), Dense (0.6347), Hybrid RRF (0.6824).
   - **BEIR NFCorpus** (3,237 cases): BM25 (0.3009), Dense (0.3207), Hybrid RRF (0.3367).
   - **BEIR FiQA** (6,611 cases): BM25 (0.2312), Dense (0.3666), Hybrid RRF (0.3408).
   - **MultiHop-RAG** (2,556 cases): BM25 (0.7370), Dense (0.5500), Hybrid RRF (0.6750), HippoRAG PPR (0.2227).
   - **BRIGHT** (752 cases): BM25 on 928K docs (0.0651 nDCG@10, 0.1307 Recall@20).
   - **MuSiQue** (22,355 cases): BM25 on 102K segments (0.4711 nDCG@10, 0.5379 Recall@20).
   - **BigANN / SIFT1M** (100,000 vectors): 7,336.9 vectors/sec ingestion, 817.8 QPS query throughput, 1.22 ms P95 latency (strictly isolated).

3. **Subagent Review Receipts:**
   - **Subagent 1 (`e742f1ed-6051-453d-8ef0-e4bcf948c8e8` — Query-Class & Statistics Reviewer):** Audited 36,620 total queries, verified 100% denominator integrity, computed 95% bootstrap CIs, paired t-tests ($p < 10^{-100}$ on FiQA), Cohen's d effect sizes, and confirmed 0.0% baseline abstention accuracy on expected abstentions. Receipt `rcpt-s6-stats-audit-20260826-0335` signed `PASS`.
   - **Subagent 2 (`019e19b3-1df5-4e20-95dc-9315a2ee598b` — Manifest & Provenance Reviewer):** Audited input manifest, repository state, dataset SHA-256 hashes against Gate D2b / DEC-P-001, confirmed zero mock/fallback paths, confirmed non-editable runner installation, verified strict BigANN vector isolation, and verified the Headless Core & Pluggable Adapter specifications. Receipt `receipt-s6-manifest-provenance-20260826` signed `PASS`.

4. **Deliverable Status:**
   - P-005 Decision Brief delivered in `evidence/p005-decision-brief.md` proposing numerical release thresholds across all 5 Release Gates for Human Gate B.
   - Master distributions summary frozen in `evidence/baseline-distributions-summary.json`.
   - Complete capability lane metrics breakdown frozen in `evidence/lane-metrics-breakdown.json`.
   - `certification_eligible: false` invariant strictly maintained awaiting Human Gate B decision.
