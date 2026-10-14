# F0a Evidence — Fixture Classification and Claim Boundary

## 1. Fixture Inventory & Analysis

| Fixture Path | Claimed Role in Manifest | Actual Content & Structure | True Claim Level & Classification | Boundary & Gate Implications |
|---|---|---|---|---|
| `src/trace_bench/datasets/trace_engineering_curated.json` (also in `tests/fixtures/`) | `release_authority: true`<br/>"Comprehensive 320-query curated engineering benchmark..." | 320 queries across 8 categories (40 each: direct lookup, chronology, contradiction, cross-domain, global context, multi-hop, historical, out-of-scope). Corpus contains 100 paragraphs describing Trace-Lite internals (Spine, RAPTOR, LATTICE, LanceDB, etc.). | **C2 — Internal Regression Evidence Only** | Must NOT be marked `release_authority: true`. Passing this fixture proves internal code stability against known Trace-Lite concepts, but does not prove domain generalization, external SOTA, or public retrieval capability. |
| `src/trace_bench/datasets/technical_docs_dev.json` (also in `tests/fixtures/`) | `release_authority: false`<br/>"Development smoke fixture" | 6 queries over a 6-paragraph technical corpus. | **C1 — Local Developer Smoke / Unit** | Developer smoke testing only. Non-certifying. |
| `src/trace_bench/generators/scale_corpus.py` (synthetic scale ladder) | Algorithmic generator (`1k`, `10k`, `100k`, `1m`) | Algorithmically generated paragraphs with embedded synthetic facts. | **C1 / Fault / Scale Stress Testing Only** | Useful for memory profiling and stress-testing index algorithms, but cannot substitute for real 100K corpus gate. |

---

## 2. In-Depth Audit of the 320-Case Curated Fixture

### Self-Descriptive Nature
Static analysis of the corpus text in `trace_engineering_curated.json` reveals that the corpus consists entirely of descriptive engineering documentation about the Trace-Lite product itself:
- Paragraph 41: *"Spine Immutability: The source Spine captures raw source documents with immutable SHA-256 content hashes and strict atomization."*
- Paragraph 44: *"RAPTOR Tree Builder: RAPTOR clusters related leaf atoms using vector embeddings and generates hierarchical multi-level summaries."*
- Paragraph 45: *"LATTICE Traversal: LATTICE search navigates top-down from root summary trees before combining results with flat dense retrieval."*
- Paragraph 52: *"Vector Storage Backend: LanceDB provides fast vector indexing with IVF-PQ quantization and zero-copy Arrow memory mapping."*

### Why `release_authority: true` is a Critical Integrity Issue
1. **Self-Referential Bias**: The queries test whether Trace-Lite can retrieve paragraphs describing Trace-Lite. This produces high baseline recall (e.g. `Recall@5 > 0.85`) but tells us nothing about how the system handles complex external corpora (e.g., scientific papers, financial data, multi-hop reasoning).
2. **Hardcoded Release Gate**: In `src/trace_bench/metrics/aggregator.py:L216-218`, `check_release_gates` explicitly verifies `if not release_authority: failures.append(...)`. Because `trace_engineering_curated.json` sets `release_authority: true`, running `trace-bench run --dataset .../trace_engineering_curated.json --assert-gate` reports:
   `[PASS] trace_hybrid: PASSED ALL RELEASE GATES`
   giving a false illusion of production certification.

### Corrected Policy for B1 & Beyond
- Set `"release_authority": false` on `trace_engineering_curated.json`.
- Downgrade the role of `trace_engineering_curated.json` to **frozen internal regression fixture** (`mode: regression`).
- Certification mode (`mode: certification`) must require an externally sourced, license-verified dataset admitted under P-001 with an immutable `EVALUATION_MANIFEST`.
