# Independent Verification Dispatch: CAP-RET03

- **Target Node:** `CAP-RET03`
- **Track:** Track 2 (Retrieval & Grounding Engine)
- **Assigned Role:** Codex Independent Verifier (`VERIF-INDEP`)
- **Assigned Worktree:** Detached worktree `/tmp/trace-wt/ret03`
- **Candidate Branch:** `cap-ret03-graph`
- **Candidate Commit:** `5b719ca53bec4d6ddb24e4691ccfecdc485a6df8`
- **Base Commit:** `94afcf3b358c351ac7a71e466a18fca67c32e81a` (`cap-ret02-fusion`)
- **Verification Directive:** `docs/program/launch/CAP_001_SESSION_PROMPTS_WAVEB_TO_1M.md` (§4A)
- **Lease Boundary:** `src/trace/v2/retrieval.py` (graph-walk / spreading activation section only), `tests/v2/test_graph_retrieval.py`
- **Deterministic Acceptance Command:**
  ```bash
  PYTHONPATH=src pytest tests/v2/test_graph_retrieval.py -v
  ```
- **Negative Assertions:**
  1. Empty graph returns hybrid candidates with explicit telemetry flag (`graph_applied=False, empty_graph=True`).
  2. Disconnected seed nodes return hybrid candidates with explicit telemetry flag (`graph_applied=False, empty_graph=True`).
  3. Non-associative relations (e.g. `OPPOSITE_OF`) filtered out.
  4. Out-degree per node strictly capped at $\le 50$.
  5. Walk depth strictly bounded at $\le 15$.
  6. Cyclic graphs terminate cleanly within max 20 iterations without infinite loop.
  7. Multihop P95 latency $\le 10$ ms budget.
- **Output:** `docs/program/inbox/cap-ret03/verification_receipt.json` (schema §12).
