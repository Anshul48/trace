# V1a Verifier Commands and Results

All verifier commands below were run against the clean verifier worktree `C:\Users\anshu\AppData\Local\trace-verifier-worktrees\v1a-benchmark-20260819` and external scratch root `C:\Users\anshu\AppData\Local\trace-verifier-scratch\v1a-benchmark-20260819`. No network access was used during the verification run, and no implementation files were mutated by the verifier.

## 1. Environment and Identity Resolution Commands

| Step | Exact Command | Result / Evidence |
| --- | --- | --- |
| Reconcile canonical repository | `git status`, `git add SCALE_EVIDENCE_PLAN.md uv.lock SOURCE_MANIFEST.json; git commit` in `trace-bench` | Created `c0ea9fbf37bc50c88336f198437be031c18d6f64` on `main` |
| Populate offline wheel cache | `uv sync --locked --extra dev --no-editable --cache-dir "C:\Users\anshu\AppData\Local\trace-verifier-cache" --python "C:\Program Files\Python312\python.exe"` | Downloaded all missing wheels including `torch==2.13.0` (116.4 MiB) into offline cache root |
| Mirror offline cache to scratch | `robocopy "C:\Users\anshu\AppData\Local\trace-verifier-cache" "C:\Users\anshu\AppData\Local\trace-verifier-scratch\v1a-benchmark-20260819\uv-cache" /E` | Cache mirrored with 51 locked dependency packages |
| Fetch clean verifier worktree | `git fetch "C:\Users\anshu\OneDrive\Documents\Code\Utilities\trace-bench" main:main; git checkout main; git config core.autocrlf false; git checkout-index -a -f` in verifier worktree | Clean worktree at commit `c0ea9fbf37bc50c88336f198437be031c18d6f64`, `core.autocrlf=false` |
| Validate source manifest | Python JSON parse & deterministic sorted `path|sha256|size_bytes` SHA-256 validation | 45 entries; composite `554555030a8ee6037b41aba3e163b616d1f43ef6b057cb98c7f9242271dad83f` matched exact declared composite |
| Build locked offline venv | `$env:UV_CACHE_DIR='...\\uv-cache'; $env:UV_PROJECT_ENVIRONMENT='...\\venv'; uv sync --locked --extra dev --no-editable --python 'C:\Program Files\Python312\python.exe' --offline` | Success; 51 packages installed into external verifier venv non-editably in 20.83s |
| Check non-editable import | `uv run --locked --no-sync python -c "import importlib.metadata as m, sys, trace_bench; print(trace_bench.__file__); print(m.version('trace-bench'))"` | Resolved from `...\\venv\\Lib\\site-packages\\trace_bench\\__init__.py`; version `0.1.0` |

## 2. Test Suite Execution Command

```powershell
$env:UV_CACHE_DIR = "C:\Users\anshu\AppData\Local\trace-verifier-scratch\v1a-benchmark-20260819\uv-cache"
$env:UV_PROJECT_ENVIRONMENT = "C:\Users\anshu\AppData\Local\trace-verifier-scratch\v1a-benchmark-20260819\venv"
uv run --locked --no-sync python -m pytest -v -o pythonpath= --basetemp "C:\Users\anshu\AppData\Local\trace-verifier-scratch\v1a-benchmark-20260819\pytest-basetemp"
```

## 3. Raw Execution Output

```text
============================= test session starts =============================
platform win32 -- Python 3.12.0, pytest-9.1.1, pluggy-1.6.0 -- C:\Users\anshu\AppData\Local\trace-verifier-scratch\v1a-benchmark-20260819\venv\Scripts\python.exe
cachedir: .pytest_cache
rootdir: C:\Users\anshu\AppData\Local\trace-verifier-worktrees\v1a-benchmark-20260819
configfile: pyproject.toml
testpaths: tests
plugins: anyio-4.14.2, asyncio-1.4.0
asyncio: mode=Mode.STRICT, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collecting ... collected 26 items

tests/test_benchmark_harness.py::test_compute_sha256 PASSED              [  3%]
tests/test_benchmark_harness.py::test_dev_manifest_loader PASSED         [  7%]
tests/test_benchmark_harness.py::test_curated_in_domain_manifest PASSED  [ 11%]
tests/test_benchmark_harness.py::test_manifest_integrity_mismatch PASSED [ 15%]
tests/test_benchmark_harness.py::test_bm25_retriever_execution PASSED    [ 19%]
tests/test_benchmark_harness.py::test_hipporag_ppr_retriever PASSED      [ 23%]
tests/test_benchmark_harness.py::test_hipporag_and_trec_adapters_with_cached_data PASSED [ 26%]
tests/test_benchmark_harness.py::test_dense_and_hybrid_rrf_retrievers PASSED [ 30%]
tests/test_benchmark_harness.py::test_flat_hierarchy_retriever PASSED    [ 34%]
tests/test_benchmark_harness.py::test_metric_calculations PASSED         [ 38%]
tests/test_benchmark_harness.py::test_paired_statistics PASSED           [ 42%]
tests/test_benchmark_harness.py::test_release_gates_enforcement PASSED   [ 46%]
tests/test_benchmark_harness.py::test_scale_generator_determinism PASSED [ 50%]
tests/test_fail_closed_negative_matrix.py::test_negative_path_01_missing_source_identity PASSED [ 53%]
tests/test_fail_closed_negative_matrix.py::test_negative_path_02_mock_provider_in_certification PASSED [ 57%]
tests/test_fail_closed_negative_matrix.py::test_negative_path_03_unavailable_provider PASSED [ 61%]
tests/test_fail_closed_negative_matrix.py::test_negative_path_04_unadmitted_or_checksum_mismatch PASSED [ 65%]
tests/test_fail_closed_negative_matrix.py::test_negative_path_05_synthetic_substitution PASSED [ 69%]
tests/test_fail_closed_negative_matrix.py::test_negative_path_06_insecure_tls PASSED [ 73%]
tests/test_fail_closed_negative_matrix.py::test_negative_path_07_stage_exceptions_and_error_receipts PASSED [ 76%]
tests/test_fail_closed_negative_matrix.py::test_negative_path_08_empty_positive_retrieval PASSED [ 80%]
tests/test_fail_closed_negative_matrix.py::test_negative_path_09_expected_abstention_metric_isolation PASSED [ 84%]
tests/test_fail_closed_negative_matrix.py::test_negative_path_10_missing_evidence_mapping PASSED [ 88%]
tests/test_fail_closed_negative_matrix.py::test_negative_path_11_unstable_query_pairing PASSED [ 92%]
tests/test_fail_closed_negative_matrix.py::test_negative_path_12_fabricated_coverage PASSED [ 96%]
tests/test_fail_closed_negative_matrix.py::test_negative_path_13_forced_flat_fallback_rejection PASSED [100%]

======================= 26 passed in 202.39s (0:03:22) ========================
```
