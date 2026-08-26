# Decision Request: P-003

> **State:** proposed  
> **Decision owner:** Human program owner  
> **Prepared by:** Trace Foundation Engineer  
> **Date Prepared:** 2026-08-19  
> **Related Packet:** T1 (Audit) -> TR1 (Implementation)

---

## 1. Decision Required

Choose the canonical architectural pattern and schema for **unified Trace Cortex Releases**:
- **Option A (Alternative 2):** Release root (`trace_cortex_releases`) with immutable component membership manifest (`trace_cortex_release_components`), enabling atomic activation, clean rollback, and efficient incremental carry-forward of validated components.
- **Option B (Alternative 1):** Monolithic full rebuild release bundle, where every release rebuilds and stores all derived components from scratch.

---

## 2. Why Now

- **Blocked Packets / DAG Edges:** Node `TR1` (Unified Cortex Release Lifecycle implementation) is blocked on this decision. Node `TR2` (Temporal and Revocation baseline) is transitively blocked.
- **Consequence of Deferral:** Trace remains in a state where candidate affinity edges and activation priors leak into ordinary queries (Risk R-01), and external indexes activate independently of hierarchy/affinity projections.
- **Safe Default:** Defer mutation. Keep Trace in read-only audit mode. Do not apply migrations or alter runtime queries without an accepted decision.

---

## 3. Evidence Available

| Evidence ID | Source / Packet | Level | What it Establishes | Limitations |
| :--- | :--- | :---: | :--- | :--- |
| `EVD-T1-MAP-01` | `T1: evidence/read-write-map.md` | observed | Candidate affinity edges are written with `status='active'` and read without release scoping; activation priors lack release identity. | Static code inspection; no runtime fault injection performed. |
| `EVD-T1-OPT-01` | `T1: evidence/P-003-options.md` | observed | Full rebuild (Option B) creates O(N) re-indexing overhead per atom edit; Carried-forward manifest (Option A) provides atomic multi-component activation with incremental scaling. | Conceptual and design analysis based on codebase architecture. |

---

## 4. Options Analysis

| Option | Description | Benefits | Risks / Cost | Compatibility & Rollback | Packets Unblocked |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **A (Recommended)** | Release root with immutable component manifest (`trace_cortex_releases` + `trace_cortex_release_components`). | - Atomic multi-component activation<br>- Efficient delta updates (carries forward unchanged vectors/hierarchy)<br>- Clean single-pointer rollback<br>- Full candidate isolation across affinity, priors, hierarchy, and indexes | Moderate schema additions; requires explicit component validation rules during carry-forward. | Additive forward-only migration with `bootstrap-v0` backfill for existing rows. Rollback via active release pointer. | Unblocks **TR1** |
| **B** | Monolithic full rebuild bundle. | - Simpler mental model<br>- Zero carry-forward complexity | - Prohibitive build latency on large corpora (100K+ atoms)<br>- Extreme disk/vector duplication<br>- Slow recovery | Heavy re-indexing required during upgrades. Rollback requires retaining massive duplicate indices. | Unblocks **TR1** (with high scale cost) |

---

## 5. Recommendation

**Recommend Option A.**  
Option A establishes strict candidate isolation (satisfying Invariant 2) and atomic multi-component rollback while preserving the sub-second incremental ingestion and delta-update performance necessary for the 100K gate.

---

## 6. Human Decision Record

- **Decision:** `<pending human review: Option A | Option B | Deferred>`
- **Rationale:** 
- **Constraints / Amendments:** 
- **Date:** 
- **Approved Successor Packets Only:** 

*(Do not treat this recommendation as accepted until completed and signed by the human owner.)*
