# Independent Verification Dispatch: CAP-RET04

- **Target Node:** `CAP-RET04`
- **Track:** Track 2 (Retrieval & Grounding Engine)
- **Assigned Role:** Codex Independent Verifier (`VERIF-INDEP`)
- **Assigned Worktree:** Clean detached worktree, read-only execution
- **Prerequisites Confirmed:** `CAP-RET02` (PASS), `CAP-RET03` (PASS), `CAP-EVAL02` (PASS, SciFact 300 / NFCorpus 323 / FiQA 648 verified)
- **Candidate Commit:** `5b719ca53bec4d6ddb24e4691ccfecdc485a6df8` (`cap-ret03-graph`)
- **Base Commit:** `94afcf3b358c351ac7a71e466a18fca67c32e81a`
- **Verification Directive:** `docs/program/launch/CAP_001_SESSION_PROMPTS_WAVEB_TO_1M.md` (§4C)
- **Lease Boundary:** `docs/program/inbox/cap-ret04/` (exclusive writes)
- **Deterministic Acceptance Command:**
  ```bash
  python benchmarks/run_frozen_retrieval_baseline.py --verify-receipt
  ```
- **Negative Assertions:**
  1. SciFact nDCG@10 point estimate $\ge 0.65$ and lower 95% bootstrap bound $\ge 0.63$.
  2. NFCorpus nDCG@10 point estimate $\ge 0.32$, lower 95% bootstrap bound $\ge 0.30$, and CI width $\le 0.10$.
  3. FiQA nDCG@10 point estimate $\ge 0.38$ and lower 95% bootstrap bound $\ge 0.36$.
  4. Receipt audit confirms exactly 0 LLM calls and $0.00 spend during retrieval.
- **Output:** `docs/program/inbox/cap-ret04/retrieval_baseline_dossier.json` + `docs/program/inbox/cap-ret04/verification_receipt.json` (schema §12).
