# TR1 Successor Outline — Unified Trace Cortex Release Lifecycle Implementation

> **Proposed Task ID:** TR1  
> **Role:** Trace Engineer  
> **Status:** Proposed Successor Packet Outline (Do NOT execute or mutate code in T1)  
> **Prerequisites:** T1 Audit Handoff, Accepted Human Decision on P-003, Clean Worktree Lease

---

## 1. Objective

Implement the unified Cortex Release lifecycle chosen in P-003, establishing candidate-scoped derived writes, active-release-only reads, durable validation receipts, atomic activation, and safe single-pointer rollback across hierarchy, affinity, priors, and search indices.

---

## 2. In-Scope Surfaces & Interfaces

| Component Surface | Target Changes |
| :--- | :--- |
| **Migrations** | Forward-only SQL migration (`migrations/005_cortex_unified_release_lifecycle.sql`):<br>- Create `trace_cortex_releases` and `trace_cortex_release_components`<br>- Add `release_id UUID` to `trace_affinity_edges` and `trace_activation_priors`<br>- Add `bootstrap-v0` backfill for existing rows |
| **Data Models** | Update `src/trace/v2/models.py` with `CortexRelease`, `CortexReleaseComponent`, `CortexValidationReceipt` |
| **Store Implementations** | Update `src/trace/v2/store.py` and `src/trace/v2/production.py`:<br>- `create_cortex_release()`, `validate_cortex_release()`, `activate_cortex_release()`, `rollback_cortex_release()`<br>- Release-scoped `put_affinity_edge()` and `affinity_neighbors()`<br>- Release-scoped `upsert_activation_prior()` and `activation_priors()`<br>- Active release pointer resolution |
| **Retrieval Engine** | Update `src/trace/v2/retrieval.py`:<br>- Enforce active `release_id` binding across all candidate generation channels<br>- Ensure candidate edges are excluded from energy transitions |
| **Service Layer** | Update `src/trace/v2/service.py`:<br>- Orchestrate candidate build, validation receipt generation, and atomic activation with index alias compensation |
| **Tests** | Add comprehensive unit & lifecycle tests in `tests/test_v2_cortex_release_lifecycle.py` |

---

## 3. Explicitly Forbidden Work

- **No Temporal Valid-Time Redesign:** Valid time intervals and revocation contracts belong to TR2.
- **No Evaluation Threshold Changes:** Do not alter benchmark fixtures or scoring rules.
- **No Direct Mutation of User Snapshot:** TR1 must execute inside an isolated worktree with a recorded lease.
- **No TL Storage Shortcuts:** Do not copy SQLite-only or embedded shortcuts into the production PostgreSQL store.

---

## 4. Acceptance Criteria & Negative Test Matrix

1. **Candidate Isolation Verification:** Candidate affinity edges, priors, and hierarchy objects written in un-activated release `R_cand` are completely invisible to ordinary queries on `R_active`.
2. **Atomic Multi-Component Activation:** Activation of `R_cand` atomically transitions all components (hierarchy, affinity, priors, lexical alias, dense alias) in a single operation.
3. **Atomic Multi-Component Rollback:** Calling `rollback_cortex_release()` reverts active pointer and index aliases to the prior active release `R_prior`.
4. **Durable Validation Receipt:** A release cannot transition to `status='active'` without a validated structural, provenance, and parity receipt recorded on the release row.
5. **Predecessor Retention:** Superseded releases and their component memberships are retained for audit and rollback until explicit retirement.
6. **Backward Compatibility:** Existing un-scoped data is cleanly backfilled to `bootstrap-v0` during migration without downtime or data loss.

---

## 5. Independent Verifier Integration

- Verifier Packet: `V1b` (Lifecycle Conformance).
- Verifier tests will be run from an independent clean worktree using pre-scripted fault-injection harnesses testing candidate leakage, failed build recovery, and rollback.
