# F0c trace-bench Component Record

> **Status:** Current observed record as of 2026-08-19.
> **Captured by:** Coordinator (read-only boundary capture).

## 1. Repository & Source Identity

- **Canonical root:** `C:\Users\anshu\OneDrive\Documents\Code\Utilities\trace-bench`
- **Git Identity:** None (`.git` is absent).
- **Source Inventory:** 41 files (excluding `.pytest_cache/`, `__pycache__/`, `src/trace_bench.egg-info/`, `results/`).
- **Content Manifest SHA256:** `739d7f42fb40c9234b716f5a30aa9e0acd224c4e486e24f95e4afa8f1ca36f1e`
- **Certification Status:** Non-certifying until P-007 defines source governance and P-008 defines the canonical runner/integration boundary.

## 2. Directory Structure & Inventory Summary

- `pyproject.toml` (package definition)
- `README.md` (benchmark documentation)
- `src/trace_bench/adapters/` (ANN scale, BEIR, BRIGHT, HiChunk, HippoRAG, LongMemEval, MTEB, MultiHop, TREC RAG adapters)
- `src/trace_bench/baselines/` (BM25, Dense, Flat Hierarchy, HippoRAG, Hybrid RRF, Trace Retriever baselines)
- `src/trace_bench/datasets/` (in-domain dataset builders, loaders, schemas, curated fixtures)
- `src/trace_bench/generators/` (in-domain benchmark generators, corpus scaling)
- `src/trace_bench/metrics/` (aggregator, operations, organization, retrieval metrics)
- `src/trace_bench/reporter.py` & `runner.py` (reporting and harness execution)
- `tests/` (harness test suite and JSON fixtures)

## 3. Exclusions from Source Identity

- `.pytest_cache/`
- `__pycache__/` (all directories)
- `src/trace_bench.egg-info/`
- Local results/logs (when generated)
- Downloaded raw datasets / model weights (when staged)

## 4. Integration Boundaries

| Interface | Producer | Consumer | Status / Risk |
| --- | --- | --- | --- |
| TraceRetriever adapter (`src/trace_bench/baselines/trace_retriever.py`) | Trace / Trace-Lite | trace-bench | Unpinned import; requires package/version pin or dedicated adapter contract. |
| Benchmark Runner (`src/trace_bench/runner.py`) | trace-bench | Benchmark sessions | Contains mock defaults and fallback paths by static inspection. B1 must enforce fail-closed execution. |

## 5. Required Decision Inputs

- **P-007 (trace-bench source governance):** Choose between (1) independent Git repository with tags/pins, or (2) external source tree with canonical content manifest and archive policy.
- **P-008 (canonical runner boundary):** Formally designate `trace-bench` as the sole certification harness, demoting legacy in-repo TL benchmark code to internal regression/exploratory use.
