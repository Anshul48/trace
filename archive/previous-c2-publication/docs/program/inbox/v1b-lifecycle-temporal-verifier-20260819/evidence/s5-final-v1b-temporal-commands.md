# Final V1b Temporal Commands

All commands used the fresh temporal verifier worktree, environment, scratch,
and result roots. Network was disabled; no provider, implementation worktree,
prior verifier state, SQLite substitute, or mock temporal backend was used.

1. Identity preflight:

```powershell
git -C C:\Users\anshu\AppData\Local\trace-verifier-worktrees\v1b-final-temporal-20260823 rev-parse HEAD
git -C C:\Users\anshu\AppData\Local\trace-verifier-worktrees\v1b-final-temporal-20260823 rev-parse HEAD^{tree}
git -C C:\Users\anshu\AppData\Local\trace-verifier-worktrees\v1b-final-temporal-20260823 status --porcelain=v1 --branch
```

Result: clean detached worktree at `0a91b278a414756da260b15c5cb9daddb5e9aac2`,
tree `0a492ca4c3f2310a123577cfa96cc72bdc2c0257`.

2. Locked dependency preflight:

```powershell
uv run --offline --locked --project C:\Users\anshu\AppData\Local\trace-verifier-worktrees\v1b-final-temporal-20260823 --extra v2 python -c "import sys, fastapi, httpx"
```

Result: blocked before test execution because `pydantic-core==2.46.4` was not
in the fresh cache and network was disabled.

3. Independent static/blocked receipt:

```powershell
& C:\Users\anshu\AppData\Local\trace-verifier-envs\v1b-final-temporal-20260823\Scripts\python.exe docs\program\inbox\v1b-lifecycle-temporal-verifier-20260819\evidence\reports\s5_final_temporal_verifier.py
```

Result: static source/migration checks 3/3 passed; all 8 runtime temporal cases
blocked by missing Pydantic/FastAPI/pytest and unavailable PostgreSQL/RLS,
external-index, deployment/object-store capabilities. Raw receipt:
`C:\Users\anshu\AppData\Local\trace-verifier-results\v1b-final-temporal-20260823\temporal-receipt.json`
SHA-256 `c321d4a5db4c8396d8dbf7b90cc2bce93dd8884527b19798a2cb88fe531cad12`.

4. Cleanup/status: both exact scratch roots were empty after the run; verifier
worktree remained clean; result root and environment were retained for review.
