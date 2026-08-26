# F0a Evidence — Current Surface Map

## 1. Executive Summary

This document maps all execution surfaces, runner entry points, adapters, loaders, baselines, and metrics across the moved `trace-bench` codebase (`C:\Users\anshu\OneDrive\Documents\Code\Utilities\trace-bench`) and legacy in-repo surfaces in `trace-lite`.

## 2. Component Boundary & Source Anchors

| Concern | File Path & Anchor | Current Behavior / Role | Mode Classification |
|---|---|---|---|
| **Harness Runner Entrypoint** | `trace-bench/src/trace_bench/runner.py:L240-328` (`cli`, `run_command`) | Parses CLI options; defaults `--mock-llm/--real-llm` to `True`. Executes baselines via `execute_benchmark`. | Non-certifying / Exploratory (mock LLM default) |
| **Scale Generator Runner** | `trace-bench/src/trace_bench/runner.py:L329-362` (`scale_command`) | Generates synthetic scale ladder benchmarks (1k to 1m atoms). | Synthetic Scale / Fault only |
| **Comparison Runner** | `trace-bench/src/trace_bench/runner.py:L363-385` (`compare_command`) | Compares two run JSONs with paired Student-t significance tests. | Exploratory / Analysis |
| **Dataset Setup Runner** | `trace-bench/src/trace_bench/runner.py:L387-448` (`setup_command`) | Invokes adapter `download_or_prepare` and `export_manifest`. | Ingestion / Staging |
| **HTML Report Generator** | `trace-bench/src/trace_bench/reporter.py:L1-536` (`generate_html_report`) | Emits standalone interactive HTML with SVG radar/Pareto charts. | Reporting |
| **Trace-Lite Baseline Adapter** | `trace-bench/src/trace_bench/baselines/trace_retriever.py:L10-122` (`TraceLiteRetriever`) | Dynamically imports `TraceLite` and `MockLLMAdapter`; swallows organize & query exceptions. | Non-certifying / Exploratory |
| **BM25 Lexical Baseline** | `trace-bench/src/trace_bench/baselines/bm25_retriever.py:L9-87` (`BM25Retriever`) | Uses `rank_bm25.BM25Okapi` with tokenized corpus. | Standard Baseline |
| **Dense Bi-Encoder Baseline** | `trace-bench/src/trace_bench/baselines/dense_retriever.py:L10-67` (`DenseRetriever`) | Uses `sentence_transformers.SentenceTransformer` (`all-MiniLM-L6-v2` or `bge-large-en-v1.5`). | Standard Baseline |
| **Hybrid RRF Baseline** | `trace-bench/src/trace_bench/baselines/hybrid_rrf_retriever.py:L10-63` (`HybridRRFRetriever`) | Reciprocal Rank Fusion ($k=60$) combining BM25 and Dense scores. | Standard Baseline |
| **Flat Hierarchy Baseline** | `trace-bench/src/trace_bench/baselines/flat_hierarchy_retriever.py:L10-98` (`FlatHierarchyRetriever`) | K-means cluster centroids over dense embeddings without LLM summaries. | Structural Baseline |
| **HippoRAG PPR Baseline** | `trace-bench/src/trace_bench/baselines/hipporag_retriever.py:L10-145` (`HippoRagPPRRetriever`) | Builds phrase co-occurrence graph in NetworkX; runs Personalized PageRank. | Associative Graph Baseline |
| **Retrieval Metrics Engine** | `trace-bench/src/trace_bench/metrics/retrieval.py:L1-133` | Computes Recall@K, nDCG@K, Complete Gold Coverage, Precision, MRR, Abstention. | Metric Calculation (Flawed Abstention Semantics) |
| **Aggregator & Gate Checker** | `trace-bench/src/trace_bench/metrics/aggregator.py:L95-235` | Aggregates case results, category breakdowns, and release gate checks. | Aggregation (Hardcoded Gate Logic) |
| **Dataset Schema & Validation** | `trace-bench/src/trace_bench/datasets/schema.py`, `loader.py` | Pydantic models and SHA-256 corpus hash verification. | Integrity / Ingestion |
| **Curated In-Domain Fixture** | `trace-bench/src/trace_bench/datasets/trace_engineering_curated.json` | 320-query hand-curated engineering corpus covering Trace-Lite concepts. | C2 Internal Regression Only |
| **Development Fixture** | `trace-bench/src/trace_bench/datasets/technical_docs_dev.json` | 6-query smoke fixture. | Unit / Smoke |

---

## 3. Dataset Adapter Surface Map

| Adapter | Source File | External Dataset Source | Download / Prepare Behavior | Failure Mode / Fallback |
|---|---|---|---|---|
| **BEIR Adapter** | `src/trace_bench/adapters/beir_adapter.py:L11-111` | TU Darmstadt public zip archives | Downloads zip archive via `download_file` and extracts `corpus.jsonl`, `queries.jsonl`, `qrels/test.tsv`. | Uses insecure TLS fallback (`verify=False`) in base `download_file`. |
| **BRIGHT Adapter** | `src/trace_bench/adapters/bright_adapter.py:L8-98` | HuggingFace `xlangai/BRIGHT` | Reads local pre-cached `documents.json` / `queries.json` or JSONL files. | Raises `FileNotFoundError` if cache missing; no auto-fetch logic. |
| **MultiHop-RAG Adapter** | `src/trace_bench/adapters/multihop_adapter.py:L8-94` | MultiHop-RAG benchmark dataset | Reads `corpus.jsonl` and `queries.jsonl` from cache. | Raises `FileNotFoundError` if cache missing. |
| **HiChunk Adapter** | `src/trace_bench/adapters/hichunk_adapter.py:L8-119` | HiCBench hierarchical chunking | Checks cache; writes 4-chunk / 2-query synthetic sample if missing. | **Silent Synthetic Data Fallback**. |
| **LongMemEval Adapter** | `src/trace_bench/adapters/longmemeval_adapter.py:L8-107` | LongMemEval temporal memory suite | Checks cache; writes 2-session / 2-query synthetic sample if missing. | **Silent Synthetic Data Fallback**. |
| **HippoRAG Adapter** | `src/trace_bench/adapters/hipporag_adapter.py:L9-124` | GitHub `OSU-NLP-Group/HippoRAG` sample.json | Fetches sample JSON from GitHub raw URL; on exception writes 2-query synthetic sample. | **Silent Synthetic Data Fallback**. |
| **TREC RAG Adapter** | `src/trace_bench/adapters/trec_rag_adapter.py:L8-80` | NIST TREC 2026 ClimbMix | Checks cache; writes 3-doc / 2-query synthetic sample if missing. | **Silent Synthetic Data Fallback**. |
| **MTEB Adapter** | `src/trace_bench/adapters/mteb_adapter.py:L8-80` | MTEB retrieval subsets | Checks cache; writes 2-doc / 2-query synthetic sample if missing. | **Silent Synthetic Data Fallback**. |
| **ANN Scale Adapter** | `src/trace_bench/adapters/ann_scale_adapter.py:L9-54` | BigANN / ANN-Benchmarks | Generates synthetic vector documents (1K, 10K, 100K) algorithmically. | **100% Synthetic Generator**. |

---

## 4. Integration Boundaries & Unpinned Dependencies

1. **`trace_lite` Import in `TraceLiteRetriever`**:
   - `trace-bench/src/trace_bench/baselines/trace_retriever.py:L35-36`:
     ```python
     from trace_lite import TraceLite
     from trace_lite.adapters import MockLLMAdapter
     ```
   - **Risk**: Unpinned runtime import. The benchmark harness does not verify the Git commit, package hash, or clean working state of `trace_lite`.
2. **Missing `trace` V2 Adapter**:
   - There is currently no `TraceRetriever` adapter in `trace-bench/src/trace_bench/baselines/` for Trace V2 (`src/trace/v2/`).
   - The harness cannot currently evaluate Trace V2 Cortex release retrieval.
3. **Legacy Duplicate Surfaces in `trace-lite`**:
   - `trace-lite/benchmarks/` contains an older copy of adapters, baselines, runner, and datasets.
   - `trace-lite/src/trace_lite/engines/benchmark.py` contains an embedded monolithic benchmark engine (695 lines) with similar fail-open behaviors.
   - P-008 must choose the external `trace-bench` as the single canonical certification runner and deprecate internal copies.
