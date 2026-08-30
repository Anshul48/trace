# Trace-Lite Provenance and Rebuild Parity Proof (TL3)

> **Status:** Empirical Parity Proof & Provenance Verification
> **Prepared by:** Worker B (Trace-Lite Empirical Profiler)
> **Target:** Foundation Hardening Wave — Lifecycle & Rebuild Verification
> **Raw Evidence Artifact:** `docs/program/inbox/l1-tl1-candidate-active-lifecycle/evidence/tl3-empirical-measurements.json`

---

## 1. Objective

Verify that incremental builds and full rebuilds over the same Spine source atoms produce:
1. Exact atom SHA-256 content hash preservation ($100.0\%$).
2. Exact source character offset and artifact provenance matching.
3. Equivalent active-read visibility and complete Forest source atom coverage ($1.0$).
4. Clean topological integrity and index validation health without orphan accumulation.

---

## 2. Empirical Parity Measurements

Empirical measurements were collected using TraceLite instances subjected to incremental chunked ingestion (`ingest()` + periodic `organize()`) versus full batch ingestion (`ingest()` + `reindex_all()` full rebuild).

### 2.1 Rebuild vs Incremental Lifecycle Metrics

| Metric | Corpus Size $N=100$ | Corpus Size $N=300$ | Status / Invariant |
| :--- | :---: | :---: | :---: |
| **Documents Ingested** | 20 documents | 60 documents | Tested over multi-document corpora |
| **Source Atom Count Parity** | `100 / 100` ($100\%$) | `300 / 300` ($100\%$) | $\text{Count}(\text{atoms}_{\text{inc}}) = \text{Count}(\text{atoms}_{\text{reb}})$ |
| **Exact SHA-256 Content Hash Parity** | **$1.0$ ($100.0\%$)** | **$1.0$ ($100.0\%$)** | `hashes_inc == hashes_reb == expected_hashes` |
| **Spine Character Offsets Match** | **`True` ($100.0\%$)** | **`True` ($100.0\%$)** | `char_offset_start` and `char_offset_end` identical |
| **Active Forest Atom Coverage** | **`1.0` ($100.0\%$)** | **`1.0` ($100.0\%$)** | 100% of non-orphan Spine atoms indexed in Forest |
| **Index Validation State (Inc)** | `healthy = True` | `healthy = True` | Candidate passes all integrity checks |
| **Index Validation State (Rebuild)** | `healthy = True` | `healthy = True` | Candidate passes all integrity checks |
| **Incremental Build Duration** | 45.65 s | 89.65 s | Periodic consolidation across chunks |
| **Full Rebuild Duration** | 3.92 s | 17.56 s | Single-pass atomic candidate build |
| **Full Rebuild Speedup Factor** | **11.64x** | **5.10x** | Rebuild amortizes clustering & staging costs |

---

## 3. Formal Invariants & Empirical Verification

### Invariant 1: Spine Immutability & Hash Determinism
- Every ingested atom computes its SHA-256 hash over raw utf-8 content:
  $$\text{content\_hash} = \text{SHA256}(\text{atom.content})$$
- Ingesting identical source documents produces strictly identical `content_hash` sets, matching across incremental and full rebuild runs with **100% parity rate** (`hash_preservation_rate = 1.0`).
- Character offset coordinates `(char_offset_start, char_offset_end)` within source artifacts remain exact and invariant under both execution modes (`offsets_exact_match = True`).

### Invariant 2: Active Forest Source Atom Coverage
- Forest trees index 100% of valid non-orphan atoms from the Spine store (`source_atom_coverage = 1.0`).
- Candidate isolation ensures that until candidate validation succeeds, active reads only see validated active builds.
- Orphan atoms from deleted or superseded source documents are excluded from active tree traversal.

### Invariant 3: Replay Idempotency & Clean Provenance
- Re-running `organize()` when no pending work exists exits immediately without redundant mutations (`trees_updated = 0`).
- Re-running `reindex_all()` over an unchanged Spine regenerates a clean, validated index manifest with identical atom coverage and summary node provenance (`summary_provenance in {'source', 'llm', 'retry'}`).
- No orphan tree nodes or ghost graph edges are retained across atomic rebuild swaps.

---

## 4. Test Suite Parity Confirmation

All 153 Trace-Lite unit, integration, and lifecycle scenario tests pass in the worktree (`trace-lite-l1`):
- `test_scenario_8_replay_restart_is_idempotent`: **PASSED**
- `test_scenario_9_concurrent_ingestion_watermark_or_pending`: **PASSED**
- `test_scenario_10_full_rebuild_and_incremental_parity`: **PASSED**
- Overall test suite: **153 passed, 1 warning in 159.39s**.
