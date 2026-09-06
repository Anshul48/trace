# Independent Verification Dispatch: CAP-EVAL02

- **Target Node:** `CAP-EVAL02`
- **Track:** Track 5 (Frozen Evaluation Datasets & Manifests)
- **Assigned Role:** Codex Independent Verifier (`VERIF-INDEP`)
- **Assigned Worktree:** `C:/Users/anshu/AppData/Local/trace-worktrees/trace-eval02` (`/mnt/c/Users/anshu/AppData/Local/trace-worktrees/trace-eval02`)
- **Candidate Branch:** `cap-eval02-datasets`
- **Candidate Commit:** `587aa514e254bc33a5bc18b90ce399cf602992ef`
- **Base Commit:** `8f6efe2` (`cap-eval01-protocol`)
- **Verification Directive:** `docs/program/launch/CAP_001_SESSION_PROMPTS_WAVEB_TO_1M.md` (§3), `CAP_001_WAVEB_DIRECTIVES.md` (Directive D1)
- **Lease Boundary:** `benchmarks/manifests/`, `benchmarks/data/`, `benchmarks/verify_dataset_checksums.py`, `tests/v2/test_eval_datasets.py`
- **Deterministic Acceptance Commands:**
  ```bash
  PYTHONPATH=src:. /home/anshul/.venv/trace/bin/pytest tests/v2/test_eval_datasets.py -v
  /home/anshul/.venv/trace/bin/python benchmarks/verify_dataset_checksums.py --manifest benchmarks/manifests/beir_musique_frozen_v1.json
  ```
- **Special Audits (Directive D1):**
  1. SciFact Count Audit: Assert test split query count is exactly 300 queries (canonical BEIR SciFact archive MD5 `5f7d1de60b170fc8027bb7898e2efca1`). Note that provisional WP text "1,000 queries" was superseded by Directive D1. If 1,000 without named split, FAIL the node.
  2. NFCorpus Count Audit: 323 test queries, canonical archive MD5 `a89dba18a62ef92f7d323ec890a0d38d`.
  3. FiQA Count Audit: 648 test queries, canonical archive MD5 `17918ed23cd04fb15047f73e6c3bd9d9`.
  4. Cryptographic integrity of `benchmarks/manifests/beir_musique_frozen_v1.json` across all 8 staged JSONL files.
- **Output:** `docs/program/inbox/cap-eval02/verification_receipt.json` (schema §12).
