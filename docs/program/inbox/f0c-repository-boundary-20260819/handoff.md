# F0c Handoff — Repository Boundary & Current-State Record

> **Task ID:** F0c (`f0c-repository-boundary-20260819`)
> **Role:** Coordinator (read-only repository-boundary capture)
> **Status:** completed (read-only capture)
> **Date:** 2026-08-19

## Outcome

- **Task ID:** F0c (`f0c-repository-boundary-20260819`)
- **Status:** completed
- **One-sentence result:** Captured and verified the exact repository roots, Git identities, working tree states, and protected path inventories across Trace-Lite, Trace, trace-bench, and Program Control Plane without modifying any product code or user worktrees.

---

## Deliverables

- **Machine-readable Repository State Records:**
  - `docs/program/inbox/f0c-repository-boundary-20260819/component-records/trace-lite.json`
  - `docs/program/inbox/f0c-repository-boundary-20260819/component-records/trace.json`
  - `docs/program/inbox/f0c-repository-boundary-20260819/component-records/trace-bench.json`
  - `docs/program/inbox/f0c-repository-boundary-20260819/component-records/program-control-plane.json`
  - `docs/program/inbox/f0c-repository-boundary-20260819/repository-state.json` (consolidated)
- **Human-readable Component Records:**
  - `docs/program/inbox/f0c-repository-boundary-20260819/component-records/trace-lite.md`
  - `docs/program/inbox/f0c-repository-boundary-20260819/component-records/trace.md`
  - `docs/program/inbox/f0c-repository-boundary-20260819/component-records/trace-bench.md`
  - `docs/program/inbox/f0c-repository-boundary-20260819/component-records/program-control-plane.md`
- **Evidence & Synthesis Documents:**
  - `docs/program/inbox/f0c-repository-boundary-20260819/evidence/component-boundaries.md`
  - `docs/program/inbox/f0c-repository-boundary-20260819/evidence/protected-paths.md`
  - `docs/program/inbox/f0c-repository-boundary-20260819/evidence/stale-packet-matrix.md`
  - `docs/program/inbox/f0c-repository-boundary-20260819/evidence/benchmark-boundary-disposition.md`
  - `docs/program/inbox/f0c-repository-boundary-20260819/evidence/safe-worktree-recommendation.md`
  - `docs/program/inbox/f0c-repository-boundary-20260819/evidence/task-board.md`
  - `docs/program/inbox/f0c-repository-boundary-20260819/evidence/decision-requests.md`
  - `docs/program/inbox/f0c-repository-boundary-20260819/evidence/implementation-preparation-checklist.md`
- **Execution & Audit Log:**
  - `docs/program/inbox/f0c-repository-boundary-20260819/commands.md`

---

## Verification

- **Commands Run:** Live read-only Git status, diff-stat, file hashing, and directory tree inspection across all three component paths and the control plane.
- **Results:**
  - **Trace-Lite:** Git commit `fe66a9eefc8372f7cc021c864d26e62a9d6cc9c1` on `main`; 0 tracked modifications; 11 untracked documentation/template files protected.
  - **Trace:** Git commit `c855bb06532b3b52b25f0bea969d2677e5049065` on `main`; 26 tracked modified files (6,291 insertions, 187 deletions; diff SHA `dbc213b9...`); 5 untracked surfaces protected.
  - **trace-bench:** Unversioned source tree (`.git` absent); 41 files in source inventory; content manifest SHA `739d7f42fb40c9234b716f5a30aa9e0acd224c4e486e24f95e4afa8f1ca36f1e`; non-certifying pending P-007 and P-008.
  - **Control Plane:** 103 files locked under snapshot `foundation-control-plane-20260819-initial` (tree SHA `c6592609...`).
- **Failure Cases Exercised:** Verified that no destructive operations (`clean`, `reset`, `checkout`) were permitted or run against any user working trees.
- **What Remains Unverified:** Runtime behavior, database schemas, and benchmark accuracy remain unverified by design (read-only boundary capture).

---

## Risks and Follow-Up

- **New or Changed Risks:**
  - **R-07 / R-15 (Elevated):** Multiple past handoffs citing `63bb3cb` or chat-only data/eval assertions are formally marked STALE / NON-DURABLE.
  - **R-01 (Observed):** Trace candidate affinity and activation priors leak into active query paths by static inspection; requires T1 audit and TR1 repair.
  - **R-02 (Observed):** Trace-Lite all-pairs co-occurrence loop in `graph.py` is an $O(n^2)$ scaling blocker; requires P-002 and TL2.
  - **R-03 (Observed):** `trace-bench` contains mock defaults and fallback paths; requires P-007, P-008, and B1 fail-closed runner.
- **Recommended Next Packets:**
  1. Dispatch read-only **F0a (Evaluation Engineer)** and **F0b (Data Steward)** in parallel.
  2. Dispatch read-only **T1 (Trace Engineer)** for Cortex Release audit.
  3. Dispatch read-only **V0 (Independent Verifier)** to freeze V1a/V1b negative test matrices.
- **Questions Requiring Human Direction:**
  - **P-007:** Canonical source governance for `trace-bench` (Git repository vs. content-manifest archive).
  - **P-008:** Canonical runner boundary (designate `trace-bench` as sole certification runner).

---

## Claim Boundary

- **Highest Justified Claim Level:** **C0 (Idea / Control Plane Baseline)** and **Observed Current-State Records**.
- **Why That Level Is Justified:** All facts reflect direct read-only static inspection of current working trees on 2026-08-19.
- **What This Work Explicitly Does Not Establish:**
  - Does NOT certify software correctness, performance, or SOTA.
  - Does NOT authorize data acquisition, model invocation, or provider calls.
  - Does NOT alter product code or clean user worktrees.
  - Does NOT mark B1, L1, TR1, or TR2 prepared without concrete worktree leases and verifier matrices.

---

## Change and State Accounting

| Field | Record |
| --- | --- |
| **Base Commit / Worktree** | `trace`: `c855bb06532b3b52b25f0bea969d2677e5049065`; `trace-lite`: `fe66a9eefc8372f7cc021c864d26e62a9d6cc9c1`; `trace-bench`: unversioned (`739d7f42fb...`). |
| **Changed Paths** | Files created solely under `docs/program/inbox/f0c-repository-boundary-20260819/`. |
| **Unchanged Protected Paths** | All 26 modified files and 5 untracked surfaces in `trace`; 11 untracked files in `trace-lite`; all 41 files in `trace-bench`. |
| **Data / External State** | None. No network requests, provider calls, or data downloads. |
| **Retained State** | All user development snapshots preserved completely intact. |
| **Rollback Path** | Delete task directory `docs/program/inbox/f0c-repository-boundary-20260819/` if needed; no product files affected. |

---

## Verification Truthfulness

- **Verified:** Repository paths, Git branches, commits, diff fingerprints, untracked file lists, and content manifest digests are verified by exact local command execution.
- **Observed:** Candidate leakage paths in Trace and all-pairs graph expansion in Trace-Lite are statically observed source patterns.
- **Planned:** B1, L1, TR1, TR2, V1a, V1b execution.
- **Blocked:** Data staging (B2/P-001), 100K certification (B3/P-005), and downstream shadowing.

---

## Reviewer Decision Prompt

1. **Exact Decision Requested:**
   - Confirm review and acceptance of F0c read-only boundary record.
   - Accept or select options for **P-007** (`trace-bench` source governance) and **P-008** (canonical certification runner boundary).
2. **Safe Default if No Decision Made:**
   - `trace-bench` remains unversioned and non-certifying.
   - Dispatch read-only exploratory audits (**F0a**, **F0b**, **T1**, **V0**); hold all mutable implementation packets (**B1**, **L1**, **TR1**, **TR2**) in `scoped / blocked` state.
3. **Smallest Next Packets:**
   - **F0a** (Evaluation Audit), **F0b** (Dataset Admission Records), **T1** (Cortex Release Audit), **V0** (Independent Verifier Plan).
