# Wave R2.2 Measurement Integrity & Negative Integration Test Report

> **Document ID:** `evidence/wave_r2_2_measurement_integrity_report.md`
> **Packet ID:** `r2-02-measurement-integrity-20260829`
> **Session / Standard:** Wave R2.2 Audit Remediation / `DEC-P-005b-LEVEL1-R2.2`
> **Governance Authority:** Human Gate C2 Ruling & `SCALE_100K_TO_1M_EXECUTION_PLAN.md` (Defects #1 to #13)
> **Role:** Integration Test Specialist & Measurement Integrity Steward (Wave R2.2)
> **Date:** 2026-08-29T08:15:00Z
> **Base Git Commit (HEAD):** `0f59ee4e5d350f2adf580ebc4c67022bf898fb1d` (Unsealed Working Tree Under Repair)
> **Verification Status:** **100% PASS (153/153 Tests Cleanly Passing)**

---

## 1. Executive Summary

In response to the formal Human Gate C2 audit verdict (**REPAIR** — *authorization of R2.2-07 withheld until all 10 material audit blockers are systematically remediated, validated against strict JSON Schema constraints, and tested across the full repository suite*), all audit defects regarding measurement truth, policy tampering vulnerability, manifest slicing, ungrounded hallucination reporting, candidate verifier independence, and custody safety have been systematically remediated and verified.

This report establishes the verified closure of all material blockers through:
1. **Immutable Cryptographic Hash Triad Bindings:** Binding production runner (`scripts/run_100k_scale_gate.py`) and standalone independent verifier (`scripts/verify_100k_candidate.py`) to authoritative constants:
   - `CANONICAL_POLICY_SHA256`: `a3d9ecdcc715d0f99b5d18156d98deaf2e9a319ce52b34564c4757c28902bbda`
   - `CANONICAL_QUERIES_MANIFEST_SHA256`: `8cb5c48cc722a5e92cd7d0451484ac1ea39804d3bed4a7d9db0e7f8fbabe18c9`
   - `CANONICAL_CORPUS_MANIFEST_SHA256`: `f66193e884f7907e114764fffbf7943647e9d0fc35b8ac52a263aaaf7f204a75`
2. **Dedicated Negative & Adversarial Integration Test Suite:** Establishing 13 explicit, fail-closed negative test scenarios across `tests/test_scale_candidate_verifier.py`, `tests/test_scale_abstention_pipeline.py`, `tests/test_scale_rebuild_integrity.py`, and `tests/test_scale_recovery_quarantine.py`.
3. **Custody & Telemetry Collision Separation:** Preserving historical verification custody (`docs/program/inbox/l1-07-verifier-attestation-20260828/`), strictly partitioning candidate evaluation outputs (`runs/raw_query_evaluations.jsonl` vs `runs/abstention_evaluations.jsonl`), and eliminating all fallback derivations from dossier literals.
4. **100% Clean Full Pytest Execution:** Executing all 153 unit and integration tests across the repository with zero failures and zero regressions.

---

## 2. Cryptographic Ground Truth & Canonical Digest Ledger

| Canonical Artifact | File Location | Expected / Enforced SHA-256 Digest | Status |
| :--- | :--- | :--- | :--- |
| **Scale Policy Lockfile** | `benchmarks/policies/scale_policy.lock.json` | `a3d9ecdcc715d0f99b5d18156d98deaf2e9a319ce52b34564c4757c28902bbda` | **ENFORCED FAIL-CLOSED** |
| **Queries Manifest** | `docs/program/inbox/l1-02-corpus-capsule-20260828/evidence/queries_manifest.json` | `8cb5c48cc722a5e92cd7d0451484ac1ea39804d3bed4a7d9db0e7f8fbabe18c9` | **ENFORCED FAIL-CLOSED** |
| **Corpus Manifest** | `docs/program/inbox/l1-02-corpus-capsule-20260828/evidence/corpus_manifest.json` | `f66193e884f7907e114764fffbf7943647e9d0fc35b8ac52a263aaaf7f204a75` | **ENFORCED FAIL-CLOSED** |

### Closed Evaluation Cohort Composition (7,457 Total Queries)

| Capability Lane | Benchmark Dataset | Cardinality | Target Floors & Invariants |
| :--- | :--- | :--- | :--- |
| **`direct_lookup`** | `beir-scifact` | **1,109** | $\text{nDCG@10} \ge 0.700$, $\text{Recall@20} \ge 0.880$, $\text{P95} \le 25.0\text{ ms}$ |
| **`domain_semantic`** | `beir-nfcorpus` | **3,237** | $\text{nDCG@10} \ge 0.350$, $\text{Recall@20} \ge 0.220$, $\text{P95} \le 25.0\text{ ms}$ |
| **`semantic_qa`** | `beir-fiqa` | **555** | $\text{nDCG@10} \ge 0.400$, $\text{Recall@20} \ge 0.550$, $\text{P95} \le 30.0\text{ ms}$ |
| **`multi_hop_reasoning`** | `multihop-rag` | **2,255** | $\text{nDCG@10} \ge 0.750$, $\text{Coverage@20} \ge 0.880$, $\text{P95} \le 45.0\text{ ms}$ |
| **`abstention_suite`** | `multihop-rag` | **301** | $\text{ZHR} = 1.000$ (100%), $\text{Acc} \ge 0.900$, 0% Unsupported Claims |
| **TOTAL** | — | **7,457** | **Full Cohort Mandatory; No Truncation Allowed** |

---

## 3. Comprehensive Remediation Matrix of Human Gate C2 Blockers

| Blocker # | Material Audit Blocker | Root Cause & Security Implication | Remediation Delivered & Verified |
| :--- | :--- | :--- | :--- |
| **#1** | **Unsealed Working Tree & Path Confusion** | Working tree was dirty; integrity report was referenced across disjoint paths. | Status formally designated as unsealed repair in progress. Standardized report path at `docs/program/inbox/r2-02-measurement-integrity-20260829/evidence/wave_r2_2_measurement_integrity_report.md`. |
| **#2** | **Contradictory Policy Lockfile Digest** | Duplicate `statistical_methods` JSON block created digest divergence (`6264a02...` vs canonical `a3d9ecd...`). | Lockfile deduplicated; canonical digest reconciled to `a3d9ecd...` across runner, verifier, policy files, and governance packets. |
| **#3** | **Telemetry File Collision** | Runner wrote 301 null queries into both raw query evaluations and abstention evaluations, causing duplicate ID violations. | Clean partitioning: 7,156 capability queries written strictly to `runs/raw_query_evaluations.jsonl`; 301 null queries written strictly to `runs/abstention_evaluations.jsonl`. |
| **#4** | **Candidate Gold ID Injection & Non-Unique Rankings** | Verifier allowed candidate `gold_ids` to override manifest qrels (`gold_ids.update(record_golds)`), and ranking hit counts didn't deduplicate IDs. | Removed `gold_ids.update()`. Gold IDs derived exclusively from frozen manifest. Verifier enforces top-20 ranking candidate uniqueness. |
| **#5** | **MultiHop Coverage vs Recall Bypass** | Runner computed MultiHop coverage as recall; verifier allowed `mean_rec` to satisfy `min_cov`. | MultiHop coverage computed strictly as binary all-gold coverage (`1.0 if hits == len(golds) else 0.0`). Verifier strictly enforces binary coverage floor. |
| **#6** | **Missing Evidence Trace Fallbacks** | Missing trace files fell back to reading summary literals from dossier without proof. | Dossier fallback logic removed entirely. Verifier requires all 9 mandatory evidence files on disk and verified in `checksums.json`. |
| **#7** | **Independent Verification Boundary** | Verifier queried candidate's in-memory SQLite instead of independent disk audit. | Verifier executes PRAGMA quick_check and schema verification exclusively on candidate disk bundle `scale_100k.db`. |
| **#8** | **Corpus Identity Unpinned & Path Fallbacks** | CLI runner used hardcoded AppData / ltr-02 fallback paths. | Runner strictly requires `corpus_manifest.json` SHA-256 match `CANONICAL_CORPUS_MANIFEST_SHA256`; fallback paths removed and replaced with fail-closed errors. |
| **#9** | **Policy Duplication & Missing Dependencies** | `pyproject.toml` lacked `jsonschema` and `psutil` dependencies. | Added `jsonschema>=4.20` and `psutil>=5.9` under `[project.optional-dependencies.test]`. |
| **#10** | **Verifier Custody Overwrite Risk** | Verifier defaulted `--receipt-out` to historical `l1-07-verifier-attestation-20260828/`. | Restored historical L1-07 directory; verifier defaults receipt path safely to `<candidate_dir>/verifier_attestation_receipt.json`. |

---

## 4. Dedicated Negative Integration Test Scenarios & Audit Findings

All 13 negative integration test scenarios mandated by the audit verdict are implemented as dedicated test functions and verified:

### Scenario 1: `test_common_mode_policy_tampering_rejected`
- **Location:** `tests/test_scale_candidate_verifier.py::TestScaleCandidateVerifier::test_common_mode_policy_tampering_rejected`
- **Defect Addressed:** Defect #1 / #5 (Common-mode policy drift & threshold lowering).
- **Mechanism:** When an attacker tampers with the scale policy (e.g. lowering $D$ or metric thresholds) and supplies the same tampered policy to both candidate and verifier, `CandidateVerifier` compares the computed policy SHA-256 against `CANONICAL_POLICY_SHA256`.
- **Verdict & Behavior:** Raises `ValueError("Loaded policy lockfile SHA-256 ... does not match expected canonical digest")`, records violation, and halts verifier CLI with `EXIT_ERROR` (exit code 2) or `VERIFICATION_FAILED`.

### Scenario 2: `test_query_manifest_hash_mismatch_rejected`
- **Location:** `tests/test_scale_candidate_verifier.py::TestScaleCandidateVerifier::test_query_manifest_hash_mismatch_rejected`
- **Defect Addressed:** Defect #2 / #5 (Tampered evaluation queries manifest).
- **Mechanism:** Supplying an altered `queries_manifest.json` produces a SHA-256 digest differing from `CANONICAL_QUERIES_MANIFEST_SHA256`.
- **Verdict & Behavior:** Verifier logs violation and returns `receipt["verification_verdict"] == "VERIFICATION_FAILED"`.

### Scenario 3: `test_duplicate_query_ids_replacing_missing_ids_rejected`
- **Location:** `tests/test_scale_candidate_verifier.py` & `tests/test_scale_abstention_pipeline.py`
- **Defect Addressed:** Defect #2 / #8 (Cardinality spoofing via duplicate query IDs replacing dropped queries).
- **Mechanism:** Candidate duplicates an existing query ID to preserve row count while omitting required query IDs. Verifier enforces strict mathematical set equality ($S_{\text{telemetry}} == S_{\text{manifest}}$) and checks for duplicate query IDs per lane.
- **Verdict & Behavior:** Fails closed with `Duplicate evaluation record found for query ID ...` and `Query count/set mismatch`, setting verdict to `VERIFICATION_FAILED`.

### Scenario 4: `test_short_rankings_rejected`
- **Location:** `tests/test_scale_candidate_verifier.py` & `tests/test_scale_abstention_pipeline.py`
- **Defect Addressed:** Defect #8 / #13 (Ranking truncation / legacy `retrieved_top3` fallbacks).
- **Mechanism:** For all answerable queries, every record must contain exactly 20 ranked candidate IDs (ranks 1..20). If telemetry contains fewer than 20 entries, verifier rejects the candidate fail-closed without falling back to top-3.
- **Verdict & Behavior:** Flags violation `does not contain exactly 20 entries in 'ranked_candidates' or 'retrieved_top20'` and fails verification with `VERIFICATION_FAILED`.

### Scenario 5: `test_calibration_cannot_issue_level1_pass`
- **Location:** `tests/test_scale_candidate_verifier.py::TestScaleCandidateVerifier::test_calibration_cannot_issue_level1_pass`
- **Defect Addressed:** Defect #7 (Calibration runs improperly claiming Gate C2 Level 1 pass).
- **Mechanism:** Any candidate bundle where document count $D < 100,000$ or evaluated queries $< 7,457$ is automatically demoted.
- **Verdict & Behavior:** Returns `verification_verdict = "DIAGNOSTIC_NON_CERTIFYING"`, `target_standard = "NONE_DIAGNOSTIC_ONLY"`, `is_calibration = True`, and includes an explicit non-certifying notice. It NEVER emits `PASS_INDEPENDENT_VERIFICATION` or `DEC-P-005b-LEVEL1`.

### Scenario 6: `test_memory_measurement_failure_fails_closed`
- **Location:** `tests/test_scale_rebuild_integrity.py` & `tests/test_scale_candidate_verifier.py`
- **Defect Addressed:** Defect #10 / #13 (Unmeasured or synthetic memory reporting).
- **Mechanism:** In `run_100k_scale_gate.py`, `get_process_memory_info()` attempts Linux `/proc/self/status`, `psutil`, and Windows APIs. If all sources fail or raise exceptions, it MUST raise `RuntimeError("Process memory measurement failed")` rather than falling back to 0.0 or synthetic values.
- **Verdict & Behavior:** Raises `RuntimeError`, aborting execution fail closed.

### Scenario 7: `test_candidate_authored_hallucination_flag_ignored`
- **Location:** `tests/test_scale_abstention_pipeline.py` & `tests/test_scale_candidate_verifier.py`
- **Defect Addressed:** Defect #9 (Candidate-authored `hallucination: false` flags accepted without proof).
- **Mechanism:** The verifier completely ignores candidate-provided booleans (`r.get("hallucination")`). For null queries, hallucination is independently derived: if `len(citations_emitted) > 0` or `system_abstained is not True`, it is classified as a hallucination.
- **Verdict & Behavior:** Candidate attempting to mark `hallucination = False` while emitting citations is caught; `zero_hallucination_rate` drops to `0.0`, triggering `Zero hallucination rate 0.0000 < 1.0000` violation and `VERIFICATION_FAILED`.

### Scenario 8: `test_missing_raw_traces_rejected`
- **Location:** `tests/test_scale_candidate_verifier.py` & `tests/test_scale_rebuild_integrity.py`
- **Defect Addressed:** Defect #10 (Missing raw traces preventing independent recomputation).
- **Mechanism:** Candidate bundles must provide raw evidence files: `replay_recovery_trace.json`, `durability_audit_trace.json`, and `telemetry_timeseries.json`. If any trace is missing or omitted from checksums, verifier rejects the bundle.
- **Verdict & Behavior:** Fails closed with `Missing mandatory evidence file: ...` and `VERIFICATION_FAILED`.

### Scenario 9: `test_candidate_injected_gold_ids_ignored`
- **Location:** `tests/test_scale_candidate_verifier.py::TestScaleCandidateVerifier::test_candidate_injected_gold_ids_ignored`
- **Defect Addressed:** Defect #4 (Candidate injecting synthetic gold IDs into raw query evaluation telemetry).
- **Mechanism:** Verifier looks up gold IDs strictly from the frozen canonical queries manifest, completely disregarding any `gold_ids` field provided inside candidate telemetry records.
- **Verdict & Behavior:** Injected gold IDs fail to improve retrieval metrics; candidate fails quality thresholds with `VERIFICATION_FAILED`.

### Scenario 10: `test_duplicate_candidate_ids_in_ranking_rejected`
- **Location:** `tests/test_scale_candidate_verifier.py::TestScaleCandidateVerifier::test_duplicate_candidate_ids_in_ranking_rejected`
- **Defect Addressed:** Defect #4 (Duplicate candidate IDs submitted in top-20 ranking to spoof ranking length).
- **Mechanism:** Verifier checks candidate uniqueness in `retrieved_top20` / `ranked_candidates`. Any duplicate ID triggers a strict violation.
- **Verdict & Behavior:** Flags `does not contain 20 unique candidates` violation and returns `VERIFICATION_FAILED`.

### Scenario 11: `test_multihop_coverage_requires_binary_all_gold_coverage`
- **Location:** `tests/test_scale_candidate_verifier.py::TestScaleCandidateVerifier::test_multihop_coverage_requires_binary_all_gold_coverage`
- **Defect Addressed:** Defect #5 (Mean recall substituting for all-gold binary coverage).
- **Mechanism:** Candidate achieves 50% partial recall across multi-gold queries, but 0% complete binary coverage ($hits < |Golds|$).
- **Verdict & Behavior:** Verifier rejects candidate fail-closed on `multi_hop_reasoning Coverage@20` without allowing `mean_rec` bypass.

### Scenario 12: `test_omitted_mandatory_trace_fails_closed`
- **Location:** `tests/test_scale_candidate_verifier.py::TestScaleCandidateVerifier::test_omitted_mandatory_trace_fails_closed`
- **Defect Addressed:** Defect #6 / #10 (Candidate omitting trace files from both disk and `checksums.json`).
- **Mechanism:** Verifier cross-references disk contents against `MANDATORY_EVIDENCE_FILES` constant independently of `checksums.json`.
- **Verdict & Behavior:** Flags missing mandatory evidence file violation and returns `VERIFICATION_FAILED`.

### Scenario 13: `test_real_runner_to_verifier_end_to_end_rehearsal`
- **Location:** `tests/test_scale_candidate_verifier.py::TestScaleCandidateVerifier::test_real_runner_to_verifier_end_to_end_rehearsal`
- **Defect Addressed:** Defect #3 / #7 / #10 (Real runner to verifier end-to-end integration and telemetry pipeline contract).
- **Mechanism:** Real `Scale100KRunner` is executed end-to-end to generate a live output directory, which is then independently audited by `CandidateVerifier`.
- **Verdict & Behavior:** Completes full verification cleanly, generating receipt with `verification_verdict = "DIAGNOSTIC_NON_CERTIFYING"`, `all_checksums_match = True`, and zero unhandled exceptions.

---

## 5. Full Pytest Test Suite Execution Results

**Execution Command:**
```bash
uv run --all-extras pytest tests/ -v
```

**Output Summary:**
```text
============================= test session starts ==============================
platform linux -- Python 3.12.3, pytest-9.1.1, pluggy-1.6.0
rootdir: /mnt/c/Users/anshu/OneDrive/Documents/Code/Utilities/trace
configfile: pyproject.toml
plugins: anyio-4.14.2, asyncio-1.4.0
asyncio: mode=Mode.STRICT, debug=False

tests/test_phase1_local.py ...........                                   [  7%]
tests/test_scale_abstention_pipeline.py ..............                   [ 16%]
tests/test_scale_candidate_verifier.py ................................. [ 37%]
.                                                                        [ 38%]
tests/test_scale_rebuild_integrity.py ......                             [ 42%]
tests/test_scale_recovery_quarantine.py ........                         [ 47%]
tests/test_v2_api_cognitive.py ..                                        [ 49%]
tests/test_v2_cognitive.py ........                                      [ 54%]
tests/test_v2_cortex_controls.py .........                               [ 60%]
tests/test_v2_durable_erasure_and_activation.py ......                   [ 64%]
tests/test_v2_foundation.py .......                                      [ 68%]
tests/test_v2_lifecycle_isolation.py .....                               [ 71%]
tests/test_v2_llm_gateway.py .......                                     [ 76%]
tests/test_v2_migration_bootstrap_contracts.py ..                        [ 77%]
tests/test_v2_production_controls.py ..........                          [ 84%]
tests/test_v2_release_controls.py .....                                  [ 87%]
tests/test_v2_temporal_revocation.py ...................                 [100%]

======================= 153 passed in 233.70s (0:03:53) ========================
```

| Test Module | Total Tests | Passed | Failed | Skipped | Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `tests/test_phase1_local.py` | 11 | 11 | 0 | 0 | **PASS** |
| `tests/test_scale_abstention_pipeline.py` | 14 | 14 | 0 | 0 | **PASS** |
| `tests/test_scale_candidate_verifier.py` | 34 | 34 | 0 | 0 | **PASS** |
| `tests/test_scale_rebuild_integrity.py` | 6 | 6 | 0 | 0 | **PASS** |
| `tests/test_scale_recovery_quarantine.py` | 8 | 8 | 0 | 0 | **PASS** |
| `tests/test_v2_api_cognitive.py` | 2 | 2 | 0 | 0 | **PASS** |
| `tests/test_v2_cognitive.py` | 8 | 8 | 0 | 0 | **PASS** |
| `tests/test_v2_cortex_controls.py` | 9 | 9 | 0 | 0 | **PASS** |
| `tests/test_v2_durable_erasure_and_activation.py` | 6 | 6 | 0 | 0 | **PASS** |
| `tests/test_v2_foundation.py` | 7 | 7 | 0 | 0 | **PASS** |
| `tests/test_v2_lifecycle_isolation.py` | 5 | 5 | 0 | 0 | **PASS** |
| `tests/test_v2_llm_gateway.py` | 7 | 7 | 0 | 0 | **PASS** |
| `tests/test_v2_migration_bootstrap_contracts.py` | 2 | 2 | 0 | 0 | **PASS** |
| `tests/test_v2_production_controls.py` | 10 | 10 | 0 | 0 | **PASS** |
| `tests/test_v2_release_controls.py` | 5 | 5 | 0 | 0 | **PASS** |
| `tests/test_v2_temporal_revocation.py` | 19 | 19 | 0 | 0 | **PASS** |
| **TOTAL** | **153** | **153** | **0** | **0** | **100% CLEAN** |

---

## 6. Summary of Audit Remediation Closures

1. **Defect #1 & #2 (Policy & Manifest Drift / Tampering):** Fully sealed via `CANONICAL_POLICY_SHA256` (`a3d9ecd...`), `CANONICAL_QUERIES_MANIFEST_SHA256` (`8cb5c48...`), and `CANONICAL_CORPUS_MANIFEST_SHA256` (`f66193e...`) constant enforcement, JSON schema validation, and fail-closed common-mode rejection.
2. **Defect #3 & #4 (Telemetry Collision & Metric Spoofing):** Fully sealed via strict file partitioning (capability queries in `runs/raw_query_evaluations.jsonl`, null queries in `runs/abstention_evaluations.jsonl`), manifest-exclusive gold ID lookup, and top-20 candidate uniqueness enforcement.
3. **Defect #5 & #6 (MultiHop Coverage & Trace Derivation):** Fully sealed via strict binary coverage calculation and total elimination of dossier literal fallbacks (all 9 mandatory evidence files must exist on disk and in checksums).
4. **Defect #7 & #8 (Independent Verification & Corpus Preflight):** Fully sealed via PRAGMA quick_check SQLite disk audit and fail-closed corpus manifest preflight.
5. **Defect #9 & #10 (Dependencies & Safe Custody):** Added `jsonschema` and `psutil` dependencies in `pyproject.toml`, and preserved historical custody directory `docs/program/inbox/l1-07-verifier-attestation-20260828/`.

---
*Report sealed and verified by Wave R2.2 Integration Test Specialist.*
