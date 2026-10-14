# WP-CAP-RET01 Handoff Summary: Dense Embedding Adapter Restoration (Repair Packet WP-CAP-RET01-REPAIR)

- **Node ID:** `CAP-RET01`
- **Work Packet:** `WP-CAP-RET01` / `WP-CAP-RET01-REPAIR`
- **Role:** Retrieval Specialist (`RET-SPEC`)
- **Worktree Branch:** `cap-ret01-embedding`
- **Governing Plan:** `docs/program/COGNITIVE_ARCHITECTURE_CORRECTION_PLAN.md` (Section 3.2, Clause `CAP-D016`)
- **Execution DAG:** `docs/program/CAP_001_EXECUTION_DAG.md` (Node `CAP-RET01`)
- **Remediated Verification Receipt:** `rcpt-cap-ret01-verif-indep-20260903T031302Z`
- **Status:** Complete, Remediated & Ready for Independent Re-Verification (`VERIF-INDEP`)

---

## 1. Scope of Mutation & Exclusive Lease Audit

Mutations strictly adhered to the exclusive file lease boundaries defined for `WP-CAP-RET01-REPAIR`:
- `src/trace/v2/adapters/embedding.py` (Modified): Added qualification telemetry, explicit backend selection properties, stable `provider_id` initialization, ONNX input graph introspection, and pinned revision passing (`e4ce9877abf3ed5223c6a46944e9514f7b60a2d2`).
- `src/trace/v2/retrieval.py` (Modified, embedding section only): Aligned `DenseEmbedder` protocol (`@runtime_checkable`, `Sequence[str] | str`), fixed single-string handling bug in `HashingDenseEmbedder` and `SentenceTransformerDenseEmbedder`, aligned `get_embedding_adapter()` with qualification contracts.
- `tests/v2/test_retrieval_embedding.py` (Modified): Added sys.path prioritization to prevent stdlib `trace` shadowing, and added 8 new unit tests verifying qualification telemetry, fallback diagnostics, protocol structural subtyping, `provider_id` stability, and single-string/batch interface compliance across all adapter implementations (total 16 unit tests).
- `docs/program/inbox/cap-ret01/handoff.md` (Deliverable receipt).

**Lease Audit:** Zero files outside this exclusive lease were modified.

---

## 2. Remediation Details (WP-CAP-RET01-REPAIR)

### A. Python Module Shadowing Resolution & Standard Execution
- **Root Cause:** Python standard library includes a built-in module named `trace` (`/usr/lib/python3.12/trace.py` or Windows `Lib/trace.py`). In a clean checkout without source path precedence or prior editable installation, `python -c "from trace.v2..."` resolves the stdlib `trace.py` module rather than the repository's `src/trace` package, throwing `ModuleNotFoundError: No module named 'trace.v2'; 'trace' is not a package`.
- **Test Suite Resolution:** In `tests/v2/test_retrieval_embedding.py`, `src_dir` is explicitly extracted and prioritized to `sys.path[0]` ahead of standard library paths. In addition, any stale or stdlib `trace` module previously cached in `sys.modules` without package identity is evicted prior to package import.
- **Documented Standard Execution:** Operators and verifiers must execute with source path configured (`$env:PYTHONPATH='src'` in PowerShell, or `PYTHONPATH=src` in POSIX bash), or under a virtual environment with package installed in editable mode.

### B. Explicit Backend Selection & Qualification Telemetry
In `src/trace/v2/adapters/embedding.py`, `LocalDenseEmbedder` now provides explicit qualification contracts:
- **Contract Fields:**
  - `model_backend_qualification`: Strictly `"QUALIFIED_NEURAL"` when running verified neural model inference (ONNX Runtime with DirectML/CUDA or SentenceTransformers), and `"NOT_ESTABLISHED"` when running in deterministic fallback mode.
  - `qualification_status`: `"QUALIFIED_NEURAL"` vs `"DETERMINISTIC_FALLBACK_UNQUALIFIED"`.
  - `is_neural`: `bool` indicating whether execution runs through a genuine neural network.
  - `is_fallback`: `bool` indicating whether execution operates via CPU fallback projection.
  - `active_backend`: `"onnx"` | `"sentence-transformers"` | `"deterministic-fallback"`.
  - `active_device`: `"directml"` | `"cuda"` | `"cpu"`.
- **Telemetry & Diagnostics Payload:**
  - `telemetry` property (and `get_telemetry()`): Captures complete model identity (`declared_model_name`, `declared_model_revision`), dimensions (384), provider ID, requested/active backends, and qualification status.
  - `diagnostics` property (and `get_diagnostics()`): Captures dependency availability (`onnxruntime_available`, `sentence_transformers_available`, `torch_available`, `cuda_available`), list of available ORT providers, structured `attempts` history for all backends tried, and explicit `fallback_reason` text explaining exactly why neural execution was or was not activated.
  - **Logging Diagnostics:** Detailed warning logged whenever deterministic CPU fallback is initialized with the exact dependency/initialization failure breakdown.

### C. Protocol & Adapter Polymorphism Unification
- **Single-String vs Sequence Handling:** Fixed defect in `HashingDenseEmbedder` and `SentenceTransformerDenseEmbedder` where passing a single string `a.embed("Test query")` iterated over individual characters instead of embedding the sentence. All embedders now seamlessly handle both single strings `str` (returning `list[float]`) and batch sequences `Sequence[str]` (returning `list[list[float]]`).
- **Protocol Decorator & Typing:** Annotated `DenseEmbedder` in both `src/trace/v2/retrieval.py` and `src/trace/v2/adapters/embedding.py` with `@runtime_checkable` and aligned their method signatures.
- **Provider ID Stability:** `LocalDenseEmbedder.provider_id` now triggers initialization if accessed prior to `embed()`, ensuring the provider tag is stable and deterministic throughout the object lifecycle.
- **ONNX Robustness:** Added session input graph inspection to conditionally feed `token_type_ids` only when present in the target ONNX model.
- **Revision Provenance:** Pinned model revision `e4ce9877abf3ed5223c6a46944e9514f7b60a2d2` is now passed to both Hugging Face Hub downloads and SentenceTransformer constructors.

---

## 3. Verification & Benchmark Evidence

### A. Unit Test Suite (`tests/v2/test_retrieval_embedding.py`)
```bash
uv run --locked --extra test pytest tests/v2/test_retrieval_embedding.py -v
```
**Results:** `16 passed in 7.45s` (100% PASS)
1. `test_embedding_output_dimension_strictly_384`: PASSED
2. `test_embedding_vector_norm_is_one`: PASSED
3. `test_embedding_consistency_identical_text_yields_identical_vector`: PASSED
4. `test_batch_encoding_throughput`: PASSED
5. `test_cpu_fallback_deterministic`: PASSED
6. `test_empty_and_edge_inputs`: PASSED
7. `test_get_embedding_adapter_wiring`: PASSED
8. `test_hybrid_retrieval_engine_wiring`: PASSED
9. `test_backend_selection_and_qualification_telemetry`: PASSED
10. `test_deterministic_fallback_diagnostics_and_qualification`: PASSED
11. `test_hashing_dense_embedder_qualification_and_telemetry`: PASSED
12. `test_single_and_batch_embed_interfaces`: PASSED
13. `test_sentence_transformer_dense_embedder_single_and_batch_interfaces`: PASSED
14. `test_provider_id_stability_before_and_after_embed`: PASSED
15. `test_dense_embedder_protocol_conformance`: PASSED
16. `test_hashing_dense_embedder_edge_and_empty_inputs`: PASSED

### B. DAG Acceptance Command
**PowerShell:**
```powershell
$env:PYTHONPATH='src'; python -c "from trace.v2.retrieval import get_embedding_adapter; a = get_embedding_adapter('all-MiniLM-L6-v2'); vec = a.embed('Test query'); assert len(vec) == 384; print('Dense Adapter Verified.')"
```

**POSIX bash:**
```bash
PYTHONPATH=src python3 -c "from trace.v2.retrieval import get_embedding_adapter; a = get_embedding_adapter('all-MiniLM-L6-v2'); vec = a.embed('Test query'); assert len(vec) == 384; print('Dense Adapter Verified.')"
```

**Observed Execution Output:**
```text
Using deterministic CPU projection fallback for LocalDenseEmbedder (qualification: NOT_ESTABLISHED). Reason: Deterministic CPU projection fallback active (model_backend_qualification=NOT_ESTABLISHED). Neural backends unavailable: [onnx: Missing ONNX dependencies: numpy, onnxruntime; sentence-transformers: Missing SentenceTransformers dependencies: torch, sentence_transformers].
Dense Adapter Verified.
```
**Result:** Exit Code 0, Assertion Passed, Output `Dense Adapter Verified.` (PASS).

**Deterministic Hashing Fallback Stub Verification:**
```bash
PYTHONPATH=src python3 -c "from trace.v2.retrieval import get_embedding_adapter; a = get_embedding_adapter('all-MiniLM-L6-v2', use_hashing_fallback=True); vec = a.embed('Test query'); assert len(vec) == 384; print('Hashing Dense Adapter Verified.')"
```
**Result:** Exit Code 0, Assertion Passed, Output `Hashing Dense Adapter Verified.` (PASS).

### C. Non-Regression Verification
```bash
uv run --extra test pytest tests/test_v2_cognitive.py -v
```
**Results:** `8 passed in 7.66s` (100% PASS).

---

## 4. Handoff to Independent Verifier (`VERIF-INDEP`)

- **Branch:** `cap-ret01-embedding`
- **Work Packet:** `WP-CAP-RET01-REPAIR`
- **Remediated Receipt Target:** `rcpt-cap-ret01-verif-indep-20260903T031302Z`
- **Successor Blocked Node Pending Clearance:** `CAP-RET02` (Hybrid BM25 + Dense RRF Fusion & Truncation Removal).
