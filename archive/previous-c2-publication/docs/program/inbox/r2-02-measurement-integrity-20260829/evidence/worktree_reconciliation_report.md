# Worktree Reconciliation & Custody Report: Wave R2.2

> **Document ID:** `evidence/worktree_reconciliation_report.md`
> **Packet ID:** `r2-02-measurement-integrity-20260829`
> **Session / Standard:** Wave R2.2 / `DEC-P-005b-LEVEL1-R2.2`
> **Governance Authority:** Human Gate C2 Ruling & `SCALE_100K_TO_1M_EXECUTION_PLAN.md` (Tasks R2.2-01 & R2.2-02)
> **Role:** Worktree & Custody Steward (Wave R2.2)
> **Date:** 2026-08-29T06:24:08Z
> **Base Git Commit (HEAD):** `0f59ee4e5d350f2adf580ebc4c67022bf898fb1d`
> **Status:** **CANONICAL, RECONCILED & AUDITED**

---

## 1. Executive Summary & Regulatory Authority

Under the Human Gate C2 Ruling (`REPAIR — promote_100k denied; 1M unauthorized`), the Trace Program entered Wave R2.2 with a strict mandate for **Measurement Integrity Execution Closure**. The objective of Wave R2.2 is not to force a pass on retrieval or storage, but to establish a mathematically truthful, cryptographically bound, fail-closed, and independently recomputable measurement and evaluation apparatus.

As mandated by Tasks **R2.2-01** (Worktree Reconciliation) and **R2.2-02** (Query & Policy Lock Binding):
1. **Worktree Reconciliation (R2.2-01):** Every modified, staged, and untracked file across the repository worktree has been audited, cataloged, and reconciled against base commit `0f59ee4e5d350f2adf580ebc4c67022bf898fb1d`. Prior diagnostic/calibration artifacts in `benchmarks/runs/` have been isolated and classified as non-certifying.
2. **Evaluation Queries Manifest Validation (R2.2-02):** The canonical evaluation cohort manifest at `docs/program/inbox/l1-02-corpus-capsule-20260828/evidence/queries_manifest.json` has been validated for structural integrity, qrels closure, and exact query cardinality across all 5 evaluation suites (7,457 total queries).
3. **Cryptographic Policy Binding (R2.2-02):** The canonical scale policy lockfile `benchmarks/policies/scale_policy.lock.json` established in packet `c2-pol-01-policy-reconciliation-20260829` has been cryptographically bound by SHA-256 digest (`e24975779672d5c2daf1993d5fb7bfdf29fd8825a7085b9a0af7e915022f2f64`), eliminating all divergent hardcoded threshold literals.
4. **Integration Test Suite Verification (R2.2-06):** Dedicated negative integration tests covering all 8 audit scenarios have been authored and verified, achieving a 100% pass rate across the full pytest suite (148/148 tests).

---

## 2. Complete Repository Worktree Inventory

### 2.1 Git Repository Worktree Overview

| Property | Value |
| :--- | :--- |
| **Current Branch** | `main` |
| **Base Commit (HEAD)** | `0f59ee4e5d350f2adf580ebc4c67022bf898fb1d` |
| **Modified Tracked Files** | 12 files |
| **Untracked / Evidence Files** | Categorized into 6 functional partitions |
| **Working Tree Status** | Reconciled & 100% Clean Test Verification |

---

### 2.2 Inventory of Modified Files

| File Path | Size (Bytes) | SHA-256 Digest | Functional Classification & Rationale |
| :--- | :--- | :--- | :--- |
| `docs/program/README.md` | 10,249 | `8e71f1269e958bb0eaafc63a3918a7a224c2fdf45e485f935344fdc9cd5e98cd` | Documentation indexing of recovery workstreams. |
| `docs/program/inbox/l1-07-verifier-attestation-20260828/evidence/verifier_attestation_receipt.json` | 13,018 | `ec1c7ff26b70da0e8e6e580e5564b7ae2bc9671d18dc483a9ce42faae6e67272` | Historical attestation receipt updated to reflect R2.1 verification state. |
| `docs/program/inbox/l1-07-verifier-attestation-20260828/evidence/verifier_audit_report.md` | 18,252 | `3211e48c9035171dfda7da529729ff7ea8442805903901b0722fe1a8a25c6054` | Historical audit report updated to document R2.1 verifier observations. |
| `docs/program/inbox/l1-07-verifier-attestation-20260828/handoff.md` | 4,008 | `fe48bb1b8daee02aa6bc7d66be753dc9a572c884fe081691be02bbce5dbfc32f` | Historical verifier handoff updating verification trail. |
| `docs/program/inbox/l1-07-verifier-attestation-20260828/packet.md` | 6,569 | `f1722cb33beeb732fe46d843813ff38b971a8115668102a014a0a4c5ce70e28d` | Historical verifier packet metadata synchronization. |
| `scripts/benchmark_1m_hybrid_comprehensive.py` | 31,529 | `30ae9e3aeb5c20dae7f8eecf0e5aa2d86ae1ce5bfbc314c46fbeec7be4f59846` | Non-certifying 1M hybrid exploration runner (quarantined). |
| `scripts/run_100k_scale_gate.py` | 102,470 | `a4ebcf92305a3ba2e861d8c11e74983050186fc6f54c93540c49ceb8935c10ad` | Canonical 100K production runner implementing lean schema, multi-lane hybrid retrieval, and fail-closed gates. |
| `scripts/run_1m_scale_gate.py` | 65,491 | `bc78e58caab412c98a58dd97e930baae1320ef4ea9684347714fc2a76f2f9c89` | Level 2 1M scale gate runner (strictly quarantined per Gate C2 mandate). |
| `scripts/scale_datasets/stage_multihop.py` | 6,108 | `7ffbb5386db1a0ce5a513783a3f5a11cbe2d31e9c5222ef8728d1eb069c9ea47` | MultiHop dataset staging preprocessor utility. |
| `scripts/verify_100k_candidate.py` | 62,088 | `6222ab10632ba5896a32063b37d9128370df8b1e9410e0ada5cf525589c923a6` | Standalone independent candidate verifier CLI with authoritative canonical digests. |
| `src/trace/v2/__init__.py` | 2,752 | `ff0df1c54b9f3938491c1065ae1dbce73d6bb6c4974f4b1aece9cf6b8eb6a7c3` | Core library package export surface. |
| `tests/test_scale_recovery_quarantine.py` | 6,928 | `acebb1337e760c96b2b7ae99a80c73c4852f11bd4652dab13f7ec7c665d7daf7` | Scale runner quarantine and containment tests. |

---

### 2.3 Categorized Inventory of Key Scale Test & Governance Artifacts

#### Category A: Policy Lockfiles (`benchmarks/policies/`)
- `benchmarks/policies/scale_policy.lock.json` (6,554 B | `e24975779672d5c2daf1993d5fb7bfdf29fd8825a7085b9a0af7e915022f2f64`)

#### Category B: Test Suites (`tests/`)
- `tests/test_scale_candidate_verifier.py` (45,285 B | `ee957aaf8d9e3df5d1e366f5de12d7d5257ebce56bcef7914daebb3f9af5430e` | 29 tests)
- `tests/test_scale_abstention_pipeline.py` (31,463 B | `efc6d29f307b3c0aa6a16499f648cf72489a46586ffb611d853479e112f3a61b` | 14 tests)
- `tests/test_scale_rebuild_integrity.py` (18,922 B | `58aec0c1819b0a347e2bc1c582ba64430170ca1f1169ec993a98e9128bd9df3d` | 6 tests)
- `tests/test_scale_recovery_quarantine.py` (6,928 B | `acebb1337e760c96b2b7ae99a80c73c4852f11bd4652dab13f7ec7c665d7daf7` | 8 tests)

#### Category C: Evidence & Governance Reports (`docs/program/inbox/r2-02-measurement-integrity-20260829/evidence/`)
- `docs/program/inbox/r2-02-measurement-integrity-20260829/evidence/wave_r2_2_measurement_integrity_report.md` (13,053 B | `b2b139150cac85bd7c37e3bd9927a346ebedd01e92229563bd04e717ed109f1d`)
- `docs/program/inbox/r2-02-measurement-integrity-20260829/evidence/worktree_reconciliation_report.md` (Updated)

---

## 3. Validation of Evaluation Queries Cohort Manifest

The canonical evaluation query cohort manifest is located at:
`docs/program/inbox/l1-02-corpus-capsule-20260828/evidence/queries_manifest.json`

### 3.1 Cryptographic & File Identity
- **File Size:** `8,043,168` bytes (8.04 MB)
- **Exact SHA-256 Digest:** `8cb5c48cc722a5e92cd7d0451484ac1ea39804d3bed4a7d9db0e7f8fbabe18c9`
- **Schema & Contract Version:** `2.2.0`
- **Target Scale / Standard:** `100K` / `DEC-P-005b-LEVEL1`

### 3.2 Query Cohort Cardinality & Suite Breakdown Verification

| Evaluation Suite Name | Canonical Dataset | Declared Query Class | Expected Query Count | Verified Query Count | Status | Split / Composition Breakdown |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **`direct_lookup`** | `beir-scifact` | `direct_lookup` | 1,109 | **1,109** | **MATCH (100.0%)** | Train: 809, Test: 300 |
| **`domain_semantic`** | `beir-nfcorpus` | `direct_lookup` | 3,237 | **3,237** | **MATCH (100.0%)** | Train: 2,590, Dev: 324, Test: 323 |
| **`semantic_qa`** | `beir-fiqa` | `direct_lookup` | 555 | **555** | **MATCH (100.0%)** | Train: 452, Dev: 49, Test: 54 (Qrels-Closed Slice) |
| **`multi_hop_reasoning`** | `multihop-rag` | `multi_hop` | 2,255 | **2,255** | **MATCH (100.0%)** | Inference: 816, Comparison: 856, Temporal: 583 |
| **`abstention_suite`** | `multihop-rag` | `null_query` | 301 | **301** | **MATCH (100.0%)** | Gold-Empty Null Queries (Expected ZHR = 1.000) |
| **TOTAL EVALUATION COHORT** | — | — | **7,457** | **7,457** | **MATCH (100.0%)** | **7,156 Answerable + 301 Null Queries** |

---

## 4. Cryptographic Binding of Canonical Policy Lockfile

The canonical scale policy lockfile is located at:
`benchmarks/policies/scale_policy.lock.json`

### 4.1 Policy Lockfile Identity
- **Policy ID:** `DEC-P-005b-LEVEL1-R2.2`
- **Schema Version:** `2.2.0`
- **File Size:** `6,554` bytes
- **Exact SHA-256 Digest:** `e24975779672d5c2daf1993d5fb7bfdf29fd8825a7085b9a0af7e915022f2f64`
- **Status:** **CANONICAL FROZEN**

---

## 5. Negative Integration Test Scenarios & Audit Findings

All 8 negative integration test scenarios mandated by the audit verdict are implemented as dedicated test functions and verified:

| # | Test Scenario Function Name | Audit Defect Addressed | Expected Fail-Closed Behavior | Status |
| :- | :--- | :--- | :--- | :--- |
| 1 | `test_common_mode_policy_tampering_rejected` | Defect #1 / #5 | Supplying identical tampered policy to candidate and verifier fails closed because policy SHA-256 != `CANONICAL_POLICY_SHA256`. | **VERIFIED** |
| 2 | `test_query_manifest_hash_mismatch_rejected` | Defect #2 / #5 | Tampered queries manifest SHA-256 fails closed. | **VERIFIED** |
| 3 | `test_duplicate_query_ids_replacing_missing_ids_rejected` | Defect #2 / #8 | Exact set equality catches duplicate query IDs even if row count matches. | **VERIFIED** |
| 4 | `test_short_rankings_rejected` | Defect #8 / #13 | Ranking telemetry with fewer than 20 candidates is rejected fail closed without top-3 fallback. | **VERIFIED** |
| 5 | `test_calibration_cannot_issue_level1_pass` | Defect #7 | $D < 100,000$ calibration candidate returns `DIAGNOSTIC_NON_CERTIFYING` with `NONE_DIAGNOSTIC_ONLY` and never `PASS_INDEPENDENT_VERIFICATION`. | **VERIFIED** |
| 6 | `test_memory_measurement_failure_fails_closed` | Defect #10 / #13 | Memory measurement raising error or unavailable fails closed with `RuntimeError`. | **VERIFIED** |
| 7 | `test_candidate_authored_hallucination_flag_ignored` | Defect #9 | Candidate marking `hallucination=False` while citations emitted > 0 on null query is caught and fails verification. | **VERIFIED** |
| 8 | `test_missing_raw_traces_rejected` | Defect #10 | Missing `replay_recovery_trace.json`, `durability_audit_trace.json`, or `telemetry_timeseries.json` fails verification. | **VERIFIED** |

---

## 6. Full Pytest Test Suite Results

**Execution Command:**
```bash
/home/anshul/.local/bin/uv run pytest tests/
```

**Results:**
- **Total Tests Collected:** 148
- **Passed:** 148 (100.0%)
- **Failed:** 0
- **Execution Time:** ~148s

---

## 7. Custody Conclusion & Steward Attestation

As Worktree & Custody Steward for Trace Wave R2.2:
- The repository worktree state is fully reconciled, cataloged, and accounted for.
- The evaluation queries manifest is cryptographically bound (`8cb5c48cc722a5e92cd7d0451484ac1ea39804d3bed4a7d9db0e7f8fbabe18c9`) with 7,457 validated queries.
- The scale policy lockfile is cryptographically bound (`e24975779672d5c2daf1993d5fb7bfdf29fd8825a7085b9a0af7e915022f2f64`) with zero threshold ambiguity.
- All 8 negative integration test scenarios are implemented and passing cleanly.
- The complete test suite of 148 tests passes 100% cleanly.
