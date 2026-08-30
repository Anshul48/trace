# Handoff: V0 — Independent Verifier Plan and Packet-Integrity Review

> **Role:** Independent Verifier / Integration Reviewer
> **Packet:** V0 (`v0-verifier-plan-20260819`)
> **Date:** 2026-08-19
> **Governing Documents:** `docs/program/launch/05_INDEPENDENT_VERIFIER.md`, `01_INVARIANTS.md`, `SESSION_OPERATING_MANUAL.md`, `04_EVALUATION_PROTOCOL.md`, `FOUNDATION_GATE_DOSSIER.md`

---

## 1. Outcome

- **Task ID:** V0 (`v0-verifier-plan-20260819`)
- **Status:** Completed (Read-Only Planning)
- **One-sentence result:** Established the immutable independent verification plan for V1a (evaluator fail-closed integrity) and V1b (Trace-Lite/Trace lifecycle, candidate leakage, and temporal faults), audited packet completeness for F0a..T1, and defined strict verifier worktree, environment, and evidence standards without modifying candidate implementations or executing certification runs.

---

## 2. Deliverables

- **Produced Artifacts:**
  - `docs/program/inbox/v0-verifier-plan-20260819/evidence/verifier-plan.md` (Frozen negative test matrices for V1a and V1b)
  - `docs/program/inbox/v0-verifier-plan-20260819/evidence/packet-completeness.md` (Audit of F0a, F0b, F0c, B1, L1, T1, V1)
  - `docs/program/inbox/v0-verifier-plan-20260819/evidence/independence-requirements.md` (Worktree, environment, and fake/in-memory boundary rules)
  - `docs/program/inbox/v0-verifier-plan-20260819/input-manifest.json` (V0 input manifest)
  - `docs/program/inbox/v0-verifier-plan-20260819/repository-state.json` (V0 repository state snapshot)
  - `docs/program/inbox/v0-verifier-plan-20260819/commands.md` (Read-only execution log)
  - `docs/program/inbox/v0-verifier-plan-20260819/verification.md` (Self-verification against program invariants)
  - `docs/program/inbox/v0-verifier-plan-20260819/handoff.md` (This document)
- **Data/Manifests Used:** `docs/program/inbox/v0-verifier-plan-20260819/input-manifest.json`
- **Evidence Locations:** `docs/program/inbox/v0-verifier-plan-20260819/evidence/`

---

## 3. Verification

- **Commands and Fixed Evaluators:** Read-only inspection of program control plane, component records in F0c, and packet definitions.
- **Results:**
  - **V1a Matrix:** 17 frozen negative cases covering missing source identity, mock providers, synthetic data, forced flat search, checksum mismatches, empty results, indexing/query exceptions, TLS retries, and write failures.
  - **V1b Matrix:** 17 frozen fault cases across 4 sub-gates (`V1b-TL-Lifecycle`, `V1b-TL-Graph`, `V1b-Trace-Release`, `V1b-Trace-Temporal`).
  - **Independence Rules:** Mandates clean verifier worktree, external test root outside OneDrive (R-14), and explicitly bars treating SQLite/in-memory tests as PostgreSQL, RLS, or external-index proof.
- **Failure Cases Exercised:** Defined all negative injection specifications for future execution in V1a and V1b.
- **What Remains Unverified:** All runtime product and benchmark behavior. No implementation code was executed or certified during V0.

---

## 4. Risks and Follow-Up

- **Risk Updates:**
  - `R-01` (Candidate Projection Leakage): Mitigated on paper by freezing V1B-TR-REL-001..005 and V1B-TL-LIF-001..006; remains Open pending TR1 and L1 execution.
  - `R-03` (Benchmark Fail-Open): Mitigated on paper by freezing V1A-SRC, V1A-PRV, V1A-DAT, V1A-FLB; remains Open pending B1 implementation and V1a verification.
  - `R-08` (Verification Conflict): Contained by establishing verifier worktree isolation, adversarial fixture ownership, and strict prohibition on candidate repairs.
  - `R-14` (Windows/OneDrive Test Root Conflicts): Contained by mandating external scratch test directory outside cloud sync.
- **Recommended Next Packets:**
  1. Complete read-only refreshes **F0a** (Evaluation audit) and **F0b** (Data records).
  2. Complete read-only audit **T1** (Trace Cortex Release audit).
  3. Prepare **L1** for execution by issuing a clean worktree lease on Trace-Lite base `fe66a9e`.
  4. Block **B1**, **TR1**, and **TR2** pending human acceptance of decisions P-007/P-008, P-003, and P-004 respectively.
- **Questions Requiring Human Direction:** Decisions P-001, P-002, P-003, P-004, P-005, P-007, and P-008 remain open.

---

## 5. Claim Boundary

- **Highest Justified Claim Level:** **C0 — Idea / Program Planning Baseline**
- **Why Level is Justified:** V0 is a read-only governance and planning deliverable that defines immutable test plans, review matrices, and independent standards.
- **What this Work Explicitly Does NOT Establish:**
  - It does NOT certify any runtime behavior of `trace-lite`, `trace`, or `trace-bench`.
  - It does NOT approve any benchmark score or public claim.
  - It does NOT grant mutable execution permission to B1, TR1, or TR2 before their prerequisite decisions and clean worktree leases are established.
  - It does NOT treat in-memory/fake tests as PostgreSQL, RLS, external-index, or production-recovery proof.

---

## 6. Change and State Accounting

| Field | Record |
| :--- | :--- |
| **Base Commit/Worktree** | Trace repository base `c855bb06532b3b52b25f0bea969d2677e5049065` (working snapshot). |
| **Changed Paths** | Created files under `docs/program/inbox/v0-verifier-plan-20260819/` only. |
| **Unchanged Protected Paths** | All product code in `src/`, `tests/`, `migrations/`, `benchmarks/`, and user-owned dirty V2 files were strictly untouched. |
| **Data/External State** | No downloads, no provider calls, no database migrations, no external network requests. |
| **Retained State** | All existing repository files and user modifications preserved unchanged. |
| **Rollback Path** | Non-destructive. Deletion of `docs/program/inbox/v0-verifier-plan-20260819/` would completely revert this task. |

---

## 7. Evidence Inventory

| Artifact | Location | What it Supports | Limitations |
| :--- | :--- | :--- | :--- |
| **Verifier Plan** | `docs/program/inbox/v0-verifier-plan-20260819/evidence/verifier-plan.md` | Immutable negative test matrices for V1a and V1b. | Planning definition only; no runtime execution. |
| **Packet Review** | `docs/program/inbox/v0-verifier-plan-20260819/evidence/packet-completeness.md` | Audit of F0a..T1 readiness, boundaries, and blockers. | Static inspection only. |
| **Independence Standard** | `docs/program/inbox/v0-verifier-plan-20260819/evidence/independence-requirements.md` | Worktree isolation, environment capture, and fake test limits. | Governs future verifier sessions. |
| **Repository State** | `docs/program/inbox/v0-verifier-plan-20260819/repository-state.json` | Snapshot of component roots and dirty state. | Observation snapshot. |
| **Input Manifest** | `docs/program/inbox/v0-verifier-plan-20260819/input-manifest.json` | Pinned inputs and authority boundary. | Task-local metadata. |
| **Commands Log** | `docs/program/inbox/v0-verifier-plan-20260819/commands.md` | Declaration of read-only inspections. | Audit trail. |
| **Verification Record** | `docs/program/inbox/v0-verifier-plan-20260819/verification.md` | Compliance with invariants and directives. | Self-audit. |

---

## 8. Verification Truthfulness

- **Verified:** V0 planning deliverables (`verifier-plan.md`, `packet-completeness.md`, `independence-requirements.md`, `repository-state.json`, `input-manifest.json`, `commands.md`, `verification.md`, `handoff.md`) are created, conform to schema, and are durably stored.
- **Observed:** Trace has 26 modified / 5 untracked files; `trace-bench` is unversioned; Trace-Lite base `fe66a9e` is clean.
- **Planned:** Future execution of V1a (after B1) and V1b (after L1/TL2 and TR1/TR2).
- **Blocked:** Mutable implementation packets B1 (on P-007/P-008), TR1 (on P-003), TR2 (on P-004).

---

## 9. Reviewer Decision Prompt

1. **Exact Decision Requested:** Accept Packet V0 as complete, establishing the immutable verification baseline for V1a and V1b.
2. **Safe Default:** Keep implementation packets B1, TR1, and TR2 blocked until prerequisite decisions (P-007, P-008, P-003, P-004) and clean worktree leases are authorized.
3. **Smallest Next Packet:**
   - Proceed with read-only F0a (Evaluation Engineer) and F0b (Data Steward).
   - Prepare L1 worktree lease on clean Trace-Lite base `fe66a9e` for Trace-Lite Engineer.
