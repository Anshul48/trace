# Work Packet L1-03: Certification Runner Contract Specification

> **Packet ID:** `l1-03-runner-contract-20260828`
> **Session:** Level 1 (100K Scale Certification Requalification)
> **Role:** Scale Architect & Evaluator
> **Date:** 2026-08-28T10:46:00Z
> **Authority Level:** C3 (Scale Architecture & Evaluation Protocol Specification)
> **Status:** **COMPLETED**
> **Prerequisites:** Wave R0 Containment (`r0-01-claim-inventory-20260828`, `r0-03-forensic-manifest-20260828`, `r0-04-reconciliation-20260828`, `r0-06-negative-tests`)
> **Authorities:** `docs/program/SCALE_CERTIFICATION_RECOVERY_PLAN.md`, `docs/program/00_GLOBAL_CONTEXT_RECOVERY.md`, `docs/program/06_DECISION_LOG.md` (DEC-P-005b)

---

## 1. Objective

Define the immutable specification and mathematical/operational contract for the canonical 100K scale gate runner (`scripts/run_100k_scale_gate.py`). This contract formalizes:
1. Exact CLI parameters, environment isolation, and fail-closed preflight integrity checks.
2. Relational SQLite WAL schemas for transactionally committed Spine events, atom nodes, edge projections, and lifecycle tracking with strict deduplication constraints.
3. True Okapi BM25 lexical ranking and TL2 Personalized PageRank (PPR) spreading activation with bounded degree ($\le 50$) and depth ($\le 15$).
4. Unclamped evaluation metrics (prohibiting artificial score floors, clamping, and hardcoded constants).
5. Empirically scored unanswerability and abstention evaluation against frozen ground truth.
6. 100% full-event replay with cryptographic table state-hash parity verification (eliminating mock replay tables).
7. 1,000 random byte-slice anchor proofs against original source text.
8. Raw per-query, graph walk, durability, and replay recovery telemetry schemas.

---

## 2. Pinned Context & Input Manifests

- **Program Blueprint:** `docs/program/SCALE_CERTIFICATION_RECOVERY_PLAN.md` (Sections 4 & 5)
- **Global Operational Control:** `docs/program/00_GLOBAL_CONTEXT_RECOVERY.md`
- **Corpus Capsule Manifest:** `docs/program/inbox/ltr-02-corpus-capsule-20260826/evidence/corpus-manifest.json`
- **Negative Integrity Suite:** `tests/test_scale_recovery_quarantine.py`
- **Quarantined Predecessor:** `scripts/run_100k_scale_gate.py` (Defects cataloged in R0-01)

---

## 3. Scope Declaration

| Field | Value |
| :--- | :--- |
| **Allowed Paths** | `docs/program/inbox/l1-03-runner-contract-20260828/*` |
| **Downstream Implementation Target** | `scripts/run_100k_scale_gate.py` (L1-04) |
| **Forbidden Actions** | Premature gate pass declaration, in-memory fallbacks, score clamping, partial replay shortcuts. |

---

## 4. Deliverables

- `evidence/runner_contract_spec.md`: Complete mathematical, relational, and behavioral specification for Level 1 runner requalification.
- `handoff.md`: Formal handoff and acceptance criteria for L1-04 Implementer and L1-05 Verifier.
