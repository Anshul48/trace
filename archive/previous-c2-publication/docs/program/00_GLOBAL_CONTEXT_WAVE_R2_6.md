# Wave R2.6 Human Gate REPAIR: Scale Certification Recovery & Contract Compliance Plan

**Date**: 2026-08-30
**Status**: ACTIVE EXECUTION / COORDINATION
**Governing Standard**: Trace Wave R2.6 / Level 1 Scale Certification Standard (`DEC-P-005b-LEVEL1-R2.6`)
**Target Milestone**: Gate C2 Requalification & Contract Compliance Remediation

---

## 1. Executive Summary & Audit Resolution

The formal audit of Level 1 (100K) scale certification rejected readiness for L1-06/L1-07 due to 8 blocking findings. This wave directly remediates all 8 findings under the governing standard of `SCALE_CERTIFICATION_RECOVERY_PLAN.md`:

| Finding | Audit Finding | Remediation Strategy |
| :--- | :--- | :--- |
| **1. Dirty Tree & Preflight** | 194 status entries, dirty tree, whitespace errors | Fix all whitespace errors (`git diff --check`), clean/ignore untracked benchmark runs, ensure clean worktree preflight. |
| **2. Product-Real Retrieval** | Runner used in-memory BM25 index rather than persisted SQLite FTS5/cortex store | Implement SQLite FTS5 virtual table (`node_fts`) and persisted graph/lexical retrieval directly via SQL queries in `Scale100KRunner`. |
| **3. Crash Recovery & Resume** | In-process rebuild only; no process interruption, restart receipts, WAL recovery, or incremental watermark proof | Implement subprocess WAL crash recovery drill with restart receipt (`restart_recovery_receipt.json`) and pre-registered incremental resume test (`incremental_resume_receipt.json`). |
| **4. Verifier Independence** | Verifier wrote receipt inside candidate dir, used global cache | Support explicit `--receipt-out`, enforce isolated detached data root, fail closed without global cache fallback. |
| **5. Policy Authority** | Conflicting policy hashes across docs/inbox | Formally bind canonical policy hash `983279467455f006a5245bea0e8c550ce3a286fbda3fc5b01f9d797b05e3d880` across all inbox files and document supersession. |
| **6. Deterministic Anchors** | Unseeded random sampling, text normalization before slicing, machine-global fallback | Implement deterministic seeded sampling, direct UTF-8 byte span verification against raw files, fail-closed isolation. |
| **7. Failed Evidence Custody** | Existing failed candidate evidence in `benchmarks/runs/100k_scale_candidate` cannot be reused | Keep failed candidate preserved for forensics; require new commit-keyed or isolated candidate root. |
| **8. Test Coverage Gaps** | Real runner rehearsal used 20 docs and skipped on exception | Eliminate `pytest.skip` on exception; add comprehensive negative and positive end-to-end tests for all contracts. |

---

## 2. Authoritative Digest Constants

| Artifact | Canonical Path | Authoritative SHA-256 |
| :--- | :--- | :--- |
| **Scale Policy Lockfile** | `benchmarks/policies/scale_policy.lock.json` | `983279467455f006a5245bea0e8c550ce3a286fbda3fc5b01f9d797b05e3d880` |
| **Scale Policy Schema** | `benchmarks/policies/scale_policy.schema.json` | `f9ce026422d4e0fc65b77f143d98559b26402629ebf56e9040d7181fa6fc2bb6` |
| **Corpus Manifest** | `docs/program/inbox/l1-02-corpus-capsule-20260828/evidence/corpus_manifest.json` | `0739a9cc9322ad647e7a1764114017ab17ba208ed2d0626f00bd1e3f1707ef6e` |
| **Blind Queries** | `docs/program/inbox/l1-02-corpus-capsule-20260828/evidence/queries_blind_eval.jsonl` | `8731e89f4e1395c459da09859f89cc7bacad5dccf2c7c367874027e9021b449b` |
| **Queries Manifest (Qrels)** | `docs/program/inbox/l1-02-corpus-capsule-20260828/evidence/queries_manifest.json` | `8cb5c48cc722a5e92cd7d0451484ac1ea39804d3bed4a7d9db0e7f8fbabe18c9` |

---

## 3. Work Allocation & Specialist Streams

1. **Stream A: Policy & Documentation Reconciliation**
   - Reconcile `docs/program/inbox/c2-pol-01-policy-reconciliation-20260829/packet.md`, `handoff.md`, and brief.
   - Record formal supersession of historical candidate and draft hashes.

2. **Stream B: Runner Implementation (`scripts/run_100k_scale_gate.py`)**
   - Persisted SQLite FTS5 index (`node_fts`) created and maintained in `scale_100k.db` and rebuilt in `scale_100k_replay.db`.
   - `retrieve_top_k` executes SQL queries against `node_fts` and `edge_versions`.
   - Process crash recovery drill with fresh-process restart and WAL verification (`restart_recovery_receipt.json`).
   - Incremental resume watermark verification drill (`incremental_resume_receipt.json`).
   - Clean up trailing whitespaces.

3. **Stream C: Verifier Implementation (`scripts/verify_100k_candidate.py`)**
   - Support independent `--receipt-out` path.
   - Deterministic seeded sampling for anchor verification.
   - Strict source data root resolution without global fallback.
   - Parity audit for `node_fts` and audit of crash recovery and incremental resume receipts.

4. **Stream D: Test Suite & Invariant Hardening**
   - Update tests in `tests/test_scale_candidate_verifier.py`, `tests/test_scale_rebuild_integrity.py`, `tests/test_scale_abstention_pipeline.py`.
   - Ensure real runner rehearsal never skips on error.
   - Verify 100% test pass rate across all suites.
