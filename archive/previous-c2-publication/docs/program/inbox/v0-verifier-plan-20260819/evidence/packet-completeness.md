# Foundation Packet Completeness & Integrity Review

> **Packet:** V0 — Independent Verifier Plan and Packet-Integrity Review
> **Role:** Independent Verifier / Integration Reviewer
> **Scope:** Audit of Foundation Packets: F0a, F0b, F0c, B1, L1, T1, V1 (V1a/V1b)
> **Status:** Completed Review
> **Evidence Level:** Observed static packet inspection (Planning & Governance baseline)

---

## 1. Executive Summary & Audit Purpose

In accordance with `SESSION_OPERATING_MANUAL.md` (Section 4 & 6) and `02_EXECUTION_DAG.md`, mutable implementation packets (B1, L1, TR1, TR2) cannot be assigned or executed until their input manifests, clean worktree leases, allowed paths, negative test matrices, independent verifier assignments, and prerequisite human decisions (P-001 through P-008) are concrete and complete.

This review evaluates the readiness, structural completeness, and authority boundaries of all starter and successor foundation packets.

---

## 2. Packet Completeness Matrix

| Packet ID | Node | Role | State | Base Identity Status | Scope & Allowed Paths | Authority Boundary | Acceptance & Negative Tests | Verifier Assignment | Stop Conditions & Decision Blocks | Overall Readiness |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **F0a** | F0a | Evaluation Engineer | **Ready** (Read-Only) | Points to moved `trace-bench` root and `trace-lite`. Correctly notes `trace-bench` is unversioned. | Strictly read-only audit of benchmark files and TL engine. | No data download, no network/TLS changes, no code edits. | Inventory of fallbacks, fixture taxonomy, stale packet check. | V0 (Verifies audit findings into V1a plan). | Stops on missing files or attempt to mutate code. | **Complete for Read-Only Execution** |
| **F0b** | F0b | Data Steward | **Ready** (Read-Only) | Audits data candidates and durable records against P-001 candidates. | Read-only dataset discovery and schema mapping. | No data download or external network calls authorized. | Provenance, checksum procedure, query mapping completeness. | Coordinator / Independent Verifier review. | Stops on missing license, unadmitted source, or network call. | **Complete for Read-Only Execution** |
| **F0c** | F0c | Coordinator + Contributors | **Ready / Executed** (Read-Only) | Captured roots, Git commits, and dirty-state inventories for TL, Trace, `trace-bench`, and control plane. | Read-only boundary mapping and dirty path classification. | No code cleanup, stash, reset, or worktree mutation. | Component records, protected path list, worktree safety recommendations. | Independent Verifier (V0 confirms records). | Stops if existing dirty files are overwritten or deleted. | **Complete & Retained in Inbox** |
| **B1** | B1 / E2a | Evaluation Engineer | **Scoped / Blocked** | Depends on F0a and human acceptance of P-007 (trace-bench repo governance) and P-008 (runner boundary). | Scoped to `trace-bench` runner and fail-closed receipts. | Prohibits data download, real certification runs, or metric alterations. | Requires fail-closed receipt emission for all prohibited fallbacks. | V1a assigned (clean verifier worktree required). | Blocked on P-007, P-008, and clean worktree lease. | **Blocked — Not Prepared for Mutation** |
| **L1** | L1 / TL1 | Trace-Lite Engineer | **Scoped / Blocked** | Pinned base `fe66a9e` exists, but requires a dedicated worktree lease to protect local untracked files. | Candidate/active lifecycle isolation in Trace-Lite. Excludes graph degree caps (TL2). | Prohibits bio-inspired research, PPR budget changes, or Alpha path revival. | Candidate invisibility, failed-build preservation, pointer rollback. | V1b (`V1b-TL-Lifecycle`) assigned. | Blocked on F0c review, clean worktree lease, and verifier plan. | **Scoped — Prepared Pending Lease** |
| **T1** | T1 | Trace Engineer | **Ready** (Read-Only) | Uses Trace base `c855bb0` snapshot with 26 modified / 5 untracked files protected. | Read-only audit of Cortex Release, affinity, priors, and temporal code. | Prohibits schema migrations or product code changes. | Mapping read/write paths, P-003 options, P-004 options, TR1 outline. | Independent Verifier (V0 verifies P-003/P-004 matrix). | Stops if migration execution is attempted. | **Complete for Read-Only Execution** |
| **V1a** | V1a | Independent Verifier | **Blocked** | Pinned to clean verifier worktree of B1 implementation commit. | Verification of B1 fail-closed runner against frozen negative matrix. | Independent verification only; forbidden from repairing candidate code. | 17 frozen negative cases (V1A-SRC, V1A-PRV, V1A-DAT, V1A-FLB, etc.). | Self (Independent Verifier role). | Blocked on B1 completion and handoff. | **Prepared — Execution Blocked on B1** |
| **V1b** | V1b | Independent Verifier | **Blocked** | Requires clean verifier worktree and disposable DB environments. | Verification of TL/Trace lifecycle, candidate isolation, and temporal contracts. | Independent verification only; no candidate patching or threshold changes. | 17 frozen fault cases across 4 sub-gates. | Self (Independent Verifier role). | Blocked on L1/TL2 and TR1/TR2 handoffs + P-002/P-003/P-004. | **Prepared — Execution Blocked on Implementation** |

---

## 3. Detailed Component & Packet Review

### 3.1 Packet F0a (Evaluation & Benchmark Re-Anchor)
- **Inputs & Base:** Clearly identifies `trace-bench` moved location (`C:\Users\anshu\OneDrive\Documents\Code\Utilities\trace-bench`) and Trace-Lite root. Correctly identifies `trace-bench` as an unversioned directory.
- **Scope & Authority:** Strictly read-only. Prohibits provider calls, data downloads, or code modifications.
- **Completeness Verdict:** **Complete for Read-Only Execution.** F0a provides the necessary empirical baseline to inform decisions P-007 and P-008.

### 3.2 Packet F0b (Durable Dataset Record Closure)
- **Inputs & Base:** Focuses on candidate datasets for the foundation portfolio (HippoRAG, TREC, LongMemEval, etc.).
- **Scope & Authority:** Read-only metadata compilation. Explicitly prohibits downloading raw datasets before source-specific authorization and P-001 acceptance.
- **Completeness Verdict:** **Complete for Read-Only Execution.**

### 3.3 Packet F0c (Repository Boundary & Current State)
- **Inputs & Base:** Comprehensive inspection of `trace-lite` (`fe66a9e`), `trace` (`c855bb0`), `trace-bench` (unversioned content hash `739d7f4...`), and `docs/program`.
- **Scope & Authority:** Read-only snapshot capture. Classifies 26 tracked modified files and 5 untracked surfaces in Trace as protected user work.
- **Completeness Verdict:** **Fully Executed & Complete.** Component records are durably stored in `inbox/f0c-repository-boundary-20260819/component-records/`.

### 3.4 Packet B1 (Fail-Closed Benchmark Runner Foundation)
- **Deficiencies & Blockers:**
  1. *Missing Source Identity:* `trace-bench` has no Git repository or versioned content manifest (blocked on P-007).
  2. *Ambiguous Runner Boundary:* Coexistence of legacy `src/trace_lite/engines/benchmark.py` and `trace-bench/src/trace_bench/runner.py` requires architectural selection (blocked on P-008).
  3. *Missing Worktree Lease:* Cannot lease a mutable worktree until source governance (P-007) is resolved.
- **Completeness Verdict:** **Scoped / Blocked.** Must remain blocked until F0a handoff is accepted and human owner accepts P-007 and P-008.

### 3.5 Packet L1 (Trace-Lite Candidate/Active Lifecycle)
- **Readiness:**
  1. Base commit `fe66a9eefc8372f7cc021c864d26e62a9d6cc9c1` is clean of tracked changes.
  2. Scope is properly narrowed to candidate/active isolation, staged derived state, and atomic handover. Graph degree/DF caps are correctly deferred to TL2 / P-002.
  3. Independent verifier matrix (`V1b-TL-Lifecycle`) is frozen in V0.
- **Completeness Verdict:** **Prepared Pending Lease.** Requires creating an isolated worktree lease (`worktree-lease.json`) before dispatching the Trace-Lite engineer.

### 3.6 Packet T1 (Trace Cortex Release Audit)
- **Inputs & Base:** Uses existing Trace working snapshot (`c855bb0`) for static analysis only.
- **Scope & Authority:** Strictly read-only audit and migration design. Prohibits executing SQL migrations or modifying product code.
- **Completeness Verdict:** **Complete for Read-Only Execution.** Sets up decision inputs for P-003 (Cortex Release schema) and P-004 (Temporal semantics).

---

## 4. Summary of Prerequisites for Mutable Dispatch

To transition from Stage 0 (Read-Only Refreshes) to Stage 1 (Parallel Foundation Construction):

1. **For B1 (Benchmark):**
   - Accept F0a handoff.
   - Human decision on **P-007** (Governed Git repo vs. content manifest archive for `trace-bench`).
   - Human decision on **P-008** (Canonical runner integration boundary).
   - Issue isolated worktree lease for `trace-bench`.

2. **For L1 (Trace-Lite):**
   - Accept F0c Trace-Lite component record.
   - Issue isolated worktree lease on clean base `fe66a9e`.
   - Confirm allowed paths: `src/trace_lite/lifecycle/`, `src/trace_lite/engines/`, `tests/`.

3. **For TR1 / TR2 (Trace):**
   - Accept T1 audit handoff.
   - Human decision on **P-003** (Unified Cortex Release schema).
   - Human decision on **P-004** (Temporal, revocation, and valid-time contract).
   - Resolve clean base branch/commit separate from dirty V2 work and issue worktree lease.
