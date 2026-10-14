# Operational Handoff: Wave R2.2 Worktree Reconciliation & Integrity Binding

> **Handoff ID:** `docs/program/inbox/r2-02-measurement-integrity-20260829/handoff.md`
> **Source Task:** Tasks R2.2-01 & R2.2-02 (Worktree Reconciliation & Integrity Binding)
> **Source Packet:** `r2-02-measurement-integrity-20260829`
> **Author / Role:** Worktree & Custody Steward (Wave R2.2)
> **Target Recipients:**
> - **Task R2.2-03 (Scale Implementer):** Runner Contract Execution (consume frozen cohorts, emit full Top-20 telemetry)
> - **Task R2.2-04 (Evaluator / Implementer):** Un-Labeled Abstention & Citations
> - **Task R2.2-05 (Verifier Implementer):** Standalone Independent Verifier Binding & Recomputation
> - **Task R2.2-06 (Test Owner):** Negative Integration Test Suite
> - **Task R2.2-07 (Run Operator):** Fresh Full 100K Measurement Candidate Run
> - **Task R2.2-08 (Independent Verifier):** Standalone Verifier Attestation
> **Date:** 2026-08-29T03:51:10Z
> **Status:** **IMPLEMENTED_AND_TESTED_UNSEALED (REPAIR_IN_PROGRESS)**

---

## 1. Executive Summary & Sealed Identity Bindings

Tasks **R2.2-01** (Worktree Reconciliation) and **R2.2-02** (Query & Policy Lock Binding) are **COMPLETED**.

The complete repository worktree (11 modified tracked files, 101 untracked files) has been audited, categorized, and reconciled. All diagnostic and historical run outputs in `benchmarks/runs/` are formally isolated and designated non-certifying.

The execution and verification apparatus is now strictly bound to the following immutable, content-addressed artifacts:

```text
========================================================================================
                      WAVE R2.2 CRYPTOGRAPHIC IDENTITY LOCKS
========================================================================================
1. Canonical Scale Policy Lockfile:
   - Path: benchmarks/policies/scale_policy.lock.json
   - Policy ID: DEC-P-005b-LEVEL1-R2.2 (Schema 2.2.0)
   - SHA-256: a3d9ecdcc715d0f99b5d18156d98deaf2e9a319ce52b34564c4757c28902bbda

2. Canonical Evaluation Queries Cohort Manifest:
   - Path: docs/program/inbox/l1-02-corpus-capsule-20260828/evidence/queries_manifest.json
   - Total Queries: 7,457 (7,156 answerable + 301 null)
   - SHA-256: 8cb5c48cc722a5e92cd7d0451484ac1ea39804d3bed4a7d9db0e7f8fbabe18c9

3. Worktree Reconciliation Report:
   - Path: docs/program/inbox/r2-02-measurement-integrity-20260829/evidence/worktree_reconciliation_report.md
   - SHA-256: d11db9691e607922e6269cc2e31eaa4ea7cb0d657bd2a833622f6277241b146b
========================================================================================
```

---

## 2. Downstream Directives & Execution Contracts

### 2.1 Directive for Task R2.2-03 (Runner Contract Execution)
1. **Dynamic Policy & Manifest Loading:** Update `scripts/run_100k_scale_gate.py` to dynamically load `benchmarks/policies/scale_policy.lock.json` and verify its SHA-256 digest (`a3d9ecdcc715d0f99b5d18156d98deaf2e9a319ce52b34564c4757c28902bbda`).
2. **Dynamic Query Manifest Loading:** Consume query IDs and suites directly from `docs/program/inbox/l1-02-corpus-capsule-20260828/evidence/queries_manifest.json` (digest `8cb5c48cc722a5e92cd7d0451484ac1ea39804d3bed4a7d9db0e7f8fbabe18c9`).
3. **Zero Sampling / Full Cohort:** Eliminate all `[:200]` slicing. Evaluate 100% of the declared 7,457 queries:
   - 1,109 SciFact queries (`direct_lookup`)
   - 3,237 NFCorpus queries (`domain_semantic`)
   - 555 FiQA queries (`semantic_qa`)
   - 2,255 MultiHop queries (`multi_hop_reasoning`)
   - 301 Null queries (`abstention_suite`)
4. **Full Top-20 Ranking Telemetry:** Emit complete top-20 candidate objects `[{"doc_id": "...", "score": ..., "rank": ...}]` for every evaluated query into `raw_query_evaluations.jsonl`.
5. **Fail-Closed Threshold Enforcement:** Compare all empirical scores against the loaded policy lock and exit with code 1 (`CANDIDATE_FAILED`) on any metric or latency breach.

### 2.2 Directive for Task R2.2-04 (Un-Labeled Abstention & Citations)
1. **No Truth Flags / No Label Leakage:** Ensure null queries pass through the exact same retrieval and citation generation code path as answerable queries without passing ground truth flags or branching on `system_abstained = True`.
2. **Strict Abstention Scoring:** Verify engine outputs `ABSTAIN_UNANSWERABLE` with empty citations on all 301 null queries, achieving `zero_hallucination_rate == 1.000` (100.0%).

### 2.3 Directive for Task R2.2-05 (Standalone Independent Verifier)
1. **Dynamic Policy & Manifest Loading:** Update `scripts/verify_100k_candidate.py` to dynamically load `benchmarks/policies/scale_policy.lock.json` and `queries_manifest.json` by exact digest.
2. **Independent Metric Recomputation:** Recompute unfloored nDCG@10, Recall@20, Coverage@20, P95 latency, ZHR, and Abstention Accuracy directly from `raw_query_evaluations.jsonl` and frozen qrels across all 7,457 queries.
3. **Direct SQLite Inspection:** Verify table schemas, span offset reconstruction on 1,000 anchor proofs, atom retention (1.000), and execute SQL query `SELECT MAX(deg) FROM (SELECT src, COUNT(*) as deg FROM edge_versions GROUP BY src)` verifying max degree $\le 10$.
4. **Encoding & Exit Code:** Enforce UTF-8 console output and clean schema exit codes (`0 = ATTESTATION_SEALED`, `1 = CANDIDATE_FAILED`, `2 = VERIFICATION_ERROR`).

### 2.4 Directive for Task R2.2-06 (Negative Integration Test Suite)
1. **Negative Integration Fixtures:** Author comprehensive tests in `tests/test_scale_candidate_verifier.py` and `tests/test_scale_abstention_pipeline.py` proving fail-closed rejection on:
   - Stale or mismatched timestamps
   - Truncated query evaluations (< 7,457 rows)
   - Missing lanes or missing top-20 candidate objects
   - Forced abstention / label leakage
   - Policy drift or manifest digest mismatch
   - Database substitution or SQLite mutation during verification
   - Memory RSS or storage multiplier breach

### 2.5 Directive for Task R2.2-07 & R2.2-08 (Candidate Execution & Verification)
1. **Isolated Output Directory:** Execute fresh candidate into a new, clean output root (e.g. `benchmarks/runs/100k_wave_r2_2_candidate/`).
2. **No Artifact Reuse:** Never reuse databases or dossiers from prior runs (`100k_scale_candidate`, `100k_calibration`, `diagnostic`).
3. **Complete Evidence Custody:** Verify that all 7,457 query evaluations and `scale_100k.db` are retained and verified by the independent verifier.

---

## 3. Invariant & Stop-Rule Summary

| Trigger Condition | Required Action |
| :--- | :--- |
| Any policy digest mismatch ($\ne \text{6264a02...}$) | Immediate fail-closed abort (`VERIFICATION_ERROR`). |
| Any manifest digest mismatch ($\ne \text{8cb5c48...}$) | Immediate fail-closed abort (`VERIFICATION_ERROR`). |
| Any query count deficit (< 7,457 evaluated rows) | Immediate fail-closed candidate rejection (`CANDIDATE_FAILED`). |
| Any missing Top-20 ranking candidate array | Immediate fail-closed candidate rejection (`CANDIDATE_FAILED`). |
| Hardcoded threshold override in code | Immediate fail-closed candidate rejection (`POLICY_VIOLATION`). |
| Reusing Aug-28 candidate database or dossier | Immediate candidate rejection (`INVALID_RUN`). |

---

## 4. Verification Checkpoint

```bash
# Verify Policy Lock Digest
python3 -c "import hashlib; print(hashlib.sha256(open('benchmarks/policies/scale_policy.lock.json','rb').read()).hexdigest())"
# Expected: a3d9ecdcc715d0f99b5d18156d98deaf2e9a319ce52b34564c4757c28902bbda

# Verify Queries Manifest Digest
python3 -c "import hashlib; print(hashlib.sha256(open('docs/program/inbox/l1-02-corpus-capsule-20260828/evidence/queries_manifest.json','rb').read()).hexdigest())"
# Expected: 8cb5c48cc722a5e92cd7d0451484ac1ea39804d3bed4a7d9db0e7f8fbabe18c9
```
