# Execution Note — S6 Real Baselines and P-005 Decision Brief

**Date:** 2026-08-25
**Operator:** S6 Evaluation Owner / Antigravity Codex
**Lease:** lease-s6-baselines-p005-20260825
**Base Commit:** c0ea9fbf37bc50c88336f198437be031c18d6f64 (trace-bench) /
7bd96e9c5e0f9326b53a074024e7ace889f6e36 (trace)

## Plan of Action

1. **Preflight & Verification of Prerequisites:**
   - Confirm Gate V1a (Runner Integrity) closed PASS (26/26 tests).
   - Confirm Gate D2b (Dataset Normalization) completed across all 7 admitted real datasets with 100% verified key resolution.
   - Confirm Gate V1b Final closed PASS with signed receipts.
   - Confirm Human Gate A (P-002 / P-004) recorded in Decision Log.

2. **Run Standard Baselines Across Admitted Portfolio:**
   - Execute BM25, Dense (ll-MiniLM-L6-v2), Hybrid RRF, HippoRAG PPR, and Flat Hierarchy across the admitted datasets.
   - Execute SIFT1M vector operations evaluation in strict isolation.
   - Track full per-case latency, memory RSS, complete gold coverage, recall@5/20/100, nDCG@10/30, precision@5/10, MRR, abstention accuracy, and errors.
   - Save immutable JSON run logs into docs/program/inbox/s6-baselines-p005-20260825/evidence/runs/.

3. **Subagent Verification & Distribution Auditing:**
   - Subagent A (Statistics & Query-Class Reviewer): Independently verify distribution percentiles (P50, P90, P95, P99), paired t-tests, Wilcoxon signed-rank tests, Cohen's d, and 95% bootstrap confidence intervals from raw run logs.
   - Subagent B (Manifest & Provenance Reviewer): Audit manifest integrity, non-editable imports, and strict fail-closed enforcement.

4. **Synthesize P-005 Decision Brief:**
   - Structure proposed numerical release thresholds across all 5 Release Gates based on observed baseline distributions.
   - Detail statistical significance criteria, practical effect size requirements ($\Delta \ge +0.03$ or  \ge 0.20$), latency/memory budgets, and failure handling.
   - Deliver packet handoff and halt for Human Gate B decision.
