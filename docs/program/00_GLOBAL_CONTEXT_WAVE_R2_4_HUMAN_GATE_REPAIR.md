# GLOBAL CONTEXT: Wave R2.4 Human Gate REPAIR Remediation Specification

**Status**: ACTIVE REPAIR REMEDIATION
**Verdict Under Remediation**: Human Gate Verdict: REPAIR (Wave R2.3 Review)
**Standard**: DEC-P-005b-LEVEL1-R2.2 / DEC-P-005b-LEVEL1-R2.4
**Date**: 2026-08-29

---

## 1. Executive Summary of Human Gate C2 Ruling

The Human Gate evaluation acknowledged substantial code repairs (canonical candidate IDs, DB membership verifications, UTF-8 byte offset math, direct replay DB comparisons, graph telemetry percentiles, frozen storage denominator, and RSS accounting). However, 9 remaining defects prevent formal Level 1 closure.

This document serves as the authoritative, shared specification for all specialist subagents and the coordinator to completely remediate all 9 defects.

---

## 2. The 9 Remaining Gate-Stopping Defects & Concrete Remediation Plans

### Defect 1: Frozen Corpus Identity & Deduplication Boundary
* **Finding**: The frozen corpus manifest specified `[0, 80000)` for MuSiQue. Global deduplication across the 5 datasets revealed 47 duplicate records (5 duplicate IDs, 42 duplicate contents). The runner read overflow records [80000:80047), violating the frozen manifest boundary.
* **Remediation**:
  1. Inspect the 5 raw dataset corpus files and compute the exact global deduplication map.
  2. Update `docs/program/inbox/l1-02-corpus-capsule-20260828/evidence/corpus_manifest.json`:
     - Update MuSiQue `selected_records_d` to `80047` with `selection_range: "[0, 80047)"` so that after global deduplication, exactly 80,000 unique MuSiQue documents are selected.
     - Compute the exact `selection_merkle_root_sha256`, `total_raw_text_bytes`, and per-dataset statistics.
     - Update all references in `benchmarks/policies/scale_policy.lock.json` and verifier constants.
  3. Ensure the runner reads strictly within the declared `selection_range` with zero unmanifested overflow.

### Defect 2: Candidate-ID Integrity on Fresh Candidate
* **Finding**: Canonical persisted ID logic and DB membership assertions are verified at code level, requiring validation on fresh full candidate runs.
* **Remediation**:
  - Keep strict canonical doc_id mapping (`self.doc_index: dict[str, Document]`).
  - Runner and verifier strictly verify 100% of candidate IDs against SQLite `ingestions.doc_id`.

### Defect 3: Qrels Separation & Blind Runner Custody
* **Finding**: Runner opened `queries_manifest.json` containing `gold_ids`, `is_null_query`, and `expected_abstention`.
* **Remediation**:
  1. Split query inputs into:
     - `queries_unlabeled.jsonl`: Contains ONLY `query_id`, `query_text`, `lane`, `dataset`. Contains NO `gold_ids`, `is_null_query`, or `expected_abstention`.
     - `queries_manifest.json`: Held exclusively in verifier custody with full qrels and expected labels.
  2. Runner accepts `--queries-file queries_unlabeled.jsonl`.
  3. Runner final verdict is `AWAITING_INDEPENDENT_VERIFICATION`, never self-issued `PASS_ALL_SCALE_GATE_INVARIANTS`.

### Defect 4: Strict Execution Provenance & Policy Reconciliation
* **Finding**: Candidate mode did not reject dirty git worktrees; tree hash was HEAD tree; verifier did not check recorded hashes against authoritative sources.
* **Remediation**:
  1. In `--candidate` mode, runner enforces `git status --porcelain` is clean (fails closed if dirty, unless running with `--diagnostic`).
  2. Compute git tree hash accurately.
  3. Verifier checks `runner_hash`, `schema_hash`, `policy_hash`, `verifier_hash` against authoritative files.
  4. Update `benchmarks/policies/scale_policy.lock.json` status to `FORMAL_REPAIR_QUALIFICATION_LOCKED`.

### Defect 5: Retained Replay Database Mandatory
* **Finding**: `scale_100k_replay.db` was optional in verifier evidence list.
* **Remediation**:
  1. Add `scale_100k_replay.db` to `MANDATORY_EVIDENCE_FILES` in `scripts/verify_100k_candidate.py`.
  2. Fail closed if `scale_100k_replay.db` is missing or fails 6-table SHA-256 parity audit against `scale_100k.db`.
  3. Update all test fixtures to include `scale_100k_replay.db`.

### Defect 6: Total Hot-State Storage Accounting
* **Finding**: Runner computed storage multiplier using raw bytes rather than frozen denominator. Verifier only counted main DB file, omitting WAL/SHM.
* **Remediation**:
  1. Both runner and verifier compute total hot database state: `size(scale_100k.db) + size(scale_100k.db-wal) + size(scale_100k.db-shm)`.
  2. Both runner and verifier compute storage multiplier strictly against frozen policy denominator (`raw_text_denominator_bytes = 62,870,136` or updated manifest denominator).

### Defect 7: Original-Source Byte Offset Anchors
* **Finding**: Verifier verified byte slices from `events.payload_json` rather than upstream corpus files. Tests lacked multibyte character coverage.
* **Remediation**:
  1. Verifier verifies sampled byte offset spans directly against raw upstream dataset corpus files using corpus offsets map.
  2. Add multibyte UTF-8 test cases in `tests/test_scale_rebuild_integrity.py`.

### Defect 8: Clean-Install Isolated Startup
* **Finding**: `uv run --isolated python scripts/run_100k_scale_gate.py --help` failed due to missing `pydantic`.
* **Remediation**:
  1. Add `pydantic>=2.10` to `dependencies` in `pyproject.toml`.
  2. Guard `src/trace/v2/__init__.py` so submodule imports don't trigger optional dependency failures.

### Defect 9: Retain Diagnostic Packets
* **Finding**: `benchmarks/runs/diagnostic/100k_scale` must persist all 11 evidence files and receipt for auditing.
* **Remediation**:
  - Retain all diagnostic run outputs and verify end-to-end.

---
