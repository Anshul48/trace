# WP-CAP-EVAL02 Dispatch Briefing: Frozen Benchmark Datasets & Anchor Manifests

- **Node ID:** `CAP-EVAL02`
- **Assigned Role:** Evaluation Specialist (`EVAL-SPEC`)
- **Assigned Worktree:** `C:/Users/anshu/AppData/Local/trace-worktrees/trace-eval02` (`/mnt/c/Users/anshu/AppData/Local/trace-worktrees/trace-eval02`)
- **Branch:** `cap-eval02-datasets`
- **Base Commit:** `8f6efe2` (`cap-eval01-protocol`)
- **Lease ID:** `lease-cap-eval02-20260903T130500Z`
- **Issued UTC:** `2026-09-03T13:05:00Z`

## Exclusive File Lease
- `benchmarks/manifests/`
- `benchmarks/data/`
- `tests/v2/test_eval_datasets.py`
- `docs/program/inbox/cap-eval02/handoff.md`

## Objectives & Deliverables
1. **Stage Frozen Benchmark Splits:**
   - SciFact (1,000 queries / assertions)
   - NFCorpus (323 queries)
   - FiQA (648 queries)
   - MuSiQue (500 multi-hop questions)
2. **Immutable Cryptographic Manifest:**
   - `benchmarks/manifests/beir_musique_frozen_v1.json` with SHA-256 digests and row counts for all staged splits.
3. **Verification Script:**
   - Standalone validator `benchmarks/verify_dataset_checksums.py` verifying file hashes against the manifest.
4. **Acceptance Test Suite:**
   - `tests/v2/test_eval_datasets.py` verifying manifest existence, SHA-256 integrity, schema validation, and reproducibility under `/home/anshul/.venv/trace/bin/pytest tests/v2/test_eval_datasets.py -v`.
