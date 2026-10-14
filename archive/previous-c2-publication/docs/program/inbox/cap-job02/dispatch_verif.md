# Independent Verification Dispatch: CAP-JOB02

- **Target Node:** `CAP-JOB02`
- **Track:** Track 4 (Job Recovery, Heartbeats & Backpressure)
- **Assigned Role:** Codex Independent Verifier (`VERIF-INDEP`)
- **Assigned Worktree:** `C:/Users/anshu/AppData/Local/trace-worktrees/trace-job02` (`/mnt/c/Users/anshu/AppData/Local/trace-worktrees/trace-job02`)
- **Candidate Branch:** `cap-job02-recovery`
- **Candidate Commit:** `d6ab37b0514bbc02108529a942fa038c946bc596`
- **Base Commit:** `c853f43` (`cap-job01-pipeline`)
- **Verification Directive:** `docs/program/launch/CAP_001_SESSION_PROMPTS_WAVEB_TO_1M.md` (§3), `CAP_001_WAVEB_DIRECTIVES.md` (Directive D3)
- **Lease Boundary:** `src/trace/v2/service.py` (lease/heartbeat section), `src/trace/v2/store.py` (job recovery section), `tests/v2/test_job_recovery.py`
- **Deterministic Acceptance Command:**
  ```bash
  PYTHONPATH=src /home/anshul/.venv/trace/bin/pytest tests/v2/test_job_recovery.py -v
  ```
- **Special Audits:**
  1. Audit overlap with CRX03 on `service.py` and `store.py`. Confirm JOB02 merges first per Directive D3.
  2. Verify 300s lease timeout with zombie reclamation.
  3. Verify 3-retry dead-letter queuing (`failed_dead_letter`).
  4. Verify 5,000-item queue backpressure cap.
- **Output:** `docs/program/inbox/cap-job02/verification_receipt.json` (schema §12).
