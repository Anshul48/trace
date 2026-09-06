# Independent Verification Dispatch: CAP-CRX03

- **Target Node:** `CAP-CRX03`
- **Track:** Track 3 (Risk-Tiered Activation & Handover)
- **Assigned Role:** Codex Independent Verifier (`VERIF-INDEP`)
- **Assigned Worktree:** `C:/Users/anshu/AppData/Local/trace-worktrees/trace-crx03` (`/mnt/c/Users/anshu/AppData/Local/trace-worktrees/trace-crx03`)
- **Candidate Branch:** `cap-crx03-activation`
- **Candidate Commit:** `824222eed180679727398401adc92d9cfed25358`
- **Base Commit:** `45c3591` (`cap-crx02-consolidator`)
- **Verification Directive:** `docs/program/launch/CAP_001_SESSION_PROMPTS_WAVEB_TO_1M.md` (§3), `CAP_001_WAVEB_DIRECTIVES.md` (Directive D3)
- **Lease Boundary:** `src/trace/v2/service.py` (activation section), `src/trace/v2/store.py` (pointer swap section), `tests/v2/test_cortex_activation.py`
- **Deterministic Acceptance Command:**
  ```bash
  PYTHONPATH=src /home/anshul/.venv/trace/bin/pytest tests/v2/test_cortex_activation.py -v
  ```
- **Special Audits:**
  1. Audit overlap with JOB02 on `service.py` and `store.py`. Mark `PASS_WITH_MERGE_RISK` and document that CRX03 requires rebase onto JOB02 prior to merge.
  2. Crash rollback proof: Injected failures or system crashes during pointer swap must cleanly restore predecessor release without dangling aliases (`test_post_swap_crash_injection_restores_last_known_good_release`).
- **Output:** `docs/program/inbox/cap-crx03/verification_receipt.json` (schema §12).
