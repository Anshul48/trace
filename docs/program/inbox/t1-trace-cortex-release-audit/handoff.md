# Handoff: T1 — Trace Cortex Release Audit and Architecture Alternatives

> **Task ID:** T1  
> **Status:** completed (read-only audit and decision preparation)  
> **Role:** Trace Foundation Engineer  
> **One-Sentence Result:** Completed comprehensive read-only audit of Trace V2 projection lifecycle, candidate isolation, and temporal semantics; mapped all 8 storage/retrieval subsystems; and prepared decision inputs and successor outlines for P-003 and P-004 without modifying product code or applying unapproved migrations.

---

## 1. Deliverables

| Deliverable | Location | Description |
| :--- | :--- | :--- |
| **Input Manifest** | `docs/program/inbox/t1-trace-cortex-release-audit/input-manifest.json` | Task input declaration and read-only authority pinning. |
| **Repository State Record** | `docs/program/inbox/t1-trace-cortex-release-audit/repository-state.json` | Pinned commit `c855bb0`, 26 modified tracked files, 5 untracked surfaces, dirty state fingerprints. |
| **Trace F0c Component Record** | `docs/program/inbox/f0c-repository-boundary-20260819/component-records/trace.md` | Trace contribution to F0c repository boundary baseline. |
| **Read/Write Map** | `docs/program/inbox/t1-trace-cortex-release-audit/evidence/read-write-map.md` | Complete map of hierarchy, affinity, priors, vectors, lexical index, hot inbox, legacy hierarchy, and evidence bundles. |
| **P-003 Options Analysis** | `docs/program/inbox/t1-trace-cortex-release-audit/evidence/P-003-options.md` | Evaluation of Monolithic Rebuild (Option B) vs Release Root with Carried-Forward Components (Option A). |
| **P-003 Decision Request** | `docs/program/inbox/t1-trace-cortex-release-audit/evidence/P-003-decision-request.md` | Structured decision request for P-003 per program template. |
| **P-004 Options Analysis** | `docs/program/inbox/t1-trace-cortex-release-audit/evidence/P-004-options.md` | Temporal dimensions, system vs valid time, source lifecycle, revocation, and historical release selection. |
| **TR1 Successor Outline** | `docs/program/inbox/t1-trace-cortex-release-audit/evidence/TR1-successor-outline.md` | Narrow implementation packet specification for unified Cortex Release lifecycle. |
| **TR2 Successor Outline** | `docs/program/inbox/t1-trace-cortex-release-audit/evidence/TR2-successor-outline.md` | Narrow implementation packet specification for temporal truth and revocation baseline. |
| **Commands Log** | `docs/program/inbox/t1-trace-cortex-release-audit/commands.md` | Exact commands and hashes executed during read-only audit. |
| **Handoff Record** | `docs/program/inbox/t1-trace-cortex-release-audit/handoff.md` | This document. |

---

## 2. Verification

| Check / Evaluator | Target | Result | Status |
| :--- | :--- | :--- | :---: |
| **Zero Product Code Mutation** | `src/trace/`, `tests/`, `migrations/` | 0 lines modified or created outside `docs/program/` | **Verified** |
| **Zero Database Mutation** | SQLite & PostgreSQL databases | 0 migrations applied, 0 DB mutations executed | **Verified** |
| **Git Working Tree Protection** | Commit `c855bb06532b3b52b25f0bea969d2677e5049065` | Diff SHA-256 `00d6c966b9a8cdfe6ca0c0ec3456766017450660b6eb018e3890370df18fb180` unchanged | **Verified** |
| **Static Code Audit Coverage** | `SqliteEventStore`, `PostgresEventStore`, `HybridRetrievalEngine`, `TraceService`, `RevisionedProjectionController` | All 8 subsystem read/write paths and isolation boundaries inspected | **Observed** |
| **Runtime Test Execution** | Unit / Integration Test Suites | Intentionally **not executed** in T1 to maintain strict read-only audit discipline | **Planned for TR1/TR2** |

---

## 3. Risks and Follow-Up

| Risk ID | Severity | Description & Impact | Mitigation Path |
| :--- | :---: | :--- | :--- |
| **R-01 (Candidate Leakage)** | **Critical** | `trace_affinity_edges` has `UNIQUE(workspace_id, pair_key)` and writes `status='active'` immediately; `trace_activation_priors` lacks release identity. Candidate modifications leak to live queries. | Implement P-003 Option A in TR1: add `release_id` scoping to affinity and priors. |
| **R-05 (Truth Confusion)** | **High** | Legacy hierarchy persists derived summary nodes directly into `trace_nodes` and `trace_edge_versions`, mixing derived summaries with canonical facts. | Fully deprecate legacy hierarchy in favor of Cortex `trace_projection_objects` during TR1. |
| **R-06 (Temporal Gap)** | **High** | `as_of_event` queries currently evaluate against latest active Cortex Release rather than resolving historical release active at event offset `N`. | Implement historical release resolution and valid-time contracts in TR2. |

---

## 4. Claim Boundary

- **Highest Justified Claim Level:** **`C0` (Static Analysis & Design Audit Only)**
- **Why C0 is Justified:** All findings are derived from static source code, relational schema inspection, and architecture analysis. No code changes, schema migrations, or runtime fault injections were performed.
- **What this Work Explicitly Does Not Establish:** Does not claim runtime verification of Postgres RLS under concurrency, does not apply migrations, does not choose P-003 or P-004, and does not certify benchmark performance.

---

## 5. Change and State Accounting

| Field | Record |
| :--- | :--- |
| **Base Commit / Worktree** | Commit `c855bb06532b3b52b25f0bea969d2677e5049065` on branch `main` (dirty user snapshot). |
| **Changed Paths** | `docs/program/inbox/f0c-repository-boundary-20260819/component-records/trace.md`, `docs/program/inbox/t1-trace-cortex-release-audit/*` |
| **Unchanged Protected Paths** | All product code in `src/trace/`, test files in `tests/`, migrations in `migrations/`, lockfiles in `uv.lock`, benchmarks in `benchmarks/`. |
| **Data / External State** | Zero external network calls, zero model API calls, zero database connections opened. |
| **Retained State** | All user uncommitted changes (26 modified tracked files, 5 untracked files) preserved intact. |
| **Rollback Path** | All created files are contained entirely in `docs/program/inbox/`; removal of directory returns repo to exact starting state. |

---

## 6. Evidence Inventory

| Artifact | Location | What it Supports | Limitations |
| :--- | :--- | :--- | :--- |
| **Read/Write Map** | `docs/program/inbox/t1-trace-cortex-release-audit/evidence/read-write-map.md` | Documents current storage, candidate IDs, selectors, failure modes, and gaps across all 8 subsystems. | Static analysis of codebase. |
| **P-003 Options Analysis** | `docs/program/inbox/t1-trace-cortex-release-audit/evidence/P-003-options.md` | Compares Monolithic Rebuild vs Release Root with Carried-Forward Components across 10 dimensions. | Design evaluation. |
| **P-003 Decision Request** | `docs/program/inbox/t1-trace-cortex-release-audit/evidence/P-003-decision-request.md` | Prepares formal human decision request for unified Cortex Release architecture. | Requires human acceptance. |
| **P-004 Options Analysis** | `docs/program/inbox/t1-trace-cortex-release-audit/evidence/P-004-options.md` | Details bitemporal dimensions, source lifecycle, revocation, and historical release resolution. | Design evaluation. |
| **TR1 Successor Outline** | `docs/program/inbox/t1-trace-cortex-release-audit/evidence/TR1-successor-outline.md` | Specifies exact scope, interfaces, and negative verifier checks for TR1. | Implementation outline only. |
| **TR2 Successor Outline** | `docs/program/inbox/t1-trace-cortex-release-audit/evidence/TR2-successor-outline.md` | Specifies exact scope, interfaces, and negative verifier checks for TR2. | Implementation outline only. |

---

## 7. Verification Truthfulness

- **Verified:** Git repository state pinned (`c855bb0`), working tree protection maintained, zero product code mutations made, all 10 durable T1 artifacts written to disk.
- **Observed:** Candidate isolation gaps in `trace_affinity_edges` and `trace_activation_priors`; temporal gaps in `hierarchy_frontier` `as_of_event` resolution; independent activation of external indices.
- **Planned:** Implementation of unified release lifecycle (TR1) and temporal/revocation contracts (TR2) upon human decision acceptance.
- **Blocked:** TR1 execution is blocked on human decision acceptance of P-003; TR2 is blocked on TR1 and P-004.
- **Not Applicable:** Runtime test execution and performance evaluation (audit packet is strictly read-only).

---

## 8. Reviewer Decision Prompt

1. **Exact Decisions Requested:**
   - **P-003 Decision:** Review and accept Option A (Release Root with Carried-Forward Components) in `docs/program/inbox/t1-trace-cortex-release-audit/evidence/P-003-decision-request.md`.
   - **P-004 Decision:** Review temporal and revocation options in `docs/program/inbox/t1-trace-cortex-release-audit/evidence/P-004-options.md`.
2. **Safe Default if No Decision is Made:**
   - Keep Trace Foundation in read-only audit mode. Do not dispatch mutable packet TR1 or apply migration `004`/`005`.
3. **Smallest Next Packet:**
   - **TR1 (Unified Cortex Release Lifecycle Implementation):** To be executed by Trace Engineer in an isolated worktree holding an explicit lease once P-003 is accepted.
