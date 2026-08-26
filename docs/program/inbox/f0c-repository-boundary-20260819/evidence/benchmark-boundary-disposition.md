# Benchmark Boundary Disposition & Resolution Plan

> **Status:** Current analysis of benchmark boundaries and required decisions.
> **Date:** 2026-08-19.

## 1. Observed State

The benchmark suite exists in two locations:
1. **External `trace-bench` directory:** `C:\Users\anshu\OneDrive\Documents\Code\Utilities\trace-bench`.
   - 41 source/fixture/config files.
   - Contains runner, multi-adapter integrations (ANN Scale, BEIR, BRIGHT, HiChunk, HippoRAG, LongMemEval, MTEB, MultiHop, TREC RAG), baselines (BM25, Dense, Flat Hierarchy, HippoRAG, Hybrid RRF, Trace Retriever), metrics, generators, and test harness.
   - Has no Git repository (`.git` absent).
   - Content manifest SHA256: `739d7f42fb40c9234b716f5a30aa9e0acd224c4e486e24f95e4afa8f1ca36f1e`.
   - Excludes `.pytest_cache/`, `__pycache__/`, `src/trace_bench.egg-info/`, `results/`.
2. **Internal `trace-lite/benchmarks/` and `src/trace_lite/engines/benchmark.py`:**
   - In-repo legacy benchmark engine with mock/default/fail-open behavior.
   - Protocol and registry documentation templates in untracked files.

## 2. Open Human Decisions Required Before B1

### Decision P-007: trace-bench Canonical Source Identity
- **Problem:** A certifying run requires an immutable source identity so that an independent verifier receives the exact same evaluator code.
- **Option A:** Initialize `trace-bench` as an independent Git repository with semantic tags and formal dependency pins (`trace-lite`, `trace`).
- **Option B:** Maintain `trace-bench` as an external tree governed by a canonical content manifest, versioned archive, inclusion/exclusion rules, and immutable release digest.
- **Safe Default:** `trace-bench` is unversioned and non-certifying.

### Decision P-008: Canonical Certification Runner Boundary
- **Problem:** Two coexisting runner surfaces create ambiguity in certification scoring, fallback rules, and adapter imports.
- **Option A:** Designate `trace-bench` as the sole canonical certification harness; demote `trace_lite/engines/benchmark.py` to internal regression/unit testing with explicit non-certifying annotations.
- **Option B:** Re-embed `trace-bench` into `trace-lite/benchmarks/`.
- **Safe Default:** Neither runner is certification-authoritative until P-008 is accepted and B1 implements fail-closed preflight and error receipts.

## 3. Immediate Path Forward

1. Dispatch **F0a (Evaluation Engineer)** to perform a read-only audit of `trace-bench` fallback paths and Trace-Lite benchmark code.
2. Present **P-007** and **P-008** decision requests to the human program owner.
3. Upon acceptance of P-007 and P-008, prepare **B1 (Fail-Closed Runner)** with concrete worktree lease, allowed paths, and **V1a** independent verifier assignment.
