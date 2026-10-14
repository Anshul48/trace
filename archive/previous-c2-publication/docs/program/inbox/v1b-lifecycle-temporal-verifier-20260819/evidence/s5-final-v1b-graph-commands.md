# Final V1b Graph Commands

All commands used the fresh graph verifier worktree, environment, scratch, and
result roots. Network was disabled; no provider, dataset, implementation
worktree, or prior verifier state was used.

1. Identity preflight:

```powershell
git -C C:\Users\anshu\AppData\Local\trace-verifier-worktrees\v1b-final-graph-20260823 rev-parse HEAD
git -C C:\Users\anshu\AppData\Local\trace-verifier-worktrees\v1b-final-graph-20260823 rev-parse HEAD^{tree}
git -C C:\Users\anshu\AppData\Local\trace-verifier-worktrees\v1b-final-graph-20260823 status --porcelain=v1 --branch
```

Result: clean detached worktree at `3e7e9f0ee460e3af75f3935343f6d6f2089f9f7c`,
tree `ef83211ff9a52bce0706bda7b102639830b5a554`.

2. Locked dependency preflight:

```powershell
uv run --offline --locked --project C:\Users\anshu\AppData\Local\trace-verifier-worktrees\v1b-final-graph-20260823 --extra dev python -c "import sys, numpy, lancedb"
```

Result: blocked before test execution because `torch==2.13.0` was not in the
fresh cache and network was disabled.

3. Low-level independent receipt:

```powershell
& C:\Users\anshu\AppData\Local\trace-verifier-envs\v1b-final-graph-20260823\Scripts\python.exe docs\program\inbox\v1b-lifecycle-temporal-verifier-20260819\evidence\reports\s5_final_graph_verifier.py
```

Result: 8/8 low-level cases passed; full sub-gate blocked by missing NumPy,
LanceDB, and pytest. Raw receipt:
`C:\Users\anshu\AppData\Local\trace-verifier-results\v1b-final-graph-20260823\graph-receipt.json`
SHA-256 `ef1931adeba7ac1e860d9c5659bed38c5311e7f2abb3510ee50a26d05e8438b4`.

4. Cleanup/status: both exact scratch roots were empty after the run; verifier
worktree remained clean; result root and environment were retained for review.
