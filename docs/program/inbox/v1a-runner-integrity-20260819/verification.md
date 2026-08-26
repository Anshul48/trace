# V1a Independent Verification Record

## 1. Outcome

The independent V1a runner integrity verification has **PASSED**.

The canonical `trace-bench` repository was reconciled on `main` at commit `c0ea9fbf37bc50c88336f198437be031c18d6f64`, tracking `uv.lock`, `SCALE_EVIDENCE_PLAN.md`, and refreshed `SOURCE_MANIFEST.json`. The missing offline wheel dependency (`torch==2.13.0`) was acquired into the verifier offline cache root `C:\Users\anshu\AppData\Local\trace-verifier-cache\` and mirrored to `C:\Users\anshu\AppData\Local\trace-verifier-scratch\v1a-benchmark-20260819\uv-cache`. The locked environment was built strictly offline without network access, and the full frozen negative fail-closed runner matrix passed cleanly with 26/26 tests passing.

## 2. Source and Environment Verification

| Check | Expected | Actual | Status |
| --- | --- | --- | --- |
| Canonical repository branch | `main` | `main` | pass |
| Commit hash | `c0ea9fbf37bc50c88336f198437be031c18d6f64` | `c0ea9fbf37bc50c88336f198437be031c18d6f64` | pass |
| Parent commit | `0b01de5e49dcb18d43876b0b6004da58b35b72aa` | `0b01de5e49dcb18d43876b0b6004da58b35b72aa` | pass |
| Verifier worktree path | `C:\Users\anshu\AppData\Local\trace-verifier-worktrees\v1a-benchmark-20260819` | clean worktree | pass |
| `core.autocrlf` | `false` | `false` | pass |
| `SOURCE_MANIFEST.json` entries | 45 non-manifest tracked files | 45 entries | pass |
| Manifest LF hash | `24e3c942227ab5203dfc324f83ed3eee4c5e4d2af784e23223b2f9f1f131b5cc` | exact match | pass |
| Manifest composite SHA-256 | `554555030a8ee6037b41aba3e163b616d1f43ef6b057cb98c7f9242271dad83f` | exact match | pass |
| `uv.lock` SHA-256 | `fd4bbc4107d965f570493afb2a425b0482363b126532d023744e0a7d46745c50` | exact match | pass |
| Offline wheel cache | `torch==2.13.0` present in cache | `torch-2.13.0-cp312-cp312-win_amd64.whl` present | pass |
| Verifier environment build | `uv sync --locked --extra dev --no-editable --offline` | 51 packages installed into external venv | pass |
| Import origin | Non-editable wheel install | `...\\venv\\Lib\\site-packages\\trace_bench\\__init__.py` | pass |

## 3. Frozen Negative Matrix Execution Results

All 13 negative matrix paths and 13 harness baseline tests executed with 0 failures and 0 skips:

| Test Name | Tested Fail-Closed Property | Expected Receipt / Error Code | Actual Result |
| --- | --- | --- | --- |
| `test_negative_path_01_missing_source_identity` | Unpinned/editable/missing source identity in certification mode | `PreflightError` (`ERR_EDITABLE_IMPORT_FORBIDDEN` / `ERR_MISSING_SOURCE_IDENTITY`) | PASSED |
| `test_negative_path_02_mock_provider_in_certification` | Mock provider in certification mode rejected | `PreflightError` (`ERR_MOCK_PROVIDER_FORBIDDEN`) | PASSED |
| `test_negative_path_03_unavailable_provider` | Unavailable provider endpoint fail-closed | `AcquisitionError` (`ERR_UNAVAILABLE_PROVIDER`) | PASSED |
| `test_negative_path_04_unadmitted_or_checksum_mismatch` | Unadmitted dataset / corrupted corpus checksum | `DatasetIntegrityError` / `PreflightError` (`ERR_DATASET_NOT_ADMITTED`, `ERR_CHECKSUM_MISMATCH`) | PASSED |
| `test_negative_path_05_synthetic_substitution` | Synthetic scale data substitution rejected | `PreflightError` (`ERR_SYNTHETIC_SUBSTITUTION_FORBIDDEN`) | PASSED |
| `test_negative_path_06_insecure_tls` | Non-TLS / insecure URL download rejected | `AcquisitionError` (`ERR_INSECURE_TLS_FORBIDDEN`) | PASSED |
| `test_negative_path_07_stage_exceptions_and_error_receipts` | Indexing/query stage exceptions emit structured error receipt with `certification_eligible: false` | `IndexStageError` (`ERR_INDEX_FAILED`), `QueryStageError` (`ERR_QUERY_FAILED`), `certification_eligible: false` | PASSED |
| `test_negative_path_08_empty_positive_retrieval` | Empty positive retrieval isolated from abstention (0.0 recall/precision/MRR) | Exact metric isolation, non-abstention outcome | PASSED |
| `test_negative_path_09_expected_abstention_metric_isolation` | Expected abstention isolated (retrieval metrics remain 0.0, abstention_accuracy = 1.0) | Dedicated abstention result, no retrieval score inflation | PASSED |
| `test_negative_path_10_missing_evidence_mapping` | Missing source evidence mapping in run manifest rejected | `PreflightError` (`ERR_MISSING_EVIDENCE_MAPPING`) | PASSED |
| `test_negative_path_11_unstable_query_pairing` | Unmatched/unpaired queries in paired statistics rejected | `UnstableQueryPairingError` (`ERR_UNSTABLE_QUERY_PAIRING`) | PASSED |
| `test_negative_path_12_fabricated_coverage` | Organization metrics cannot default to hardcoded 1.0 | `ERR_FABRICATED_COVERAGE` on empty/fabricated atom map | PASSED |
| `test_negative_path_13_forced_flat_fallback_rejection` | Tree indexing failure must not silently fall back to flat search | `IndexStageError` (`ERR_FORCED_FALLBACK_FORBIDDEN`) | PASSED |
| `test_compute_sha256` | CRLF/LF normalization determinism | Consistent SHA-256 | PASSED |
| `test_dev_manifest_loader` | Dev manifest loader and schema | Non-certifying dev manifest verified | PASSED |
| `test_curated_in_domain_manifest` | Curated in-domain manifest and corpus checksum | 320 cases verified | PASSED |
| `test_manifest_integrity_mismatch` | Tampered manifest detection | `DatasetIntegrityError` raised | PASSED |
| `test_bm25_retriever_execution` | BM25 lexical baseline retriever | Lexical search verified | PASSED |
| `test_hipporag_ppr_retriever` | HippoRAG PPR graph baseline retriever | Multi-hop graph search verified | PASSED |
| `test_hipporag_and_trec_adapters_with_cached_data` | HippoRAG & TREC RAG benchmark adapters | Cached dataset loading verified | PASSED |
| `test_dense_and_hybrid_rrf_retrievers` | Dense nearest neighbor & Hybrid RRF retrievers | Dense & RRF rankings verified | PASSED |
| `test_flat_hierarchy_retriever` | Flat hierarchy clustered retriever | Hierarchy retrieval verified | PASSED |
| `test_metric_calculations` | Core retrieval metrics calculation | Recall, coverage, precision, MRR, abstention | PASSED |
| `test_paired_statistics` | Paired bootstrap / t-test statistical significance | Delta & p-value significance verified | PASSED |
| `test_release_gates_enforcement` | Release gates enforcement | Threshold checking in certification mode | PASSED |
| `test_scale_generator_determinism` | Scale benchmark synthetic corpus generation | Deterministic generation verified | PASSED |

## 4. Invariant and Fail-Closed Verification

- Every negative case blocks or fails closed, emitting the expected error code and structured receipt.
- Every failed run records `certification_eligible: false`, leaving no partial aggregate or misleading score.
- Non-editable package installation was strictly enforced (`trace_bench` imported from `site-packages`).
- Offline verification ran with zero network access and no shared implementation mutable state.

## 5. Claim Boundary

Authority level C1: This verification proves only the fail-closed negative runner matrix and source/dependency identity of `trace-bench` at commit `c0ea9fbf37bc50c88336f198437be031c18d6f64`. It does not certify benchmark retrieval scores, real-world data plane performance, lifecycle safety, or downstream system integration.
