# Implementation Wave Handoff — WP-CAP-CRX01 (Cortex Projections Schema & Evidence Anchors)

## 1. Identity

```yaml
packet_id: "WP-CAP-CRX01"
work_packet_name: "Cortex Projections Schema & Evidence Anchors"
assigned_role: "CRX-SPEC (Cortex Specialist)"
branch: "cap-crx01-schema"
status: "completed"
base_commit: "a9255b4"
governing_plan: "docs/program/COGNITIVE_ARCHITECTURE_CORRECTION_PLAN.md"
execution_dag: "docs/program/02_EXECUTION_DAG.md"
invariants: "docs/program/01_INVARIANTS.md"
independent_verifier: "VERIF-INDEP"
```

## 2. Executive Summary

In strict accordance with `WP-CAP-CRX01`, Program Invariants (`docs/program/01_INVARIANTS.md` Invariants 1, 3, 8), Clause `CAP-D004` ("Keep Spine state canonical and all learned/generated organization rebuildable, revisioned, evidence-anchored Cortex state"), and Clause `CAP-D014` ("Add one versioned `semantic_organization` release component whose manifest binds compatible summary/entity/claim/relation/active-schema artifacts"):

1. **Typed Pydantic Models for Cortex Projections (`src/trace/v2/cortex/`):**
   - Implemented `TopicHolon`: `topic_id`, `title`, `summary`, `source_atom_ids: list[str]`, `parent_topic_id: str | None = None`, `confidence: float`, `model_id: str`, `prompt_hash: str`.
   - Implemented `SectionSummary`: `section_id`, `title`, `content`, `anchor_atom_ids: list[str]`, `token_count: int`.
   - Implemented `EntityCandidate`: `entity_id`, `canonical_name`, `entity_type`, `aliases: list[str]`, `source_atom_ids: list[str]`, `mention_contexts: list[str]`.
   - Implemented `RelationCandidate`: `source_entity_id`, `target_entity_id`, `relation_type`, `evidence_atom_ids: list[str]`, `weight: float = 1.0`.
   - Implemented `CortexProjectionManifest`: `release_id`, `projection_type`, `created_at`, `atom_version_ids: list[str]`, `artifacts: dict[str, Any]`, `lineage_hash: str`.

2. **Strict Invariant Validation on Evidence Anchors:**
   - Strictly enforced non-empty evidence anchors across all models: any instantiation with empty, omitted, whitespace-only, non-string, or blank-element `source_atom_ids`, `anchor_atom_ids`, or `evidence_atom_ids` fails closed with `pydantic.ValidationError`.
   - Reusable evidence anchor validator `validate_evidence_anchor_list` validates anchor sequences and collections (`list`, `tuple`, `set`, `frozenset`) with leading/trailing whitespace normalization.
   - Comprehensive boundary validation enforces `0.0 <= confidence <= 1.0`, non-negative `token_count`, non-negative `weight`, finite float checks (rejecting `NaN` and `Inf`), and explicit rejection of boolean spoofing on numeric fields.
   - Identifier validation rejects empty or whitespace-only strings across all key identifiers (`topic_id`, `section_id`, `entity_id`, `source_entity_id`, `target_entity_id`, `release_id`, `projection_type`, etc.).
   - Cycle prevention strictly rejects self-parenting topics (`parent_topic_id == topic_id`).
   - Manifest element validation ensures non-empty string atom IDs inside `atom_version_ids`.

3. **Deterministic JSON Serialization & Cryptographic Lineage Digests:**
   - Implemented `deterministic_json(data)`: Guarantees recursive key sorting across both string and heterogeneous key types without type errors, compact separators `(',', ':')`, UTC ISO 8601 datetimes with trailing `'Z'`, deterministically sorted sets, float zero sign normalization (`-0.0` to `0.0`), extended type support (`date`, `UUID`, `Path`, `Decimal`, `Enum`), and strict rejection of un-serializable `NaN`/`Inf`.
   - Implemented `compute_lineage_hash(manifest)`: Computes authoritative SHA-256 hex digest over manifest contents while excluding `lineage_hash` itself, ensuring idempotency and equivalence across model instances, raw Python dictionaries, and serialized JSON dictionaries.
   - Timezone normalization: All timezone representations of the exact same instant (e.g. UTC, UTC+4, UTC-5) are normalized to UTC, ensuring hash determinism and eliminating false mismatches.
   - Implemented `digest(obj)`: Exposes cryptographic SHA-256 digest computation across all projection models (`TopicHolon.digest()`, `SectionSummary.digest()`, `EntityCandidate.digest()`, `RelationCandidate.digest()`, and `CortexProjectionManifest.digest()`), with parity for manifest dictionary mappings.
   - Verified that `CortexProjectionManifest` auto-computes its `lineage_hash` upon instantiation if not explicitly provided, exposes `.verify_lineage_hash()` for tamper-checking, and `.recompute_lineage_hash()` for refreshing.

4. **Backward Compatibility & Package Structure:**
   - Created package `src/trace/v2/cortex/` with schemas in `schemas.py`, re-exports in `models.py`, and package initialization in `__init__.py`.
   - Preserved seamless backward compatibility with existing modules (`trace.v2.store`, `trace.v2.retrieval`, `trace.v2.service`, `trace.v2.production`, `run_100k_scale_gate.py`) by re-exporting legacy primitives (`ActivationEdge`, `ActivationEngine`, `ActivationWeights`, `canonical_pair`, etc.).

5. **Comprehensive Unit Test Suite (`tests/v2/test_cortex_schemas.py`):**
   - Authored 56 unit tests covering:
     * Package exports and import parity across `trace.v2.cortex`, `trace.v2.cortex.schemas`, and `trace.v2.cortex.models`.
     * Legacy primitive availability.
     * Valid instantiation and field access.
     * Strict rejection on missing, empty, or whitespace-only evidence anchors across all models.
     * Input boundary checks (confidence range, token count non-negativity, weight bounds, boolean rejection, non-empty identifiers).
     * Deterministic JSON key sorting, whitespace compaction, set sorting, and NaN/Inf rejection.
     * Timezone normalization and lineage hash invariance across multiple timezone representations.
     * Heterogeneous mapping key sorting without `TypeError`.
     * Extended type serialization (`date`, `UUID`, `Path`, `Decimal`, `Enum`, `-0.0`).
     * Whitespace-only identifier rejection across all schemas.
     * Self-parenting rejection in `TopicHolon`.
     * Manifest atom version ID element validation.
     * Manifest tamper verification (`verify_lineage_hash()`) and recomputation (`recompute_lineage_hash()`).
     * Sensitivity of SHA-256 digests to every field mutation.
     * Lossless roundtrip serialization to/from dictionary and JSON for all 5 models.
   - Verified 100% pass rate (56/56 tests pass).

---

## 3. Scope of Mutation & Lease Adherence

### Exclusive Writable File Lease Paths
- `src/trace/v2/cortex/` (`__init__.py`, `schemas.py`, `models.py`)
- `tests/v2/test_cortex_schemas.py`
- `docs/program/inbox/cap-crx01/handoff.md`

### Read-Only Context Inspected
- `src/trace/v2/models.py`
- `src/trace/v2/cortex.py`
- `docs/program/01_INVARIANTS.md`
- `docs/program/COGNITIVE_ARCHITECTURE_CORRECTION_PLAN.md` (Section 5.2, Section 5.3, Clauses CAP-D004, CAP-D014)

Zero files outside the authorized lease were modified.

---

## 4. Verification Commands & Results

### 1. Acceptance Test Suite Execution
```bash
PATH=./.venv/bin:$PATH PYTHONPATH=src pytest tests/v2/test_cortex_schemas.py -v
```
**Output:**
```text
============================= test session starts ==============================
platform linux -- Python 3.12.3, pytest-9.1.1, pluggy-1.6.0 -- /mnt/c/Users/anshu/AppData/Local/trace-worktrees/trace-crx01/.venv/bin/python
cachedir: .pytest_cache
rootdir: /mnt/c/Users/anshu/AppData/Local/trace-worktrees/trace-crx01
configfile: pyproject.toml
plugins: anyio-4.15.0, asyncio-1.4.0
asyncio: mode=Mode.STRICT, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collecting ... collected 56 items

tests/v2/test_cortex_schemas.py::test_package_exports_parity PASSED      [  1%]
tests/v2/test_cortex_schemas.py::test_legacy_cortex_primitives_remain_available PASSED [  3%]
tests/v2/test_cortex_schemas.py::test_topic_holon_valid_instantiation PASSED [  5%]
tests/v2/test_cortex_schemas.py::test_section_summary_valid_instantiation PASSED [  7%]
tests/v2/test_cortex_schemas.py::test_entity_candidate_valid_instantiation PASSED [  8%]
tests/v2/test_cortex_schemas.py::test_relation_candidate_valid_instantiation PASSED [ 10%]
tests/v2/test_cortex_schemas.py::test_cortex_projection_manifest_valid_instantiation PASSED [ 12%]
tests/v2/test_cortex_schemas.py::test_cortex_projection_manifest_from_iso_string PASSED [ 14%]
tests/v2/test_cortex_schemas.py::test_cortex_projection_manifest_naive_datetime_attaches_utc PASSED [ 16%]
tests/v2/test_cortex_schemas.py::test_topic_holon_strictly_rejects_empty_source_atoms[invalid_anchors0] PASSED [ 17%]
tests/v2/test_cortex_schemas.py::test_topic_holon_strictly_rejects_empty_source_atoms[invalid_anchors1] PASSED [ 19%]
tests/v2/test_cortex_schemas.py::test_topic_holon_strictly_rejects_empty_source_atoms[invalid_anchors2] PASSED [ 21%]
tests/v2/test_cortex_schemas.py::test_topic_holon_strictly_rejects_empty_source_atoms[invalid_anchors3] PASSED [ 23%]
tests/v2/test_cortex_schemas.py::test_topic_holon_strictly_rejects_empty_source_atoms[invalid_anchors4] PASSED [ 25%]
tests/v2/test_cortex_schemas.py::test_topic_holon_rejects_missing_source_atoms PASSED [ 26%]
tests/v2/test_cortex_schemas.py::test_section_summary_strictly_rejects_empty_anchor_atoms[invalid_anchors0] PASSED [ 28%]
tests/v2/test_cortex_schemas.py::test_section_summary_strictly_rejects_empty_anchor_atoms[invalid_anchors1] PASSED [ 30%]
tests/v2/test_cortex_schemas.py::test_section_summary_strictly_rejects_empty_anchor_atoms[invalid_anchors2] PASSED [ 32%]
tests/v2/test_cortex_schemas.py::test_section_summary_strictly_rejects_empty_anchor_atoms[invalid_anchors3] PASSED [ 33%]
tests/v2/test_cortex_schemas.py::test_section_summary_rejects_missing_anchor_atoms PASSED [ 35%]
tests/v2/test_cortex_schemas.py::test_entity_candidate_strictly_rejects_empty_source_atoms[invalid_anchors0] PASSED [ 37%]
tests/v2/test_cortex_schemas.py::test_entity_candidate_strictly_rejects_empty_source_atoms[invalid_anchors1] PASSED [ 39%]
tests/v2/test_cortex_schemas.py::test_entity_candidate_strictly_rejects_empty_source_atoms[invalid_anchors2] PASSED [ 41%]
tests/v2/test_cortex_schemas.py::test_entity_candidate_strictly_rejects_empty_source_atoms[invalid_anchors3] PASSED [ 42%]
tests/v2/test_cortex_schemas.py::test_entity_candidate_rejects_missing_source_atoms PASSED [ 44%]
tests/v2/test_cortex_schemas.py::test_relation_candidate_strictly_rejects_empty_evidence_atoms[invalid_anchors0] PASSED [ 46%]
tests/v2/test_cortex_schemas.py::test_relation_candidate_strictly_rejects_empty_evidence_atoms[invalid_anchors1] PASSED [ 48%]
tests/v2/test_cortex_schemas.py::test_relation_candidate_strictly_rejects_empty_evidence_atoms[invalid_anchors2] PASSED [ 50%]
tests/v2/test_cortex_schemas.py::test_relation_candidate_strictly_rejects_empty_evidence_atoms[invalid_anchors3] PASSED [ 51%]
tests/v2/test_cortex_schemas.py::test_relation_candidate_rejects_missing_evidence_atoms PASSED [ 53%]
tests/v2/test_cortex_schemas.py::test_validate_evidence_anchor_list_standalone PASSED [ 55%]
tests/v2/test_cortex_schemas.py::test_topic_holon_confidence_boundaries PASSED [ 57%]
tests/v2/test_cortex_schemas.py::test_section_summary_token_count_boundaries PASSED [ 58%]
tests/v2/test_cortex_schemas.py::test_relation_candidate_weight_boundaries PASSED [ 60%]
tests/v2/test_cortex_schemas.py::test_string_fields_reject_empty_strings PASSED [ 62%]
tests/v2/test_cortex_schemas.py::test_deterministic_json_key_sorting PASSED [ 64%]
tests/v2/test_cortex_schemas.py::test_deterministic_json_whitespace_compaction PASSED [ 66%]
tests/v2/test_cortex_schemas.py::test_deterministic_json_set_sorting PASSED [ 67%]
tests/v2/test_cortex_schemas.py::test_deterministic_json_rejects_nan_inf PASSED [ 69%]
tests/v2/test_cortex_schemas.py::test_compute_lineage_hash_manifest_parity PASSED [ 71%]
tests/v2/test_cortex_schemas.py::test_compute_lineage_hash_excludes_lineage_hash_itself PASSED [ 73%]
tests/v2/test_cortex_schemas.py::test_digest_methods_on_all_models PASSED [ 75%]
tests/v2/test_cortex_schemas.py::test_digest_is_sensitive_to_every_field_change PASSED [ 76%]
tests/v2/test_cortex_schemas.py::test_topic_holon_roundtrip PASSED       [ 78%]
tests/v2/test_cortex_schemas.py::test_section_summary_roundtrip PASSED   [ 80%]
tests/v2/test_cortex_schemas.py::test_entity_candidate_roundtrip PASSED  [ 82%]
tests/v2/test_cortex_schemas.py::test_relation_candidate_roundtrip PASSED [ 83%]
tests/v2/test_cortex_schemas.py::test_cortex_projection_manifest_roundtrip PASSED [ 85%]
tests/v2/test_cortex_schemas.py::test_timezone_normalization_hash_invariance PASSED [ 87%]
tests/v2/test_cortex_schemas.py::test_deterministic_json_heterogeneous_key_sorting PASSED [ 89%]
tests/v2/test_cortex_schemas.py::test_deterministic_json_extended_types PASSED [ 91%]
tests/v2/test_cortex_schemas.py::test_whitespace_only_identifiers_strictly_rejected PASSED [ 92%]
tests/v2/test_cortex_schemas.py::test_topic_holon_rejects_self_parenting PASSED [ 94%]
tests/v2/test_cortex_schemas.py::test_cortex_projection_manifest_atom_version_ids_validation PASSED [ 96%]
tests/v2/test_cortex_schemas.py::test_manifest_verification_and_recompute_helpers PASSED [ 98%]
tests/v2/test_cortex_schemas.py::test_digest_manifest_mapping_parity PASSED [100%]

============================== 56 passed in 4.39s ==============================
```

### 2. Full Regression Test Suite Execution
```bash
PATH=./.venv/bin:$PATH PYTHONPATH=src pytest tests/ -v
```
**Output:**
```text
======================== 188 passed, 1 skipped in 19.46s =======================
```

### 3. Programmatic Invariant Assertion
```bash
PATH=./.venv/bin:$PATH PYTHONPATH=src python3 -c "
from datetime import datetime, timezone, timedelta
from pydantic import ValidationError
from trace.v2.cortex import (
    TopicHolon,
    SectionSummary,
    EntityCandidate,
    RelationCandidate,
    CortexProjectionManifest,
    compute_lineage_hash,
)

# 1. Non-empty evidence anchors invariant
for model_cls, kw in [
    (TopicHolon, {'topic_id': 't', 'title': 'T', 'summary': 'S', 'source_atom_ids': [], 'confidence': 0.9, 'model_id': 'm', 'prompt_hash': 'p'}),
    (SectionSummary, {'section_id': 's', 'title': 'T', 'content': 'C', 'anchor_atom_ids': [], 'token_count': 10}),
    (EntityCandidate, {'entity_id': 'e', 'canonical_name': 'N', 'entity_type': 'T', 'source_atom_ids': []}),
    (RelationCandidate, {'source_entity_id': 'e1', 'target_entity_id': 'e2', 'relation_type': 'r', 'evidence_atom_ids': []}),
]:
    try:
        model_cls(**kw)
        assert False, f'{model_cls.__name__} should have rejected empty evidence anchors'
    except ValidationError:
        pass

# 2. Timezone normalization and lineage hash determinism
tz4 = timezone(timedelta(hours=4))
m_utc = CortexProjectionManifest(release_id='rel-test', projection_type='test', created_at=datetime(2026, 9, 3, 8, 0, 0, tzinfo=timezone.utc), atom_version_ids=['a1'])
m_tz4 = CortexProjectionManifest(release_id='rel-test', projection_type='test', created_at=datetime(2026, 9, 3, 12, 0, 0, tzinfo=tz4), atom_version_ids=['a1'])
assert m_utc.lineage_hash == m_tz4.lineage_hash
assert m_utc.verify_lineage_hash() is True

print('WP-CAP-CRX01 Cortex Schema & Evidence Anchor Invariants Verified.')
"
```
**Output:**
```text
WP-CAP-CRX01 Cortex Schema & Evidence Anchor Invariants Verified.
```

---

## 5. Handoff to Independent Verifier

The branch `cap-crx01-schema` is fully implemented, hardened, verified with 56 unit tests, free of regressions (188 passed across repository), and ready for detached independent verification by `VERIF-INDEP`.
