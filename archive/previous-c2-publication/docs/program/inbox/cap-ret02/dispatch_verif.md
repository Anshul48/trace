# Independent Verification Dispatch: CAP-RET02

- **Target Node:** `CAP-RET02`
- **Track:** Track 2 (Retrieval & Fusion Engine)
- **Assigned Role:** Codex Independent Verifier (`VERIF-INDEP`)
- **Assigned Worktree:** `C:/Users/anshu/AppData/Local/trace-worktrees/trace-ret02` (`/mnt/c/Users/anshu/AppData/Local/trace-worktrees/trace-ret02`)
- **Candidate Branch:** `cap-ret02-fusion`
- **Candidate Commit:** `94afcf3b358c351ac7a71e466a18fca67c32e81a`
- **Base Commit:** `9f90ac8` (`cap-ret01-embedding`) / `a9255b4` (`main`)
- **Verification Directive:** `docs/program/launch/CAP_001_SESSION_PROMPTS_WAVEB_TO_1M.md` (§2)
- **Lease Boundary:** `src/trace/v2/retrieval.py` (RRF fusion section only), `tests/v2/test_hybrid_retrieval.py`
- **Deterministic Acceptance Command:**
  ```bash
  PYTHONPATH=src /home/anshul/.venv/trace/bin/pytest tests/v2/test_hybrid_retrieval.py tests/v2/test_retrieval_embedding.py -v
  ```
- **Negative Assertions:**
  1. No `[:300]` hard truncation remains anywhere on the retrieval candidate generation path.
  2. RRF score calculation: `Score(d) = (w_bm25 / (k + rank_bm25(d))) + (w_dense / (k + rank_dense(d)))` with `k=60` bit-exact.
- **Output:** `docs/program/inbox/cap-ret02/verification_receipt.json` (schema §12).
