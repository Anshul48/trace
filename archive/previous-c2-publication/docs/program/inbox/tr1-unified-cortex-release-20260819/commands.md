# Commands Log — S3 Trace V2 Cortex Release Owner

> Task ID: `tr1-unified-cortex-release-20260819`
> Role: S3 — Trace V2 Cortex Release Owner / Worker A Hardening
> Worktree: `C:\Users\anshu\AppData\Local\trace-worktrees\trace-tr1`
> Lease: `docs/program/inbox/d0-coordinator-20260819/leases/lease-s3-t0-tr1.json`

---

## 1. T0 Snapshot and Preflight

```powershell
# 1. Inspect original dirty working tree
cd C:\Users\anshu\OneDrive\Documents\Code\Utilities\trace
git status
git rev-parse HEAD
# Output: Commit c855bb06532b3b52b25f0bea969d2677e5049065; 26 modified files; 5 untracked surfaces

# 2. Create isolated worktree for TR1 implementation
git worktree add -b feat/tr1-unified-cortex-release C:\Users\anshu\AppData\Local\trace-worktrees\trace-tr1
cd C:\Users\anshu\AppData\Local\trace-worktrees\trace-tr1
git add -A
git commit -m "feat(trace): freeze isolated V2 implementation base snapshot (T0)"
# Output: Base snapshot commit 5626bde7bc4086f5d9a4f96dae8e1d04a1191936
```

---

## 2. TR1 Implementation and Lifecycle Tests

```powershell
# 1. Implementation changes in C:\Users\anshu\AppData\Local\trace-worktrees\trace-tr1:
#    - migrations/005_cortex_unified_release_lifecycle.sql (PostgreSQL schema for Cortex release roots & components)
#    - src/trace/v2/models.py (CortexValidationReceipt, CortexReleaseComponent, CortexRelease models)
#    - src/trace/v2/repository.py (Cortex release lifecycle interface protocol)
#    - src/trace/v2/store.py (SQLite release management, validation receipts, atomic pointer swap, rollback)
#    - src/trace/v2/production.py (PostgreSQL release management, RLS, alias promotion compensation)
#    - src/trace/v2/retrieval.py (Active release binding for PPR traversal and diagnostics)
#    - src/trace/v2/service.py (Orchestration for validation gating, atomic activation, alias rollback)
#    - src/trace/v2/api.py (/v2/cortex/releases REST endpoints)
#    - tests/test_v2_lifecycle_isolation.py (Candidate isolation, atomic activation, rollback, tenant isolation)
#    - tests/test_v2_api_cognitive.py (Cortex release API endpoint validation)

# 2. Execute test suite in worktree
uv run --extra dev pytest -v
# Output: 52 passed in 11.65s (0 failures, 0 regressions)

# 3. Commit TR1 implementation
git add -A
git commit -m "feat(cortex): implement unified Cortex Release lifecycle root (DEC-P-003 Option A)"
# Output: Commit 454c5aed2200796ac9874e4fbe6e099bdb53f830
```

---

## 3. Dependency Hardening (Foundation Hardening Wave)

```powershell
# 1. Declare httpx and python-multipart in dev optional dependencies in pyproject.toml
#    pyproject.toml: added httpx>=0.27.0 and python-multipart>=0.0.9 to [project.optional-dependencies].dev

# 2. Stage and commit dependency declaration
cd C:\Users\anshu\AppData\Local\trace-worktrees\trace-tr1
git add pyproject.toml
git commit -m "fix(deps): declare httpx and python-multipart as dev dependencies"
# Output: Commit ffbf51813e3cfd0bd69774132376a00ec1bfefdc

# 3. Verify clean dev execution without extra CLI flags
uv run --extra dev pytest -v
# Output: 52 passed in 6.53s
```

---

## 4. Verification and Invariant Checks

- [x] Zero mutations applied to canonical checkout `C:\Users\anshu\OneDrive\Documents\Code\Utilities\trace`.
- [x] Predecessor migrations `001` through `004` preserved strictly immutable.
- [x] Candidate releases completely isolated from normal queries.
- [x] Pointer advancement physically gated on complete validation receipts.
- [x] Rollback tested and proven as an atomic pointer operation preserving history.
- [x] All 52 tests pass in isolated worktree with dev dependencies declared.
