# Safe Worktree & Isolation Recommendations

> **Status:** Recommended procedures for future mutable tasks.
> **Date:** 2026-08-19.

## 1. Principles of Isolated Execution

1. **Never mutate user working trees:** The active working directories of Trace, Trace-Lite, and trace-bench contain user development state, untracked templates, and uncommitted code.
2. **One worktree per mutable task:** Each mutable task packet (e.g. B1, L1, TR1, TR2) must operate in an isolated branch/worktree created specifically for that task.
3. **Formal worktree lease:** No worker begins editing without a valid, non-expired `worktree-lease.json` signed by the coordinator.
4. **Independent verifier isolation:** The verifier must never share the implementer's worktree; verification occurs in a fresh, clean clone/worktree checking out the implementer's final commit.

## 2. Component Worktree Strategies

### A. Trace-Lite (L1 Preparation)
- **Base Commit:** `fe66a9eefc8372f7cc021c864d26e62a9d6cc9c1`
- **Worktree Command:**
  ```powershell
  git worktree add -b l1-lifecycle-20260819 ..\trace-lite-l1 fe66a9eefc8372f7cc021c864d26e62a9d6cc9c1
  ```
- **Scope:** `src/trace_lite/retrieval/`, `src/trace_lite/models/`, `tests/`
- **Protected Outside Worktree:** `benchmarks/protocols/`, `benchmarks/registry/`, `docs/program/`

### B. Trace (TR1 Preparation after T1 & P-003)
- **Base Commit:** `c855bb06532b3b52b25f0bea969d2677e5049065` (or a human-accepted baseline commit encompassing reviewed V2 work).
- **Worktree Command:**
  ```powershell
  git worktree add -b tr1-cortex-release-20260819 ..\trace-tr1 <accepted-base-commit>
  ```
- **Scope:** `src/trace/v2/cortex.py`, `src/trace/v2/release.py`, `src/trace/v2/store.py`, `tests/`
- **Protected Outside Worktree:** All active user changes in the main workspace.

### C. trace-bench (B1 Preparation after F0a, P-007, & P-008)
- **Base:** Depending on P-007 outcome:
  - If Git: create a dedicated branch/worktree.
  - If Content-Manifest Archive: create an isolated staging copy matching manifest digest `739d7f42fb40c9234b716f5a30aa9e0acd224c4e486e24f95e4afa8f1ca36f1e`.
- **Scope:** `src/trace_bench/runner.py`, `src/trace_bench/adapters/`, `tests/`
