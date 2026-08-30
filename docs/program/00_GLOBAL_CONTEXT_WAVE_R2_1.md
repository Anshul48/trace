# Global Context: Wave R2.1 Scale Certification Recovery (Measurement Integrity & Truth Protocol)

> **Context Version:** `2.1.0`
> **Session State:** ACTIVE EXECUTION
> **Target Scale:** $D = 100,000$ unique documents (Level 1)
> **Target Standard:** DEC-P-005b-LEVEL1
> **Governance Authority:** Human Gate C2 Ruling (`REPAIR — promote_100k denied; 1M unauthorized`)
> **Parent Coordinator:** `5da88617-b762-4287-b08e-6b9d983937f2`
> **Date:** 2026-08-29

---

## 1. Governance Principles & Strict Gate Protocol

1. **Gate C2 Status:** Status is strictly **`REPAIR`**. `promote_100k` is **DENIED**. Level 2 / 1M planning is **UNAUTHORIZED**.
2. **Fail-Closed Contract:** Runner and verifier MUST exit with code 1 (`CANDIDATE_FAILED` / `VERIFICATION_FAILED`) whenever any metric breaches any frozen threshold.
3. **No Retrospective Threshold Relaxation:** No performance floors or latency limits are relaxed to rescue the candidate. Performance contracts must reflect true measurements.
4. **Independent Verifier Separation:** The verifier MUST recompute every retrieval metric (nDCG@10, Recall@20, Coverage@20, P95 latency, Zero Hallucination Rate, Abstention Accuracy) directly from raw top-20 ranking telemetry and frozen qrels without trusting dossier self-reports.
5. **Real Un-Labeled Abstention Path:** Null queries MUST pass through the exact same retrieval and citation generation pipeline as capability queries without exposing query labels or branching on `system_abstained = True`.
6. **Qrels / Corpus Cohort Closure:** 100% of evaluated queries in the evaluation suite MUST have their complete gold evidence present in the ingested 100K database capsule.

---

## 2. Seven Material Defects & Non-Negotiable Repairs

| # | Material Defect Identified | Wave R2.1 Remediation Contract |
| :--- | :--- | :--- |
| **1** | **Control-Flow Forced Abstention** | Remove `system_abstained = True`. Route null queries through unified retrieval and citation verification filter. |
| **2** | **Verifier Metric Dependency** | Remove 500-record cap; emit complete top-20 candidate rankings and full gold sets in `raw_query_evaluations.jsonl`. Verifier recomputes all metrics directly. |
| **3** | **Incomplete Fail-Closed Enforcement** | Enforce all declared latency thresholds (SciFact $\le 25\text{ ms}$, NFCorpus $\le 25\text{ ms}$, FiQA $\le 30\text{ ms}$, MultiHop $\le 45\text{ ms}$), memory, scale, and abstention. |
| **4** | **Premature Retrieval Diagnosis / FiQA Slicing** | Construct qrels-closed query cohort where all evaluated queries have their full gold evidence inside the 100K ingested capsule. |
| **5** | **Storage Proposal Insufficiency** | Author `scripts/profile_scale_storage.py` and generate page-level storage breakdown across 6 tables and 13 indexes. |
| **6** | **Unsealed Git Custody** | Verify all Wave R2.1 code, manifests, and test fixtures are clean, committed, and content-addressed. |
| **7** | **HMAC Secret Embedded in Verifier** | Replace repo-internal HMAC with content-addressed SHA-256 Merkle root binding over candidate evidence. |

---

## 3. Work Breakdown & Subagent Dispatch Plan

- **Task R2.1-01 (Data Steward):** Build qrels-closed evaluation query cohort in `docs/program/inbox/l1-02-corpus-capsule-20260828/`.
- **Task R2.1-02 (Scale Architect):** Repair `scripts/run_100k_scale_gate.py` (un-labeled abstention, top-20 ranking telemetry, complete fail-closed latency enforcement).
- **Task R2.1-03 (Storage Specialist):** Author `scripts/profile_scale_storage.py` and produce `storage_page_accounting_report.md`.
- **Task R2.1-04 (Quarantine & Test Specialist):** Author `tests/test_scale_abstention_pipeline.py` and run full pytest suite.
- **Task R2.1-05 (Scale Architect):** Execute 1K and 10K calibration runs.
- **Task R2.1-06 (Independent Verifier):** Repair `scripts/verify_100k_candidate.py` (independent metric recomputation, fail-closed latency enforcement, cryptographic evidence Merkle root).
- **Task R2.1-07 (Execution & Attestation):** Run full 100K candidate gate and standalone verifier; deliver sealed attestation receipt and audit reports.
