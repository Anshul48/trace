# Handoff — F0a / Current Evaluation and Benchmark Re-anchor

> **State:** Completed (Read-only audit)
> **Role:** Evaluation Engineer / Benchmark Foundation Owner
> **DAG Node:** F0a

---

## 1. Outcome

- **Task ID:** `f0a-e1-refresh-20260819`
- **Status:** `completed`
- **One-sentence result:** Completed exhaustive read-only static audit of the moved `trace-bench` codebase and legacy Trace-Lite benchmark surfaces; cataloged 6 critical fail-open/fallback integrity flaws (mock LLM defaults, silent error swallowing, empty-as-abstention metric inflation, insecure TLS retries, synthetic dataset generation, and mislabelled fixture authority); re-classified the 320-case internal fixture as C2 regression-only; and established exact B1 prerequisites pending human decisions P-007 and P-008.

---

## 2. Deliverables

- **Task Artifacts Produced:**
  - `repository-state.json` — Component state record for unversioned `trace-bench`.
  - `commands.md` — Read-only execution record (zero mutations/commands run).
  - `evidence/current-surface-map.md` — Comprehensive mapping of runners, baselines, adapters, loaders, and unpinned dependencies.
  - `evidence/fallback-inventory.md` — Detailed breakdown of 6 forbidden fallback mechanisms, error-receipt codes, and required negative tests.
  - `evidence/fixture-claim-boundary.md` — Fixture classification downgrading the 320-case fixture to C2 regression evidence.
  - `evidence/stale-packet-matrix.md` — Inventory of stale assumptions and required corrections.

---

## 3. Verification

- **Commands & Checks:** Static code and AST inspection across all Python files, Pydantic schemas, Click entrypoints, and JSON fixtures in `C:\Users\anshu\OneDrive\Documents\Code\Utilities\trace-bench` and `trace-lite/benchmarks`.
- **Results:**
  - `trace-bench` has no Git repository identity and contains untracked local results/cache files.
  - `TraceLiteRetriever` uses `MockLLMAdapter` by default and swallows indexing and query exceptions.
  - `evaluate_case_retrieval` inflates empty retrievals on out-of-scope queries to 100% across all retrieval metrics.
  - `download_file` in `adapters/base.py` falls back to `verify=False` on exception.
  - Dataset adapters for HiChunk, LongMemEval, HippoRAG, TREC RAG, MTEB, and ANN Scale silently create synthetic sample data when real data is missing.
  - `trace_engineering_curated.json` is a self-descriptive 320-query internal fixture incorrectly marked `release_authority: true`.
- **What remains unverified:** Runtime execution of fixed negative test matrix (deferred to B1 / V1a).

---

## 4. Risks and Follow-Up

- **Risk Status:**
  - **R-03 (Benchmark fail-open behavior):** Observed directly in code. Mitigated by F0a audit; requires B1 fail-closed implementation.
  - **R-04 (Weak external evidence):** Observed. Internal 320-case fixture cannot certify external SOTA or public quality.
  - **R-07 / R-15 (Agent-context drift / stale docs):** Mitigated by producing durable source-anchored evidence files.
- **Prerequisites for B1:**
  1. Human decision on **P-007** (trace-bench source control: dedicated git repo vs content manifest).
  2. Human decision on **P-008** (canonical certification runner boundary: trace-bench vs legacy in-repo code).
  3. Isolated worktree lease for B1.

---

## 5. Claim Boundary

- **Highest Justified Claim Level:** **C1 — Local Behavior / Static Audit**
- **Why justified:** Exhaustive inspection of the current unversioned checkout.
- **Explicit Exclusions:** This audit does NOT run certification benchmarks, download datasets, certify Trace-Lite/Trace runtime retrieval quality, or alter any thresholds or codebase files. `trace-bench` is strictly non-certifying in its current state.

---

## 6. Change and State Accounting

| Field | Record |
|---|---|
| **Base Commit / Tree** | `trace-bench`: Unversioned source directory (`C:\Users\anshu\OneDrive\Documents\Code\Utilities\trace-bench`).<br/>`trace-lite`: `fe66a9eefc8372f7cc021c864d26e62a9d6cc9c1`.<br/>`trace`: `c855bb06532b3b52b25f0bea969d2677e5049065` (protected working state). |
| **Changed Paths** | Only task-local documentation and evidence files under `docs/program/inbox/f0a-e1-refresh-20260819/`. |
| **Unchanged Protected Paths** | Zero product code or benchmark code files modified. |
| **Data / External State** | Zero data downloaded; zero provider calls made. |
| **Rollback Path** | Delete task directory `docs/program/inbox/f0a-e1-refresh-20260819/` if invalidated. |

---

## 7. Reviewer Decision Prompt

1. **Decisions Requested:**
   - Review and accept F0a findings.
   - Authorize P-007 (trace-bench repository/manifest policy) and P-008 (canonical certification runner boundary).
2. **Safe Default:**
   - Treat `trace-bench` as unversioned and non-certifying. Keep B1 in `scoped, not prepared` state until P-007 and P-008 are decided.
3. **Smallest Next Packet:**
   - Prepare B1 fail-closed runner packet once P-007 and P-008 are decided.
