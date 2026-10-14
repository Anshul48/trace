# WP-CAP-CRX02 Handoff Summary: Consolidator Engine Refactor

- **Node ID:** `CAP-CRX02`
- **Work Packet:** `WP-CAP-CRX02`
- **Role:** Cortex Specialist (`CRX-SPEC`)
- **Worktree Branch:** `cap-crx02-consolidator`
- **Base Commit:** `59ce53a152ca6331908bc7489bb2e15bc963b156` (Gate CAP-CRX01 verified)
- **Governing Plan:** `docs/program/COGNITIVE_ARCHITECTURE_CORRECTION_PLAN.md` (Section 3.3, Clauses `CAP-D002`, `CAP-D003`)
- **Execution DAG:** `docs/program/CAP_001_EXECUTION_DAG.md` (Node `CAP-CRX02`)
- **Status:** Complete & Ready for Independent Verification (`VERIF-INDEP`)

---

## 1. Scope of Mutation & Exclusive Lease Audit

Mutations strictly adhered to exclusive file lease boundaries declared in `docs/program/CAP_001_RESPONSIBILITY_LEASE_MAP.md`:
- `src/trace/v2/cortex_consolidator.py` (New):
  - Created `CortexConsolidator` engine supporting both `mode="extractive_control"` and `mode="semantic_slm"`.
  - Implemented typed holon generation (`TopicHolon`, `SectionSummary`, `EntityCandidate`, `RelationCandidate`, `CortexProjectionManifest`).
  - Implemented `TraceModelGateway.call_json` integration for SLM extraction with fail-closed validation.
  - Implemented `materialize_to_store` to persist holons as derived nodes and proposals into the durable event store.
  - Implemented backward-compatible `EvidenceHierarchyBuilder` and `HierarchyBuildResult`.
- `src/trace/v2/organization.py` (Modified):
  - Refactored to import and re-export `CortexConsolidator`, `EvidenceHierarchyBuilder`, `ExtractiveSummaryGenerator`, `SummaryValidator`, and related helpers from `cortex_consolidator.py`, maintaining 100% API and behavioral backward compatibility.
- `tests/v2/test_cortex_consolidator.py` (New test suite):
  - 11 unit and integration tests covering extractive baseline control, deterministic idempotency, SLM gateway interface, fail-closed anchor validation, store materialization, and `EvidenceHierarchyBuilder` drop-in parity.
- `docs/program/inbox/cap-crx02/handoff.md` (Deliverable receipt).

Forbidden boundary check:
- `src/trace/v2/cortex/` was **NOT** modified.
- `src/trace/v2/model_gateway.py` was **NOT** modified.
- `src/trace/v2/service.py` was **NOT** modified.

---

## 2. Technical Architecture & Dual-Mode Consolidation

### A. Mode 1: `extractive_control` (Factual Baseline Control)
- Provides deterministic, reproducible extraction directly from source atoms without calling external model gateways.
- Generates:
  - `SectionSummary`: chunked by `section_size`, validated against source atom tokens.
  - `TopicHolon`: clustered by transparent Jaccard term overlap, with `confidence=1.0` and `model_id="extractive-control-v1"`.
  - `EntityCandidate`: extracted from capitalized and frequent key terms anchored to source atoms.
  - `RelationCandidate`: co-occurrence pairs using conservative `ALLOWED_RELATIONS` (`supports`, `depends_on`).
  - `CortexProjectionManifest`: verified lineage hash matching `CortexProjectionManifest.verify_lineage_hash() == True`.

### B. Mode 2: `semantic_slm` (Model-Assisted Consolidation)
- Interfaces with `TraceModelGateway.call_json` using structured schema `CORTEX_CONSOLIDATION_RESPONSE_SCHEMA`.
- Supports registered flash and pro models (`deepseek-v4-flash`, `ollama/qwen2.5:1.5b`, etc.).
- Enforces strict fail-closed validation:
  - Every returned `anchor_atom_ids`, `source_atom_ids`, and `evidence_atom_ids` is asserted against the known input source atom IDs.
  - Any hallucinated or ungrounded anchor ID raises `SummaryValidationError` immediately, halting the pipeline.
  - Non-empty validation text is checked via `SummaryValidator.validate`.
  - Attaches model gateway audit cost records into the consolidation result and manifest.

### C. Store Materialization & Backward Compatibility
- `materialize_to_store` writes derived nodes with facets `["summary", "section_summary"]`, `["summary", "topic_holon"]`, and `["entity", "entity_candidate"]`, and records relation candidates as durable proposals with mapped entity node IDs in `store`.
- `EvidenceHierarchyBuilder` inherits from `CortexConsolidator`, preserving full backward compatibility for `build()` and `build_delta()` across all callers.

---

## 3. Verification & Acceptance Evidence

### Acceptance Test Command:
```powershell
PYTHONPATH=src pytest tests/v2/test_cortex_consolidator.py -v
```

**Results:** `15 passed in 2.43s` (100% PASS)
1. `test_extractive_control_deterministic_idempotency`: PASSED
2. `test_extractive_control_generates_typed_holons_and_manifest`: PASSED
3. `test_materialize_to_store_creates_derived_nodes_and_proposals`: PASSED (verifies section summaries, topic holons, and entity candidates are materialized)
4. `test_semantic_slm_interfaces_with_gateway`: PASSED
5. `test_semantic_slm_missing_gateway_raises`: PASSED
6. `test_semantic_slm_rejects_hallucinated_anchors_fail_closed`: PASSED
7. `test_semantic_slm_rejects_unapproved_relation_type`: PASSED (rejects relations not in ALLOWED_RELATIONS)
8. `test_semantic_slm_rejects_ungrounded_entity_references`: PASSED (rejects relations referencing phantom entities)
9. `test_semantic_slm_rejects_self_referencing_relation`: PASSED (rejects self-loops where source == target)
10. `test_semantic_slm_rejects_self_referencing_topic_parent`: PASSED (rejects cyclic topic parenting)
11. `test_cross_workspace_atoms_rejected`: PASSED
12. `test_empty_source_atoms_rejected`: PASSED
13. `test_unsupported_mode_raises`: PASSED
14. `test_build_delta_exact_parity`: PASSED
15. `test_builder_inherits_cortex_consolidator`: PASSED

### Full Regression Suite:
```powershell
PYTHONPATH=src pytest tests/v2/test_cortex_schemas.py tests/test_v2_foundation.py -v
```
**Results:** `63 passed in 3.02s` (100% PASS, zero regressions)

---

## 4. Handoff to Independent Verifier (`VERIF-INDEP`)

- **Branch:** `cap-crx02-consolidator`
- **Worktree:** `C:/Users/anshu/AppData/Local/trace-worktrees/trace-crx02`
- **Predecessor:** Gate `CAP-CRX01` (`59ce53a`)
- **Successor Unlocked:** Node `CAP-EVAL02` (LLM-as-a-Judge Evaluation Engine & Golden Datasets)
