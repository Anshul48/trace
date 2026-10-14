# S5 Initial V1b Verification Report

## Result

The two executable sub-gates passed the declared local lifecycle contract in
separate verifier worktrees:

- **V1b-TL lifecycle:** `PASS` for the local SQLite/MockVectorStore contract;
  11/11 independent cases passed.
- **V1b-Trace release:** `PASS` for the local SQLite Cortex Release contract;
  6/6 independent cases passed.

These are C1 local receipts, not C4 deployment or release certification. The
clean TL dependency environment could not be provisioned offline because the
locked Torch wheel was absent from cache. The host interpreter was used only
with the fresh verifier checkouts on `PYTHONPATH`; TL used deterministic local
Mock adapters and Trace used local SQLite with deterministic in-process
adapters.

## Exact commands and results

### Preflight

```powershell
git -C C:\Users\anshu\AppData\Local\trace-worktrees\trace-lite-l1 status --short --branch
git -C C:\Users\anshu\AppData\Local\trace-worktrees\trace-lite-l1 rev-parse HEAD
git -C C:\Users\anshu\AppData\Local\trace-worktrees\trace-tr1 status --short --branch
git -C C:\Users\anshu\AppData\Local\trace-worktrees\trace-tr1 rev-parse HEAD
git -C C:\Users\anshu\OneDrive\Documents\Code\Utilities\trace-lite worktree list --porcelain
git -C C:\Users\anshu\OneDrive\Documents\Code\Utilities\trace worktree list --porcelain
```

Results: L1 implementation `7ff40dc46fe3d5e8eef31c485ed0337b8f71602d` and
TR1 implementation `454c5aed2200796ac9874e4fbe6e099bdb53f830` were clean;
each verifier worktree was created at the same full commit and remained clean.
Both leases were `assigned` and unexpired at `2026-08-20T02:19:18Z`.

### TL dependency preflight

```powershell
$env:UV_PROJECT_ENVIRONMENT='C:\Users\anshu\AppData\Local\trace-verifier-scratch\v1b-tl-lifecycle-20260819\.venv'
$env:UV_CACHE_DIR='C:\Users\anshu\AppData\Local\trace-verifier-scratch\v1b-tl-lifecycle-20260819\uv-cache'
uv run --offline --locked --project C:\Users\anshu\AppData\Local\trace-verifier-worktrees\v1b-tl-lifecycle-20260819 --extra dev --extra ui python -c "import sys; import trace_lite; print(sys.version); print(trace_lite.__file__)"
```

Result: `BLOCKED` before test execution because `torch==2.13.0` was not
available in the offline cache. No network fallback was attempted.

### Independent TL receipt

```powershell
$env:PYTHONPATH='C:\Users\anshu\AppData\Local\trace-verifier-worktrees\v1b-tl-lifecycle-20260819\src'
$env:S5_SCRATCH='C:\Users\anshu\AppData\Local\trace-verifier-scratch\v1b-tl-lifecycle-20260819'
$env:S5_RECEIPT='...\evidence\reports\tl-receipt.json'
python '...\evidence\reports\tl_independent_lifecycle.py'
```

Result: `11/11` passed. Cases covered candidate visibility, validation
failure, crash before candidate graph writes, crash after hierarchy writes,
crash after graph writes, pointer rollback, stale graph/vector isolation,
orphan validation, replay idempotency, source arrival during a build, and
incremental/full parity. The raw receipt contains candidate/active IDs,
source hashes, fault messages, visible read sets, and validation observations.

### Trace implementation suites

```powershell
$env:PYTHONPATH='C:\Users\anshu\AppData\Local\trace-verifier-worktrees\v1b-trace-release-20260819\src'
python -m unittest discover -s tests -p 'test_v2_lifecycle_isolation.py' -v
```

Result: `5` tests passed in `0.078s`.

```powershell
$env:PYTHONPATH='C:\Users\anshu\AppData\Local\trace-verifier-worktrees\v1b-trace-release-20260819\src'
python 'tests\test_v2_api_cognitive.py'
```

Result: `2` tests passed in `0.607s`.

### Independent Trace receipt

```powershell
$env:PYTHONPATH='C:\Users\anshu\AppData\Local\trace-verifier-worktrees\v1b-trace-release-20260819\src'
$env:S5_SCRATCH='C:\Users\anshu\AppData\Local\trace-verifier-scratch\v1b-trace-release-20260819'
$env:S5_RECEIPT='...\evidence\reports\trace-receipt.json'
python '...\evidence\reports\trace_independent_release.py'
```

Result: `6/6` passed. Cases covered candidate same-pair isolation for affinity
and priors, validation/atomic handover, injected activation crash followed by
SQLite restart and replay, pointer rollback, workspace isolation, external
alias-promotion compensation, source watermark pinning, and release identity
in ordinary read/bundle diagnostics.

## Independent fault matrix

| Fault or contract | TL local | Trace local | Limitation |
| --- | --- | --- | --- |
| Crash before candidate writes | pass | not attempted | Trace release API has no projection builder fault hook in this packet. |
| Partial hierarchy writes | pass | not applicable | Trace component rows are created with the release; no builder was exercised. |
| Partial affinity/prior/graph writes | pass for candidate graph/vector visibility; pass for Trace affinity/prior release scoping | pass | No real external projection worker was run. |
| Validation failure and attempted activation | pass | pass | Local stores only. |
| Restart/replay after interruption | replay pass; persistent LanceDB restart blocked | pass with file-backed SQLite activation rollback and replay | TL persistent vector backend unavailable. |
| Source arrival during build | pass; source remained pending | pass; release watermark remained pinned before later source arrival | Trace source arrival was tested at release boundary, not a concurrent external worker. |
| Stale candidate/graph rows | pass | pass for release-scoped affinity/prior rows | No PostgreSQL query plan or external index was exercised. |
| Pointer handover/predecessor retention/rollback | pass | pass | Local stores. |
| Cross-workspace candidate access | not applicable to TL data model | pass | PostgreSQL RLS not exercised. |
| External index promotion failure/compensation | not applicable | pass with injected failing alias adapter | Real OpenSearch/Qdrant promotion and compensation remain unverified. |
| Evidence bundle/release identity on ordinary reads | active build identity observed in local manifest/read path | pass; `active_cortex_release_id` present in ordinary response and persisted bundle diagnostics | This does not certify transport/deployment behavior. |

## Unsupported claims

- PostgreSQL, RLS, external indexes, migration deployment, distributed
  concurrency, and real process-kill recovery were not independently exercised.
- TL LanceDB and its active marker were not exercised; `lancedb` is absent from
  the host interpreter and the locked offline environment was blocked by the
  uncached Torch wheel.
- P-002 graph degree/PPR/work budgets and P-004 temporal, revocation,
  supersession, erasure, and historical semantics were not attempted and
  remain explicitly deferred.
- No public benchmark, SOTA, 100K/1M, provider, or certification claim is
  supported by these receipts.

## Cleanup

The two exact external scratch roots were removed after the raw receipts were
persisted. The two verifier worktrees were retained, clean, and available for
coordinator review. The protected user checkouts and implementation worktrees
were not modified.
