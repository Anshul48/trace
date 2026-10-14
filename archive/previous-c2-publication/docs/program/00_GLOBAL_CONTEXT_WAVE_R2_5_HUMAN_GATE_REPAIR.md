# Wave R2.5 Human Gate REPAIR: Forensic Remediation & 100K Requalification Plan

**Date**: 2026-08-29
**Status**: ACTIVE EXECUTION / COORDINATION
**Governing Standard**: Trace Wave R2.5 / Level 1 Scale Certification Standard (`DEC-P-005b-LEVEL1-R2.5`)
**Target Milestone**: Gate C2 Requalification & Formal 100K Candidate Certification

---

## 1. Executive Context & Human Gate C2 Ruling

The Human Gate evaluation of Wave R2.4 noted that while implementation fixes are substantial (including verified 100,047 row reduction to 100,000 unique records, 65,394,921 raw text bytes, isolated startup, and 63/63 passing tests), the formal Gate C2 promotion is **REPAIR** due to remaining evidence chain and verification custody gaps:

1. **Defect 3 (Blind Queries Hash Binding & Qrels Custody)**:
   - Behavioral blindness exists, but both candidate runner and independent verifier must cryptographically bind the exact SHA-256 digest of the blind queries file:
     `CANONICAL_BLIND_QUERIES_SHA256 = "8731e89f4e1395c459da09859f89cc7bacad5dccf2c7c367874027e9021b449b"`
   - Candidate manifest must record `blind_queries_sha256`.
   - Independent verifier must assert `candidate_manifest["blind_queries_sha256"] == CANONICAL_BLIND_QUERIES_SHA256`.
   - Verifier must hold exclusive custody of `queries_manifest.json` (`8cb5c48cc722a5e9...`) containing qrels.

2. **Defect 4 (Execution Provenance & Clean Worktree)**:
   - In candidate mode, the runner verifies a clean Git worktree (`git status --porcelain`).
   - Verifier verifies all cryptographic identity bindings (`runner_hash`, `verifier_hash`, `schema_hash`, `policy_hash`, `corpus_manifest_sha256`, `blind_queries_sha256`).

3. **Defect 7 (Strict Original-Source Byte Offset Anchor Verification)**:
   - Source anchor verification must strictly verify byte offset slices against raw upstream dataset corpus files (`data_root` / `corpus_manifest.json`).
   - Eliminate fallback to candidate-authored SQLite event payloads for original-source proof! Slicing candidate's own DB payload does NOT prove original upstream source fidelity.
   - 100% of sampled anchors must match the upstream source dataset files.

4. **Defect 9 (Output Directory Safety & Fresh Candidate Evidence)**:
   - Fix runner/tests so `output_dir=None` with `force_overwrite=True` can never accidentally overwrite or delete root-level retained evidence in default directories. Tests must always use isolated `tmp_path`.
   - Produce a newly generated, timestamped/isolated diagnostic bundle, acknowledging the historical deletion.
   - Execute a fresh 100K candidate run from clean worktree, sealed and verified by the independent verifier.

---

## 2. Cryptographic Digest Constants

| Artifact | Canonical Path | Authoritative SHA-256 |
| :--- | :--- | :--- |
| **Corpus Manifest** | `docs/program/inbox/l1-02-corpus-capsule-20260828/evidence/corpus_manifest.json` | `0739a9cc9322ad647e7a1764114017ab17ba208ed2d0626f00bd1e3f1707ef6e` |
| **Blind Queries** | `docs/program/inbox/l1-02-corpus-capsule-20260828/evidence/queries_blind_eval.jsonl` | `8731e89f4e1395c459da09859f89cc7bacad5dccf2c7c367874027e9021b449b` |
| **Queries Manifest (Qrels)** | `docs/program/inbox/l1-02-corpus-capsule-20260828/evidence/queries_manifest.json` | `8cb5c48cc722a5e92cd7d0451484ac1ea39804d3bed4a7d9db0e7f8fbabe18c9` |
| **Scale Policy Lockfile** | `benchmarks/policies/scale_policy.lock.json` | `983279467455f006a5245bea0e8c550ce3a286fbda3fc5b01f9d797b05e3d880` |
| **Scale Policy Schema** | `benchmarks/policies/scale_policy.schema.json` | `a935b0b230232479e9daae5a755d7b5ea5f63ec0492cb470878e1215ee540fc7` |

---

## 3. Action Plan & Specialist Agent Delegation

### Agent 1: Runner Specialist
1. Update `scripts/run_100k_scale_gate.py`:
   - Bind `CANONICAL_BLIND_QUERIES_SHA256`. Validate `queries_file` digest on load; fail closed on mismatch.
   - Record `blind_queries_sha256` in `candidate_manifest.json` and `checksums.json`.
   - Prevent default output directory clobbering when `output_dir=None` and `force_overwrite=True`.

### Agent 2: Verifier Specialist
1. Update `scripts/verify_100k_candidate.py`:
   - Bind `CANONICAL_BLIND_QUERIES_SHA256`. Check `candidate_manifest["blind_queries_sha256"] == CANONICAL_BLIND_QUERIES_SHA256`.
   - Source-Only Anchor Verification: Verify sampled node version slices `content_bytes[span_start:span_end]` strictly against original raw corpus dataset files loaded via `data_root` / `corpus_manifest.json`. Remove fallback to candidate event payload.

### Agent 3: Test Suite Specialist
1. Update `tests/test_scale_candidate_verifier.py`, `tests/test_scale_abstention_pipeline.py`, `tests/test_scale_rebuild_integrity.py`:
   - Update mock candidate generators to include `blind_queries_sha256`.
   - Ensure mock candidate generators create mock source dataset files in a mock `data_root` so source-only anchor verification tests pass.
   - Guarantee all test runner invocations use isolated `tmp_path` directories.

---

## 4. Verification & Rehearsal Pipeline
1. Run full unit and system test suite:
   ```bash
   uv run pytest tests/test_scale_candidate_verifier.py tests/test_scale_rebuild_integrity.py tests/test_scale_abstention_pipeline.py tests/test_scale_recovery_quarantine.py
   ```
2. Execute fresh diagnostic rehearsal in an isolated timestamped directory:
   ```bash
   python scripts/run_100k_scale_gate.py --diagnostic --target-docs 1000 --sample-size 50 --output-dir benchmarks/runs/diagnostic/100k_scale_rehearsal_r2_5 --force-overwrite
   python scripts/verify_100k_candidate.py --candidate-dir benchmarks/runs/diagnostic/100k_scale_rehearsal_r2_5 --policy benchmarks/policies/scale_policy.lock.json
   ```
3. Prepare for full 100K candidate certification run.
