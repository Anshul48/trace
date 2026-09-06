# Independent Verification Dispatch: CAP-JOB01

- **Target Node:** `CAP-JOB01`
- **Track:** Track 4 (Background Job Engine & Pipeline)
- **Assigned Role:** Codex Independent Verifier (`VERIF-INDEP`)
- **Assigned Worktree:** `C:/Users/anshu/AppData/Local/trace-worktrees/trace-job01` (`/mnt/c/Users/anshu/AppData/Local/trace-worktrees/trace-job01`)
- **Candidate Branch:** `cap-job01-pipeline`
- **Candidate Commit:** `c853f43b0361e085c9ab0bb63e3ac16758a89fb1`
- **Base Commit:** `a9255b4` (`main`)
- **Verification Directive:** `docs/program/launch/CAP_001_SESSION_PROMPTS_WAVEB_TO_1M.md` (§2)
- **Lease Boundary:** `src/trace/v2/service.py` (job chaining section only), `tests/v2/test_job_pipeline.py`
- **Deterministic Acceptance Command:**
  ```bash
  PYTHONPATH=src /home/anshul/.venv/trace/bin/pytest tests/v2/test_job_pipeline.py -v
  ```
- **Negative Assertions:**
  1. Ingestion hot path latency `<10ms` non-blocking (`test_raw_atom_ingestion_returns_under_10ms_nonblocking`).
  2. Zero blocking on downstream LLM / consolidators during raw atom ingestion.
  3. Fail closed on synthetic fallbacks.
- **Output:** `docs/program/inbox/cap-job01/verification_receipt.json` (schema §12).
