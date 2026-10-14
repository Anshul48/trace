# F0a Evidence — Forbidden Fallback and Integrity Flaw Inventory

## 1. Mandatory Findings Summary Table

The table below catalogs all observed mock, synthetic, forced fallback, error swallowing, empty-result reinterpretation, and insecure TLS paths identified during the static code audit of `trace-bench`.

| # | File & Symbol Anchor | Trigger & Observed Behavior | Allowed in Unit / Regr / Expl / Cert? | Required B1 Behavior & Reason Code | Negative Test Required | Contamination Scope |
|---|---|---|:---:|---|---|---|
| **1** | `src/trace_bench/runner.py:L38-62, L255`<br/>`src/trace_bench/baselines/trace_retriever.py:L21, L44-52` (`TraceLiteRetriever.__init__`, `_init_db`) | Default `mock_llm=True` in CLI options and `AVAILABLE_BASELINES`. Injects `MockLLMAdapter` into `TraceLite` database, `raptor.llm`, `lattice.llm`, `router.llm`. | Unit: **Yes**<br/>Regr: **Yes**<br/>Expl: **Yes** (labeled)<br/>Cert: **FORBIDDEN** | Fail closed on certification mode. Require explicit provider/model config. If mock provider used: emit `ERROR_RECEIPT` (`MOCK_PROVIDER_FORBIDDEN`) and exit code 1. | `test_fail_closed_on_mock_provider_in_certification_mode` | **Metric & Hierarchy** (produces fake tree navigation & invalid SOTA scores). |
| **2** | `src/trace_bench/baselines/trace_retriever.py:L76-87` (`TraceLiteRetriever.index`) | In `tree`/`hybrid` mode, if `_db.organize()` raises an exception, catches and tries `_db.reindex_all()`; if that fails, catches and executes `pass`. | Unit: **No**<br/>Regr: **No**<br/>Expl: **Yes** (with warning)<br/>Cert: **FORBIDDEN** | Propagate exception or emit `ERROR_RECEIPT` (`STAGE_ERROR` / `FALLBACK_FORBIDDEN`). No silent fallback to flat search or swallowed failure. | `test_fail_closed_on_indexing_organization_exception` | **Metric & Index Integrity** (converts broken tree into flat search without notice). |
| **3** | `src/trace_bench/baselines/trace_retriever.py:L94-116` (`TraceLiteRetriever.retrieve`) | Unhandled exceptions inside `_db.query(...)` are caught by bare `except Exception: return []`. | Unit: **No**<br/>Regr: **No**<br/>Expl: **No**<br/>Cert: **FORBIDDEN** | Log explicit query exception and record failure in case result. Do not return empty candidate list on error. Reason: `STAGE_ERROR`. | `test_fail_closed_on_retrieval_query_exception` | **Metric & Abstention** (interacts with flaw #4 to score broken queries as 100% abstentions). |
| **4** | `src/trace_bench/runner.py:L96`<br/>`src/trace_bench/metrics/retrieval.py:L98-115` (`evaluate_case_retrieval`) | `is_abstaining = (len(candidates) == 0)`. When `expected_abstention=True` and `is_abstaining=True`, sets **all** retrieval metrics (`recall@5..100`, `ndcg@10..30`, `coverage@10..20`, `precision@5..10`, `mrr`) to `1.0`. | Unit: **No**<br/>Regr: **No**<br/>Expl: **No**<br/>Cert: **FORBIDDEN** | Abstention correctness must only be tracked in `abstention_accuracy`. Retrieval metrics on empty results must remain `0.0`. Empty positive queries must fail. Reason: `EMPTY_RESULT_NOT_ABSTENTION`. | `test_empty_retrieval_does_not_inflate_retrieval_metrics` | **Metric Distortion** (artificially boosts aggregate Recall/nDCG/Coverage on out-of-scope queries). |
| **5** | `src/trace_bench/adapters/base.py:L28-35` (`download_file`) | If initial `httpx.stream` fails, retries inside `except Exception:` block with `verify=False` (disabling SSL/TLS certificate verification). | Unit: **No**<br/>Regr: **No**<br/>Expl: **No**<br/>Cert: **FORBIDDEN** | Enforce strict TLS certificate verification (`verify=True`). On transport failure, raise `RuntimeError` and emit `ERROR_RECEIPT` (`INSECURE_TLS_FORBIDDEN`). | `test_fail_closed_on_insecure_tls_or_invalid_cert` | **Security & Transport Integrity**. |
| **6** | `src/trace_bench/adapters/hipporag_adapter.py:L34-68`<br/>`src/trace_bench/adapters/trec_rag_adapter.py:L27-45`<br/>`src/trace_bench/adapters/longmemeval_adapter.py:L26-63`<br/>`src/trace_bench/adapters/hichunk_adapter.py:L26-78`<br/>`src/trace_bench/adapters/mteb_adapter.py:L28-44`<br/>`src/trace_bench/adapters/ann_scale_adapter.py:L27-53` | If external dataset file is missing or network download fails, adapters write hardcoded synthetic sample JSON/JSONL fixtures (2-4 cases) to cache. | Unit: **Yes** (mock fixtures)<br/>Regr: **No**<br/>Expl: **No**<br/>Cert: **FORBIDDEN** | In certification mode, missing dataset must fail preflight check with `ERROR_RECEIPT` (`MISSING_DATASET` / `SYNTHETIC_SUBSTITUTION_FORBIDDEN`). No synthetic substitute. | `test_fail_closed_on_missing_dataset_no_synthetic_substitute` | **Metric & Benchmark Validity** (passes benchmarks against 2 trivial hardcoded questions). |

---

## 2. Detailed Technical Analysis of Each Path

### Flaw 1: Implicit Mock LLM Default
- **Root Cause**: `TraceLiteRetriever` uses `MockLLMAdapter` by default to allow local offline execution without API keys.
- **Problem**: When running `trace-bench run --assert-gate`, the user or CI pipeline evaluates a mock-powered tree against production quality thresholds.
- **Remedy in B1**: Introduce `--mode` flag with strict validation. In `certification` mode, the runner verifies that `mock_llm=False` and provider credentials/model fingerprints are explicitly pinned in the run manifest.

### Flaw 2 & 3: Silent Exception Swallowing in Indexing and Retrieval
- **Root Cause**: Defensive try/except blocks intended to prevent script crashes during exploratory runs.
- **Problem**: If `_db.organize()` fails (e.g. LLM timeout, clustering error), it falls back to flat vector search silently. If `_db.query()` crashes (e.g. SQLite lock, invalid embedding), it returns `[]`.
- **Remedy in B1**: In `certification` mode, all exceptions during ingestion or query execution must be recorded as stage failures, terminating the certification run with an `ERROR_RECEIPT`.

### Flaw 4: Empty Retrieval Inflating Retrieval Metrics
- **Root Cause**: `evaluate_case_retrieval` assigns `1.0` to `recall_at_5`, `ndcg_at_10`, `complete_gold_coverage_at_10`, etc., for out-of-scope cases when `is_abstaining` is True.
- **Problem**: A completely broken retriever that returns `0` results for all queries will receive a 100% score on all out-of-scope test cases across all metric dimensions.
- **Remedy in B1**: Abstention must only evaluate `abstention_accuracy` (1.0 for true negative, 0.0 for false positive). Standard retrieval metrics (`Recall`, `nDCG`, `Precision`) must evaluate only positive queries or report N/A / 0.0 on abstentions.

### Flaw 5: Insecure TLS Fallback
- **Root Cause**: `download_file` in `adapters/base.py` attempts a second download with `verify=False` if any exception occurs.
- **Problem**: Man-in-the-middle attacks or corrupted downloads can slip into the dataset cache without detection.
- **Remedy in B1**: Remove the `verify=False` retry block completely. All HTTP streams must enforce certificate verification and validate post-download SHA-256 digests.

### Flaw 6: Silent Synthetic Dataset Creation
- **Root Cause**: Adapters contain fallback sample generators designed to make unit tests pass without internet connectivity.
- **Problem**: If an operator runs `trace-bench run --dataset hichunk`, the adapter silently creates a 4-chunk synthetic file instead of loading the real HiCBench dataset, and evaluates against it.
- **Remedy in B1**: Keep synthetic fixtures strictly in `tests/fixtures/` for unit testing. Dataset adapters must require pre-staged real data verified against P-001 admission manifests.
