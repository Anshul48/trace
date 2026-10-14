# P-004 Options — Temporal Semantics, Source Lifecycle, and Revocation Contract

> **Task ID:** T1
> **Topic:** Decision P-004 Temporal and Revocation Inputs
> **Status:** Design Alternatives for Human Decision (Do NOT unilaterally choose)
> **Governing Invariants:** Invariant 1 (Truth vs Projection), Invariant 3 (Evidence and Provenance), Invariant 6 (Operational Boundaries)

---

## 1. Executive Summary & Problem Definition

The T1 audit observed that Trace V2's current temporal support is **partial system-event history**:
- `as_of_event: int` filters `trace_node_versions.created_event_offset <= as_of_event` and `trace_edge_versions.created_event_offset <= as_of_event`.
- **Gaps Identified (Risk R-06):**
  1. **System Time vs Valid Time:** No distinction between when an event was recorded in Trace (system time / `event_offset`) and when the assertion occurred or was true in the real world (valid time / effective period).
  2. **Historical Projection Release Selection:** A query with `as_of_event=N` does not resolve the Cortex Release that was active at offset `N`. It queries the latest active hierarchy and indices, applying atom-level filters post-hoc.
  3. **Content Revocation & Deletion Lifecycle:** No first-class evented contract for content retraction, supersession marking, or regulatory compliance deletion (GDPR/PII).
  4. **Historical Authorization:** No verification of whether an actor had access rights at historical event offset `N`.

---

## 2. Core Temporal Dimensions & Requirements

### 2.1 System Time vs Valid Time (Bitemporality)
- **System / Transaction Time:**
  - Tracked on Spine via `event_offset`, `occurred_at`, and `created_event_offset`.
  - Immutable, append-only, monotonically increasing.
  - Answers: *"What did the memory system know as of system event N?"*
- **Valid Time (Real-World Effective Time):**
  - Tracked via `valid_from_utc` and `valid_to_utc` (TIMESTAMPTZ).
  - Can represent historical facts, future-dated validity, or open-ended ranges (`valid_to_utc IS NULL`).
  - Answers: *"What was true in the real world during time interval [T1, T2]?"*
- **Point-in-Time & Uncertain Time:**
  - Supported via metadata JSONB (`{"temporal_granularity": "year|month|day|minute", "confidence": float}`).

### 2.2 Source Lifecycle, Versioning & Supersession
- **Ingestion Versioning:**
  - An ingestion creates or updates source attachments (`trace_attachments`) and atom versions (`trace_node_versions`).
- **Supersession Semantics:**
  - A newer version `v + 1` of a node supersedes version `v`.
  - **Current Read Rule:** Resolves the highest version `v` where `created_event_offset <= current_watermark`.
  - **Historical Read Rule (`as_of_event = E`):** Resolves the highest version `v` where `created_event_offset <= E`.

### 2.3 Revocation, Tombstone & Deletion Policy
- **Content Revocation:**
  - Occurs when an ingested source is found to be false, retracted, or invalidated.
  - Event `atom.revoked` or `ingestion.revoked` records the retraction with causation and reason.
  - **Visibility Rule:** Revoked atoms are excluded from normal current queries. Historical queries return them marked with `temporal_status: "revoked"` and `visibility: "revoked"` in evidence bundles, ensuring auditability without spreading falsehoods.
- **Tombstone / Soft Deletion:**
  - Event `node.deleted` sets a tombstone.
  - Atom versions prior to deletion remain in event history for audit replay.
- **Hard / Compliance Deletion (Privacy / GDPR Erasure):**
  - Canonical content in `trace_node_versions` and `trace_attachments` is overwritten with `[REDACTED_BY_COMPLIANCE_POLICY]` and cryptographic signature preserved.
  - Rebuildable Cortex projections are cleared or rebuilt to remove derived vector/lexical embeddings.

### 2.4 Historical Authorization and Release Pointer Selection
- **Release Pointer Resolution Rule:**
  ```sql
  SELECT release_id FROM trace_cortex_releases
  WHERE workspace_id = :workspace_id
    AND status IN ('active', 'superseded')
    AND activated_at_event_offset <= :as_of_event
    AND (superseded_at_event_offset > :as_of_event OR superseded_at_event_offset IS NULL)
  ORDER BY activated_at_event_offset DESC LIMIT 1;
  ```
- **Historical Policy Rule:**
  - Evaluates authorization using the cognitive policy active at `as_of_event`, preventing historical data leakage while respecting retroactive revocations.

---

## 3. Decision Options for P-004

### Option A: Full Bitemporal Contract with First-Class Revocation and Historical Cortex Release Selection (Comprehensive Foundation)
- **Scope:**
  1. Add `valid_from_utc` and `valid_to_utc` to `trace_node_versions` and query parameters.
  2. Implement evented `atom.revoked` and `document.revoked` lifecycle with evidence-bundle attribution.
  3. Implement historical Cortex Release pointer selection for all `as_of_event` queries.
  4. Implement compliance content redaction protocol with projection eviction.
- **Pros:** Completely satisfies Invariants 1, 3, and 6; eliminates temporal distortion; audit-grade historical replay.
- **Cons:** Requires schema additions to node versions and updates to query models in TR2.

### Option B: Event-Watermark Resolution with Revocation Status Flag (Minimal Foundation)
- **Scope:**
  1. Retain system-event time (`as_of_event`) only; defer valid-time interval fields to later research.
  2. Add `status` (`'active' | 'revoked' | 'deleted'`) to node versions.
  3. Implement historical Cortex Release pointer lookup based on `event_offset`.
- **Pros:** Lower implementation complexity for initial baseline.
- **Cons:** Cannot query real-world historical facts distinct from system recording time; does not support retroactive assertions.

---

## 4. Next Step & TR2 Scope

- P-004 will be submitted to the human program owner alongside P-003.
- TR2 will implement the human-accepted option under an isolated worktree following TR1 completion.
