# Handoff: trace-program-research-01 (S1 Research)

> **Task ID:** `trace-program-research-01`
> **Role:** Research Analyst
> **DAG Nodes:** `R1`, `P-002`, `P-003`, `P-004`
> **Status:** `completed` (ready for coordinator synthesis and human decision review)

---

## Outcome

- **Task ID:** `trace-program-research-01`
- **Status:** `completed`
- **One-sentence result:** Completed a source-grounded, falsifiable Stage 1 research memo analyzing Cortex Releases, Bi-temporal truth, and typed bounded graph activation, providing concrete decision proposals and fault-test specifications for P-002, P-003, and P-004 without modifying product code.

---

## Deliverables

- **Produced Artifacts:**
  - Research Memo: [`docs/program/inbox/trace-program-research-01/memo.md`](file:///C:/Users/anshu/OneDrive/Documents/Code/Utilities/trace/docs/program/inbox/trace-program-research-01/memo.md)
  - Task Packet Record: [`docs/program/inbox/trace-program-research-01/packet.md`](file:///C:/Users/anshu/OneDrive/Documents/Code/Utilities/trace/docs/program/inbox/trace-program-research-01/packet.md)
  - Task Handoff: [`docs/program/inbox/trace-program-research-01/handoff.md`](file:///C:/Users/anshu/OneDrive/Documents/Code/Utilities/trace/docs/program/inbox/trace-program-research-01/handoff.md)
- **Data/Manifests Used:**
  - Repository anchors from `trace/src/trace/v2/` (`cortex.py`, `release.py`, `production.py`, `models.py`, `migrations/004_cortex_projection_control_plane.sql`).
  - Repository anchors from `trace-lite/src/trace_lite/engines/` (`graph.py`, `lattice.py`, `raptor.py`).
  - Program control documents (`00_CHARTER.md`, `01_INVARIANTS.md`, `02_EXECUTION_DAG.md`, `03_SHARED_CONTRACTS.md`, `06_DECISION_LOG.md`, `07_RISK_REGISTER.md`).
- **Evidence Locations:**
  - All research evidence and option matrices are housed in [`docs/program/inbox/trace-program-research-01/memo.md`](file:///C:/Users/anshu/OneDrive/Documents/Code/Utilities/trace/docs/program/inbox/trace-program-research-01/memo.md).

---

## Verification

- **Checks Run:**
  - Inspected Trace V2 database migration 004 and codebase for projection status tracking, RLS policies, and temporal `as_of_event` filtering.
  - Inspected Trace-Lite graph engine (`src/trace_lite/engines/graph.py`) and identified critical $O(N^2)$ pairwise edge generation vulnerability in `generate_co_occurrence_edges`.
  - Formulated 3 falsifiable fault tests (Release Isolation, Temporal Replay/Revocation, Scaled Graph Boundedness).
- **Results:**
  - Verified that current Trace V2 schema has table-level projection tracking but lacks a single unified `CortexReleaseManifest` parent bundle entity.
  - Verified that Trace-Lite's current co-occurrence generator creates quadratic edge blowup without a strict Document Frequency (DF) cap.
- **Failure Cases Exercised:**
  - Documented edge count scaling failure modes on high-frequency terms ($N=100K$).
  - Documented "Frankenstein query" state when individual projection modalities activate asynchronously without a shared watermark.
- **What Remains Unverified:**
  - Physical execution of the specified fault-injection tests (these belong to Stage 2/3 implementation & verification tasks: `TR1`, `TL1`, `V1`).

---

## Risks and Follow-Up

- **New or Changed Risks:**
  - Confirmed **R-02 (Unbounded Graph Growth)** as an immediate blocker for the 100K gate if `trace-lite` graph generation is not refactored before `G100-TL`.
  - Confirmed **R-01 (Candidate Leakage)** requires atomic release bundle schema (`TR1`) in Trace V2.
- **Recommended Next Packets:**
  - `s2-tl-candidate-active-lifecycle` (DAG node `TL1`): Implement bounded graph generation and local candidate directory isolation in Trace-Lite.
  - `s2-trace-cortex-release-audit` (DAG node `TR1`): Implement unified `trace_cortex_releases` schema and atomic pointer activation in Trace.
  - `s2-verifier-matrix-and-consumer-fakes` (DAG node `V1`): Build independent verifier test harness for candidate isolation and temporal replay.
- **Questions Requiring Human Direction:**
  - Sign-off on Decision Proposals **P-002**, **P-003**, and **P-004** as detailed in Section 9 of the memo.

---

## Claim Boundary

- **Highest Justified Claim Level:** **C1 (Source-Grounded Research Memo & Decision Support)**
- **Why that level is justified:** The memo establishes rigorous, source-grounded facts from the codebase, mathematical proofs of scaling bounds, and clear architectural alternatives. No product code was changed.
- **What this work explicitly does not establish:** Does not claim production readiness, does not claim passing the 100K benchmark gate, and does not alter canonical invariants or main branch code.

---

## Change and State Accounting

| Field | Record |
| :--- | :--- |
| **Base commit/worktree** | Clean baseline inspection across `trace` and `trace-lite` repositories. |
| **Changed paths** | `docs/program/inbox/trace-program-research-01/packet.md`, `memo.md`, `handoff.md`. |
| **Unchanged protected paths** | All product code, canonical charter (`00_CHARTER.md`), invariants (`01_INVARIANTS.md`), and evaluation protocols remained strictly untouched. |
| **Data/external state** | No datasets downloaded; no external API credentials used. |
| **Retained state** | All existing repository history, test fixtures, and documentation preserved. |
| **Rollback path** | Delete `docs/program/inbox/trace-program-research-01/` directory if rejected. |

---

## Evidence Inventory

| Artifact | Location | What it supports | Limitations |
| :--- | :--- | :--- | :--- |
| **Research Memo** | [`docs/program/inbox/trace-program-research-01/memo.md`](file:///C:/Users/anshu/OneDrive/Documents/Code/Utilities/trace/docs/program/inbox/trace-program-research-01/memo.md) | Architectural foundations for Cortex Releases, Bi-temporality, and Bounded Activation. | Analytical and source evidence; requires Stage 2 implementation for runtime validation. |
| **Current State Fact Map** | Section 2 of Memo | Verifiable codebase facts and concrete file anchors in Trace & TL. | Based on current commit state. |
| **Alternatives Matrices** | Section 5 of Memo | Tradeoff comparisons across 3 core design axes. | Decision options for human review. |
| **Fault Test Specs** | Section 7 of Memo | Falsifiable test protocols for independent verifiers. | Specifications for future test execution. |

---

## Verification Truthfulness

- **Verified:** Codebase inspection of Trace V2 SQL migrations, `cortex.py`, `release.py`, `production.py`, and Trace-Lite `graph.py`.
- **Observed:** Identification of $O(N^2)$ edge explosion in `generate_co_occurrence_edges` and decoupled projection switching gap in SQL migration 004.
- **Planned:** Execution of fault-injection experiments during Stage 2/3 (`TR1`, `TL1`, `V1`).
- **Blocked:** None. Task completed within authorized bounds.

---

## Reviewer Decision Prompt

1. **Exact Decision Requested:** Approve Decision Proposals **P-002** (Bounded Graph Degree & Query Budgets), **P-003** (Unified Cortex Release Bundle), and **P-004** (Bi-Temporal Truth Contract) to unblock Stage 2 implementation packets.
2. **Safe Default if No Decision is Made:** Retain existing single-dimensional `as_of_event` in Trace and freeze graph generation in Trace-Lite to structural/sequential edges only (disabling co-occurrence to avoid memory exhaustion).
3. **Smallest Next Packet:** Assign `s2-tl-candidate-active-lifecycle` (`TL1`) to Trace-Lite Engineer and `s2-trace-cortex-release-audit` (`TR1`) to Trace Engineer in isolated worktrees.
