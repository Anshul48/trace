# Independent Verification Dispatch: CAP-CRX02

- **Target Node:** `CAP-CRX02`
- **Track:** Track 3 (Cortex Engine)
- **Assigned Role:** Codex Independent Verifier (`VERIF-INDEP`)
- **Assigned Worktree:** `C:/Users/anshu/AppData/Local/trace-worktrees/trace-crx02` (`/mnt/c/Users/anshu/AppData/Local/trace-worktrees/trace-crx02`)
- **Candidate Branch:** `cap-crx02-consolidator`
- **Candidate Commit:** `45c359118991bb6670092baf36cee3f573fc6454`
- **Base Commit:** `59ce53a` (`cap-crx01-schema`) / `a9255b4` (`main`)
- **Verification Directive:** `docs/program/launch/CAP_001_SESSION_PROMPTS_WAVEB_TO_1M.md` (§2)
- **Lease Boundary:** `src/trace/v2/organization.py`, `src/trace/v2/cortex_consolidator.py`, `tests/v2/test_cortex_consolidator.py`
- **Deterministic Acceptance Command:**
  ```bash
  PYTHONPATH=src /home/anshul/.venv/trace/bin/pytest tests/v2/test_cortex_consolidator.py -v
  ```
- **Negative Assertions:**
  1. `extractive_control` mode output must be byte-identical to legacy clipping (`test_build_delta_exact_parity`).
  2. Hallucinated evidence anchors and ungrounded entities fail closed with `InvariantViolation`.
- **Output:** `docs/program/inbox/cap-crx02/verification_receipt.json` (schema §12).
