# F0a Evidence — Stale References and Assumptions Matrix

## 1. Stale Reference Inventory

| Prior Packet / Doc Reference | Prior Stated Assumption | Observed Current Fact (2026-08-19 Audit) | Required Correction / Action |
|---|---|---|---|
| Older program notes / chat references | Benchmark harness is located inside `Trace-Lite` under `benchmarks/` and `src/trace_lite/engines/benchmark.py`. | Benchmark codebase was moved out of `Trace-Lite` into `Utilities/trace-bench`. Legacy benchmark files still exist in `trace-lite/benchmarks/` and `trace_lite/engines/benchmark.py`. | Re-anchor all evaluation tasks to `Utilities/trace-bench`. Await P-008 to formally deprecate legacy in-repo surfaces. |
| `trace-bench/README.md:L133-141` | `--assert-gate` establishes publication-ready / production release readiness. | Current harness uses `MockLLMAdapter` by default, swallows errors, generates synthetic data on missing downloads, and inflates abstentions to 100%. | `--assert-gate` is currently non-certifying. Must implement fail-closed architecture in B1. |
| `trace_engineering_curated.json` | Manifest specifies `release_authority: true`. | Fixture is a 320-case self-descriptive internal regression dataset covering Trace-Lite concepts. | Mark `release_authority: false`; classify strictly as C2 regression evidence. |
| Initial B1 packet assumptions | B1 can be dispatched immediately to make the runner fail-closed. | `trace-bench` is an unversioned directory without Git identity, and P-007 (source control) / P-008 (integration boundary) remain undecided. | B1 cannot be dispatched until P-007 and P-008 are formally resolved. |
| Adapters (`HiChunk`, `LongMemEval`, `HippoRAG`, `TREC RAG`, `MTEB`) | Adapters prepare benchmark datasets for evaluation. | Adapters fall back to hardcoded 2-4 question synthetic sample data without real data acquisition. | Require real data staging under P-001 and D2 before running public benchmark modes. |
| `TraceLiteRetriever` | Evaluates Trace-Lite LATTICE hierarchical tree traversal. | Uses unpinned `MockLLMAdapter`, swallows `_db.organize()` exceptions, falls back to flat search, and catches `_db.query()` crashes. | Refactor `TraceLiteRetriever` in B1 to fail closed on errors and require real provider configuration. |
