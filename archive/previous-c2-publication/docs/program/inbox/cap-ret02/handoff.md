# WP-CAP-RET02 Handoff Summary: Hybrid BM25 + Dense RRF Fusion & Truncation Removal

- **Node ID:** `CAP-RET02`
- **Work Packet:** `WP-CAP-RET02`
- **Role:** Retrieval Specialist (`RET-SPEC`)
- **Worktree Branch:** `cap-ret02-fusion`
- **Governing Plan:** `docs/program/COGNITIVE_ARCHITECTURE_CORRECTION_PLAN.md` (Section 3.2, Clauses `CAP-D016`, `CAP-D008`)
- **Execution DAG:** `docs/program/CAP_001_EXECUTION_DAG.md` (Node `CAP-RET02`)
- **Status:** Complete & Ready for Independent Verification (`VERIF-INDEP`)

---

## 1. Scope of Mutation & Exclusive Lease Audit

Mutations strictly adhered to exclusive file lease boundaries:
- `src/trace/v2/retrieval.py` (Modified):
  - Removed arbitrary candidate truncations (`[:max(1, min(int(limit), 1_000))]`) from candidate dense vector evaluation.
  - Implemented `compute_rrf_score` helper implementing bit-exact Reciprocal Rank Fusion with configurable parameter $k$ (default $k=60$).
  - Implemented `_extract_rrf_weights` and `_extract_rrf_k` supporting configurable $w_{\text{bm25}}$, $w_{\text{dense}}$, and $k$ from explicit arguments, `RetrievalBudget`, or `QueryRequest` (default: 1.0, 1.0, 60), preserving pre-configured values without clobbering.
  - Added semantic similarity threshold (`dense_threshold=0.30`) for dense-only candidates to prevent background cosine noise from corrupting abstention contracts.
  - Added `InMemoryBM25Index` providing inverted postings list evaluation without hardcoded code slices, with idempotent re-indexing (`_remove_doc`) and filtering by `workspace_id`, `visibility`, and `facets`.
  - Added `InMemoryDenseIndex` providing normalized embedding matrix dot product search.
  - Added `retrieve_hybrid` standalone function and `HybridRetrievalEngine.retrieve_hybrid` instance method.
  - Instrumented `HybridRetrievalEngine.retrieve` with RRF fusion, weight configuration, and diagnostics flags (`dense_unpopulated`, `dense_fallback_lexical`, `w_bm25`, `w_dense`, `rrf_k`).
- `tests/v2/test_hybrid_retrieval.py` (New test suite): 23 unit tests covering formula bit-exactness, weight configuration, dynamic $k$ configuration, weight preservation, BM25 upsert idempotency, dense noise abstention, truncation removal beyond 300 items, hybrid ordering / modality complementarity, degraded fallback telemetry, and $\le 15\text{ ms}$ P95 latency benchmarks.
- `docs/program/inbox/cap-ret02/handoff.md` (Deliverable receipt).

No files outside the exclusive lease were modified.

---

## 2. Technical Implementation Details

### A. Postings Truncation Elimination
- Legacy retrieval logic and historical scripts truncated candidate postings via hardcoded slices (`[:300]`, `[:1000]`).
- In `src/trace/v2/retrieval.py`:
  - `_dense_scores` no longer truncates missing candidates before embedding generation; all candidates within the retrieval scope are evaluated.
  - `InMemoryBM25Index` indexes and traverses the complete postings list for each query term, fully evaluating every document containing the query term without slice cutoffs.
  - Candidate pools are governed strictly by the requested retrieval budget (`lexical_limit`, `dense_limit`, `candidate_limit`) rather than arbitrary code slices.

### B. Reciprocal Rank Fusion (RRF with configurable $k$, default $k=60$)
- Formula:
  $$\text{Score}(d) = \left(\frac{w_{\text{bm25}}}{k + \text{rank}_{\text{bm25}}(d)}\right) + \left(\frac{w_{\text{dense}}}{k + \text{rank}_{\text{dense}}(d)}\right)$$
- Defaults: $w_{\text{bm25}} = 1.0, w_{\text{dense}} = 1.0, k = 60$.
- Ranks are 1-indexed (1, 2, ...). If a document is absent from a modality or has non-positive score, that modality's reciprocal rank term is $0.0$.
- Configurable via:
  - Function arguments `w_bm25`, `w_dense`, and `k` in `retrieve_hybrid(...)`.
  - Attributes on `QueryRequest` and `RetrievalBudget`.
  - Keys in `request.privacy_context` (`w_bm25`, `w_dense`, `rrf_k`).
- Deterministic tie-breaking: Candidates are ordered descending by `score`, breaking ties by `atom_version_id`.

### C. Dense Thresholding & Abstention Preservation
- Dense embeddings from `all-MiniLM-L6-v2` exhibit positive baseline cosine similarity (~0.20-0.30) across unrelated English sentences.
- To preserve the Zero Hallucination contract (`test_query_returns_auditable_bundle_and_abstains`), dense-only candidates (`atom_id not in lexical`) must meet a semantic threshold (`>= 0.30`, configurable via `dense_threshold`) to be admitted as evidence.
- When no candidates clear the lexical or dense threshold, the engine cleanly abstains with `sufficiency_state = "insufficient_evidence"`.

### D. Fallback & Telemetry
- When dense vectors are unpopulated, retrieval gracefully falls back to lexical BM25 ranking without throwing an exception.
- Outcome diagnostics explicitly record:
  - `"dense_unpopulated": True/False`
  - `"dense_fallback_lexical": True/False`
  - `"w_bm25": float`
  - `"w_dense": float`
  - `"rrf_k": int`

---

## 3. Verification & Benchmark Evidence

### A. Acceptance Command 1: Hybrid Retrieval Unit Test Suite
```powershell
pytest tests/v2/test_hybrid_retrieval.py -v
```
**Results:** `23 passed in 35.68s` (100% PASS)
1. `test_rrf_score_formula_bit_exactness`: PASSED
2. `test_candidate_rrf_scores_in_engine_match_bit_exact`: PASSED
3. `test_rrf_weights_configurable_via_function_args`: PASSED
4. `test_rrf_weights_configurable_via_query_request_and_budget`: PASSED
5. `test_rrf_weights_configurable_via_privacy_context`: PASSED
6. `test_full_postings_evaluation_beyond_300_cutoff`: PASSED
7. `test_dense_scores_evaluates_all_candidates_without_cutoff`: PASSED
8. `test_hybrid_dense_rescues_vocabulary_mismatch`: PASSED
9. `test_hybrid_bm25_rescues_rare_exact_identifier`: PASSED
10. `test_joint_reinforcement_elevates_candidate_above_single_modality`: PASSED
11. `test_lexical_fallback_when_dense_unpopulated`: PASSED
12. `test_populated_dense_telemetry_flags`: PASSED
13. `test_unified_top_20_atom_ranking_and_monotonicity`: PASSED
14. `test_p95_retrieval_latency_in_memory_index`: PASSED
15. `test_p95_retrieval_latency_sqlite_index`: PASSED
16. `test_empty_query_returns_insufficient_evidence`: PASSED
17. `test_empty_atoms_returns_insufficient_evidence`: PASSED
18. `test_stopwords_only_query_returns_insufficient_evidence`: PASSED
19. `test_custom_top_k_parameter`: PASSED
20. `test_retrieve_hybrid_preserves_query_request_weights`: PASSED
21. `test_rrf_k_parameter_configurable_and_scored`: PASSED
22. `test_in_memory_bm25_index_upsert_idempotent`: PASSED
23. `test_unrelated_dense_noise_below_threshold_abstains`: PASSED

### B. Acceptance Command 2: Embedding Regression Test Suite
```powershell
pytest tests/v2/test_retrieval_embedding.py -v
```
**Results:** `8 passed in 37.61s` (100% PASS)

### C. Foundation & Cognitive Test Suites (Zero Regressions)
```powershell
pytest tests/test_v2_foundation.py -v
pytest tests/test_v2_cognitive.py -v
pytest tests/test_scale_abstention_pipeline.py -v
```
**Results:**
- `test_v2_foundation.py`: `7 passed in 45.84s` (100% PASS)
- `test_v2_cognitive.py`: `8 passed in 86.96s` (100% PASS)
- `test_scale_abstention_pipeline.py`: `14 passed in 80.60s` (100% PASS)

### D. Latency Benchmark Evidence (Target: P95 $\le 15\text{ ms}$)
- **In-Memory Benchmark (2,000 documents, 50 queries):**
  - **Mean Latency:** 7.43 ms
  - **P50 Latency:** 6.45 ms
  - **P95 Latency:** **10.15 ms** (PASS, $\le 15.0\text{ ms}$)
- **SQLite Benchmark (500 documents, 50 queries):**
  - **Mean Latency:** 2.14 ms
  - **P50 Latency:** 2.01 ms
  - **P95 Latency:** **3.25 ms** (PASS, $\le 15.0\text{ ms}$)

---

## 4. Handoff to Independent Verifier (`VERIF-INDEP`)

- **Branch:** `cap-ret02-fusion`
- **Candidate Commit:** `d1ab26a` (repaired and verified 23/23 tests pass)
- **Predecessor:** `cap-ret01-embedding` (`9f90ac8bd00f07935d40d1b01ac4ea2283121c97`)
- **Successor Unlocked:** Node `CAP-RET03` (Graph PPR & Typed Structural Associations).

---

## 5. Repair Record — R-RET02 Round 2 (RET-SPEC, 2026-09-03)

- **Lease scope:** Step-0 FUSION-NECESSARY hunks only; no other code motion.
- **Old SHA:** `94afcf3b358c351ac7a71e466a18fca67c32e81a`
- **New SHA:** `cd6dfc2d7da0b429a9520fc931ff87bd33c50a40` (detached-HEAD commit `R-RET02:`, branch `cap-ret02-fusion` advanced via `update-ref`; worktree `/tmp/trace-wt/ret02` removed)
- **Files changed (2 lines total):**
  - `src/trace/v2/adapters/embedding.py:27` — `PINNED_MODEL_REVISION`: `e4ce9877abf3ed5223c6a46944e9514f7b60a2d2` → `1110a243fdf4706b3f48f1d95db1a4f5529b4d41`
  - `tests/v2/test_retrieval_embedding.py:241` — matching `declared_model_revision` assertion updated to `1110a243...`
- **Pin-change evidence:**
  - Old pin `e4ce9877...` returns HF 404 (`RemoteEntryNotFoundError`; all files at that pin are `.no_exist`) — root cause of deterministic-fallback activation, NOT missing deps (round 1: torch 2.14.0+cpu + sentence_transformers 6.0.1 present, 39/39 with fallback ACTIVE).
  - New pin `1110a243fdf4706b3f48f1d95db1a4f5529b4d41` loads (weights warm in `HF_HOME=/tmp/hf-cache-coord`) with 384-dim normalized output.
- **Lease read-only checks (no fix needed, untouched):** no `[:300]` truncation on retrieval path (`retrieval.py:650` — "Full postings evaluation: no [:300] cutoff"); RRF `k=60` bit-exact (`compute_rrf_score`, `retrieval.py:56-74`, default `k=60` at line 59, fallback `60` at line 94).
- **Acceptance log** (`PYTHONPATH=src HF_HOME=/tmp/hf-cache-coord /tmp/trace-ret02-venv/bin/pytest tests/v2/test_hybrid_retrieval.py tests/v2/test_retrieval_embedding.py`):
  - Final run: **39 passed in 9.55s**.
  - Note: `test_p95_retrieval_latency_in_memory_index` is timing-flaky on this box (observed P95 19.11 ms / 22.32 ms vs 15.0 ms budget on earlier runs); confirmed it also fails on the unmodified base (`94afcf3`, P95 15.75 ms) using `HashingDenseEmbedder`, so the failure is pre-existing/environmental and unrelated to this pin change.
- **Backend telemetry (real adapter, `LocalDenseEmbedder()` default):**
  - `is_fallback=false`, `is_neural=true`, `model_backend_qualification=QUALIFIED_NEURAL`, `qualification_status=QUALIFIED_NEURAL`
  - `provider_id=local-dense:sentence-transformers/all-MiniLM-L6-v2:onnx:cpu` (no `deterministic-fallback`)
  - `active_backend=onnx`, `active_device=cpu`, `declared_model_revision=1110a243...`, `dimensions=384`, embed dim 384, norm 1.0
- **Guard test:** `test_backend_selection_and_qualification_telemetry` takes the real-adapter path (`standard_adapter` fixture → `get_embedding_adapter(PINNED_MODEL_NAME)`) and PASSED against the new pin (all 16/16 in `test_retrieval_embedding.py`).
- **Left uncommitted in parent checkout:** this handoff note only (per brief; do NOT commit parent changes).
