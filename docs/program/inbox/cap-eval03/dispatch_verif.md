# Independent Verification Dispatch: CAP-EVAL03

- **Target Node:** `CAP-EVAL03`
- **Track:** Track 5 (Evaluation Harness & Safety Protocols)
- **Assigned Role:** Codex Independent Verifier (`VERIF-INDEP`)
- **Assigned Worktree:** Detached worktree `/tmp/trace-wt/eval03`
- **Candidate Branch:** `cap-eval03-faithfulness`
- **Candidate Commit:** `d00cd0533c4353aa3b3bf9100c5492094ea09e51`
- **Base Commit:** `587aa514e254bc33a5bc18b90ce399cf602992ef` (`cap-eval02-datasets`)
- **Verification Directive:** `docs/program/launch/CAP_001_SESSION_PROMPTS_WAVEB_TO_1M.md` (§4B), `CAP_001_BENCHMARK_METHODOLOGY_ANNEX.md` (§4)
- **Lease Boundary:** `benchmarks/evaluators/faithfulness_validator.py`, `tests/evaluators/test_faithfulness.py`
- **Deterministic Acceptance Command:**
  ```bash
  PYTHONPATH=src:. pytest tests/evaluators/test_faithfulness.py -v
  ```
- **Negative Assertions:**
  1. Adversarial hallucination set rejected at 100% (15/15 cases across unsupported entities, invented numbers, cross-atom splices).
  2. Dual-adjudicated proposition sample ($N = 210 \ge 200$) achieves Cohen's $\kappa \ge 0.70$ (observed $0.9195$).
  3. Generator independence strictly enforced: judge model sharing identity/lineage with generator raises `ValueError`.
  4. Empty/corrupt inputs fail closed with `passed=False, support_ratio=0.0`.
- **Output:** `docs/program/inbox/cap-eval03/verification_receipt.json` (schema §12).
